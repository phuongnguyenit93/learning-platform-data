# ResourceBundle: Giới hạn Control khi dùng named module và lựa chọn cơ chế provider phù hợp

## Mục tiêu học tập

Java `ResourceBundle` là API chuẩn để chọn chuỗi và tài nguyên theo `Locale`. Tuy nhiên, từ khi Java dùng hệ thống module JPMS, cách nạp bundle phụ thuộc vào **module của mã đang gọi**, cách đóng gói bundle và service providers. Không thể mang nguyên vẹn mọi lời gọi `ResourceBundle.getBundle(..., ResourceBundle.Control)` trên classpath sang named module.

Sau bài này, bạn có thể:

- Nhận diện chính xác **`UnsupportedOperationException`** khi gọi overload `ResourceBundle.getBundle` có tham số `ResourceBundle.Control` từ **named module**; phân biệt với lỗi `MissingResourceException` khi không tìm được bundle.
- Hiểu `ResourceBundle.Control` **vẫn là API hiện hành** dành cho unnamed module/classpath, không phải class đã bị xóa, nhưng không có vai trò tùy chỉnh bundle lookup của named caller.
- Chọn ba cơ chế đúng nhu cầu: **resource trong cùng named module**, **`ResourceBundleProvider` qua `uses/provides`**, hoặc **`Control` trên classpath**.
- Viết service interface đúng quy tắc tên `<package của baseName>.spi.<SimpleName>Provider`, tổ chức API/provider/consumer modules và chạy chúng trên module path.
- Hiểu vì sao `ResourceBundleControlProvider` không giải quyết giới hạn named module, và khi nào `AbstractResourceBundleProvider` có thể hỗ trợ cách đóng gói resources.
- Phân biệt module encapsulation, resource visibility, class loader, fallback, caching và vấn đề split packages.
- Thực hiện các ví dụ Java 17+ độc lập đã được kiểm chứng bằng JDK 24: **Control bị từ chối ở named module**, provider module chạy đúng, local bundle trong named module chạy đúng, và classpath Control chạy đúng.

**Phạm vi:** Chủ đề **ResourceBundle**. Nội dung chỉ dùng những API **vẫn còn được hỗ trợ trong Java hiện đại** (`java.util.ResourceBundle`, `ResourceBundle.Control` trong phạm vi phù hợp, `java.util.spi.ResourceBundleProvider`, `AbstractResourceBundleProvider`, `ServiceLoader`, JPMS). Tài liệu chính được đối chiếu với Java SE 26.

## 1. Vì sao Control chạy trên classpath nhưng lại thất bại trong named module?

Giả sử ứng dụng muốn chỉ dùng bundles dạng `.properties` và không fallback sang locale mặc định của máy:

```java
ResourceBundle.Control propertiesOnly =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);

ResourceBundle bundle = ResourceBundle.getBundle(
        "demo.Messages", Locale.FRENCH, propertiesOnly);
```

Đây là **đoạn minh họa trong một method**, chưa có imports/`main` đầy đủ. Với code chạy trong **unnamed module** (`java -cp ...`), cách gọi hoàn toàn hợp lệ.

Nhưng nếu **lời gọi** xuất phát từ code của **named module**, overload nhận `Control` sẽ ném:

```text
java.lang.UnsupportedOperationException
```

Đây là **hành vi theo hợp đồng** của `java.util.ResourceBundle`, không phải lỗi ngẫu nhiên do JDK mới, file dịch thiếu, cache hoặc tên bundle sai.

```text
ResourceBundle.getBundle(baseName, locale, control)
                         |
          +--------------+----------------+
          |                               |
    caller unnamed                  caller named
    java -cp ...                    java --module-path...
          |                               |
  Control được hỗ trợ             UnsupportedOperationException
          |                               |
  Tùy chỉnh search                 Dùng cách module-aware:
  theo classpath                   - local bundle
                                   - ResourceBundleProvider
                                   - getBundle(..., Module)
```

**Quan trọng:** JDK hiện đại không đồng nghĩa mọi ứng dụng đều là named module. Code chạy trong một `.jar` trên classpath và không có module descriptor thường thuộc **unnamed module** dù JVM là JDK 24 hay 26.

### Phân biệt các kiểu thất bại

| Hiện tượng | Ý nghĩa |
| --- | --- |
| `UnsupportedOperationException` tại overload có `Control` | API **không hỗ trợ** loại lời gọi từ named module; chưa cần xét bundle có tồn tại. |
| `MissingResourceException` khi `getBundle` | Đã tìm bundle theo cơ chế hợp lệ nhưng không tìm thấy baseName/locale theo điều kiện hiện tại. |
| `MissingResourceException` khi `getString(key)` | Bundle tìm được nhưng không có key phù hợp ở bundle/parent chain. |
| `NullPointerException` | Một tham số bắt buộc của overload tương ứng là `null`. |
| `IllegalArgumentException` ở overload `Control` | Một số trường hợp Control implementation trả dữ liệu không hợp lệ theo API. |

Đừng catch mọi exception rồi chuyển thành thông báo “file không tồn tại”. Với `UnsupportedOperationException`, sửa đúng **cách nạp bundle**, không phải chỉ đổi đường dẫn.

## 2. Bảng các overload `ResourceBundle.getBundle`

