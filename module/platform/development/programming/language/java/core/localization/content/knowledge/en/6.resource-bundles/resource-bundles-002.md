# Base name, package và quy tắc đặt tên bundle trong Java `ResourceBundle`

## 1. Từ một tên logic đến một tài nguyên thật

`java.util.ResourceBundle` là cơ chế Java dùng để tìm và đọc các tập tài nguyên theo `Locale`, thường là chuỗi giao diện, nhãn, thông báo lỗi hoặc các giá trị văn bản cần bản địa hóa.

Một bộ tài nguyên có thể có các tệp:

```text
com/example/i18n/Messages.properties
com/example/i18n/Messages_vi.properties
com/example/i18n/Messages_vi_VN.properties
com/example/i18n/Messages_en.properties
```

Trong mã Java:

```java
ResourceBundle bundle = ResourceBundle.getBundle(
        "com.example.i18n.Messages",
        Locale.forLanguageTag("vi-VN"));
String greeting = bundle.getString("hello");
```

Chuỗi `"com.example.i18n.Messages"` là **base name (tên cơ sở)** của cả họ bundle; nó **không bao gồm** hậu tố locale và **không bao gồm** `.properties`. Java dùng base name cùng locale để tạo danh sách tên bundle ứng viên, tìm tài nguyên tương ứng rồi trả về bundle đã chọn.

Một tệp được đặt đúng tên nhưng sai vị trí trong classpath, hoặc được đóng gói vào JAR sai đường dẫn, vẫn không được tìm thấy. Vì vậy phải hiểu đồng thời **base name**, **package**, **đường dẫn runtime** và **quy tắc hậu tố locale**.

## 2. Base name là gì?

**Base name** là phần định danh chung để Java tra cứu các bản ngôn ngữ của cùng một tập tài nguyên:

- `Messages`: tên cơ sở ngắn, dùng khi các bundle ở gốc classpath.
- `com.example.i18n.Messages`: tên cơ sở **fully qualified**, dùng khi các bundle thuộc package logic `com.example.i18n`.

Từ tên cơ sở `com.example.i18n.Messages`, các tên ứng viên có thể là:

```text
com.example.i18n.Messages_vi_VN
com.example.i18n.Messages_vi
com.example.i18n.Messages
```

Với bundle kiểu `.properties`, Java ánh xạ dấu chấm trong phần định danh package thành dấu `/` của đường dẫn tài nguyên:

```text
com.example.i18n.Messages_vi_VN
                 ↓
com/example/i18n/Messages_vi_VN.properties
```

**Quy tắc quan trọng:**

1. Truyền **base name**, ví dụ `com.example.i18n.Messages`, cho `getBundle`. Không truyền tên tệp có phần mở rộng như `Messages_vi_VN.properties`.
2. Không nhúng locale cố định vào base name. Nếu truyền `com.example.i18n.Messages_vi` làm base name, Java sẽ coi `_vi` là phần của tên cơ sở và tiếp tục tạo các ứng viên khác từ đó.
3. Chọn tên rõ chức năng: `Messages`, `ValidationMessages`, `Labels`. Các họ bundle có base name khác nhau được tìm độc lập.
4. Dấu chấm trong base name biểu diễn package; dấu gạch dưới phân tách các thành phần locale trong tên bundle. Dấu gạch nối `-` được dùng trong **BCP 47 language tag**, không phải dấu phân cách thông thường của tên tệp bundle.

So sánh:

| Giá trị / vị trí | Ví dụ | Mục đích |
| --- | --- | --- |
| Base name truyền cho API | `com.example.i18n.Messages` | Chỉ họ bundle cần tìm |
| Thẻ ngôn ngữ | `vi-VN` | Biểu diễn locale theo BCP 47 |
| Tên bundle ứng viên | `com.example.i18n.Messages_vi_VN` | Kết hợp base name với locale |
| Tệp resource | `com/example/i18n/Messages_vi_VN.properties` | Tài nguyên thật được nạp |
| Khóa trong bundle | `hello` | Lấy giá trị qua `getString("hello")` |

## 3. Package và thư mục: vì sao phải khớp chính xác?

Một class Java có khai báo:

```java
package com.example.i18n;
```

