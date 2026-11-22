# Đóng gói JAR hoặc runtime image và kiểm tra tài nguyên bản dịch trong Java

## 1. Mục tiêu thực hành và ba loại sản phẩm triển khai

Một ứng dụng Java đã sử dụng `ResourceBundle` để hiển thị thông điệp đa ngôn ngữ có thể chạy đúng trong IDE nhưng sai khi triển khai:

- File `Texts_vi.properties` tồn tại trong thư mục `src/main/resources`, nhưng không xuất hiện trong JAR.
- File có trong JAR nhưng ở sai đường dẫn, làm `ResourceBundle.getBundle(...)` không tìm được.
- Chương trình vẫn tìm thấy bundle tiếng Việt, nhưng số/ngày được định dạng khác trên **runtime image tối giản** vì thiếu dữ liệu locale của JDK.
- Ứng dụng chỉ chạy khi có JDK đầy đủ trên máy người phát triển, nhưng bản phân phối lại thiếu runtime.
- Một bộ cài `jpackage` chứa runtime đúng nhưng launcher dùng nhầm JAR, hoặc chỉ chép thư mục runtime mà quên mã/tài nguyên ứng dụng.

Để giải quyết đúng, phải phân biệt **ba sản phẩm**:

| Sản phẩm | Công cụ | Chứa gì? | Cách dùng điển hình |
| --- | --- | --- | --- |
| **JAR ứng dụng** | `jar`, Maven hoặc Gradle | `.class` và `.properties` của ứng dụng; có thể có manifest | `java -jar app.jar`, cần Java runtime có sẵn |
| **Custom runtime image** | `jlink` | JVM và **các Java modules** được chọn (ví dụ `java.base`, `jdk.localedata`) | `runtime/bin/java -jar app.jar`; **không tự chứa app JAR** |
| **Application image** | `jpackage --type app-image` | Launcher + ứng dụng/JAR + runtime image tương thích | Chạy launcher phân phối theo hệ điều hành |

Điểm quan trọng: **`jlink` không tự đưa file `Messages*.properties` hoặc ứng dụng classpath thông thường vào runtime image.** Nó tạo một bộ runtime có các module Java. Để tạo bản phân phối thực sự “có cả ứng dụng và runtime”, bạn phải cung cấp **app JAR bên cạnh runtime** hoặc dùng `jpackage` (hay một cơ chế phân phối khác).

Bài thực hành sử dụng **Java 17+**, một class `ResourceAudit` và ba file `.properties`. Sau khi học, bạn sẽ:

1. Tạo ứng dụng có hai ngôn ngữ Anh–Việt.
2. Biên dịch, đóng gói thành executable JAR và kiểm tra entry thực tế.
3. Tạo runtime image bằng `jlink`, kèm dữ liệu locale thích hợp.
4. Chạy app JAR bằng runtime vừa tạo, kiểm chứng thông điệp và định dạng.
5. Tùy chọn dùng `jpackage` để kết hợp JAR và runtime thành app image.
6. Viết tiêu chí kiểm thử đóng gói, phát hiện thiếu file, thiếu module, sai charset hoặc sai đường dẫn.

## 2. ResourceBundle có hai tầng cần kiểm tra

`ResourceBundle` sử dụng các thông tin:

- **Base name**: ví dụ `com.example.i18n.Texts`.
- **Locale được yêu cầu**: ví dụ `Locale.forLanguageTag("vi-VN")`.
- **Runtime classpath/module**: nơi các file `.properties` hoặc các lớp bundle tồn tại.

Với base name ở ví dụ, cấu trúc resource ứng dụng trên classpath là:

```text
com/example/i18n/Texts.properties
com/example/i18n/Texts_en.properties
com/example/i18n/Texts_vi.properties
```

Trong Java, lời gọi:

```java
ResourceBundle bundle = ResourceBundle.getBundle(
        "com.example.i18n.Texts",
        Locale.forLanguageTag("vi-VN"));
```

sẽ xét các candidate locale (ví dụ `vi_VN`, `vi` và root) theo thuật toán của `ResourceBundle`. Nếu không có `Texts_vi_VN.properties` nhưng có `Texts_vi.properties`, bundle ngôn ngữ `vi` vẫn có thể được chọn.

Cần kiểm tra **hai tầng khác nhau**:

1. **Bundle của ứng dụng** (`Texts_vi.properties`) có tồn tại, được đặt đúng path và được load không?
2. **Locale data của JDK** (`jdk.localedata`) có đủ cho các API Java như `NumberFormat`, `DateTimeFormatter`, `Collator` hay không?

Ví dụ, nếu thiếu module `jdk.localedata`, một số runtime image vẫn load được các **chuỗi do chính ứng dụng dịch** từ `Texts_vi.properties`, bởi `PropertyResourceBundle` thuộc `java.base`. Tuy nhiên **quy tắc format bản địa hóa của JDK** có thể fallback về dữ liệu locale có sẵn; không thể suy ra “tiếng Việt đầy đủ” chỉ vì `getString("greeting")` trả đúng.

**Kết luận:** kiểm thử resource bundle và kiểm thử runtime locale data là **hai phép kiểm tra riêng**, đều cần trong quá trình đóng gói.

## 3. Cấu trúc dự án mẫu

Dự án không có thư viện thứ ba; `ResourceAudit` ở package `com.example.app`, resource ở namespace `com.example.i18n`:

```text
locale-packaging-demo/
├── src/
│   └── main/
│       ├── java/
│       │   └── com/
│       │       └── example/
│       │           └── app/
│       │               └── ResourceAudit.java
│       └── resources/
│           └── com/
│               └── example/
│                   └── i18n/
│                       ├── Texts.properties
│                       ├── Texts_en.properties
│                       └── Texts_vi.properties
└── build/                      # sinh ra sau khi chạy lệnh build
    ├── classes/
    ├── dist/
    ├── runtime/
    └── package/
```

Bộ thư mục `build` **không phải dữ liệu nguồn**; nó được tạo bởi `javac`, `jar`, `jlink` và `jpackage` khi chạy các lệnh ở mục sau. Không cần phải viết `build` vào resource bundle base name.

Tên class sẽ là `com.example.app.ResourceAudit`. Base name luôn là `com.example.i18n.Texts`; Java không bắt buộc resource cùng package với class Main, miễn nó nằm ở đường dẫn thích hợp trên classpath/runtime.

### Quy tắc dịch tên logic thành đường dẫn

