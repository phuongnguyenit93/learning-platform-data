# Đặt tên tệp META-INF/services theo tên nhị phân của kiểu dịch vụ

## 1. Vì sao tên tệp quyết định ServiceLoader có tìm được plugin?

Khi triển khai **Java SPI trên classpath**, lớp cung cấp dịch vụ (provider) không tự được đăng ký chỉ vì nó đã viết `implements` một giao diện. Với cơ chế đăng ký bằng tệp của `java.util.ServiceLoader`, provider phải được khai báo trong một **tệp tài nguyên (provider-configuration file)** tại đúng đường dẫn:

```text
META-INF/services/<tên-nhị-phân-đầy-đủ-của-kiểu-dịch-vụ>
```

Phần sau `META-INF/services/` là **tên nhị phân đầy đủ (fully qualified binary name)** của **kiểu dịch vụ** mà host yêu cầu, thường là một `interface` hoặc lớp trừu tượng. Nó không phải tên lớp provider, không phải tên module, không phải tên JAR và không có hậu tố `.java`, `.class` hoặc `.txt`.

Ví dụ, nếu host gọi:

```java
ServiceLoader.load(com.example.spi.TextFormatter.class);
```

thì một provider được đăng ký trên classpath có thể được tìm qua tài nguyên mang tên chính xác:

```text
META-INF/services/com.example.spi.TextFormatter
```

Vì sao? `ServiceLoader` phải biết **đang tìm provider cho dịch vụ nào** trước khi biết các lớp triển khai. Tên tệp là khóa tìm kiếm; **các dòng bên trong tệp** mới liệt kê tên các lớp provider cần tải. Đặt tên sai có thể khiến hệ thống tìm thấy **0 provider** dù JAR và lớp triển khai có mặt.

## 2. Tên nhị phân khác tên dùng trong mã Java như thế nào?

Với kiểu top-level, tên nhị phân thường trùng với tên đầy đủ quen thuộc `package.TypeName`. Nhưng với **kiểu thành viên lồng nhau (nested member type)**, tên nhị phân dùng dấu `$` để nối lớp bao ngoài và kiểu bên trong; cách viết trong mã nguồn Java dùng dấu `.`.

| Khai báo/kiểu nhìn thấy trong mã Java | Tên nhị phân mà JVM nhận diện | Tên tệp cần đặt dưới `META-INF/services/` |
|---|---|---|
| `com.example.spi.TextFormatter` (top-level) | `com.example.spi.TextFormatter` | `com.example.spi.TextFormatter` |
| `com.example.spi.Contracts.Formatter` (kiểu lồng trong `Contracts`) | `com.example.spi.Contracts$Formatter` | `com.example.spi.Contracts$Formatter` |
| `com.example.spi.Outer.Middle.Processor` (lồng nhiều cấp) | `com.example.spi.Outer$Middle$Processor` | `com.example.spi.Outer$Middle$Processor` |

**Quy tắc chính xác:** lấy `serviceType.getName()` hoặc `YourService.class.getName()` để có tên dùng cho tệp đăng ký. Trong trường hợp service type là kiểu tham chiếu thông thường, `Class.getName()` trả về tên nhị phân; không tự thay tất cả dấu chấm thành dấu `$`. **Dấu chấm giữa các thành phần package vẫn giữ nguyên**; chỉ dấu phân cách giữa các cấp kiểu lồng nhau trở thành `$`.

Ví dụ:

```java
// Kiểu lồng: trong mã nguồn viết Contracts.Formatter
System.out.println(Contracts.Formatter.class.getName());
// com.example.spi.Contracts$Formatter

System.out.println(Contracts.Formatter.class.getCanonicalName());
// com.example.spi.Contracts.Formatter
```

Đoạn trên chỉ minh họa hai phương thức và giả sử `Contracts` là lớp trong package `com.example.spi` đã được khai báo. Đây **không phải chương trình độc lập**; phần tiếp theo có ví dụ chạy đầy đủ.

**Không dùng `getCanonicalName()` làm tên tệp** khi hợp đồng là kiểu lồng nhau. Tên canonical thuận tiện cho cách viết Java, nhưng không khớp tên tài nguyên mà SPI trên classpath tra cứu. Với local/anonymous class, tên JVM còn có thành phần sinh tự động; chúng không phù hợp làm service contract công khai, ổn định.

