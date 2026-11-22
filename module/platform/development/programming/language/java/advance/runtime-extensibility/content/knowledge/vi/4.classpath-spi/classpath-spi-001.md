# Định nghĩa dịch vụ và tạo nhiều phần triển khai độc lập trên classpath

Khi xây dựng ứng dụng Java có thể mở rộng, ta thường muốn thêm một cách xử lý mới mà không phải sửa mọi nơi đang sử dụng chức năng đó. Một hướng thiết kế là **định nghĩa một hợp đồng dịch vụ (service contract)** rồi cho nhiều thư viện độc lập hiện thực hợp đồng. Trên Java classpath, `ServiceLoader` giúp ứng dụng khám phá những phần triển khai (service provider) đã được đăng ký.

Bài này xây dựng **một SPI, hai provider nằm trong hai JAR riêng và một ứng dụng gọi chúng**. Qua đó, bạn sẽ thấy phần nào được chia sẻ khi biên dịch, phần nào có thể thêm/bớt khi chạy, và điều kiện để Java thực sự tìm được provider.

## 1. Mô hình cần nắm trước khi viết mã

Giả sử ứng dụng cần lời chào theo nhiều ngôn ngữ. Cách viết phụ thuộc trực tiếp vào implementation thường trông như sau:

```java
// Minh họa mã ghép cứng, không phải chương trình hoàn chỉnh.
if (language.equals("en")) {
    return new EnglishGreetingService().greet(name);
}
return new VietnameseGreetingService().greet(name);
```

Mỗi lần thêm một ngôn ngữ, đoạn chọn lớp có nguy cơ phải sửa. Hơn nữa, ứng dụng phải biết tên lớp triển khai ngay từ lúc biên dịch.

Mô hình SPI tách ba trách nhiệm:

1. **Hợp đồng dịch vụ:** mô tả chức năng và các quy tắc mà mọi provider phải tuân theo.
2. **Các provider độc lập:** mỗi provider hiện thực cùng hợp đồng nhưng tự quyết định thuật toán và cách đóng gói; provider A không phải import provider B.
3. **Consumer và bộ khám phá:** ứng dụng chỉ biết hợp đồng, để `ServiceLoader` tìm các provider có mặt và đã đăng ký trong môi trường chạy.

```text
                 Phụ thuộc vào hợp đồng chung
                              |
                 +------------v------------+
                 | GreetingService (SPI)   |
                 | languageTag(), greet()  |
                 +------------+------------+
                              |
          +-------------------+-------------------+
          |                                       |
+---------v---------------+          +------------v------------+
| greeting-en.jar         |          | greeting-vi.jar         |
| EnglishGreetingService  |          | VietnameseGreetingService|
| + META-INF/services     |          | + META-INF/services     |
+-------------------------+          +-------------------------+
          |                                       |
          +-------------------+-------------------+
                              |
             ServiceLoader tìm provider
                              |
                 +------------v------------+
                 | greeting-app.jar        |
                 | Main dùng hợp đồng SPI  |
                 +-------------------------+
```

Interface `GreetingService` là **SPI đối với người viết provider** và đồng thời là kiểu dịch vụ mà consumer có thể gọi. Thuật ngữ API/SPI mô tả *vai trò sử dụng hợp đồng*, không bắt buộc mỗi vai trò phải có một interface riêng.

**“Độc lập” ở đây có nghĩa:** hai provider có mã nguồn, vòng đời phát hành và JAR riêng; chúng chỉ phụ thuộc vào hợp đồng chung, không phụ thuộc vào nhau. Điều này không có nghĩa provider được cách ly tiến trình, được tự động cập nhật nóng hoặc có thể bỏ qua việc quản lý phiên bản SPI.

## 2. Thiết kế hợp đồng dịch vụ

Trước khi viết provider, ta cần xác định điều gì phải ổn định. Trong ví dụ:

- `languageTag()` trả về mã ngôn ngữ để consumer nhận diện dịch vụ. Mỗi provider dùng một mã duy nhất, ví dụ `en` hoặc `vi`.
- `greet(name)` nhận tên người dùng và trả về câu chào.
- Để demo có đầu ra rõ ràng, quy ước `name` khác `null`, không rỗng; lời chào trả về khác `null`. Đây là **quy ước hợp đồng**; interface Java tự nó chưa kiểm tra các điều kiện đó.
- Provider không duy trì trạng thái thay đổi giữa các lần gọi, nên có thể tái sử dụng instance trong ví dụ. Với dịch vụ có trạng thái/tài nguyên, hợp đồng cần nói rõ thread safety và cách đóng tài nguyên.