| Phần tử | Giá trị |
| --- | --- |
| Base name | `com.example.i18n.Texts` |
| Tên root file | `Texts.properties` |
| Locale `en` | `Texts_en.properties` |
| Locale `vi-VN` khi chỉ có bản `vi` | `Texts_vi.properties` |
| Entry JAR cần có | `com/example/i18n/Texts_vi.properties` |
| Thư mục nguồn | `src/main/resources/com/example/i18n/` |
| Truy cập resource bằng classloader | `getResource("com/example/i18n/Texts_vi.properties")` |

Khi dùng `ClassLoader.getResource`, **không** thêm dấu `/` vào đầu đường dẫn. Trái lại, `SomeClass.class.getResource("/com/example/i18n/Texts_vi.properties")` có thể dùng dấu `/` đầu để tìm từ classpath root. Sự khác biệt nhỏ này thường gây lỗi khi viết bộ kiểm tra tài nguyên.

## 4. Tạo ba file thông điệp UTF-8

Các tệp `.properties` sau phải được lưu **UTF-8** và đặt đúng vị trí đã nêu.

### 4.1. src/main/resources/com/example/i18n/Texts.properties

```properties
greeting=Hello, {0}!
count=Messages: {0,number,integer}
only.root=ROOT_OK
```

File root có thể được dùng như fallback nếu một key thiếu ở bản dịch cụ thể. Giá trị `only.root` cố tình **chỉ có ở root** để chứng minh cơ chế kế thừa key.

### 4.2. src/main/resources/com/example/i18n/Texts_en.properties

```properties
greeting=Hello, {0}!
count=Messages: {0,number,integer}
```

### 4.3. src/main/resources/com/example/i18n/Texts_vi.properties

```properties
greeting=Xin chào, {0}!
count=Tin nhắn: {0,number,integer}
```

Các giá trị nằm trong **câu thông điệp hoàn chỉnh**, không tách thành các fragment kiểu `prefix`, `noun`, `suffix`. Với `{0}`, Java sẽ truyền một giá trị, còn bản dịch quyết định vị trí nó xuất hiện. `{0,number,integer}` cho phép `MessageFormat` định dạng số nguyên theo `Locale`.

Từ Java 9, `PropertyResourceBundle` mặc định thử UTF-8 với fallback ISO-8859-1 cho các byte UTF-8 không hợp lệ, theo JEP 226, trừ khi cấu hình khác. Không nhầm với `Properties.load(InputStream)` có quy tắc ISO-8859-1 riêng. Để kiểm tra chính xác file nguồn, đặt encoding UTF-8 thống nhất và cân nhắc thuộc tính `java.util.PropertyResourceBundle.encoding=UTF-8` trong môi trường cần đọc nghiêm ngặt.

### Vì sao không có Texts_vi_VN.properties?

Mục đích là cho thấy **fallback từ locale vùng `vi-VN` xuống bundle ngôn ngữ `vi`**. Chương trình vẫn yêu cầu `vi-VN`, nhưng `bundle.getLocale().toLanguageTag()` dự kiến là `vi`. Đây là hành vi bình thường: **locale yêu cầu** và **locale của bundle tìm được** không phải lúc nào cũng trùng nhau.

## 5. Chương trình Java 17+ hoàn chỉnh: ResourceAudit.java

Tạo file **src/main/java/com/example/app/ResourceAudit.java**:

```java
package com.example.app;

import java.net.URL;
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public final class ResourceAudit {
    private static final String BASE =
            "com.example.i18n.Texts";

    public static void main(String[] args) {
        String code = args.length == 0 ? "en" : args[0];

        Locale locale;
        switch (code.toLowerCase(Locale.ROOT)) {
            case "en" -> locale = Locale.ENGLISH;
            case "vi" -> locale =
                    Locale.forLanguageTag("vi-VN");
            default -> {
                System.err.println("Use en or vi");
                System.exit(2);
                return;
            }
        }

        ResourceBundle bundle =
                ResourceBundle.getBundle(BASE, locale);

        ClassLoader loader =
                ResourceAudit.class.getClassLoader();
        String rootPath =
                "com/example/i18n/Texts.properties";
        String localizedPath = code.equalsIgnoreCase("vi")
                ? "com/example/i18n/Texts_vi.properties"
                : "com/example/i18n/Texts_en.properties";

        URL rootUrl = loader.getResource(rootPath);
        URL localizedUrl = loader.getResource(localizedPath);

        System.out.println("requested=" +
                locale.toLanguageTag());
        System.out.println("bundle-locale=" +
                bundle.getLocale().toLanguageTag());
        System.out.println("root-resource=" +
                (rootUrl != null));
        System.out.println("localized-resource=" +
                (localizedUrl != null));

        MessageFormat greeting = new MessageFormat(
                bundle.getString("greeting"), locale);
        MessageFormat count = new MessageFormat(
                bundle.getString("count"), locale);

        System.out.println("greeting=" +
                greeting.format(new Object[]{"Lan"}));
        System.out.println("count=" +
                count.format(new Object[]{1234}));
        System.out.println("fallback=" +
                bundle.getString("only.root"));
    }
}
```

**Phân tích code:**

1. Chương trình chấp nhận đối số `en` hoặc `vi`; không cần thay đổi `Locale.setDefault(...)` toàn JVM.
2. `Locale.ENGLISH` yêu cầu bản dịch tiếng Anh; `Locale.forLanguageTag("vi-VN")` yêu cầu tiếng Việt Việt Nam.
3. `ResourceBundle.getBundle(BASE, locale)` tìm bundle từ classpath (vì ví dụ là JAR không có `module-info.java`).
4. `getLocale()` trả locale của bundle tìm được; có thể là `vi` dù locale yêu cầu là `vi-VN`.
5. `ClassLoader.getResource(...)` kiểm tra **entry cụ thể có mặt** theo đúng path. Đây không phải cách thay `getBundle` trong toàn ứng dụng, chỉ là một probe cho bài thực hành.
6. `MessageFormat` được tạo với locale người dùng chứ không dựa vào default locale của máy; định dạng `1234` vì vậy có thể dùng dấu nhóm nghìn phù hợp vùng.
7. `only.root` được tra qua parent chain, chứng minh root resource có hiệu lực.
8. Mã trả về `2` cho tham số ngôn ngữ không hỗ trợ, giúp script/CI phân biệt tình huống lỗi.

**Giới hạn của probe:** `ClassLoader.getResource(...) != null` chứng minh classloader nhìn thấy file ở path đó, **không tự chứng minh đúng nội dung, đủ mọi key hoặc là bản dịch đã được kiểm tra chất lượng**. Vì vậy cần kiểm thử cả `getString` và kết quả format thực tế.

### Đầu ra khi dùng đủ resource và locale data

Chạy với `en`:

```text
requested=en
bundle-locale=en
root-resource=true
localized-resource=true
greeting=Hello, Lan!
count=Messages: 1,234
fallback=ROOT_OK
```

Chạy với `vi` trên JDK có dữ liệu locale `vi-VN` phù hợp:

```text
requested=vi-VN
bundle-locale=vi
root-resource=true
localized-resource=true
greeting=Xin chào, Lan!
count=Tin nhắn: 1.234
fallback=ROOT_OK
```

Các ví dụ output dựa trên quy tắc định dạng số của JDK hiện đại với locale data tương ứng (vi-VN thường dùng dấu chấm nhóm nghìn). **Vẫn phải kiểm tra trên JDK/runtime image được phát hành**, vì dữ liệu locale và provider có thể khác nhau. File bundle đúng không bảo đảm format số luôn như snapshot ở trên nếu bạn cắt giảm `jdk.localedata`.

## 6. Biên dịch và đóng gói JAR bằng JDK 17+

Mở terminal tại **gốc thư mục `locale-packaging-demo`**.

### Bước 1 — Compile

```bash
javac -encoding UTF-8 -d build/classes src/main/java/com/example/app/ResourceAudit.java
```

Lệnh tạo `build/classes/com/example/app/ResourceAudit.class`. `-encoding UTF-8` chỉ rõ charset của source Java, không liên quan trực tiếp tới cách `PropertyResourceBundle` đọc tài nguyên sau khi đóng gói.

### Bước 2 — Tạo thư mục phân phối

Linux/macOS:

```bash
mkdir -p build/dist
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force -Path build/dist
```

### Bước 3 — Tạo executable JAR

```bash
jar --create --file build/dist/localization-demo.jar \
    --main-class com.example.app.ResourceAudit \
    -C build/classes . -C src/main/resources .
```

Trong Bash, dấu `\` ở cuối dòng là ký hiệu nối dòng. Trên Windows PowerShell, dùng lệnh **một dòng**:

```powershell
jar --create --file build/dist/localization-demo.jar --main-class com.example.app.ResourceAudit -C build/classes . -C src/main/resources .
```

Ý nghĩa quan trọng:

- `--main-class` ghi tên Main vào manifest để `java -jar` biết class khởi chạy.
- `-C build/classes .` đưa **nội dung bên trong `build/classes`** vào gốc JAR.
- `-C src/main/resources .` đưa **nội dung của resource root** vào gốc JAR.
- `-C` không phải một phần của tên file bundle; nó giúp giữ đúng entry như `com/example/i18n/Texts_vi.properties`.

Đừng dùng `jar ... src/main/resources` theo cách đưa cả tiền tố nguồn vào JAR; nếu entry thành `src/main/resources/com/example/i18n/Texts_vi.properties` thì base name `com.example.i18n.Texts` sẽ **không** tìm được nó theo classpath root thông thường.

### Bước 4 — Kiểm tra nội dung JAR

```bash
jar tf build/dist/localization-demo.jar
```

Trong danh sách phải có ít nhất (đây chỉ là trích đoạn):

```text
META-INF/MANIFEST.MF
com/example/app/ResourceAudit.class
com/example/i18n/Texts.properties
com/example/i18n/Texts_en.properties
com/example/i18n/Texts_vi.properties
```

Kiểm tra manifest nếu cần:

```bash
unzip -p build/dist/localization-demo.jar META-INF/MANIFEST.MF
```

`unzip` là công cụ tùy môi trường, không thuộc mọi cài đặt JDK. Nếu không có, có thể dùng công cụ mở ZIP/JAR của hệ điều hành hoặc `jar --extract` trong một thư mục test an toàn. Manifest phải ghi `Main-Class: com.example.app.ResourceAudit` nếu JAR được tạo như lệnh ở trên.

### Bước 5 — Chạy bằng JDK thông thường

```bash
java -jar build/dist/localization-demo.jar en
java -jar build/dist/localization-demo.jar vi
```

Output mong muốn là hai bảng ở mục 5. Đây là **smoke test thực sự trên JAR thành phẩm**. Chạy được bằng `java -cp build/classes:src/main/resources ...` chỉ chứng minh thư mục source resources có trong classpath, **không chứng minh JAR đúng**.

### Bước 6 — Chạy ở thư mục khác

Chép `localization-demo.jar` sang một thư mục không có `src/main/resources` rồi chạy `java -jar ...`. Nếu tài nguyên được đóng gói đúng, chương trình vẫn tìm được hai bản dịch. Test này phát hiện trường hợp code còn vô tình đọc resource bằng `new File("src/main/resources/...")`.

## 7. JAR và runtime image không phải một thứ

Một JAR app có mã và properties, nhưng chạy bằng:

```bash
java -jar build/dist/localization-demo.jar vi
```

vẫn yêu cầu hệ điều hành có Java runtime tương thích. Bạn có thể phân phối JAR cùng hướng dẫn cài JRE/JDK, hoặc tạo một **custom runtime image** để không phụ thuộc vào Java cài sẵn.

`jlink` là công cụ chuẩn của JDK 9+ liên kết Java modules và các dependency module của chúng thành một thư mục runtime. Nó sử dụng `jmods` của JDK và có thể tạo một image nhỏ hơn bản JDK đầy đủ.

**Phân biệt:**

```text
build/dist/localization-demo.jar
    └── app .class + Texts*.properties

build/runtime/
    ├── bin/java[.exe]
    ├── conf/...
    ├── lib/modules
    └── ...
        (Java runtime modules; không tự có app JAR)
```

Khi phân phối theo cách thủ công, người dùng cần **cả hai**: `build/runtime` và `localization-demo.jar`. Không thể chỉ gửi thư mục runtime rồi kỳ vọng class `com.example.app.ResourceAudit` nằm trong đó.

## 8. Tạo custom runtime image với jlink

### 8.1. Modules cần có cho ứng dụng mẫu

Chương trình `ResourceAudit` dùng những API của `java.base`:

- `java.util.Locale`, `ResourceBundle`;
- `java.text.MessageFormat`;
- `java.lang`;
- `java.net.URL`.

Vì thế **`java.base` là module nền tảng bắt buộc**. Nhưng để định dạng số/ngày theo nhiều locale trong JDK, thường cần **`jdk.localedata`**, là module chứa thêm dữ liệu locale ngoài US English/ROOT của nhiều bản JDK.

Trong Oracle JDK 21, dữ liệu en-US/root cơ bản có trong `java.base`; các locale data bổ sung thuộc `jdk.localedata`. Một số runtime chỉ có `java.base` vẫn gọi `Locale.forLanguageTag("vi-VN")` và load file `Texts_vi.properties`, nhưng **NumberFormat** có thể fallback vì chưa có dữ liệu format vi-VN.

### 8.2. Command jlink với dữ liệu locale

Với JDK 17+ có `jlink`:

```bash
jlink --add-modules java.base,jdk.localedata \
      --include-locales=en,vi \
      --strip-debug --no-header-files --no-man-pages \
      --output build/runtime