| Overload | Mục đích | Khi caller là named module |
| --- | --- | --- |
| `getBundle(baseName)` | Dùng locale mặc định và module của caller | Hỗ trợ |
| `getBundle(baseName, locale)` | Dùng locale và module của caller | Hỗ trợ |
| `getBundle(baseName, module)` | Tìm bundle on behalf of module được cung cấp | Hỗ trợ, theo quy tắc module |
| `getBundle(baseName, locale, module)` | Chỉ định locale và module mục tiêu | Hỗ trợ, có ràng buộc encapsulation |
| `getBundle(baseName, locale, loader)` | Tìm qua class loader, có special case cho loader của caller module | Hỗ trợ nhưng không phải luôn tương đương module lookup |
| `getBundle(baseName, control)` | Tùy chỉnh nạp bằng `Control` | **Ném `UnsupportedOperationException`** |
| `getBundle(baseName, locale, control)` | Locale và `Control` | **Ném `UnsupportedOperationException`** |
| `getBundle(baseName, locale, loader, control)` | Loader và `Control` | **Ném `UnsupportedOperationException`** |

Các overload không nhận `Control` có cơ chế nạp mặc định theo module và có thể tìm `ResourceBundleProvider`. Những overload nhận `Control` được tài liệu hóa cho ứng dụng ở **unnamed module**.

Một **named JAR** khác với **unnamed JAR trên classpath**. Cũng đừng suy ra rằng vì `Control` có mặt trên classpath hoặc compile thành công nên lời gọi runtime trong named module sẽ được chấp nhận.

### Vì sao hệ thống module tạo khác biệt?

JPMS giới thiệu **named modules**, `module-info.java` và các quy tắc quản lý truy cập giữa packages. Một bundle trong named module có thể bị đóng gói và không được hiển thị cho module khác. Java cung cấp con đường:

1. Local bundle do module gọi sở hữu.
2. Bundle cung cấp qua **service provider** đúng contract.
3. Một số module-aware lookups theo `Module`, vẫn chịu quy tắc truy cập.

`Control` được thiết kế cho tùy chỉnh lookup trong không gian classpath/unnamed module, không phải công cụ vượt module encapsulation. Do đó Java định nghĩa giới hạn rõ ràng thay vì âm thầm cố chạy một `Control` không đúng ngữ cảnh.

## 3. Control vẫn hiện hành — nhưng phạm vi sử dụng phải đúng

`ResourceBundle.Control` **không bị loại khỏi API hiện đại**. Nó vẫn có các hook:

- `getFormats(baseName)`: định dạng bundle cho quá trình tìm kiếm.
- `getCandidateLocales(baseName, locale)`: tạo danh sách locale ứng viên.
- `getFallbackLocale(baseName, locale)`: xử lý fallback locale, thường liên quan default locale.
- `toBundleName(baseName, locale)`: cách ghép bundle name.
- `newBundle(...)`: khởi tạo bundle từ class, properties hoặc format tùy biến.
- `getTimeToLive(baseName, locale)` và `needsReload(...)`: chiến lược cache và refresh trong lookup có Control.

Với unnamed module, nếu chỉ muốn properties và tránh fallback sang default locale, không nhất thiết viết custom subclass:

```java
ResourceBundle.Control ctl =
        ResourceBundle.Control.getNoFallbackControl(
                ResourceBundle.Control.FORMAT_PROPERTIES);
```

**Chú ý:** `getNoFallbackControl` không đồng nghĩa bỏ base/root bundle. Nó tắt fallback sang default locale; base bundle vẫn có thể nằm trong candidate search.

Nếu ứng dụng không cần tùy biến lookup, hãy dùng `ResourceBundle.getBundle(baseName, locale)` ngay cả trên classpath để tránh code không cần thiết.

### Điều không còn phù hợp trong named module

Đây là đoạn **không đúng** khi chạy từ một named module:

```java
// Không dùng trong named caller:
var resource = ResourceBundle.getBundle(
        "demo.Messages", locale, myControl);
```

Giả sử `locale` và `myControl` đã được tạo. Cách sửa không phải thay `myControl` bằng một subclass khác: mọi overload nhận `Control` có giới hạn đối với named caller. Cần lựa chọn chiến lược module-aware khác.

## 4. Chọn cơ chế nạp theo kiến trúc

| Bối cảnh | Hướng được khuyến nghị | Lý do |
| --- | --- | --- |
| Classpath/unnamed module, muốn tùy chỉnh candidates hoặc format | `ResourceBundle.Control` nếu thật sự cần | API hỗ trợ |
| Named module và resource được đóng **cùng module** | `getBundle(baseName, locale)` | Đơn giản nhất, không tạo SPI dư thừa |
| Named consumer lấy bundle từ **module provider khác** | `ResourceBundleProvider`, `uses`, `provides` | JPMS service binding, chủ động hóa quyền cung cấp |
| Named module với XML/nguồn định dạng riêng | Custom `ResourceBundleProvider` hoặc helper `AbstractResourceBundleProvider` khi phù hợp | Không dùng Control trong named caller |
| Cần lookup thay mặt một module cụ thể | `getBundle(baseName, locale, module)` | Có ngữ nghĩa module-aware và access rules |
| Chuyển đổi từng bước từ classpath sang JPMS | Giữ Control tại phần **unnamed** hợp lệ; chuyển named bundles sang local/provider | Không ép migrate toàn bộ cùng lúc |

**Không cần provider chỉ vì dự án có `module-info.java`.** Nếu bản dịch nằm trong chính app module, no-Control `getBundle` thường đủ.

Ngược lại, nếu một bộ localization được cung cấp bởi plugin module hoặc nhiều provider modules, interface `ResourceBundleProvider` giúp tổ chức quan hệ module rõ ràng hơn.

## 5. Cách 1 — bundle nằm trong cùng named module

Hãy tạo ví dụ `demo.local`, với resource `.properties` nằm trong module đó.

Cấu trúc nguồn:

```text
local-demo/
├── src/
│   └── demo.local/
│       ├── module-info.java
│       └── demo/local/LocalDemo.java
├── resources/
│   └── demo/local/messages/Labels_fr.properties
└── mods/       (được tạo khi build)
```