thường được lưu tại thư mục nguồn tương ứng. Nhưng tệp `.properties` là **tài nguyên runtime**, được tìm qua classloader hoặc hệ thống module, không phải được Java tự suy đoán theo thư mục của tệp `.java` đang gọi nó.

Ví dụ dự án Gradle/Maven dùng quy ước thư mục phổ biến:

```text
project/
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/i18n/BundleNamingDemo.java
│   │   └── resources/
│   │       └── com/example/i18n/
│   │           ├── Messages.properties
│   │           ├── Messages_vi.properties
│   │           └── Messages_vi_VN.properties
```

Khi build đúng cấu hình, resource được sao chép vào runtime classpath, ví dụ:

```text
build/classes/java/main/com/example/i18n/BundleNamingDemo.class
build/resources/main/com/example/i18n/Messages.properties
build/resources/main/com/example/i18n/Messages_vi.properties
build/resources/main/com/example/i18n/Messages_vi_VN.properties
```

Khi các thư mục runtime đó nằm trên classpath, base name `com.example.i18n.Messages` dẫn tới đúng các tài nguyên.

**Đừng nhầm:** `src/main/resources` là **thư mục nguồn khi build**, không phải một phần của base name. Nếu truyền `"src.main.resources.com.example.i18n.Messages"`, Java sẽ tìm đường dẫn khác và thường không thấy bundle.

Nếu đang chạy bằng `java -cp ...` mà không dùng Gradle/Maven, bạn phải tự bảo đảm các tệp `.properties` nằm trong một **classpath root** ở đúng đường dẫn package. Chỉ đặt resource bên cạnh tệp nguồn `.java` không đủ nếu thư mục đó không được đưa vào runtime classpath.

### Package của class gọi không tự xác định base name

Giả sử class `com.example.app.Main` gọi:

```java
ResourceBundle.getBundle("Messages", locale);
```

Java tìm họ `Messages` ở **gốc** đường dẫn tài nguyên tương ứng; nó không tự đổi thành `com.example.app.Messages`. Muốn bundle nằm trong `com/example/app`, hãy dùng `"com.example.app.Messages"`.

Đó là lý do tên cơ sở fully qualified thường an toàn và dễ bảo trì hơn trong dự án nhiều package.

## 4. Quy tắc đặt tên tệp `.properties` theo `Locale`

Hình thức thường gặp:

```text
<BaseName>.properties
<BaseName>_<language>.properties
<BaseName>_<language>_<COUNTRY>.properties
<BaseName>_<language>_<COUNTRY>_<VARIANT>.properties
```

Đối với locale có **script**, Java còn có các dạng ứng viên chứa script, ví dụ `Messages_zh_Hant_TW.properties`.

Các ví dụ:

| Locale được yêu cầu | Tên tệp điển hình | Ý nghĩa |
| --- | --- | --- |
| `Locale.ROOT` | `Messages.properties` | Bundle gốc, không gắn ngôn ngữ/vùng |
| `Locale.forLanguageTag("vi")` | `Messages_vi.properties` | Tiếng Việt chung |
| `Locale.forLanguageTag("vi-VN")` | `Messages_vi_VN.properties` | Tiếng Việt, vùng Việt Nam |
| `Locale.forLanguageTag("en-US")` | `Messages_en_US.properties` | Tiếng Anh, vùng Hoa Kỳ |
| `Locale.forLanguageTag("en-GB")` | `Messages_en_GB.properties` | Tiếng Anh, vùng Anh |
| `Locale.forLanguageTag("zh-Hant-TW")` | `Messages_zh_Hant_TW.properties` | Tiếng Hoa, chữ phồn thể, vùng Đài Loan |

Với locale có script/variant, `ResourceBundle.Control.getCandidateLocales` xác định các ứng viên cụ thể theo thuật toán Java; không nên tự ghép mọi thành phần theo một mẫu đơn giản. Chẳng hạn với `zh-Hant-TW`, danh sách có thể gồm các ứng viên có hoặc không có script/region trước khi đến bundle gốc.

**Quy ước cần nhớ:**