Tệp `contract/src/com/example/spi/GreetingService.java`:

```java
package com.example.spi;

public interface GreetingService {
    String languageTag();

    String greet(String name);
}
```

Đây là một **service type** hợp lệ cho `ServiceLoader`. Interface chỉ nêu những thao tác mà các implementation phải cung cấp. Nó không biết lớp tiếng Anh, lớp tiếng Việt, thư mục lưu JAR, hay cơ chế chọn provider. Việc giữ hợp đồng nhỏ, có ngữ nghĩa rõ ràng giúp tác giả provider độc lập thực hiện đúng cùng một kỳ vọng.

## 3. Cấu trúc dự án: bốn thành phần riêng

Để dễ theo dõi, ta dùng bốn thư mục nguồn. Bạn có thể tạo cây tệp sau trong thư mục `spi-demo`:

```text
spi-demo/
├── contract/
│   └── src/com/example/spi/GreetingService.java
├── provider-en/
│   ├── src/com/example/provider/en/EnglishGreetingService.java
│   └── resources/META-INF/services/com.example.spi.GreetingService
├── provider-vi/
│   ├── src/com/example/provider/vi/VietnameseGreetingService.java
│   └── resources/META-INF/services/com.example.spi.GreetingService
└── app/
    └── src/com/example/app/Main.java
```

Khi biên dịch, ta sẽ tạo bốn JAR:

| JAR | Chứa gì? | Phụ thuộc khi biên dịch |
|---|---|---|
| `greeting-spi.jar` | Interface `GreetingService` | Không phụ thuộc provider |
| `greeting-en.jar` | Provider tiếng Anh và đăng ký của nó | `greeting-spi.jar` |
| `greeting-vi.jar` | Provider tiếng Việt và đăng ký của nó | `greeting-spi.jar` |
| `greeting-app.jar` | Consumer `Main` | `greeting-spi.jar` |

Hai provider **không cần thấy mã hoặc JAR của nhau** khi biên dịch. Consumer cũng không cần import lớp provider cụ thể. Đây là ranh giới phụ thuộc quan trọng nhất của bài.

## 4. Hai implementation độc lập

### 4.1. Provider tiếng Anh

Tệp `provider-en/src/com/example/provider/en/EnglishGreetingService.java`:

```java
package com.example.provider.en;

import com.example.spi.GreetingService;

public final class EnglishGreetingService implements GreetingService {
    @Override
    public String languageTag() {
        return "en";
    }

    @Override
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

`EnglishGreetingService` tự hiện thực hai method của SPI. Vì class là `public` và không khai báo constructor riêng, Java cấp constructor không tham số với mức truy cập công khai, đáp ứng cách khởi tạo provider theo classpath trong ví dụ.

### 4.2. Provider tiếng Việt

Tệp `provider-vi/src/com/example/provider/vi/VietnameseGreetingService.java`:

```java
package com.example.provider.vi;

import com.example.spi.GreetingService;

public final class VietnameseGreetingService implements GreetingService {
    @Override
    public String languageTag() {
        return "vi";
    }