File `src/demo.local/module-info.java`:

```java
module demo.local {}
```

File `resources/demo/local/messages/Labels_fr.properties`:

```properties
hello=Bonjour-local
```

File `src/demo.local/demo/local/LocalDemo.java`:

```java
package demo.local;

import java.util.Locale;
import java.util.ResourceBundle;

public final class LocalDemo {
    public static void main(String[] args) {
        var bundle = ResourceBundle.getBundle(
                "demo.local.messages.Labels", Locale.FRENCH);
        if (!bundle.getString("hello").equals("Bonjour-local")) {
            throw new AssertionError("Unexpected local bundle");
        }
        System.out.println("localNoControl=true");

        var viaModule = ResourceBundle.getBundle(
                "demo.local.messages.Labels", Locale.FRENCH,
                LocalDemo.class.getModule());
        if (!viaModule.getString("hello").equals("Bonjour-local")) {
            throw new AssertionError("Module lookup failed");
        }
        System.out.println("localExplicitModule=true");
    }
}
```

### Chạy trên Windows PowerShell

Từ `local-demo`:

```powershell
New-Item -ItemType Directory -Force mods | Out-Null
$files = @(Get-ChildItem src -Recurse -Filter '*.java' |
    Select-Object -ExpandProperty FullName)
javac --release 17 --module-source-path src -d mods $files

New-Item -ItemType Directory -Force "mods/demo.local/demo/local/messages" | Out-Null
Copy-Item "resources/demo/local/messages/Labels_fr.properties" "mods/demo.local/demo/local/messages/Labels_fr.properties"

java --module-path mods --module demo.local/demo.local.LocalDemo
```

### Chạy trên Bash

```bash
mkdir -p mods
javac --release 17 --module-source-path src -d mods \
  $(find src -name '*.java')

mkdir -p mods/demo.local/demo/local/messages
cp resources/demo/local/messages/Labels_fr.properties \
   mods/demo.local/demo/local/messages/Labels_fr.properties

java --module-path mods --module demo.local/demo.local.LocalDemo
```

Output đã xác minh trên JDK 24:

```text
localNoControl=true
localExplicitModule=true
```

Ở đây cả hai lời gọi **không truyền `Control`**, nên không vướng giới hạn named module. `LocalDemo.class.getModule()` cho tham chiếu module hiện tại, dùng ở overload nhận `Module`.

**Lưu ý đóng gói:** `javac` chỉ biên dịch code, không tự động copy tất cả `.properties` từ thư mục resources. Vì vậy lệnh copy resource vào `mods/demo.local/demo/local/messages` rất quan trọng. Trong Gradle/Maven, build pipeline cần đặt bundle vào JAR/module artifact đúng đường package tương tự.

**Giới hạn truy cập:** đọc resource của **module đang gọi** không có nghĩa module khác đương nhiên đọc được resource ấy. Khi dùng overload nhận module mục tiêu, `ResourceBundle` vẫn tuân theo yêu cầu đóng gói resource tương ứng `Module.getResourceAsStream`. Đừng mở mọi package với `--add-opens` chỉ để chữa lỗi đặt resource sai vị trí.

## 6. Cách 2 — ResourceBundleProvider cho named modules

Nếu bundle được một module khác cung cấp, Java hiện hành dùng `java.util.spi.ResourceBundleProvider`.

Chữ ký API:

```java
ResourceBundle getBundle(String baseName, Locale locale);
```

Provider trả `ResourceBundle` cho cặp baseName/locale phù hợp, hoặc `null` khi không có bundle. Trả `null` cho locale chưa hỗ trợ là hành vi hợp lệ theo contract.

### 6.1. Quy tắc đặt tên service interface

Với bundle baseName:

```text
com.example.messages.Messages
```

service type **phải có fully qualified name**:

```text
com.example.messages.spi.MessagesProvider
```

Quy tắc chuẩn:

```text
<package of baseName> + ".spi." +
<simple name of baseName> + "Provider"
```

**Không phải** cứ tạo một interface `MyProvider` trong package tùy ý là `ResourceBundle.getBundle` sẽ tìm. Cơ chế ResourceBundle xác định service type dựa trên baseName; một tên service sai sẽ làm provider không được nhận diện dù các class có thể biên dịch hoàn toàn hợp lệ.

### 6.2. Module consumer và provider có hợp đồng khác nhau

| Vai trò | Module-info |
| --- | --- |
| **API module** sở hữu SPI | `exports com.example.messages.spi;` |
| **Consumer module** dùng bundles | `requires com.example.messages.api; uses com.example.messages.spi.MessagesProvider;` |
| **Provider module** cài đặt SPI | `requires com.example.messages.api; provides ... with ...;` |

Provider module **không nhất thiết export implementation package** chỉ để `ServiceLoader` tạo instance từ declaration `provides`. Điều này giúp tránh lộ API nội bộ.

## 7. Ví dụ Java 17+ đầy đủ: provider qua ba named modules

Dự án gồm:

- `com.example.messages.api`: interface `MessagesProvider` đúng quy tắc.
- `com.example.messages.provider`: triển khai provider cho tiếng Pháp và tiếng Anh.
- `com.example.app`: lấy resource bundles từ provider qua `ResourceBundle.getBundle`; xác minh overload nhận Control bị từ chối.

### 7.1. Cấu trúc

```text
module-demo/
├── src/
│   ├── com.example.messages.api/
│   │   ├── module-info.java
│   │   └── com/example/messages/spi/MessagesProvider.java
│   ├── com.example.messages.provider/
│   │   ├── module-info.java
│   │   └── com/example/impl/MessagesProviderImpl.java
│   └── com.example.app/
│       ├── module-info.java
│       └── com/example/app/App.java
└── mods/
```