## 3. Tên tệp và nội dung tệp đảm nhận hai vai trò khác nhau

Giả sử:

- Kiểu dịch vụ: `com.example.spi.Contracts.Transformer`.
- Tên nhị phân dịch vụ: `com.example.spi.Contracts$Transformer`.
- Lớp triển khai: `com.example.plugin.UpperTransformer`.

Vị trí và nội dung tệp đăng ký:

```text
ĐƯỜNG DẪN TÀI NGUYÊN TRONG JAR:
META-INF/services/com.example.spi.Contracts$Transformer

NỘI DUNG TỆP (một dòng):
com.example.plugin.UpperTransformer
```

Dòng đầu mô tả **tên/path của tệp**, dòng thứ hai mô tả **nội dung thật**. Không chép cả khối minh họa này vào tệp. Tệp chỉ cần chứa tên lớp provider.

Một tệp dịch vụ có thể đăng ký **nhiều provider** bằng cách ghi mỗi tên nhị phân đầy đủ trên một dòng:

```text
# Các provider của cùng một kiểu dịch vụ
com.example.plugin.UpperTransformer
com.example.plugin.LowerTransformer
```

Tên `LowerTransformer` ở đây chỉ minh họa provider thứ hai và cần lớp triển khai thật khi sử dụng. Nếu ứng dụng có **hai service type khác nhau**, mỗi service type cần tệp đăng ký riêng mang tên nhị phân tương ứng.

Theo đặc tả của `ServiceLoader` trên classpath:

- Tệp phải là văn bản **UTF-8**; để tránh vấn đề ký tự đầu tệp, nên lưu **UTF-8 không BOM**.
- Dòng trống và khoảng trắng/tab ở đầu, cuối tên provider được bỏ qua.
- Từ dấu `#` đầu tiên tới hết dòng được xem là chú thích.
- Các tên provider trùng lặp bị bỏ qua.
- Tên provider cũng phải là **tên nhị phân đầy đủ** của lớp cung cấp dịch vụ. Với ví dụ này, provider là lớp top-level nên tên có dấu chấm thông thường.
- Tệp đăng ký và lớp provider **không bắt buộc cùng một JAR**, nhưng cả hai phải được classloader tương ứng nhìn thấy; không nên giả định một tệp ở chỗ bất kỳ trên ổ đĩa đều được quét.

Lưu ý rằng tên tệp sử dụng các **dấu chấm trong package**, ví dụ `com.example.spi.Contracts$Transformer`. Đừng đổi thành cấu trúc thư mục `com/example/spi/Contracts$Transformer` dưới `META-INF/services`: đó sẽ là một **đường dẫn tài nguyên khác**.

## 4. Ví dụ Java 17+ đầy đủ: kiểu dịch vụ lồng nhau

Ví dụ cố tình dùng service là kiểu lồng nhau để chứng minh tại sao tên tệp phải có `$`. Host và plugin dùng cùng thư viện hợp đồng, biên dịch riêng, rồi được kết nối bằng `ServiceLoader` khi chạy.

### 4.1. Cấu trúc dự án

```text
spi-demo/
├── api/
│   └── src/com/example/spi/Contracts.java
├── host/
│   └── src/com/example/host/Main.java
└── plugin/
    ├── src/com/example/plugin/UpperTransformer.java
    └── resources/
        └── META-INF/
            └── services/
                └── com.example.spi.Contracts$Transformer
```

Tệp dưới `services/` **không có đuôi mở rộng**. Ký tự `$` là một phần tên tệp thật, không phải dấu hiệu thay thế.

### 4.2. Hợp đồng — `api/src/com/example/spi/Contracts.java`

```java
package com.example.spi;

public final class Contracts {
    private Contracts() {
    }

    public interface Transformer {
        String transform(String input);
    }
}
```

`Transformer` là giao diện thành viên `public`; giao diện thành viên trong Java mặc nhiên là `static`. Vì vậy lớp host có thể dùng `Contracts.Transformer.class`, còn tên nhị phân là `com.example.spi.Contracts$Transformer`.

### 4.3. Provider — `plugin/src/com/example/plugin/UpperTransformer.java`