    @Override
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Lớp này chỉ biết `GreetingService`. Nó không `extends`, `imports` hoặc gọi `EnglishGreetingService`. Hai provider được phép dùng thư viện nội bộ khác nhau, miễn tuân thủ hợp đồng chung.

**Phân biệt quan trọng:** `implements GreetingService` chỉ thỏa yêu cầu về kiểu Java. Để `ServiceLoader` *tìm thấy* provider trên classpath, ta vẫn phải đăng ký lớp bằng tài nguyên dịch vụ.

## 5. Đăng ký từng provider bằng `META-INF/services`

Cơ chế đăng ký trên **classpath** dùng tệp cấu hình với đường dẫn chính xác:

```text
META-INF/services/<tên-đầy-đủ-của-service-type>
```

Trong ví dụ, cả hai JAR đều có một tệp cùng đường dẫn:

```text
META-INF/services/com.example.spi.GreetingService
```

Nhưng **nội dung mỗi tệp khác nhau**.

Nội dung `provider-en/resources/META-INF/services/com.example.spi.GreetingService`:

```text
com.example.provider.en.EnglishGreetingService
```

Nội dung `provider-vi/resources/META-INF/services/com.example.spi.GreetingService`:

```text
com.example.provider.vi.VietnameseGreetingService
```

`ServiceLoader` đọc các tài nguyên cấu hình dịch vụ mà class loader nhìn thấy. Khi hai JAR cùng nằm trên classpath, hai tài nguyên có cùng tên vẫn được khám phá; **không phải ghép hai tệp thành một hoặc chỉ giữ một tệp**. Mỗi JAR tự mang đăng ký của chính nó. Đây là điều khiến việc thêm/bớt provider JAR thuận tiện.

Các quy tắc cần nhớ:

- Tên file sau `services/` phải là tên đầy đủ của **interface dịch vụ**, không phải tên provider.
- Mỗi dòng nội dung ghi tên đầy đủ của **lớp provider**. Có thể có nhiều provider trong một file, nhưng ví dụ cố ý đặt một provider trên một JAR.
- Không đặt phần mở rộng `.txt`, `.java` hoặc `.properties` cho tệp đăng ký.
- Trên classpath, lớp provider phải hiện thực service type và có constructor không tham số công khai phù hợp cơ chế khởi tạo của `ServiceLoader`.
- File cấu hình phải được đóng gói **bên trong provider JAR**, đúng đường dẫn gốc `META-INF/services/...`. Để file bên ngoài JAR nhưng không nằm trong đường dẫn tài nguyên được tìm thấy sẽ không đủ.
- Khai báo sai tên lớp, kiểu không phù hợp hoặc lỗi tạo instance có thể gây `ServiceConfigurationError` khi duyệt provider.

Không cần dùng `Class.forName(...)`, không cần đăng ký thủ công qua `new` trong consumer và không cần thay đổi hợp đồng SPI khi thêm một implementation tuân thủ hợp đồng hiện có.

## 6. Viết consumer chỉ biết hợp đồng

Tệp `app/src/com/example/app/Main.java`:

```java
package com.example.app;

import com.example.spi.GreetingService;
import java.util.Map;
import java.util.ServiceLoader;
import java.util.TreeMap;

public final class Main {
    public static void main(String[] args) {
        Map<String, GreetingService> byLanguage = new TreeMap<>();

        for (GreetingService provider : ServiceLoader.load(GreetingService.class)) {
            String language = provider.languageTag();

            GreetingService previous = byLanguage.putIfAbsent(language, provider);
            if (previous != null) {
                throw new IllegalStateException(
                        "Duplicate language tag: " + language);
            }
        }

        if (byLanguage.isEmpty()) {
            throw new IllegalStateException("No greeting providers found");
        }

        byLanguage.forEach((language, provider) ->
                System.out.println(language + " => " + provider.greet("Linh")));
    }
}
```

Mã consumer không import `EnglishGreetingService` hay `VietnameseGreetingService`. Nó yêu cầu dịch vụ qua `GreetingService.class`, duyệt provider được phát hiện, kiểm tra mã ngôn ngữ trùng rồi sử dụng method `greet()`.

Vì `ServiceLoader` **không hứa thứ tự các provider**, ví dụ đưa chúng vào `TreeMap` để in theo thứ tự từ điển của mã ngôn ngữ. Điều này bảo đảm đầu ra `en` rồi `vi`, dù thứ tự khám phá thực tế khác nhau. Dùng `putIfAbsent` còn tránh lỗi âm thầm ghi đè hai provider khai báo cùng `languageTag()`.

Với ứng dụng lớn, bạn có thể viết một lớp điều phối hoặc facade để consumer chỉ gọi `getGreeting("vi")`. `ServiceLoader` là cơ chế phát hiện provider; chính ứng dụng quyết định cách chọn, ưu tiên, xử lý trùng lặp và báo lỗi.

## 7. Biên dịch, đóng JAR và chạy trên Java 17+

Ví dụ không dùng Maven/Gradle để làm rõ trực tiếp quan hệ classpath. Cần cài **JDK 17 trở lên** và có lệnh `javac`, `jar`, `java`. Chạy từ thư mục gốc `spi-demo`; đảm bảo đã tạo đúng các tệp ở phần trên.

### 7.1. Lệnh trên Windows PowerShell

```powershell
New-Item -ItemType Directory -Force -Path out/spi,out/en,out/vi,out/app,dist | Out-Null

javac -encoding UTF-8 -d out/spi contract/src/com/example/spi/GreetingService.java
jar --create --file dist/greeting-spi.jar -C out/spi .

javac -encoding UTF-8 --class-path dist/greeting-spi.jar -d out/en provider-en/src/com/example/provider/en/EnglishGreetingService.java
jar --create --file dist/greeting-en.jar -C out/en . -C provider-en/resources .

javac -encoding UTF-8 --class-path dist/greeting-spi.jar -d out/vi provider-vi/src/com/example/provider/vi/VietnameseGreetingService.java
jar --create --file dist/greeting-vi.jar -C out/vi . -C provider-vi/resources .

javac -encoding UTF-8 --class-path dist/greeting-spi.jar -d out/app app/src/com/example/app/Main.java
jar --create --file dist/greeting-app.jar -C out/app .

java --class-path 'dist/greeting-spi.jar;dist/greeting-en.jar;dist/greeting-vi.jar;dist/greeting-app.jar' com.example.app.Main
```

### 7.2. Lệnh trên Linux/macOS

Cùng các tệp nguồn, trên hệ Unix dùng dấu `:` để ngăn các phần tử classpath:

```bash
mkdir -p out/spi out/en out/vi out/app dist

javac -encoding UTF-8 -d out/spi contract/src/com/example/spi/GreetingService.java
jar --create --file dist/greeting-spi.jar -C out/spi .

javac -encoding UTF-8 -cp dist/greeting-spi.jar -d out/en provider-en/src/com/example/provider/en/EnglishGreetingService.java
jar --create --file dist/greeting-en.jar -C out/en . -C provider-en/resources .

javac -encoding UTF-8 -cp dist/greeting-spi.jar -d out/vi provider-vi/src/com/example/provider/vi/VietnameseGreetingService.java
jar --create --file dist/greeting-vi.jar -C out/vi . -C provider-vi/resources .

javac -encoding UTF-8 -cp dist/greeting-spi.jar -d out/app app/src/com/example/app/Main.java
jar --create --file dist/greeting-app.jar -C out/app .

java -cp "dist/greeting-spi.jar:dist/greeting-en.jar:dist/greeting-vi.jar:dist/greeting-app.jar" com.example.app.Main
```

Đầu ra tiêu chuẩn khi có đủ hai provider và terminal hiển thị Unicode:

```text
en => Hello, Linh!
vi => Xin chào, Linh!
```

Trong cả hai bộ lệnh:

1. `greeting-spi.jar` được biên dịch **trước** vì ba thành phần còn lại phụ thuộc hợp đồng.
2. Mỗi provider được biên dịch chỉ với `greeting-spi.jar` trên compile classpath; không cần JAR của provider còn lại.
3. `jar -C ... . -C provider-.../resources .` đưa cả class đã biên dịch và tài nguyên `META-INF/services/...` vào cùng JAR.
4. Consumer được biên dịch **chỉ với hợp đồng SPI**, chưa cần biết JAR provider.
5. Khi chạy, classpath chứa contract, app và **hai provider JAR** để `ServiceLoader` nhìn thấy đủ dịch vụ.

Để kiểm tra nội dung đăng ký thực sự đã vào JAR, chạy:

```powershell
jar --list --file dist/greeting-en.jar
jar --list --file dist/greeting-vi.jar
```

Trong danh sách của **cả hai JAR** phải có `META-INF/services/com.example.spi.GreetingService` và class tương ứng. Thứ tự các mục mà lệnh `jar --list` in ra không phải hợp đồng của ví dụ.

## 8. Thử thay đổi classpath mà không sửa consumer

### Thử nghiệm A: chỉ mang provider tiếng Anh

Trên Windows:

```powershell
java --class-path 'dist/greeting-spi.jar;dist/greeting-en.jar;dist/greeting-app.jar' com.example.app.Main
```

Đầu ra:

```text
en => Hello, Linh!
```

Trên Linux/macOS thay dấu `;` trong classpath bằng `:`. Mã nguồn `Main.java` và JAR consumer **không đổi**: chỉ môi trường chạy thiếu `greeting-vi.jar` nên danh sách dịch vụ có một provider.

### Thử nghiệm B: không có provider nào

Trên Windows:

```powershell
java --class-path 'dist/greeting-spi.jar;dist/greeting-app.jar' com.example.app.Main
```

`ServiceLoader` không tìm thấy provider qua classpath này. `byLanguage` rỗng, nên chương trình ném `IllegalStateException` với thông báo:

```text
No greeting providers found
```

Đây là **thông báo ngoại lệ**, không phải một dòng stdout do chương trình in ra; Java còn có stack trace trên stderr. Trong sản phẩm thật, phải chọn rõ chính sách thiếu provider: thất bại sớm, dịch vụ mặc định, hay cấu hình bắt buộc.

### Thử nghiệm C: thêm provider mới

Bạn có thể tạo `FrenchGreetingService implements GreetingService`, dùng mã `fr`, đóng một `greeting-fr.jar` riêng gồm class và tệp `META-INF/services/com.example.spi.GreetingService`, rồi **thêm JAR này vào classpath khi khởi chạy**.

Nếu hợp đồng không đổi và provider đúng quy định, consumer đã biên dịch vẫn chạy được mà không cần import, sửa `switch`, hoặc biên dịch lại `Main.java`. Nhớ rằng “thêm JAR vào lệnh chạy mới” khác với “thả JAR vào thư mục trong khi JVM đang chạy”: classpath mặc định không tự cập nhật để nạp nóng plugin mới.

## 9. Điều gì thật sự xảy ra khi `ServiceLoader` hoạt động?

Đối với chương trình chạy bằng **classpath** như ví dụ:

1. `Main` yêu cầu `ServiceLoader.load(GreetingService.class)`.
2. Cơ chế nạp dùng class loader phù hợp (overload một tham số dùng context class loader của luồng) để tra cứu các tài nguyên `META-INF/services/com.example.spi.GreetingService`.
3. Khi chương trình duyệt các provider, `ServiceLoader` đọc khai báo và nạp/khởi tạo lớp provider theo cơ chế dành cho classpath.
4. Đối tượng trả về có kiểu `GreetingService` và được consumer gọi qua hai method của interface.

Quá trình khám phá/khởi tạo thường **lười (lazy)**: gọi `load` không khởi tạo sẵn toàn bộ provider. Việc duyệt `for` trong `Main` mới khiến các provider được sử dụng. Một đối tượng `ServiceLoader` có cache các provider đã nạp; `reload()` làm mới cache của đối tượng loader đó nhưng **không thêm JAR vào classpath hoặc thay lớp đã nạp**.

Không nên dùng chung một instance `ServiceLoader` giữa nhiều luồng mà không tự quản lý đồng bộ vì `ServiceLoader` không bảo đảm thread-safe. `ServiceLoader` cũng **không phải bộ chứa dependency injection**, không tự kiểm tra nghiệp vụ của các method và không cung cấp cơ chế cô lập bảo mật cho mã provider.

Bài này áp dụng mô hình **classpath**. Với Java Platform Module System (JPMS), named module thường khai báo `uses` và `provides ... with ...` trong `module-info.java`. Đó là cơ chế đăng ký khác; không được nhầm việc đóng gói JAR classpath ở đây với cấu hình module path.

## 10. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Kiểm tra hoặc xử lý |
|---|---|---|
| Không tìm thấy provider dù có class | Provider JAR không nằm trên runtime classpath, hoặc thiếu resource đăng ký | Kiểm tra `java -cp` và `jar --list --file ...` |
| Thiếu một provider khi có nhiều JAR | Chỉ đưa một JAR vào classpath hoặc một JAR thiếu `META-INF/services` | Xác minh từng JAR đóng gói metadata độc lập |
| `ServiceConfigurationError` khi duyệt | Sai tên class trong tệp đăng ký, provider không đúng kiểu, không khởi tạo được | Kiểm tra tên đầy đủ, `implements`, quyền truy cập, constructor và nguyên nhân lỗi |
| `ClassNotFoundException`/`NoClassDefFoundError` | Thiếu JAR contract hoặc phụ thuộc của provider lúc chạy | Kiểm tra đủ dependency trên classpath |
| “Not a subtype” trong lỗi cấu hình | Provider không thực sự hiện thực đúng `GreetingService`, đôi khi do class loader nạp hai bản khác nhau của cùng interface | Kiểm tra class loader và thống nhất artifact chứa SPI |
| Kết quả không theo thứ tự mong muốn | Phụ thuộc thứ tự `ServiceLoader` phát hiện provider | Chọn/sắp xếp theo khóa rõ ràng như `TreeMap` |
| Hai provider cùng `languageTag()` | Hợp đồng nhận diện không bảo đảm duy nhất | Phát hiện trùng và quy định cách xử lý, như mã `putIfAbsent` |
| Thêm JAR nhưng JVM đang chạy không thấy | Classpath/class loader hiện tại không tự cập nhật | Khởi chạy lại hoặc thiết kế riêng cơ chế nạp plugin/class loader động |

**Tương thích phiên bản cũng là một phần của thiết kế.** Nếu nâng SPI bằng cách thêm method trừu tượng mới, provider cũ có thể không còn tương thích khi được gọi; cần quản lý version và lựa chọn chiến lược tiến hóa hợp đồng. Kiểm tra tương thích phải xét cả chữ ký method, ý nghĩa kết quả, ngoại lệ và vòng đời.

**Bảo mật:** provider chạy trong JVM của ứng dụng với khả năng truy cập tương ứng; việc đi qua SPI không tự tạo sandbox. Chỉ tải provider JAR đáng tin cậy hoặc thiết kế lớp cô lập thật sự nếu cần chạy mã không tin cậy.

## 11. Tiêu chí của một service extensible tốt

Khi thiết kế SPI mới, tự trả lời:

- **Hợp đồng:** consumer và provider hiểu thống nhất đầu vào, đầu ra, lỗi, tính bất biến/thread safety và giới hạn trách nhiệm chưa?
- **Độc lập:** mỗi provider biên dịch chỉ cần SPI và phụ thuộc riêng, không tham chiếu provider khác chưa?
- **Đăng ký:** mỗi JAR tự mang đúng file `META-INF/services` và lớp provider có thể được khởi tạo theo hợp đồng chưa?
- **Khám phá:** ứng dụng biết phải làm gì khi không có provider, khi provider lỗi, khi có nhiều provider hoặc trùng mã chưa?
- **Thử nghiệm:** có chạy với 0, 1 và nhiều provider bằng cách thay classpath mà không sửa consumer chưa?
- **Phát hành:** hợp đồng SPI có quản lý phiên bản và bộ kiểm thử tương thích cho provider ngoài nhóm phát triển chưa?

## 12. Bài tập củng cố

1. **Tạo provider thứ ba:** hiện thực `GreetingService` cho mã `fr` trong JAR riêng. Biên dịch nó với duy nhất `greeting-spi.jar`, đóng gói tài nguyên dịch vụ và thêm JAR mới vào lệnh chạy. Dự đoán vì sao `Main` không cần biên dịch lại.
2. **Phá đăng ký có kiểm soát:** bỏ tệp `META-INF/services/...` khỏi bản đóng gói của `greeting-vi.jar` rồi chạy lại. Phân biệt “class có trong JAR” với “provider được khai báo”.
3. **Thử lỗi trùng mã:** tạo thêm provider trả `"en"` ở `languageTag()`. Giải thích vì sao `Main` báo lỗi trùng thay vì âm thầm ghi đè. Hãy thay bằng một chính sách chọn ưu tiên có quy tắc nếu sản phẩm cho phép nhiều provider cùng nhóm.
4. **Đánh dấu phụ thuộc:** vẽ mũi tên compile-time từ app và từng provider về `greeting-spi.jar`; sau đó liệt kê các JAR phải có trên runtime classpath. Hai sơ đồ này có gì khác nhau?
5. **Thảo luận mở rộng:** khi nào interface SPI nhỏ như ví dụ là đủ, và khi nào cần hợp đồng bổ sung về version, khởi tạo, đóng tài nguyên, cấu hình, lỗi và bảo mật?

Nắm được cách định nghĩa service type, đóng gói từng implementation và đăng ký provider vào classpath là nền tảng để xây dựng extension point trong Java. Điểm cốt lõi là **provider độc lập với nhau nhưng cùng tuân thủ một hợp đồng**, còn consumer chỉ phụ thuộc vào hợp đồng và quyết định cách sử dụng các provider được khám phá.