```

Windows PowerShell (một dòng):

```powershell
jlink --add-modules java.base,jdk.localedata --include-locales=en,vi --strip-debug --no-header-files --no-man-pages --output build/runtime
```

**Chỉ chạy khi `build/runtime` chưa tồn tại** hoặc đã được dọn dẹp có chủ đích cho lần build mới: `jlink` không dùng để ghi đè tùy ý lên một image đã có. Hãy xem kỹ đường dẫn output trước thao tác xóa hoặc thay thế.

Giải thích option:

| Option | Tác dụng |
| --- | --- |
| `--add-modules java.base,jdk.localedata` | Đưa các module cần thiết vào image; `jdk.localedata` phục vụ dữ liệu locale bổ sung |
| `--include-locales=en,vi` | Giữ dữ liệu locale phù hợp bộ lọc BCP 47 đã chọn; phải có `jdk.localedata` |
| `--strip-debug` | Giảm thông tin debug trong image |
| `--no-header-files` | Không đưa header C dùng cho phát triển native |
| `--no-man-pages` | Không đưa trang manual |
| `--output build/runtime` | Nơi sinh runtime image |

`--include-locales` là plugin của `jlink`. Theo tài liệu chính thức, khi dùng option này cần có `jdk.localedata` trong tập module. Dạng `en,vi` là danh sách các language tag, không phải tên file `Messages_en.properties` hay `Messages_vi.properties`.

**Cảnh báo về bộ lọc locale:** plugin sử dụng matching theo BCP 47/RFC 4647. Hãy chạy test trực tiếp với `vi-VN` và `en` trên image thực tế; đừng chỉ kết luận “đã giữ tiếng Việt” vì option có chữ `vi`. Nếu app hỗ trợ thêm các vùng như `fr-FR` hoặc `ja-JP`, phải cập nhật image và kiểm thử cả số, ngày, tiền và collation tương ứng.

### 8.3. Kiểm tra image tạo ra

Linux/macOS:

```bash
build/runtime/bin/java --version
build/runtime/bin/java --list-modules
```

Windows PowerShell:

```powershell
.\build\runtime\bin\java.exe --version
.\build\runtime\bin\java.exe --list-modules
```

Trong `--list-modules` phải thấy ít nhất:

```text
java.base@<JDK_VERSION>
jdk.localedata@<JDK_VERSION>
```

Hai dòng trên là **mẫu dạng đầu ra**, `<JDK_VERSION>` là placeholder dùng để giải thích, không phải output cố định. Version thực tế lấy từ JDK mà bạn đã chạy `jlink`. Các module khác nếu có thể xuất hiện do dependency hoặc tùy cấu hình.

Chạy ứng dụng bằng **chính Java trong runtime image**, không phải `java` của PATH:

Linux/macOS:

```bash
build/runtime/bin/java -jar build/dist/localization-demo.jar vi
build/runtime/bin/java -jar build/dist/localization-demo.jar en
```

Windows PowerShell:

```powershell
.\build\runtime\bin\java.exe -jar build/dist/localization-demo.jar vi
.\build\runtime\bin\java.exe -jar build/dist/localization-demo.jar en
```

Nếu tất cả file tài nguyên đi kèm JAR và `jdk.localedata` được giữ đúng, kết quả về `root-resource`, `localized-resource`, `greeting`, `count` và `fallback` dự kiến giống khi chạy bằng JDK đầy đủ.

**Đừng dùng `java -jar ...` không có đường dẫn `build/runtime/bin/java` để kiểm thử image**: lệnh ấy có thể vô tình chạy JDK hệ thống, khiến thử nghiệm “runtime tùy biến” không còn giá trị.

## 9. Thí nghiệm so sánh runtime thiếu và đủ locale data

Đây là một bài kiểm thử rất quan trọng, bởi có thể xảy ra tình huống **bản dịch hiển thị đúng nhưng số/ngày không đúng vùng**.

Tạo image tối giản chỉ có `java.base` ở **thư mục khác**:

```bash
jlink --add-modules java.base --output build/runtime-base
```

Sau đó chạy cùng JAR:

```bash
build/runtime-base/bin/java -jar build/dist/localization-demo.jar vi
```

Ở Windows, dùng `.\build\runtime-base\bin\java.exe` thay cho `build/runtime-base/bin/java`.

Hãy quan sát ba nhóm output:

1. `localized-resource=true` có thể vẫn đúng vì file `Texts_vi.properties` nằm trong **app JAR**, không nằm trong `jdk.localedata`.
2. `greeting=Xin chào, Lan!` có thể vẫn đúng vì chuỗi dịch do app cung cấp.
3. `count=Tin nhắn: ...` có thể được định dạng theo dữ liệu locale **fallback** của runtime. Trên nhiều bản JDK chỉ có `java.base`, quy tắc phân cách nghìn cho vi-VN không có đủ, nên có thể khác image đủ dữ liệu.

**Không hardcode một output sai bắt buộc như “mọi image java.base-only in 1,234”**. JDK/provider có thể biến đổi theo phiên bản hoặc triển khai. Bài thực hành yêu cầu so sánh **thực tế** hai image ở cùng môi trường, ghi lại `--list-modules` và các giá trị quan sát được.

### Tại sao không chỉ test ResourceBundle.getString?

`getString` chỉ kiểm tra dữ liệu bản dịch do app tự đóng gói. Những chức năng bản địa hóa khác cần có dữ liệu JDK:

- `NumberFormat.getNumberInstance(locale)`;
- `DateTimeFormatter.ofLocalizedDate(...).withLocale(locale)`;
- `Collator.getInstance(locale)`, `BreakIterator` khi có hỗ trợ theo nhà cung cấp dữ liệu;
- tên tháng/thứ, định dạng ngày/giờ, đơn vị tiền theo `Locale`.

Các API này có thể phụ thuộc nhiều module/provider khác nhau. **`jdeps` phân tích static module dependencies**, nhưng thường không suy ra được mọi nhu cầu dữ liệu runtime được chọn động qua `Locale` hoặc resource/provider service. Vì vậy chạy thử trên image đã cắt là bắt buộc.

## 10. jdeps: kiểm tra dependency module nhưng đừng bỏ quên locale

`jdeps` là công cụ phân tích dependency của class/JAR. Với JAR mẫu:

```bash
jdeps --print-module-deps build/dist/localization-demo.jar
```

Đối với mã Java SE đơn giản của bài, kết quả thường là:

```text
java.base
```

Điều này đúng: các lớp được tham chiếu tĩnh đều thuộc `java.base`. Nhưng **không đồng nghĩa ứng dụng chỉ cần dữ liệu của `java.base` để format mọi locale**. `jdk.localedata` chủ yếu cung cấp dữ liệu locale được sử dụng qua cơ chế locale providers chứ không nhất thiết là tham chiếu lớp tĩnh trong bytecode `ResourceAudit`.

Vì vậy khi chọn modules cho `jlink`:

1. Dùng `jdeps` làm điểm bắt đầu để phát hiện Java modules mà code cần.
2. Bổ sung modules cho locale/provider/runtime features mà test chứng minh là cần.
3. Chạy lại `--list-modules` và smoke test thực sự.
4. Không áp dụng máy móc `jlink --add-modules $(jdeps ...)` và cho rằng mọi chức năng bản địa hóa sẽ luôn đủ.
5. Với thư viện ngoài, xem dependency không modular, reflective access, JNI, ServiceLoader và các module cần thiết trước khi tối giản image.

Một ứng dụng phức tạp có thể cần `java.sql`, `java.desktop`, `java.logging` hoặc modules khác. Đừng copy danh sách chỉ có `java.base,jdk.localedata` từ bài demo sang app production mà không phân tích dependency.

## 11. jpackage: kết hợp JAR và runtime thành application image

`jlink` tạo **runtime image**, trong khi `jpackage` có thể tạo **app image** chứa launcher, ứng dụng và runtime.

Với các artifact đã có:

```text
build/dist/localization-demo.jar  (app JAR)
build/runtime/                    (custom runtime)
```

Bạn có thể dùng `jpackage` từ JDK 17+:

```bash
jpackage --type app-image \
         --name LocaleDemo \
         --input build/dist \
         --main-jar localization-demo.jar \
         --main-class com.example.app.ResourceAudit \
         --runtime-image build/runtime \
         --dest build/package