```java
package com.example.plugin;

import com.example.spi.Contracts.Transformer;
import java.util.Locale;

public final class UpperTransformer implements Transformer {
    public UpperTransformer() {
    }

    @Override
    public String transform(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
```

Provider là lớp `public`, triển khai đúng kiểu dịch vụ và có constructor `public` không tham số. Đó là các điều kiện phù hợp với cách `ServiceLoader` khởi tạo provider nằm trên classpath. Ví dụ giả định `input` không phải `null`; hợp đồng thực tế cần quy định rõ trường hợp này.

### 4.4. Tệp đăng ký — `plugin/resources/META-INF/services/com.example.spi.Contracts$Transformer`

Nội dung **toàn bộ tệp**:

```text
com.example.plugin.UpperTransformer
```

Tên tệp phải lấy từ `Contracts.Transformer.class.getName()`, không lấy từ tên provider. Đặc biệt, **không** lưu thành `com.example.spi.Contracts.Transformer`, vì tên đó là tên canonical, sai quy tắc cho service lồng nhau.

### 4.5. Host — `host/src/com/example/host/Main.java`

```java
package com.example.host;

import com.example.spi.Contracts.Transformer;
import java.util.ServiceLoader;

public final class Main {
    public static void main(String[] args) {
        Class<Transformer> type = Transformer.class;
        String resourceName = "META-INF/services/" + type.getName();

        System.out.println("binary=" + type.getName());
        System.out.println("canonical=" + type.getCanonicalName());
        System.out.println("resource=" + resourceName);

        int providers = 0;
        for (Transformer transformer : ServiceLoader.load(type)) {
            System.out.println("result=" + transformer.transform("Java SPI"));
            providers++;
        }
        System.out.println("providers=" + providers);
    }
}
```

Host chỉ biết kiểu dịch vụ `Transformer`, không phải lớp `UpperTransformer`. In cả tên binary và canonical là cách kiểm tra trực tiếp tên tệp cần đặt.

### 4.6. Biên dịch, đóng gói, chạy

Từ thư mục `spi-demo`, với **PowerShell trên Windows** và **JDK 17+**:

```powershell
New-Item -ItemType Directory -Force -Path out\api,out\host,out\plugin | Out-Null

javac -d out\api api\src\com\example\spi\Contracts.java
javac -cp out\api -d out\plugin plugin\src\com\example\plugin\UpperTransformer.java
javac -cp out\api -d out\host host\src\com\example\host\Main.java

Copy-Item -Path plugin\resources\META-INF -Destination out\plugin -Recurse
jar --create --file out\plugin.jar -C out\plugin .

jar --list --file out\plugin.jar |
    Select-String -SimpleMatch 'META-INF/services/com.example.spi.Contracts$Transformer'

java -cp "out\api;out\host;out\plugin.jar" com.example.host.Main
```

Lệnh `jar --list` lọc ra đúng dòng:

```text
META-INF/services/com.example.spi.Contracts$Transformer
```

Chương trình in:

```text
binary=com.example.spi.Contracts$Transformer
canonical=com.example.spi.Contracts.Transformer
resource=META-INF/services/com.example.spi.Contracts$Transformer
result=JAVA SPI
providers=1
```

Trên macOS/Linux, thay `;` trong classpath bằng `:` và dùng lệnh tạo thư mục/sao chép tương đương. **Trong PowerShell, khi gõ hoặc kiểm tra đường dẫn có `$Transformer`, hãy đặt đường dẫn trong dấu nháy đơn**, như tham số của `Select-String` ở trên; nháy kép có thể khiến PowerShell diễn giải `$Transformer` như biến và làm sai tên.

**Điểm cần hiểu:** `ServiceLoader.load(type)` lấy tên nhị phân của service để định vị tệp cấu hình trên classpath, đọc tên provider từ tệp, rồi tìm và khởi tạo lớp cung cấp dịch vụ. Mã host không cần gọi `new UpperTransformer()`.

### 4.7. Thử đặt sai tên tệp

Trong bản sao dự án dùng để thực hành, đổi tên tệp thành:

```text
META-INF/services/com.example.spi.Contracts.Transformer
```