### 7.2. `src/com.example.messages.api/module-info.java`

```java
module com.example.messages.api {
    exports com.example.messages.spi;
}
```

### 7.3. `src/com.example.messages.api/com/example/messages/spi/MessagesProvider.java`

```java
package com.example.messages.spi;

import java.util.spi.ResourceBundleProvider;

public interface MessagesProvider extends ResourceBundleProvider {}
```

Đây là service type gắn đúng tên bundle `com.example.messages.Messages`. Giao diện `ResourceBundleProvider` thuộc Java SE, không phải thư viện ngoài.

### 7.4. `src/com.example.messages.provider/module-info.java`

```java
module com.example.messages.provider {
    requires com.example.messages.api;
    provides com.example.messages.spi.MessagesProvider
        with com.example.impl.MessagesProviderImpl;
}
```

Module này cung cấp implementation, không phải consumer. `provides ... with ...` giúp module system định vị service provider hợp lệ.

### 7.5. `src/com.example.messages.provider/com/example/impl/MessagesProviderImpl.java`

```java
package com.example.impl;

import com.example.messages.spi.MessagesProvider;
import java.util.ListResourceBundle;
import java.util.Locale;
import java.util.ResourceBundle;

public final class MessagesProviderImpl implements MessagesProvider {
    @Override
    public ResourceBundle getBundle(String baseName, Locale locale) {
        if (!baseName.equals("com.example.messages.Messages")) {
            return null;
        }
        String greeting;
        if (locale.equals(Locale.FRENCH)) {
            greeting = "Bonjour";
        } else if (locale.equals(Locale.ENGLISH)) {
            greeting = "Hello";
        } else {
            return null;
        }
        final String value = greeting;
        return new ListResourceBundle() {
            @Override
            protected Object[][] getContents() {
                return new Object[][] {{"hello", value}};
            }
        };
    }
}
```

Ví dụ dùng `ListResourceBundle` tạo ở runtime để không phụ thuộc files. Provider thật có thể trả `PropertyResourceBundle` hoặc bundle từ định dạng khác tùy hợp đồng. Nếu provider không có bundle đúng locale, trả `null` thay vì tự giả định luôn phải throw.

**Đây là code có chủ đích giới hạn hai locale.** Demo không kiểm thử fallback cho mọi locale, và không chứng minh logic cache hoặc reload của provider production.

### 7.6. `src/com.example.app/module-info.java`

```java
module com.example.app {
    requires com.example.messages.api;
    uses com.example.messages.spi.MessagesProvider;
}
```

`uses` là điểm rất dễ quên. Nếu consumer bỏ nó trong cấu hình module cần service, `ResourceBundle.getBundle` sẽ không tìm provider theo ý định. `requires` đảm bảo consumer đọc API module chứa service interface.

Không thay `uses com.example.messages.spi.MessagesProvider;` bằng `uses java.util.spi.ResourceBundleProvider;` rồi hy vọng mọi baseName được phục vụ: service type **được suy ra từ baseName**.

### 7.7. `src/com.example.app/com/example/app/App.java`

```java
package com.example.app;

import java.util.Locale;
import java.util.ResourceBundle;

public final class App {
    private static void check(String name, boolean condition) {
        if (!condition) throw new AssertionError(name);
        System.out.println(name + "=true");
    }

    public static void main(String[] args) {
        check("namedModule", App.class.getModule().isNamed());
        var fr = ResourceBundle.getBundle(
                "com.example.messages.Messages", Locale.FRENCH);
        var en = ResourceBundle.getBundle(
                "com.example.messages.Messages", Locale.ENGLISH);
        check("providerFrench", fr.getString("hello").equals("Bonjour"));
        check("providerEnglish", en.getString("hello").equals("Hello"));
        boolean rejected = false;
        try {
            ResourceBundle.getBundle("com.example.messages.Messages",
                    Locale.FRENCH, ResourceBundle.Control.getControl(
                            ResourceBundle.Control.FORMAT_DEFAULT));
        } catch (UnsupportedOperationException expected) {
            rejected = true;
        }
        check("controlRejectedInNamedModule", rejected);
    }
}
```

Ở đây `App.class.getModule().isNamed()` là phép kiểm tra **chắc chắn code đang chạy trong named module**. `ResourceBundle.getBundle` không nhận `Control` nên tìm được provider cho hai locale. Phép thử thứ ba **mong đợi** `UnsupportedOperationException` khi overload Control được gọi.

**Kết quả kiểm thử âm tính:** Nếu chương trình bắt đúng exception và in `controlRejectedInNamedModule=true`, test đã **pass**. Không phải test thất bại. Ngược lại, nếu không ném exception, `check` mới ném `AssertionError`.

### 7.8. Chạy với PowerShell

Ở thư mục `module-demo`:

```powershell
New-Item -ItemType Directory -Force mods | Out-Null

$sources = @(Get-ChildItem src -Recurse -Filter '*.java' |
    Select-Object -ExpandProperty FullName)

javac --release 17 --module-source-path src -d mods $sources

java --module-path mods --module com.example.app/com.example.app.App
```

### 7.9. Chạy với Bash

```bash
mkdir -p mods

javac --release 17 --module-source-path src -d mods \
  $(find src -name '*.java')

java --module-path mods --module com.example.app/com.example.app.App
```

Lệnh dùng `--module-source-path` để compile ba source modules, và `--module-path ... --module ...` để chạy bằng JPMS. Đó là **khác biệt quan trọng** với chạy classpath. Khi module graph liên kết consumer/service, provider module có thể được resolved và service lookup hoạt động.