```

Trên Windows PowerShell, dùng lệnh một dòng:

```powershell
jpackage --type app-image --name LocaleDemo --input build/dist --main-jar localization-demo.jar --main-class com.example.app.ResourceAudit --runtime-image build/runtime --dest build/package --win-console
```

`--win-console` là option **chỉ dành cho Windows** để launcher có console phù hợp với ứng dụng dòng lệnh. Trên Linux/macOS, bỏ option này.

| Tham số | Tác dụng |
| --- | --- |
| `--type app-image` | Tạo application image, chưa phải installer .msi/.deb |
| `--name LocaleDemo` | Tên app và launcher |
| `--input build/dist` | Thư mục chứa JAR ứng dụng |
| `--main-jar localization-demo.jar` | Tên JAR **tương đối với input directory** |
| `--main-class com.example.app.ResourceAudit` | Main class của ứng dụng |
| `--runtime-image build/runtime` | Sao chép custom runtime đã tạo |
| `--dest build/package` | Nơi lưu app image |
| `--win-console` | Hiển thị console launcher trên Windows |

**Chú ý:** `jpackage` có thể tự tạo runtime image qua `jlink` nếu không chỉ định `--runtime-image`. Ở đây ta chỉ rõ image sẵn có để kiểm soát module `jdk.localedata` và bộ locale. Không được lấy JAR thiếu `Texts_vi.properties` rồi kỳ vọng `jpackage` tự tìm source resource và sửa lỗi packaging cho bạn.

### Cách chạy app image

Sau khi tạo, app image thường nằm ở `build/package/LocaleDemo` nhưng layout launcher khác theo OS.

Linux (ví dụ):

```bash
build/package/LocaleDemo/bin/LocaleDemo vi
```

Windows PowerShell (ví dụ):

```powershell
.\build\package\LocaleDemo\LocaleDemo.exe vi
```

macOS sử dụng bundle `LocaleDemo.app` với launcher bên trong `Contents/MacOS`; đường dẫn cụ thể phụ thuộc tên/bản đóng gói. Hãy kiểm tra **layout thực tế được công cụ tạo**, không áp một đường dẫn launcher chung cho mọi nền tảng.

`jpackage` tạo image/package **theo platform máy build**, không tự tạo một executable chung chạy đồng nhất trên Windows, Linux và macOS. Cần pipeline build phù hợp cho từng hệ điều hành và kiến trúc CPU.

### Xác minh dữ liệu bản dịch trong app image

App image thường chứa JAR trong thư mục dành cho ứng dụng, và runtime riêng. Bạn cần xác minh:

1. File JAR đã được đóng gói **chính là artifact đã kiểm tra**.
2. JAR vẫn có các entry `com/example/i18n/Texts*.properties`.
3. Runtime image được sao chép vẫn có `java.base` và `jdk.localedata`.
4. Launcher chạy được `en` và `vi`.
5. Dòng `localized-resource=true` và các thông điệp/chữ có dấu đúng.
6. Chương trình chạy được trên máy thử **không có JDK/JRE cài sẵn** (theo OS/architecture tương thích).

Không chỉ dựa vào việc thư mục `LocaleDemo` được sinh thành công để kết luận i18n đã đúng. Test cuối cùng phải gọi launcher thật và kiểm tra **nội dung đầu ra**.

## 12. Hai lớp kiểm tra khi xây pipeline CI

Bộ kiểm tra triển khai nên chia thành hai tầng.

### Tầng A — Artifact integrity: file dịch có được gói đúng?

Đối với JAR truyền thống, các bất biến:

```text
com/example/app/ResourceAudit.class
com/example/i18n/Texts.properties
com/example/i18n/Texts_en.properties
com/example/i18n/Texts_vi.properties
```

Cần xác minh tên entry **chính xác**, không thêm `src/main/resources` hoặc thư mục `build` vào đầu. `jar tf` là công cụ chuẩn để xem các entry.

Nếu app có nhiều JAR/phụ thuộc, tài nguyên có thể nằm trong một JAR riêng. Khi đó phải kiểm tra **runtime classpath** thực sự. Với Spring Boot executable JAR, tài nguyên có thể nằm ở `BOOT-INF/classes/com/example/i18n/...` và được loader của Spring Boot tìm theo layout đặc biệt; đừng áp quy tắc root entry của JAR truyền thống một cách máy móc cho mọi archive layout.

### Tầng B — Runtime behavior: ứng dụng có thực sự bản địa hóa?

Các phép thử trên **chính runtime được phát hành**:

| Kiểm tra | Input | Kết quả cần xác minh |
| --- | --- | --- |
| Main class | `java -jar ... en` | Khởi động thành công |
| English bundle | `en` | `bundle-locale=en`, `greeting=Hello, Lan!` |
| Vietnamese bundle | `vi` | `bundle-locale=vi`, `greeting=Xin chào, Lan!` |
| Root fallback | `en` hoặc `vi` | `fallback=ROOT_OK` |
| Classloader resource path | `en` hoặc `vi` | `root-resource=true` và `localized-resource=true` |
| Number formatting | `en` | `count=Messages: 1,234` theo locale data mong đợi |
| Number formatting | `vi` | `count=Tin nhắn: 1.234` theo locale data mục tiêu |
| Unsupported locale | `fr` | Exit code 2, không bị root fallback ngầm coi là hỗ trợ |
| JAR distribution | Move JAR ra khỏi source tree | App vẫn tìm được bundles |
| Custom runtime | `runtime/bin/java -jar ... vi` | Không vô tình dùng system Java |
| Module inventory | `runtime/bin/java --list-modules` | Các modules cần thiết thực sự hiện diện |
| App image | Launcher `LocaleDemo vi` | Không cần system JDK, thông điệp đúng |
| Encoding | File UTF-8 và stdout | Không mojibake, không lỗi Unicode |

CI có thể dùng script Bash/PowerShell đọc stdout, so sánh một số dòng ổn định, kiểm tra exit code và xác nhận các JAR entries. Tránh khẳng định mọi provider/JDK luôn có cùng dấu phân cách số/ngày nếu không cố định runtime data hoặc policy của ứng dụng.

### Không kiểm tra bằng mỗi tên file

Chỉ có `Texts_vi.properties` trong JAR chưa chứng minh:

- File được **load qua base name** đúng.
- Key `count` tồn tại và parse được bằng `MessageFormat`.
- Văn bản UTF-8 được đọc đúng.
- Runtime có `jdk.localedata`.
- Chữ tiếng Việt hiển thị chính xác qua terminal.
- Key bị thiếu có được phát hiện trước release.
- Nội dung dịch đúng ngữ pháp, ngữ cảnh hoặc bố cục UI.

Do đó bài thực hành cố tình dùng **resource probe + getBundle + getString + MessageFormat + locale formatting** trong cùng chương trình.

## 13. Phân biệt fallback của bundle và fallback của dữ liệu locale

Hai kiểu fallback này dễ bị nhầm.

### 13.1. Fallback của ResourceBundle

Nếu ứng dụng yêu cầu `vi-VN` mà chỉ có:

```text
Texts_vi.properties
Texts.properties
```

`ResourceBundle` có thể chọn `Texts_vi.properties`. Nếu key `only.root` thiếu trong bản `vi`, nó được tìm ở parent bundle root.

Điều đó xảy ra theo **các resource do ứng dụng cung cấp**; nó không cần JDK sở hữu danh sách từ vựng tiếng Việt.

### 13.2. Fallback của JDK locale providers

`NumberFormat` hay `DateTimeFormatter` dựa vào dữ liệu locale của các provider Java. Trong một runtime image đã cắt `jdk.localedata`, dữ liệu format cho một số locale có thể thiếu, dù đối tượng `Locale.forLanguageTag("vi-VN")` vẫn được tạo hợp lệ.

**Không suy ra `bundle.getLocale() == vi` nghĩa là `NumberFormat` có đủ dữ liệu vi-VN.** Cũng không dùng `Locale.getAvailableLocales()` đơn lẻ để chứng minh dữ liệu cụ thể tốt: cần test trực tiếp những API được ứng dụng sử dụng.

### Ví dụ đo đủ module

```bash
build/runtime/bin/java --list-modules
```

Nên bao gồm:

```text
java.base@...
jdk.localedata@...
```

Nhưng `--list-modules` chỉ chứng minh module hiện diện, **không tự kiểm tra bộ lọc `--include-locales`** đã giữ đúng ngôn ngữ/vùng. Vẫn phải chạy `ResourceAudit vi`, in định dạng số và kiểm thử các locale sản phẩm hỗ trợ.

## 14. Encoding trong JAR và runtime image

Tệp `.properties` không trở thành “text đã chuẩn hóa” khi bạn nén vào JAR. Công cụ `jar` chủ yếu đưa các byte tệp vào archive; nó không tự dịch tiếng Việt và không tự sửa file sai charset.

Với Java 17+:

- Property resource bundles mặc định ưu tiên UTF-8 theo JEP 226 (Java 9+).
- Khi file chứa byte không hợp lệ trong UTF-8, có cơ chế fallback ISO-8859-1 (tùy cấu hình).
- `java.util.PropertyResourceBundle.encoding` có thể điều khiển cách đọc của `PropertyResourceBundle`.
- `System.out`/terminal có thể dùng cơ chế encoding khác và cần kiểm tra riêng.

**Một tình huống dễ gây nhầm:**

```text
JAR entry đúng path
    ↓