- Trong **language tag**, thường viết `vi-VN`, `zh-Hant-TW` với dấu gạch nối.
- Trong **hậu tố tên bundle**, dùng dấu gạch dưới, như `_vi_VN`, `_zh_Hant_TW`.
- Language thường chữ thường (`vi`, `en`), region thường chữ hoa (`VN`, `US`), script thường dạng title case (`Hant`, `Latn`). Trên hệ thống tệp phân biệt hoa/thường, `Messages_vi_VN.properties` và `messages_vi_vn.properties` có thể là hai đường dẫn khác nhau.
- Không tự đổi tên tệp theo chuỗi `locale.toLanguageTag()` rồi ghép trực tiếp vào filename. Tên ứng viên của `ResourceBundle` được tạo từ các thành phần của `Locale` theo quy tắc riêng.
- Tệp có phần mở rộng `.properties` (không phải `.property`, `.yml`, `.txt`), trừ khi bạn chủ động triển khai cơ chế bundle tùy biến.

## 5. Java tìm bundle theo thứ tự nào?

Với:

```java
ResourceBundle.getBundle("com.example.i18n.Messages",
        Locale.forLanguageTag("vi-VN"));
```

và các bundle cơ bản, Java thường xem xét các ứng viên theo mức độ cụ thể giảm dần:

```text
Messages_vi_VN
      ↓
Messages_vi
      ↓
Messages  (ROOT)
```

**Đây là sơ đồ giản lược cho locale chỉ có language và region.** Thuật toán chuẩn còn có thể bao gồm script, variant, thứ tự ưu tiên của dạng class/properties và một vòng xem xét default locale của JVM. Vì vậy không phải mọi lời gọi đều luôn theo đúng ba bước trên.

Có hai mức fallback cần phân biệt:

1. **Chọn bundle phù hợp:** nếu không có `Messages_vi_VN.properties` nhưng có `Messages_vi.properties`, `getBundle` có thể chọn bundle cấp `vi`.
2. **Tìm khóa qua parent bundle:** nếu bundle `vi_VN` tồn tại nhưng không chứa khóa `thanks`, `getString("thanks")` có thể lấy từ bundle cha `vi` hoặc gốc. Khi đó `bundle.getLocale()` vẫn mô tả **bundle được chọn**, không phải locale của từng giá trị khóa đã lấy.

Nếu không có bundle nào khả dụng trong cơ chế tìm kiếm, `getBundle` ném `MissingResourceException`. Nếu bundle đã tìm được nhưng khóa không tồn tại trong chuỗi tra cứu của bundle đó, `getString` cũng có thể ném `MissingResourceException`.

### Bundle gốc và default locale không giống nhau

`Messages.properties` là tài nguyên **gốc (`Locale.ROOT`)** của một họ bundle. Nó không có nghĩa là “bản dịch của locale mặc định JVM”. Trong khi đó, `Locale.getDefault()` là một thiết lập môi trường có thể ảnh hưởng vòng fallback khi dùng overload `getBundle` mặc định.

Để quan sát rõ việc chọn các ứng viên theo locale mà **không thử fallback sang default locale JVM**, ví dụ bên dưới dùng `ResourceBundle.Control.getNoFallbackControl(ResourceBundle.Control.FORMAT_PROPERTIES)`. Chế độ “no fallback” này **không loại bỏ bundle gốc**; nó chỉ bỏ qua một nhánh fallback sang default locale trong thuật toán.

## 6. Ví dụ hoàn chỉnh Java 17+: đặt đúng tên, đúng package, đọc đúng bundle

Ví dụ sau độc lập, không cần thư viện bên ngoài. Nó dùng **classpath** (unnamed module) và cố định cơ chế chọn file properties để kết quả không bị thay đổi bởi default locale JVM.

Tạo đúng cấu trúc:

```text
workspace/
├── src/
│   └── com/example/i18n/BundleNamingDemo.java
└── com/
    └── example/i18n/
        ├── Messages.properties
        ├── Messages_vi.properties
        └── Messages_vi_VN.properties
```

**Tệp `com/example/i18n/Messages.properties`** — bundle gốc:

```properties
hello=Hello (default)
thanks=Thank you
```

**Tệp `com/example/i18n/Messages_vi.properties`** — tiếng Việt chung:

```properties
hello=Xin chào
thanks=Cảm ơn
```

**Tệp `com/example/i18n/Messages_vi_VN.properties`** — bản địa hóa cho Việt Nam:

```properties
hello=Xin chào Việt Nam
```