nhưng giữ nguyên nội dung provider. Sau khi đóng gói lại plugin JAR từ thư mục sạch, nếu không có cấu hình hợp lệ nào khác cho service này, chương trình vẫn chạy nhưng in `providers=0` và không có dòng `result=JAVA SPI`. `ServiceLoader` không tự đoán rằng dấu chấm cuối đáng ra phải là `$`.

Ngược lại, giữ **tên tệp đúng** nhưng ghi sai tên lớp provider, ví dụ `com.example.plugin.DoesNotExist`, thì khi duyệt provider có thể phát sinh `ServiceConfigurationError`. Hai tình huống khác nhau: **không tìm thấy tệp hợp lệ** so với **tìm thấy tệp nhưng khai báo provider không thể nạp**.

## 5. Đưa tệp vào JAR đúng vị trí

Tên đầy đủ của tài nguyên được tính **từ gốc classpath/JAR**, không tính từ thư mục mã nguồn. Cấu trúc JAR đúng có dạng:

```text
plugin.jar
├── META-INF/
│   ├── MANIFEST.MF
│   └── services/
│       └── com.example.spi.Contracts$Transformer
└── com/
    └── example/
        └── plugin/
            └── UpperTransformer.class
```

Nếu dùng bố cục chuẩn của Maven hoặc Gradle, hãy đặt tệp nguồn tại:

```text
src/main/resources/META-INF/services/com.example.spi.Contracts$Transformer
```

Hệ thống build bình thường sẽ đóng gói **nội dung** của `src/main/resources` vào gốc JAR. Nếu JAR vô tình chứa `resources/META-INF/services/...` hoặc `src/main/resources/META-INF/services/...` thì đường dẫn cuối cùng **không khớp** tên tài nguyên mà `ServiceLoader` tìm.

Chú ý trường hợp plugin có provider class nhưng thiếu thư viện chứa **hợp đồng dùng chung** trong classpath: việc tìm resource chưa đủ. Khi nạp, JVM cần nhìn thấy service type và provider tương thích, thường thông qua cùng một bản hợp đồng mà host sử dụng.

## 6. Kiểm tra tên bằng API thay vì nhớ thủ công

Đối với một service type cụ thể đã biên dịch, công thức:

```java
String expectedPath = "META-INF/services/" + Transformer.class.getName();
```

là cách đơn giản nhất để xây dựng đường dẫn kỳ vọng. Đoạn này cần `Transformer` được import hoặc khai báo trong phạm vi sử dụng.

Để xác định có nhìn thấy tệp qua classloader hay không, có thể thêm mã chẩn đoán vào host trong ví dụ:

```java
String path = "META-INF/services/" + Transformer.class.getName();
ClassLoader loader = Thread.currentThread().getContextClassLoader();
System.out.println(loader.getResource(path));
```

Đây là **đoạn bổ sung** dùng trong `Main`, không phải chương trình Java độc lập. Nếu trả về `null` thì classloader đang kiểm tra không thấy tài nguyên mang tên đó. Khi chạy với JAR như ví dụ, kết quả thường là một URL `jar:file:...!/META-INF/services/com.example.spi.Contracts$Transformer`; đường dẫn URL cụ thể tùy máy. Khi kiểm tra hệ plugin nhiều classloader, phải dùng classloader tương ứng với lời gọi `ServiceLoader.load(...)`; kiểm tra sai loader có thể đưa tới kết luận sai.

Kiểm tra theo thứ tự:

1. Dùng `Transformer.class.getName()` để lấy tên binary thật.
2. Đối chiếu **chính xác từng ký tự** với tên tệp trong `META-INF/services`, kể cả chữ hoa/chữ thường và ký tự `$`.
3. Dùng `jar --list --file <tên-jar>` để xác nhận đường dẫn nằm trong artifact đã đóng gói.
4. Xác nhận JAR có trên classpath được truyền cho `java` và classloader có thể thấy resource.
5. Nếu tài nguyên được tìm thấy nhưng provider không tải được, kiểm tra từng tên lớp trong nội dung và điều kiện khởi tạo/provider có tương thích service type.

## 7. Những lỗi thường gặp