ResourceBundle load được
    ↓
Chuỗi Java đúng Unicode
    ↓
System.out encode sang console charset
    ↓
Terminal giải mã sai hoặc thiếu font
    ↓
Người dùng thấy chữ lỗi
```

Trong trường hợp đó, sửa classpath không giải quyết lỗi hiển thị. Có thể kiểm tra byte hoặc Unicode code point của chuỗi trước khi in ra terminal. Một kỹ thuật debug tạm thời là in từng code point:

```java
String sample = bundle.getString("greeting");
sample.codePoints().forEach(cp ->
        System.out.printf("U+%04X%n", cp));
```

Đây chỉ là **snippet**, cần biến `bundle` đã có. Nếu code point đúng nhưng terminal sai hình dạng chữ, nguyên nhân có thể nằm ở output encoding hoặc font. Nếu code point đã sai, hãy kiểm tra byte nguồn và pipeline build resource filtering/charset.

Lưu ý JEP 400 (JDK 18: UTF-8 by Default) điều chỉnh default charset của nhiều API, nhưng **không đồng nghĩa** `Properties.load(InputStream)`, `PropertyResourceBundle`, console I/O hay mọi giao thức đều đổi theo cùng một quy tắc. Không gộp JEP 226 và JEP 400 thành một thay đổi.

## 15. Những lỗi thường gặp và cách khắc phục

| Lỗi | Triệu chứng | Cách khắc phục |
| --- | --- | --- |
| Đặt `Texts_vi.properties` sai path trong JAR | `MissingResourceException` hoặc fallback root | Đưa entry vào `com/example/i18n/` tính từ root |
| Đặt file ở `src/main/java` | CLI build bỏ resource | Đưa vào `src/main/resources` |
| Truyền `com/example/i18n/Texts.properties` vào `getBundle` | Không tìm được family | Truyền base name `com.example.i18n.Texts` |
| Dùng `java -jar` nhưng JAR không có Main-Class | No main manifest attribute | Tạo JAR với `--main-class` |
| Chạy class từ thư mục nhưng quên resources trong classpath | Bundle không tìm được | Thêm `src/main/resources` vào classpath hoặc package JAR |
| Dùng `new File("src/main/resources/...")` | IDE chạy, deployment lỗi | Dùng `ResourceBundle`/`getResourceAsStream` |
| Chỉ chạy `jlink` rồi gửi runtime image | Không có ứng dụng để chạy | Phân phối app JAR hoặc dùng `jpackage` |
| Dùng `jlink --add-modules java.base` cho mọi ứng dụng | Thiếu module khác | Xem `jdeps` + test runtime features |
| Không có `jdk.localedata` | Bundle đúng nhưng locale format thiếu | Thêm module và test dữ liệu locale |
| Có `jdk.localedata` nhưng `--include-locales` quá hẹp | Một số locale bị bỏ | Cập nhật bộ lọc và chạy test thực |
| Chỉ kiểm tra `--list-modules` | Không biết JAR có đúng resource không | Thêm `jar tf` và test `getBundle/getString` |
| Chỉ kiểm tra `jar tf` | Không biết runtime có đủ locale không | Chạy JAR bằng runtime image thực tế |
| Lệnh `java` dùng JDK hệ thống | Test runtime image không có giá trị | Gọi `build/runtime/bin/java` tường minh |
| jpackage tạo launcher không có console trên Windows | CLI không thấy output | Thêm `--win-console` cho Windows |
| App image sinh thành công nhưng Việt hóa sai | Bản dịch/locale data vẫn lỗi | Chạy launcher và so sánh nội dung |
| Thay đổi source resources sau build | Artifact vẫn chứa bản cũ | Rebuild JAR và app image |
| Dấu tiếng Việt bị lỗi | Encoding hoặc font terminal | Kiểm tra UTF-8 từng ranh giới |
| Thiếu một key nhưng chương trình vẫn chạy | Root fallback che lỗi bản dịch | Kiểm tra translation coverage theo locale |
| Trùng resource path ở nhiều dependencies | Classloader chọn bản khác | Đặt namespace riêng, kiểm tra runtime classpath |
| JAR chạy trong Java desktop nhưng không ở runtime cắt | Thiếu `java.desktop` hoặc modules khác | Dựa trên dependency thực và test `jlink` |
| Runtime đã cũ sau cập nhật JDK | Lỗ hổng hoặc dữ liệu locale cũ | Rebuild và phân phối lại runtime image |

## 16. Kiểm thử nâng cao: kiểm tra tính đầy đủ của bản dịch

`ResourceBundle.getString` có thể lấy key từ parent bundle. Điều đó giúp fallback, nhưng cũng có thể khiến bản tiếng Việt **không hoàn chỉnh** mà pipeline vẫn báo không lỗi.

Để kiểm tra **chất lượng đóng gói** thay vì chỉ hoạt động tối thiểu, có thể thực hiện:

1. Liệt kê các key bắt buộc từ catalog gốc.
2. Kiểm tra key có mặt trực tiếp trong mỗi file nguồn bản dịch, không chỉ qua parent.
3. Kiểm tra pattern `MessageFormat` parse được ở từng locale.
4. Kiểm tra placeholder của các bản dịch có cùng vai trò và kiểu, cho phép **đổi vị trí**.
5. Chạy các đối số edge case: `0`, `1`, `1234`, tên chứa Unicode, dấu nháy đơn.
6. Kiểm tra số nhiều theo quy tắc ngôn ngữ; `MessageFormat` truyền thống không tự là bộ plural CLDR hoàn chỉnh.
7. Kiểm tra dấu câu, độ dài bản dịch và khả năng hiển thị trong terminal/UI.
8. Chạy test cả từ source layout và từ **JAR/app image thành phẩm**, so sánh behavior.

Đừng dựa vào `ResourceBundle.containsKey(key)` làm bằng chứng bản dịch con có key: phương thức có thể nhìn thấy key kế thừa từ parent. Muốn kiểm tra riêng file, hãy kiểm tra catalog source/archived entry một cách có chủ đích.

### Kiểm thử phiên bản ngôn ngữ thực

Một ứng dụng có thể hỗ trợ `en-US`, `vi-VN`, `ja-JP` nhưng triển khai chỉ bundle en, vi. `ResourceBundle` thường có fallback, vì vậy yêu cầu ja-JP có thể hiển thị English mà không phát sinh lỗi. Danh sách ngôn ngữ được hỗ trợ cần được **quy định riêng**, không suy ra từ việc `getBundle` trả về bundle nào đó.

Cần thêm bài kiểm thử cho tình huống “ngôn ngữ không hỗ trợ” để app hiển thị thông báo rõ hoặc fallback theo chính sách sản phẩm, thay vì âm thầm tuyên bố đã đổi ngôn ngữ.

## 17. Phân phối runtime image và quản lý bảo mật

Custom runtime image là **bản sao runtime được sinh từ một JDK ở thời điểm build**. Nó **không tự cập nhật** khi hệ điều hành cài bản Java mới. Khi có bản vá JDK hoặc dữ liệu locale/timezone thay đổi, bạn phải:

1. Cập nhật JDK dùng để build image.
2. Chạy lại `jlink` trên JDK đã cập nhật.
3. Chạy lại test JAR với runtime mới.
4. Tạo lại `jpackage app-image` hoặc gói phân phối khác.
5. Phát hành lại artifact ứng dụng kèm runtime và ghi nhận phiên bản.

Không copy riêng file `lib/modules` từ image cũ rồi ghép với `bin/java` của bản khác; runtime image là một tập thống nhất, liên quan đến module graph và các thư viện native của cùng JDK/build.

### Tính di động

- JAR Java 17 (chỉ dùng Java SE) thường có thể chạy trên những Java runtime tương thích version ≥17.
- Custom runtime image **phụ thuộc OS/architecture** mà nó được xây và thư viện native của JDK tương ứng; không phải archive “write once, run everywhere” theo cùng nghĩa với một JAR bytecode.
- `jpackage` tạo app image/installer theo OS, cần build pipeline riêng cho Linux, Windows và macOS khi hỗ trợ nhiều nền tảng.
- Không đưa JDK tools `javac`, `jar` vào image rồi mong máy người dùng biên dịch: image tối giản thường chỉ cần runtime để chạy ứng dụng.

Vì vậy một pipeline có thể phát hành **một JAR logic** và **nhiều runtime/app images theo OS**, mỗi bản được thử nghiệm về resource bundle và locale data.

## 18. Bài tập tự luyện

**Bài 1.** Base name là `com.acme.i18n.Labels`, locale `vi-VN`. Nếu chỉ cung cấp file cho tiếng Việt chung, entry JAR đúng là gì?

**Đáp án:** `com/acme/i18n/Labels_vi.properties`. Có thể thêm `Labels_vi_VN.properties` nếu cần ghi đè riêng cho Việt Nam, và `Labels.properties` làm root fallback.

**Bài 2.** `jar tf` thấy `src/main/resources/com/example/i18n/Texts_vi.properties` nhưng Java không tìm thấy. Vì sao?

**Đáp án:** File nằm dưới tiền tố nguồn thay vì classpath root. Java đang tìm `com/example/i18n/Texts_vi.properties` theo base name của app.

**Bài 3.** Runtime image có `java.base` nhưng không `jdk.localedata`. App vẫn load được `Texts_vi.properties` thì có thể khẳng định số/ngày vi-VN được format chính xác không?

**Đáp án:** Không. Bundle chứa chuỗi dịch do app cung cấp; locale data của Java formatter là tầng khác, cần test `NumberFormat`/`DateTimeFormatter` với runtime image đó.

**Bài 4.** Lệnh `jlink --add-modules java.base,jdk.localedata --include-locales=en,vi` có tự chép `localization-demo.jar` vào image?

**Đáp án:** Không. `jlink` tạo runtime module image. App JAR phải được phân phối riêng hoặc kết hợp bằng `jpackage`.

**Bài 5.** Sau khi chạy `jdeps --print-module-deps`, output chỉ có `java.base`. Tại sao vẫn nên bổ sung `jdk.localedata`?

**Đáp án:** `jdeps` chủ yếu phát hiện module dependencies tĩnh từ bytecode; dữ liệu locale bổ sung có thể được sử dụng động qua locale providers và không xuất hiện thành dependency class trực tiếp.

**Bài 6.** `ResourceBundle.getBundle` trả bundle `vi` khi yêu cầu `vi-VN`. Đó có phải lỗi?

**Đáp án:** Không, nếu có `Texts_vi.properties` và không có bản vùng chi tiết. Đây là fallback locale phù hợp. Kiểm tra `getLocale()` để biết candidate thực sự được dùng.

**Bài 7.** Vì sao `jpackage --type app-image` vẫn cần kiểm tra `jar tf`?

**Đáp án:** App image chỉ sao chép/đóng gói các artifact được cung cấp. Nếu JAR thiếu resources, jpackage không tự dựng lại file dịch từ source.

**Bài 8.** Một bản runtime image chạy được trên Windows có thể đưa thẳng sang Linux không?

**Đáp án:** Không. Runtime image chứa binary và thư viện native phụ thuộc OS/CPU; cần tạo image phù hợp cho từng nền tảng.

**Bài 9.** Làm thế nào kiểm tra bạn đang chạy đúng Java trong image?

**Đáp án:** Gọi `build/runtime/bin/java --version`, `--list-modules` và chạy `build/runtime/bin/java -jar ...` với đường dẫn tường minh, thay vì lệnh `java` từ PATH.

**Bài 10.** Nếu màn hình in `Xin chÃ o`, đó có chắc chắn là sai `ResourceBundle` path không?

**Đáp án:** Không. Nếu `getString` và classloader probe thành công, lỗi có thể nằm ở bytes file dịch, build filtering, encoder stdout hoặc decoder của terminal. Cần kiểm tra từng tầng.

## 19. Checklist trước khi phát hành

| Hạng mục | Điều kiện đạt |
| --- | --- |
| Build JAR | Thành công, Main-Class hợp lệ |
| JAR entries | Có toàn bộ `Texts*.properties` dưới đúng `com/example/i18n/` |
| UTF-8 | File nguồn và output không mojibake |
| English locale | Message và số theo cấu hình được duyệt |
| Vietnamese locale | Thông điệp tiếng Việt và số/ngày theo dữ liệu locale mục tiêu |
| Root fallback | Key `only.root` hoạt động |
| Missing keys | Translation coverage được kiểm tra, không chỉ fallback |
| Custom runtime | `--list-modules` hiển thị Java modules cần có |
| Include locales | Bộ lọc có đủ ngôn ngữ/vùng và smoke test thực chứng |
| Runtime selection | Chạy chính `runtime/bin/java`, không phải system Java |
| App packaging | `jpackage` có JAR + runtime + launcher |
| CI | Test en/vi, unsupported locale, move artifact ra khỏi source tree |
| Multiplatform | Image build/test riêng theo OS/architecture |
| Security | Quy trình cập nhật JDK và build lại image được xác định |

## 20. Tổng kết

1. **JAR** phải chứa cả bytecode và file bản dịch đúng **classpath path**. Với base name `com.example.i18n.Texts`, entry `com/example/i18n/Texts_vi.properties` là bắt buộc nếu muốn bản dịch tiếng Việt.
2. **`jlink`** tạo **custom Java runtime image**. Nó không tự mang app JAR, và `--include-locales` cần `jdk.localedata`.
3. **`jpackage`** có thể kết hợp **ứng dụng + runtime + launcher** thành app image; nội dung vẫn phải được kiểm thử.
4. **Bundle resource** khác với **locale data của JDK**. Khi giảm size runtime, phải kiểm tra cả chuỗi dịch lẫn định dạng số/ngày.
5. **`jar tf`, `jdeps`, `--list-modules` và smoke test bằng runtime/launcher thành phẩm** giải quyết các lớp lỗi khác nhau; không công cụ nào thay thế tất cả.
6. Test cần chạy **ngoài IDE/source tree**, trên artifact và hệ điều hành thực tế, kể cả Unicode, fallback, key coverage và charset.
7. Khi cập nhật JDK, hãy **rebuild runtime image** và phát hành lại; runtime image không tự nhận bản vá của Java cài trên máy.

**Tài liệu tham khảo chính thức:**

- [Java SE 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html)
- [Java SE 21 — PropertyResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/PropertyResourceBundle.html)
- [Java SE 21 — jlink](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html)
- [Java SE 21 — jpackage](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jpackage.html)
- [Java SE 21 — jar](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html)
- [Java SE 21 — jdeps](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html)
- [Oracle JDK 21 — Supported Locales and jdk.localedata](https://www.oracle.com/java/technologies/javase/jdk21-supported-locales.html)
- [OpenJDK JEP 226 — UTF-8 Property Resource Bundles](https://openjdk.org/jeps/226)