### 7.10. Stdout đã xác minh trên JDK 24

```text
namedModule=true
providerFrench=true
providerEnglish=true
controlRejectedInNamedModule=true
```

Từng dòng chỉ được in sau `check` thành công. Toàn bộ ví dụ đã được compile bằng `javac --release 17` và chạy trên OpenJDK 24 với exit code thành công.

### 7.11. Tại sao không gọi trực tiếp `ServiceLoader.load`?

`ResourceBundle.getBundle` đã có cơ chế tìm ResourceBundleProvider theo tên service type được xác định từ baseName. Việc tự gọi `ServiceLoader.load(ResourceBundleProvider.class)` không phải là một API thay thế tương đương. Trong demo, service cụ thể là `MessagesProvider`, không phải một service chung không phân biệt bundles.

Một ứng dụng có thể sử dụng `ServiceLoader` trực tiếp cho các SPI của riêng mình, nhưng không nên đánh đồng yêu cầu đó với contract của `ResourceBundle`.

## 8. Ví dụ classpath: chứng minh Control vẫn được hỗ trợ

Để phân biệt phạm vi chính xác, tạo một app **unnamed module** không có `module-info.java`.

```text
classpath-demo/
├── src/
│   ├── ClasspathDemo.java
│   └── demo/Messages_fr.properties
└── out/
```

File `src/ClasspathDemo.java`:

```java
import java.util.Locale;
import java.util.ResourceBundle;

public final class ClasspathDemo {
    public static void main(String[] args) {
        ResourceBundle.Control propertiesOnly =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);
        ResourceBundle bundle = ResourceBundle.getBundle(
                "demo.Messages", Locale.FRENCH, propertiesOnly);
        if (!bundle.getString("hello").equals("Bonjour-classpath")) {
            throw new AssertionError("Unexpected classpath bundle");
        }
        System.out.println("controlOnClasspath=true");
    }
}
```

File `src/demo/Messages_fr.properties`:

```properties
hello=Bonjour-classpath
```

PowerShell:

```powershell
New-Item -ItemType Directory -Force out/demo | Out-Null
javac --release 17 -d out src/ClasspathDemo.java
Copy-Item src/demo/Messages_fr.properties out/demo/Messages_fr.properties
java -cp out ClasspathDemo
```

Bash:

```bash
mkdir -p out/demo
javac --release 17 -d out src/ClasspathDemo.java
cp src/demo/Messages_fr.properties out/demo/Messages_fr.properties
java -cp out ClasspathDemo
```

Kết quả thật trên JDK 24:

```text
controlOnClasspath=true
```

`Control.getNoFallbackControl` và `FORMAT_PROPERTIES` hoạt động ở đây vì caller chạy bằng **classpath/unnamed module**. Đừng rút ra kết luận “`Control` chỉ hoạt động vì properties file”, hoặc “`Control` không bao giờ hoạt động trên Java mới”. Ranh giới là **named versus unnamed caller**.

## 9. ResourceBundleControlProvider khác ResourceBundleProvider

Tên hai API dễ gây nhầm, nhưng chúng có nhiệm vụ khác nhau:

| Thuộc tính | `ResourceBundleControlProvider` | `ResourceBundleProvider` |
| --- | --- | --- |
| Trả về | `ResourceBundle.Control` cho một baseName | `ResourceBundle` cho baseName/locale |
| Vai trò | Tùy chỉnh mặc định của `getBundle` trên classpath | Cung cấp resource bundles qua module service |
| Phạm vi named module | **Bị bỏ qua** | **Được dùng**, nếu khai báo đúng |
| Cách cấu hình | ServiceLoader provider ở classpath | Service type theo baseName + `uses/provides` |
| Thay thế Control khi chuyển sang JPMS? | **Không** | **Đúng hướng** cho bundles do module khác cung cấp |

Javadoc `ResourceBundleControlProvider` nói rõ **mọi provider loại này bị bỏ qua trong named modules**. Vì vậy tạo một `ResourceBundleControlProvider` rồi đăng ký với ServiceLoader **không** khôi phục được quyền tùy chỉnh Control cho named caller.

### AbstractResourceBundleProvider dùng khi nào?

`java.util.spi.AbstractResourceBundleProvider` là một implementation cơ sở của **ResourceBundleProvider**, cung cấp những hỗ trợ chung để nạp bundle theo format phù hợp và có phương thức `toBundleName(...)` cho mapping tên resource. Nó hữu ích khi modules đóng bundle thành `java.class` / `java.properties` hoặc muốn bố trí tài nguyên theo package riêng.

Trong demo, `MessagesProviderImpl` trả một `ListResourceBundle` trực tiếp, nên không cần dùng lớp trừu tượng này. Nếu cần nạp resource từ các package theo locale và tránh module split package, `AbstractResourceBundleProvider` có thể giúp giảm code mapping.

**Không gọi nhầm `AbstractResourceBundleProvider` là một loại `ResourceBundle.Control`.** Nó là công cụ xây provider trong mô hình module, không phải cách vượt giới hạn của overload Control.

## 10. Split packages, resource paths và module encapsulation

JPMS không cho phép nhiều named modules cùng cung cấp package trùng nhau trong một resolved module graph theo cách gây split package. Nếu nhiều provider modules mang các bản dịch theo cùng package path, bạn cần thiết kế lại packaging.

Ví dụ một bundle `com.example.messages.Messages` được chia thành modules cung cấp tiếng Pháp và tiếng Đức. Có thể:

- Giữ một API module `com.example.messages.api` sở hữu service interface `com.example.messages.spi.MessagesProvider`.
- Đặt implementation của từng provider trong package riêng như `com.example.provider.fr` và `com.example.provider.de`.
- Nếu dùng `.properties`, tổ chức bundle resources ở đường path riêng theo module/provider, hoặc dùng `AbstractResourceBundleProvider.toBundleName(...)` để ánh xạ tên bundle.
- Đặt `provides` tương ứng ở từng module, consumer `uses` đúng interface.
- Tích hợp kiểm thử module resolution, lookup và fallback khi nhiều provider cùng hoạt động.

Không “giải quyết split package” bằng cách export toàn bộ packages; `exports` liên quan quyền truy cập, không thay đổi tên package hoặc điều kiện đóng gói.

### Resource có trong JAR chưa chắc đã đọc được

Resource trong named module có thể bị encapsulated. Đặc biệt khi tìm từ module khác, **có tệp trong JAR** không phải bằng chứng đủ. Hãy xác định module sở hữu, lookup API, quan hệ service và quy tắc `Module.getResourceAsStream`.

Với bundle local, hãy bảo đảm build tool đã copy đúng `.properties` vào output. Với bundle provider, kiểm tra API `uses/provides`, khả năng resolve provider module và dữ liệu locale.

Không dùng `--add-opens ALL-UNNAMED` đại trà chỉ để “chữa” lỗi missing resource. Trước tiên phải xác định resource có đúng module và đúng contract không; mở quyền không cần thiết làm tăng khả năng truy cập ngoài ý muốn.

## 11. Locale fallback, root bundle và cache sau migration

Custom `Control` trước đây có thể can thiệp:

- Danh sách candidate locales.
- Thứ tự tìm formats và resource names.
- Fallback từ locale yêu cầu sang default locale.
- Root bundle và parent chain.
- TTL, reload và cache invalidation.

`ResourceBundleProvider` **không đơn thuần là bản đổi tên** của `ResourceBundle.Control`. Trên named module, bạn cần phân định trách nhiệm:

| Trách nhiệm | Điểm cần thiết kế |
| --- | --- |
| Chọn provider | Service interface + module binding |
| Bundle nào có thể phục vụ | `getBundle(baseName, locale)` và quy tắc `null` khi không hỗ trợ |
| Fallback và root | Theo contract factory, có test với locale không tồn tại |
| Cache/reload | Cơ chế `ResourceBundle` cùng chiến lược dữ liệu riêng của provider khi cần |
| Resource lookup | Đúng module/package/resource path và encapsulation |
| Nonstandard format | Provider đọc/tạo `ResourceBundle` thích hợp |

**Đừng suy ra** provider ví dụ cho `Locale.FRENCH` và `Locale.ENGLISH` đã chứng minh mọi tình huống fallback. Chưa có test cho `Locale.CANADA_FRENCH`, default locale khác, root bundle, missing key hoặc hai provider modules cùng phục vụ một locale.

### Khi provider trả null

`ResourceBundleProvider.getBundle` được phép trả `null`. Điều đó nói rằng provider **không có bundle** cho cặp baseName và locale được hỏi. `ResourceBundle.getBundle` còn có quy trình tìm kiếm và fallback theo Javadoc. Đừng bắt buộc provider phải tự đoán toàn bộ fallback trong mọi lần gọi.

### Cache không biến mất

`ResourceBundle` vẫn cache bundles theo các quy tắc hiện hành. Khi chuyển từ Control sang provider, không được mặc định `getTimeToLive` của Control vẫn can thiệp lookup trong named caller.

Nếu translation có thể thay đổi trong lúc ứng dụng đang chạy, lựa chọn phù hợp có thể là:
- Dữ liệu localization được phát hành bất biến theo version.
- Provider sở hữu cache/version và một cơ chế refresh được test riêng.
- Quản lý `ResourceBundle.clearCache()` theo caller/module/class loader đúng contract khi phù hợp.

Cache invalidation là một yêu cầu kiến trúc riêng; không cố gọi overload `Control` chỉ để đổi TTL khi caller đang ở named module.

## 12. Cách chẩn đoán MissingResourceException và lỗi module

Khi `getBundle` không tìm ra dữ liệu, kiểm tra theo thứ tự:

1. **Code gọi thuộc module nào?** Kiểm tra `SomeClass.class.getModule().isNamed()`.
2. **Overload nào đang được dùng?** Nếu nhận Control từ named caller, đó là nhánh **unsupported** cần sửa trước.
3. **Bundle ở đâu?** Cùng module, module khác, hay classpath?
4. **BaseName đúng chưa?** Với `com.example.messages.Messages`, interface phải là `com.example.messages.spi.MessagesProvider`.
5. **Module descriptors đúng chưa?** Consumer `requires`/`uses`, provider `requires`/`provides`.
6. **Provider module có được resolved và có trên module path không?**
7. **File resources có được copy vào output/JAR không?** `javac` không tự đóng gói toàn bộ `.properties`.
8. **Resource có bị encapsulated không?** Đặc biệt ở cross-module lookup.
9. **Locale và root/fallback có đúng contract không?** Provider có trả `null` hay không?
10. **Key có tồn tại?** `getString("key")` có thể ném `MissingResourceException` dù bundle đã được tìm.

**Mẹo test:** luôn có một smoke test thực thi bằng `java --module-path ... --module ...`, đừng chỉ compile từng module riêng và kết luận service discovery đã đúng.

## 13. Ma trận quyết định khi dùng Control hoặc provider