**Tệp `src/com/example/i18n/BundleNamingDemo.java`:**

```java
package com.example.i18n;

import java.util.Locale;
import java.util.ResourceBundle;

public class BundleNamingDemo {
    private static final String BASE_NAME = "com.example.i18n.Messages";

    private static final ResourceBundle.Control CONTROL =
            ResourceBundle.Control.getNoFallbackControl(
                    ResourceBundle.Control.FORMAT_PROPERTIES);

    public static void main(String[] args) {
        show("vi-VN");
        show("vi-AU");
        show("ja-JP");
    }

    private static void show(String tag) {
        Locale requested = Locale.forLanguageTag(tag);
        ResourceBundle bundle = ResourceBundle.getBundle(
                BASE_NAME, requested, CONTROL);

        System.out.printf(
                "requested=%s, loaded=%s, hello=%s, thanks=%s%n",
                requested.toLanguageTag(),
                bundle.getLocale().toLanguageTag(),
                bundle.getString("hello"),
                bundle.getString("thanks"));
    }
}
```

Từ thư mục `workspace`, biên dịch và chạy:

```bash
javac -encoding UTF-8 -d . src/com/example/i18n/BundleNamingDemo.java
java -cp . com.example.i18n.BundleNamingDemo
```

Kết quả chính xác với ba tệp properties trên và JDK 17+:

```text
requested=vi-VN, loaded=vi-VN, hello=Xin chào Việt Nam, thanks=Cảm ơn
requested=vi-AU, loaded=vi, hello=Xin chào, thanks=Cảm ơn
requested=ja-JP, loaded=und, hello=Hello (default), thanks=Thank you
```

**Giải thích từng ca:**

- `vi-VN`: có `Messages_vi_VN.properties`, nên bundle được chọn là `vi-VN`. Khóa `hello` lấy từ bundle này; khóa `thanks` không có tại `vi-VN` nên tra tiếp parent `vi`, nhận `Cảm ơn`.
- `vi-AU`: không có bundle `vi_AU`, nhưng có `Messages_vi.properties`; cả hai khóa lấy từ bundle `vi`. `getLocale()` trả `vi`.
- `ja-JP`: không có bundle Nhật tương ứng, nên dùng `Messages.properties` gốc. `Locale.ROOT.toLanguageTag()` trả `und` (*undetermined*), vì vậy chuỗi `loaded=und` là đúng.

Ví dụ không phụ thuộc locale mặc định của máy vì đã vô hiệu hóa fallback sang default locale. Lưu ý `getNoFallbackControl` là một cách dùng `ResourceBundle.Control` cho môi trường classpath; với **named modules** có những hạn chế khác, xem phần 8.

**Điểm học được:** base name trong code phải khớp chính xác đường dẫn `com/example/i18n/Messages...`, nhưng tên bundle được chọn có thể khác locale yêu cầu. Ngoài ra, một khóa riêng lẻ có thể đến từ **parent** thay vì tệp của bundle đang được chọn.

## 7. Bundle dưới dạng Java class và thứ tự ưu tiên định dạng

`ResourceBundle` không chỉ đọc `.properties`. Nó còn hỗ trợ bundle là **class** (chẳng hạn class kế thừa `ListResourceBundle`) với tên ứng viên tương ứng.

Ví dụ định nghĩa class **`com.example.i18n.Messages_en`**:

```java
package com.example.i18n;

import java.util.ListResourceBundle;

public class Messages_en extends ListResourceBundle {
    @Override
    protected Object[][] getContents() {
        return new Object[][] {
                {"hello", "Hello"},
                {"thanks", "Thanks"}
        };
    }
}
```

Đây là một **thành phần** trong ứng dụng đã có lời gọi `ResourceBundle.getBundle("com.example.i18n.Messages", locale)`; nếu muốn chạy như một chương trình độc lập, vẫn cần class có `main` và đặt/biên dịch class trong đúng package.

Với cơ chế mặc định trên classpath, Java có thể tìm cả bundle kiểu class và `.properties`. Nếu cả class và tệp properties cùng đại diện cho **một tên ứng viên**, class thường được ưu tiên theo thứ tự định dạng mặc định. Dùng `ResourceBundle.Control.FORMAT_PROPERTIES` khi chủ đích chỉ tìm properties, hoặc `FORMAT_CLASS` khi chỉ dùng class; ví dụ hoàn chỉnh phần 6 cố ý chỉ chọn properties.