| Hiện tượng | Sai ở đâu? | Cách giải quyết |
|---|---|---|
| `providers=0` dù đã có class provider | Đặt tên tệp theo provider thay vì service | Tên tệp phải là `serviceType.getName()` |
| `providers=0` với service lồng nhau | Đặt `Contracts.Transformer` thay vì `Contracts$Transformer` | Dùng tên binary có `$` |
| Không thấy provider từ JAR | Tệp nằm sai gốc, thiếu `META-INF/services/` hoặc không được copy vào JAR | Xem cấu trúc JAR và đường dẫn tài nguyên |
| Không thấy provider dù tệp đúng | Plugin JAR không nằm trên classpath/classloader đang dùng | Kiểm tra lệnh chạy và khả năng nhìn thấy tài nguyên |
| `ServiceConfigurationError` | Tệp có nội dung sai định dạng, tên lớp không tồn tại hoặc provider không hợp lệ | Kiểm tra UTF-8 không BOM, tên provider, constructor, `implements` |
| Sai tên trên Windows/PowerShell | Dấu `$` bị diễn giải như biến khi đặt trong chuỗi nháy kép | Dùng đường dẫn nháy đơn khi thao tác tệp |
| Không khớp sau đổi package/rename | Tệp đăng ký giữ tên binary cũ | Cập nhật tên tệp khi đổi kiểu dịch vụ, cập nhật nội dung khi đổi provider |
| Tệp đuôi `.txt` do trình soạn thảo | Tên trên JAR khác tên ServiceLoader tìm | Lưu đúng tên, không phần mở rộng |

Đừng sửa lỗi `providers=0` bằng cách thêm `new Provider()` vào host nếu mục tiêu là học cơ chế đăng ký SPI: thao tác đó bỏ qua bước khám phá và che giấu lỗi cấu hình.

## 8. Phân biệt cách đăng ký trên classpath và named module

Bài học này tập trung vào **provider JAR trên classpath** (unnamed module), nơi tệp `META-INF/services/<binary-name>` là cơ chế đăng ký.

Với provider được phát triển thành **named module** trong JPMS, cách đăng ký chính là khai báo `provides ... with ...` trong `module-info.java`, ví dụ:

```java
provides com.example.spi.Contracts.Transformer
    with com.example.plugin.UpperTransformer;
```

Đây là **đoạn khai báo bên trong `module-info.java`**, không phải một tệp Java độc lập để chạy theo lệnh ở mục 4. Đừng lấy việc có hay không có `META-INF/services` làm kết luận duy nhất cho một plugin hoạt động theo named module. Với cấu hình JPMS thực tế, module tiêu thụ service cũng thường phải khai báo `uses`.

Dù ở classpath hay module path, nguyên tắc chung vẫn là: **chỉ định đúng service type và khai báo đúng provider tương ứng**. Các cơ chế đăng ký có thể khác nhau.

## 9. Câu hỏi và bài tập tự kiểm tra

1. Với `package vn.demo.spi; public interface Parser { }`, tệp cần đặt tên gì? — `META-INF/services/vn.demo.spi.Parser`.
2. Với `public class Api { public interface Parser {} }` trong package `vn.demo.spi`, tệp cần tên gì? — `META-INF/services/vn.demo.spi.Api$Parser`, không phải `vn.demo.spi.Api.Parser`.
3. Một tệp đăng ký nên đặt tên theo service hay provider? — **Theo service**; các dòng bên trong liệt kê provider.
4. Tệp đăng ký đã đúng nhưng lớp provider không tồn tại thì có luôn trả danh sách trống không? — Không; khi duyệt provider có thể ném `ServiceConfigurationError`.
5. Tên tệp có bắt buộc thêm `.class` hoặc `.txt` không? — Không, thêm hậu tố sẽ thay đổi tên tài nguyên cần tìm.

**Thực hành:** sao chép ví dụ mục 4, dùng `Transformer.class.getName()` xác minh tên nhị phân, sau đó chủ động đổi `$` thành `.` ở tên tệp đăng ký, đóng gói lại JAR sạch và quan sát số provider. Đổi tên về đúng giá trị từ `getName()` rồi chạy lại. Bài tập này phân biệt được lỗi **đặt tên tệp cấu hình** với lỗi **viết lớp triển khai**.

## Tài liệu tham khảo

- Oracle Java SE 17, `java.util.ServiceLoader` — mục *Deploying service providers on the class path*: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- Oracle Java SE 17, `java.lang.Class#getName()`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getName()