| Câu hỏi | Chọn gì? |
| --- | --- |
| Ứng dụng vẫn chạy `java -cp ...`, cần custom format? | `Control` có thể hợp lệ và hữu ích. |
| Ứng dụng đã có named module, properties ngay trong module? | `getBundle(baseName,locale)`, không `Control`. |
| Bundle cung cấp bởi plugin modules khác? | `ResourceBundleProvider` cùng `uses/provides`. |
| Cần xử lý resource XML trong named module? | Custom `ResourceBundleProvider` với cách parse an toàn. |
| Có sẵn một `ResourceBundleControlProvider` chạy classpath? | Có thể giữ tại unnamed scope, nhưng **không** thay provider module. |
| Module có một tham chiếu target Module và cần đọc bundle của nó? | `getBundle(baseName,locale,module)` với đúng access rules. |
| Cần kiểm soát cache nóng và TTL? | Thiết kế provider/application cache; không bê `Control` vào named caller. |
| Hệ thống đang dùng Java 17+ nhưng chưa modularize? | Không cần đổi vội nếu app là unnamed và cách nạp hiện tại đáp ứng yêu cầu. |

## 14. Quy trình migration từ classpath sang module path

**Bước 1:** Liệt kê các lời gọi `ResourceBundle.getBundle`; phân loại những overload có `Control` và những ứng dụng đang chạy `-cp` hay `--module-path`.

**Bước 2:** Xác định resource ownership. Bundle nằm trong chính app module có thể được chuyển sang no-Control local lookup; bundle từ module khác cần thiết kế SPI hoặc module-aware lookup.

**Bước 3:** Nếu dùng provider, tạo interface đặt tên đúng theo baseName và đặt trong API module có `exports`.

**Bước 4:** Khai báo consumer `uses` và provider `provides`; xác minh module graph, không tự mở implementation packages khi không cần.

**Bước 5:** Kiểm tra định dạng, resource paths, package ownership và split packages. `.properties` phải được đóng gói đúng JAR/module, và provider XML/DB nếu có phải xử lý dữ liệu đúng cách.

**Bước 6:** Chuyển các hooks của Control thành requirement cụ thể: locale fallback, format selection, root, TTL/cache, reload. Không mặc định mọi hooks có phép đổi tên một-một sang provider.

**Bước 7:** Viết positive + negative tests. Named Control phải bị từ chối; no-Control local/provider phải trả đúng strings; unnamed Control vẫn hoạt động nếu còn chạy classpath.

**Bước 8:** Kiểm thử các locales: language/region, locale không được hỗ trợ, root bundle, thiếu key, encoding, cache và thứ tự lựa chọn providers.

**Bước 9:** Kiểm tra packaging sau khi build release, không chỉ chạy bằng source tree. Một JAR có resource sai path có thể build xanh nhưng runtime lỗi.

**Bước 10:** Phát hành có giám sát. Khi đổi locale policy hoặc cơ chế nạp, kiểm tra không phát sinh fallback tiếng Anh ngoài ý muốn trong chức năng cần bản dịch bắt buộc.

## 15. Các lỗi lập trình thường gặp

| Sai lầm | Tác hại | Cách sửa |
| --- | --- | --- |
| Dùng `getBundle(...,Control)` trong named module | `UnsupportedOperationException` | No-Control hoặc provider/module-aware lookup |
| Nghĩ Control đã bị xóa khỏi Java 26 | Migrate sai cả ứng dụng classpath vẫn hợp lệ | Phân biệt named/unnamed caller |
| Thay `Control` bằng `ResourceBundleControlProvider` trong named module | Custom Control SPI vẫn bị bỏ qua | `ResourceBundleProvider` |
| Đặt service interface tên tùy ý | Factory không tìm đúng provider | `<package>.spi.<SimpleName>Provider` |
| Quên `uses` trong consumer | Không có service binding dự kiến | Khai báo đúng service type |
| Quên `provides` trong provider | Implementation không được công bố | Khai báo `provides ... with ...` |
| Không copy `.properties` vào module output | `MissingResourceException` | Đóng gói resource đúng path |
| Nhầm class loader với module lookup | Không thấy named encapsulated bundle | Dùng `getBundle(...,Module)` hoặc SPI đúng |
| Mở mọi package bằng `--add-opens` | Tăng access không cần thiết | Sửa module structure/lookup |
| Trùng package ở nhiều provider modules | Split package conflict | Tách package, map resource riêng |
| Nói `getNoFallbackControl` bỏ luôn root | Hiểu sai fallback | Phân biệt fallback default locale và base/root |
| Provider ném exception cho locale không hỗ trợ | Chặn factory tìm ứng viên khác | Trả `null` đúng contract |
| Gọi ServiceLoader theo generic interface rồi mong tự tìm baseName | Không đúng service naming | Để ResourceBundle factory xử lý |
| Không kiểm tra cache khi đổi dữ liệu | Dùng bản dịch cũ | Thiết kế cache invalidation |
| Chỉ chạy tests trên classpath | Không phát hiện giới hạn JPMS | Có integration tests trên module path |

## 16. Bộ kiểm thử tối thiểu trước khi triển khai