**Không nhầm `Messages_en.java` với resource `Messages_en.properties`:** tệp Java phải được biên dịch thành `Messages_en.class` trong package thích hợp, trong khi properties được nạp như tài nguyên. Cả hai có thể chia sẻ base name nhưng có cơ chế đóng gói khác nhau.

## 8. Classpath, JAR và named modules

### 8.1. Khi chạy bằng classpath

Với một chương trình không dùng named module, `getBundle` cần tìm được tài nguyên/class qua classloader thích hợp. Những phần sau đều phải nhất quán:

- Base name: `com.example.i18n.Messages`.
- Thư mục runtime: `com/example/i18n/`.
- Filename: `Messages_vi_VN.properties`.
- Classpath: thư mục hoặc JAR chứa đường dẫn đó phải được chỉ định khi chạy.

Trong JAR, mục tài nguyên cần có tên như:

```text
com/example/i18n/Messages.properties
com/example/i18n/Messages_vi.properties
com/example/i18n/Messages_vi_VN.properties
```

Bạn có thể kiểm tra nội dung JAR bằng:

```bash
jar tf my-application.jar
```

Nếu không thấy những mục tài nguyên này (hoặc thấy chúng bị đặt thừa `src/main/resources/` ở đầu đường dẫn), cần sửa cấu hình đóng gói hoặc vị trí nguồn; đổi chuỗi base name một cách tùy tiện không giải quyết nguyên nhân.

Trong dự án Gradle/Maven, hãy sử dụng thư mục nguồn tài nguyên chuẩn hoặc cấu hình resource root rõ ràng. Đừng giả định thư mục `resources` được Java tìm tự động khi trực tiếp chạy `java` mà chưa được đưa vào classpath.

### 8.2. Khi dùng Java Platform Module System (JPMS)

Với **named module**, việc tìm resource còn phụ thuộc ranh giới module, vị trí bundle, cách sử dụng các overload của `ResourceBundle.getBundle` và khả năng truy cập package. Không nên sao chép máy móc ví dụ `getBundle(baseName, locale, control)` chạy trên classpath vào named module; các overload sử dụng `ResourceBundle.Control` có hạn chế và có thể ném `UnsupportedOperationException` trong bối cảnh named module.

Trong named module, ưu tiên API/module-aware phù hợp như `ResourceBundle.getBundle(baseName, locale)` theo ngữ cảnh người gọi hoặc overload nhận `Module`, và thiết lập khả năng truy cập resource package khi cần theo quy tắc module. Nếu chọn triển khai `ResourceBundleProvider`, phải làm theo hợp đồng service/provider tương ứng. Kiểm thử **trên module path thực tế**, không chỉ trong chế độ classpath, vì hai môi trường có thể nạp tài nguyên khác nhau.

Phần này là lưu ý về nơi tài nguyên được tìm; bản chất của base name và nguyên tắc đặt tên bundle vẫn giữ nguyên.

## 9. Những lỗi phổ biến và cách chẩn đoán

| Dấu hiệu | Nguyên nhân thường gặp | Cách kiểm tra hoặc sửa |
| --- | --- | --- |
| `MissingResourceException: Can't find bundle for base name ...` | Sai base name hoặc thiếu bundle ứng viên trong runtime | Kiểm tra package, classpath/JAR và bundle gốc |
| Có tệp `Messages_vi_VN.properties` nhưng không được dùng | Đặt sai thư mục, sai chữ hoa/thường, không được đóng gói hoặc base name sai | Đối chiếu `com/example/i18n/` với base name và `jar tf` |
| Truyền `Messages_vi_VN.properties` vào `getBundle` | Đã truyền tên tệp thay vì base name | Truyền `com.example.i18n.Messages` và locale riêng |
| Đặt `Messages_vi-VN.properties` | Nhầm dấu `-` của BCP 47 với `_` của bundle filename | Đặt `Messages_vi_VN.properties` |
| `getBundle("Messages", locale)` tìm không ra file trong package | Base name thiếu package | Dùng tên fully qualified |
| Có bundle `vi_VN` nhưng một số khóa vẫn bằng tiếng Anh | Thiếu khóa trong child, lấy từ parent/gốc | Kiểm tra độ phủ khóa trên từng bundle |
| Ứng dụng dùng sai ngôn ngữ khi thiếu bản dịch | Default locale JVM có thể tham gia fallback | Định nghĩa chính sách fallback rõ, kiểm thử `bundle.getLocale()` |
| Sửa properties nhưng kết quả chưa đổi | Tệp trong JAR chưa được đóng gói lại hoặc bundle đang cache | Kiểm tra artifact/runtime và vòng đời cache, triển khai lại khi cần |
| Tài nguyên chạy trên classpath nhưng lỗi trên module path | Quy tắc truy cập resource khác nhau | Kiểm tra module, overload và khả năng truy cập package |
| Dấu tiếng Việt hiển thị sai | Encoding của tài nguyên hoặc pipeline đóng gói không nhất quán | Lưu tệp UTF-8, kiểm tra encoding và runtime/JDK |

### Lưu ý thêm về encoding và cache

- Trên **Java 9+**, `PropertyResourceBundle` mặc định đọc `.properties` theo UTF-8, có cơ chế tương thích với tệp được mã hóa theo kiểu cũ. Với Java 17+, ví dụ tiếng Việt có dấu trong phần 6 là phù hợp. Cần bảo đảm IDE, hệ thống build và công cụ dịch dùng encoding nhất quán.
- `ResourceBundle` có **cơ chế cache**. Cập nhật tệp trên đĩa hay trong một JAR đã đóng gói không bảo đảm mọi lời gọi đang chạy sẽ thấy ngay nội dung mới. Nếu yêu cầu hot reload, cần thiết kế vòng đời cache, cập nhật tài nguyên và cơ chế nạp riêng.
- Tên file, key và giá trị có vai trò khác nhau: đổi tên bundle sai có thể khiến **không tìm được cả bundle**; thiếu một key có thể khiến Java **tìm về parent** hoặc ném lỗi khi khóa không có ở đâu cả.

## 10. Danh sách kiểm tra khi bổ sung một ngôn ngữ mới

1. Xác định **base name** đang dùng ở mã và vị trí resource root runtime.
2. Tạo tệp theo hậu tố locale chuẩn, ví dụ thêm `Messages_en_GB.properties` cho `en-GB`.
3. Đặt tệp trong cùng đường dẫn package của họ bundle, ví dụ `com/example/i18n/`; không tạo thêm thư mục mang tên locale khi API mong chờ hậu tố tên file.
4. Kiểm tra các khóa quan trọng có bản dịch, không phụ thuộc vô ý vào giá trị mặc định.
5. Build và kiểm tra artifact thực tế (thư mục runtime hoặc nội dung JAR).
6. Gọi `getBundle` với locale đích, quan sát `bundle.getLocale()`, kiểm tra nội dung từng key quan trọng và fallback.
7. Thử thêm locale có cùng ngôn ngữ nhưng khác vùng, một locale không có bundle, và trường hợp thiếu khóa.
8. Nếu ứng dụng chạy như named module, kiểm thử đường nạp tài nguyên theo JPMS.
9. Ghi nhận quy tắc fallback, locale mặc định và cơ chế cache để tránh các khác biệt giữa máy phát triển và môi trường triển khai.

## 11. Ghi nhớ

- **Base name** là tên logic chung của một họ bundle, ví dụ `com.example.i18n.Messages`; không thêm `.properties` hay hậu tố ngôn ngữ khi gọi `getBundle`.
- **Package** trong base name tương ứng với **đường dẫn tài nguyên runtime**: `com.example.i18n.Messages` → `com/example/i18n/Messages*.properties`.
- **Hậu tố locale của bundle dùng dấu gạch dưới** như `_vi`, `_vi_VN`, `_zh_Hant_TW`, trong khi language tag BCP 47 dùng dấu gạch nối như `vi-VN`.
- **Tên bundle được chọn và nguồn của từng khóa có thể khác nhau** vì fallback và parent bundle; hãy quan sát `bundle.getLocale()` và kiểm thử độ phủ khóa.
- **Classpath, nội dung JAR và named module** quyết định tài nguyên có thực sự truy cập được. Đặt tên đúng mới là một nửa công việc; phải đóng gói và chạy đúng môi trường.