1. **Caller scope:** Có assertion xác nhận app thực sự chạy trong named/unnamed module đúng với deploy.
2. **Named Control negative:** `ResourceBundle.getBundle(...,Control)` phải ném `UnsupportedOperationException`.
3. **Named local positive:** `getBundle(baseName,locale)` trả đúng local bundle nếu resource trong module.
4. **Named service positive:** Provider nhận đúng baseName, consumer uses, provider provides, trả đúng locale.
5. **Unnamed Control positive:** `getBundle(...,Control)` tìm đúng property resource trên classpath.
6. **Missing locale:** Có kiểm thử fallback/root cho những locale sản phẩm thực sự hỗ trợ.
7. **Missing key:** Hệ thống xử lý `MissingResourceException` theo yêu cầu.
8. **Resource visibility:** Các modules chỉ mở/export những packages cần thiết, không mở toàn bộ hệ thống.
9. **Packaging:** Xác minh các file `.properties` đã được copy; không chỉ compile Java.
10. **Provider order:** Khi có nhiều providers, test lựa chọn bundles/fallback chính xác.
11. **Cache:** Kiểm thử cách cập nhật resource trong runtime khi hệ thống cho phép thay đổi bản dịch.
12. **Concurrency:** Provider implementation thread-safe khi trả các bundles được dùng đồng thời.
13. **Build tool:** Lệnh chạy thực tế giống module path/classpath trong môi trường sản phẩm.
14. **JDK support:** API và options tương thích JDK hỗ trợ; ví dụ bài dùng `--release 17` và JDK 24.
15. **Không xử lý sai exception:** Phân biệt unsupported overload với missing bundle để nhận diện lỗi thiết kế.

## 17. Câu hỏi tự kiểm tra

**1. `ResourceBundle.Control` đã obsolete và nên xóa khỏi mọi project Java 17+?**

Không. Nó còn được hỗ trợ cho **unnamed module/classpath**; giới hạn cụ thể là overload nhận Control **không hỗ trợ named caller**.

**2. Nếu named module gọi `getBundle(baseName,Locale.FRENCH,control)` và ném UnsupportedOperationException, sửa resource path có giải quyết được không?**

Không. Lỗi do loại overload bị cấm theo module context. Dùng lookup no-Control hoặc service provider phù hợp.

**3. Named module cần đọc `.properties` nằm trong chính module, có phải tạo provider module mới?**

Không. Chỉ cần `ResourceBundle.getBundle(baseName,locale)` và đóng gói file đúng.

**4. Bundle baseName `com.example.messages.Messages` có service type tên gì?**

`com.example.messages.spi.MessagesProvider`. Consumer `uses` loại đó, provider `provides` implementation.

**5. `ResourceBundleControlProvider` có giải quyết giới hạn JPMS của Control?**

Không. Java SE quy định Control providers bị bỏ qua trong named modules. ResourceBundleProvider mới là SPI cung cấp bundles ở module context.

**6. Vì sao cần `App.class.getModule().isNamed()` trong bài kiểm thử?**

Để bảo đảm chương trình thực sự đang chạy trong named module. Nếu vô ý chạy classpath, kết quả Control có thể khác hoàn toàn.

**7. `ResourceBundleProvider.getBundle` nên trả gì nếu không hỗ trợ locale đó?**

Trả `null` theo contract, cho phép quy trình tìm kiếm/fallback của factory diễn ra phù hợp.

**8. Có thể dùng `getBundle(baseName,locale,module)` để bỏ qua mọi encapsulation?**

Không. API module-aware vẫn chịu resource access rules và yêu cầu service liên quan.

**9. Vì sao không lấy việc `javac` compile thành công làm bằng chứng resource bundle chạy?**

Vì `javac` không tự copy mọi `.properties`, và code vẫn có thể thiếu uses/provides hoặc module resolution. Cần test runtime.

**10. Một app unnamed có thể dùng `Control.getNoFallbackControl(FORMAT_PROPERTIES)` để chỉ nạp properties?**

Có. Đó là một factory Control hợp lệ; khi chạy classpath, demo đã kiểm chứng được `controlOnClasspath=true`.

**11. Nếu resource provider nằm trong module khác, vì sao phải cẩn thận split packages?**

JPMS có các quy tắc package ownership; nhiều modules chứa cùng package có thể xung đột. Tách implementation/resource packages hoặc dùng mapping phù hợp.

**12. Khi migration, có thể bê `Control.getTimeToLive` thẳng sang provider để đổi TTL?**

Không có phép port một-một tự động. Cần thiết kế và kiểm thử chiến lược cache/reload tương ứng với module-aware provider.

## Tài liệu chính thức còn hiệu lực

- [Java SE 26 — `ResourceBundle`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.html): phần *Resource Bundles and Named Modules*, các overload và `UnsupportedOperationException`.
- [Java SE 26 — `ResourceBundle.Control`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ResourceBundle.Control.html): control format, candidate locales, fallback và cache.
- [Java SE 26 — `ResourceBundleProvider`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/ResourceBundleProvider.html): service naming convention, `getBundle(baseName,locale)` và `uses/provides`.
- [Java SE 26 — `AbstractResourceBundleProvider`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/AbstractResourceBundleProvider.html): hỗ trợ implementation của provider.
- [Java SE 26 — `ResourceBundleControlProvider`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/spi/ResourceBundleControlProvider.html): provider cung cấp Control bị bỏ qua trong named modules.
- [Java SE 26 — `Module.getResourceAsStream`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Module.html#getResourceAsStream(java.lang.String)): truy cập resource trong module.
- [Java SE 26 — `ServiceLoader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ServiceLoader.html): service deployment với JPMS `uses/provides`.
- [Oracle Java SE 26 — Internationalization Guide](https://docs.oracle.com/en/java/javase/26/intl/internationalization-guide.pdf): tổng quan ResourceBundle và giới hạn Control trong named modules.

**Ghi nhớ:** `ResourceBundle.Control` vẫn hữu ích trên classpath nhưng **getBundle overload nhận Control không dùng được khi caller là named module**. Với bundle nội bộ module, ưu tiên `getBundle(baseName,locale)`; với module cung cấp bản dịch riêng, dùng `ResourceBundleProvider` và khai báo service chính xác; với classpath/unnamed module, `Control` tiếp tục là lựa chọn hợp lệ khi cần tùy chỉnh. Luôn kiểm tra module path, resource packaging, service binding và các quy tắc fallback/cache.
