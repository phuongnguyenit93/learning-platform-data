# Dùng `ServiceLoader.findFirst()` và xử lý `Optional` khi không tìm thấy provider

## 1. Vấn đề cần giải quyết

Trong cơ chế Java Service Provider Interface (SPI), ứng dụng có thể công bố một *service contract* rồi để các thư viện cung cấp những lớp triển khai (*provider*). Khi khám phá provider, câu hỏi thường gặp là: **lấy provider đầu tiên như thế nào, và xử lý ra sao nếu ứng dụng chưa cài provider nào?**

Từ **Java 9**, `java.util.ServiceLoader` có phương thức:

```java
public Optional<S> findFirst()
```

`S` là kiểu service cần tìm. Ví dụ, với `ServiceLoader<Greeter>`, lời gọi `findFirst()` trả về `Optional<Greeter>`. Nó diễn đạt được hai kết quả bình thường:

- `Optional.of(provider)` (về mặt ý nghĩa): đã phát hiện và tạo được một provider;
- `Optional.empty()`: quá trình duyệt kết thúc mà **không tìm thấy provider nào**.

Vì thế không cần dùng `Iterator.next()` rồi dựa vào `NoSuchElementException` để xác định tình trạng thiếu provider; càng không nên gọi `optional.get()` mà không kiểm tra.

**Quan trọng:** Không tìm thấy provider khác với **provider được khai báo nhưng bị lỗi**. `ServiceLoader.findFirst()` có thể ném `ServiceConfigurationError` nếu khai báo SPI không hợp lệ, không thể nạp/tạo provider hoặc lỗi cấu hình xảy ra trong quá trình tìm kiếm. Đó là lỗi cần chẩn đoán, **không phải** tín hiệu `Optional.empty()`.

### Cơ chế ở mức khái niệm

```text
ServiceLoader.load(ServiceType.class)
             │
             ▼
        findFirst()
             │
       ┌─────┴─────────────────┐
       │                       │
  tìm và tạo được          duyệt hết, không có
    provider                 provider nào
       │                       │
       ▼                       ▼
Optional<Provider>        Optional.empty()
       │                       │
       ▼                       ▼
 dùng provider           thông báo / fallback /
                        từ chối chức năng
```

Trong sơ đồ, `Optional<Provider>` chỉ mang nghĩa chung “Optional chứa một instance provider”; kiểu Java thực tế của **`ServiceLoader<S>.findFirst()`** là **`Optional<S>`**. Phân biệt cụ thể với `ServiceLoader.stream()` ở mục 5.

## 2. API cơ bản: lấy provider đầu tiên

Giả sử contract có tên `demo.Greeter`:

```java
ServiceLoader<Greeter> loader = ServiceLoader.load(Greeter.class);
Optional<Greeter> first = loader.findFirst();
```

Đây là **đoạn minh họa**, cần có `Greeter` được định nghĩa và `import java.util.*` phù hợp; mục 4 có chương trình đầy đủ.

`ServiceLoader.load(Greeter.class)` lấy service loader dùng context class loader của thread hiện tại. Nó sẽ tìm provider bằng cơ chế SPI trên classpath hoặc qua module system phù hợp. Trên classpath, JAR provider cần chứa tài nguyên đúng tên `META-INF/services/demo.Greeter`, với nội dung là tên lớp triển khai; đối với named module, dùng khai báo `uses` và `provides ... with ...` theo JPMS.

`findFirst()` tìm provider **đầu tiên được ServiceLoader duyệt thấy**, tạo instance của nó khi cần và trả kết quả trong `Optional`. Nó không tự gọi các phương thức vòng đời nghiệp vụ như `start()`, `activate()` hay `stop()`; nếu contract có các phương thức đó, host phải tự điều phối.

Không giả định provider “đầu tiên” là tốt nhất hoặc có độ ưu tiên cao nhất: khi có nhiều provider, thứ tự phát hiện có thể phụ thuộc module configuration, các resource và class loader, cũng như thứ tự đóng gói. Nếu bài toán cần provider theo ID, version, capability hoặc priority, phải định nghĩa quy tắc lựa chọn rõ ràng (xem mục 5).

## 3. Các cách xử lý `Optional<Greeter>`

Các đoạn trong mục này sử dụng biến `first` đã lấy ở trên.

### 3.1. Có thì dùng, không có thì báo rõ — `ifPresentOrElse`

```java
first.ifPresentOrElse(
    provider -> System.out.println(provider.greet("Java")),
    () -> System.out.println("Không tìm thấy Greeter provider")
);
```

- Nhánh đầu chỉ chạy khi `Optional` có provider.
- Nhánh sau chạy khi không có provider.
- `ifPresentOrElse` phù hợp với tác vụ chỉ tạo *side effect* như hiển thị, đăng ký hoặc ghi log; phương thức này trả về `void`, không trả về provider.

### 3.2. Tính kết quả khi có provider — `map` và `orElse`

```java
String message = first
    .map(provider -> provider.greet("Java"))
    .orElse("Chức năng chào hỏi chưa được cài đặt");

System.out.println(message);
```

`map` chỉ gọi `greet` khi có provider. Nếu không có, `Optional<String>` vẫn trống và `orElse` trả về thông báo mặc định. Phù hợp khi kết quả đã chuyển thành một giá trị nhỏ, có sẵn và không tốn chi phí.

### 3.3. Tạo provider dự phòng khi cần — `orElseGet`

```java
Greeter chosen = first.orElseGet(
    () -> name -> "Mặc định: " + name
);
System.out.println(chosen.greet("Java"));
```

`orElseGet(Supplier<? extends Greeter>)` chỉ gọi supplier nếu `Optional` trống. Đây là phương án tốt nếu provider dự phòng cần được tạo/lấy tốn chi phí.

So sánh:

- `first.orElse(createFallback())`: `createFallback()` được **đánh giá trước** lời gọi `orElse`, ngay cả khi đã tìm thấy provider.
- `first.orElseGet(() -> createFallback())`: chỉ gọi `createFallback()` khi thiếu provider.

Chỉ dùng fallback khi hành vi dự phòng thực sự được phép theo yêu cầu nghiệp vụ. Với dịch vụ bảo mật, xác thực, lưu trữ bắt buộc hoặc kết nối tới hệ thống quan trọng, âm thầm thay provider bằng mặc định có thể che giấu lỗi cấu hình.

### 3.4. Provider bắt buộc — `orElseThrow`

```java
Greeter required = first.orElseThrow(
    () -> new IllegalStateException(
        "Ứng dụng yêu cầu Greeter provider nhưng chưa cài đặt"
    )
);
System.out.println(required.greet("Java"));
```

Khi thiếu provider, chương trình ném lỗi với thông điệp có ý nghĩa, thay vì `NoSuchElementException` chung chung từ `Optional.get()`. Phù hợp với extension bắt buộc: không có provider thì không thể phục vụ chức năng.

### 3.5. Chọn cách nào?

| Yêu cầu nghiệp vụ | Cách nên dùng | Hành vi khi thiếu provider |
| --- | --- | --- |
| Chức năng là tùy chọn, cần ghi log/thông báo | `ifPresentOrElse` | Chạy nhánh thông báo |
| Cần ánh xạ thành giá trị kết quả | `map(...).orElse(...)` | Dùng giá trị có sẵn |
| Có implementation dự phòng cần khởi tạo có điều kiện | `orElseGet(...)` | Chỉ tạo dự phòng khi thiếu |
| Không có provider là lỗi cấu hình không thể tiếp tục | `orElseThrow(...)` | Ném lỗi rõ nguyên nhân |
| Cần xử lý bằng `if` vì có nhiều câu lệnh | `isPresent()/isEmpty()` rồi `get()` có kiểm soát | Rẽ nhánh rõ ràng, nhưng thường dài dòng hơn |

**Tránh:** `first.get()` không kiểm tra; `catch (Exception)` để biến mọi lỗi thành “không tìm thấy”; `Optional<Greeter>` bằng `null`. Dùng `Optional` cho trường hợp *vắng mặt hợp lệ*; lỗi cấu hình nên có kênh báo lỗi riêng.

## 4. Ví dụ Java 17+ hoàn chỉnh: có và không có provider

Ví dụ sau chạy được bằng JDK 17+ và không cần Maven/Gradle. Một lần chạy host **không có** JAR provider trên classpath sẽ trả `Optional.empty()`; một lần chạy **có** JAR sẽ tìm được `HelloGreeter`. Có ba chế độ `optional`, `fallback` và `required` để so sánh.

Cấu trúc từ thư mục `demo`:

```text
demo/
├── src/
│   └── demo/
│       ├── Greeter.java
│       ├── HelloGreeter.java
│       └── App.java
└── providers/
    └── META-INF/
        └── services/
            └── demo.Greeter
```

### 4.1. Contract — `src/demo/Greeter.java`

```java
package demo;

public interface Greeter {
    String greet(String name);
}
```

### 4.2. Provider — `src/demo/HelloGreeter.java`

```java
package demo;

public final class HelloGreeter implements Greeter {
    public HelloGreeter() {
        // Constructor không tham số, có thể tạo qua SPI.
    }

    @Override
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

### 4.3. Host — `src/demo/App.java`

```java
package demo;

import java.util.Optional;
import java.util.ServiceLoader;

public final class App {
    private static Greeter createFallback() {
        System.out.println("[host] Tạo fallback");
        return name -> "Mặc định: " + name;
    }

    public static void main(String[] args) {
        String mode = args.length == 0 ? "optional" : args[0];

        // Java 9+: findFirst() trả Optional<Greeter>.
        Optional<Greeter> first =
            ServiceLoader.load(Greeter.class).findFirst();

        switch (mode) {
            case "optional" -> first.ifPresentOrElse(
                provider -> System.out.println(provider.greet("Java")),
                () -> System.out.println(
                    "Không tìm thấy Greeter provider")
            );

            case "fallback" -> {
                Greeter chosen = first.orElseGet(App::createFallback);
                System.out.println(chosen.greet("Java"));
            }

            case "required" -> {
                Greeter chosen = first.orElseThrow(
                    () -> new IllegalStateException(
                        "Greeter provider bắt buộc nhưng chưa cài đặt")
                );
                System.out.println(chosen.greet("Java"));
            }

            default -> throw new IllegalArgumentException(
                "Mode hợp lệ: optional, fallback, required"
            );
        }
    }
}
```

**Giải thích:** `App` chỉ phụ thuộc vào interface `Greeter`. `Optional` biểu diễn việc chưa có provider; mã `switch` quyết định cách phản ứng theo chính sách chức năng. `createFallback()` in một dòng khi được gọi để quan sát rằng `orElseGet` chỉ tạo fallback lúc cần.

### 4.4. Descriptor SPI — `providers/META-INF/services/demo.Greeter`

Nội dung của file (chính xác một tên lớp provider):

```text
demo.HelloGreeter
```

Tên file phải khớp *fully qualified name* của service interface; dòng bên trong phải khớp *fully qualified name* của provider. Khi dùng SPI theo classpath, tài nguyên này cần được đóng **bên trong** JAR provider đúng đường dẫn `META-INF/services/demo.Greeter`.

### 4.5. Biên dịch, đóng JAR và chạy trên Windows PowerShell

Tại thư mục `demo`, bảo đảm `java`, `javac` và `jar` thuộc JDK 17+ đã nằm trong `PATH`:

```powershell
New-Item -ItemType Directory -Force build/host, build/plugin | Out-Null

# Host chỉ chứa contract và App, chưa có provider.
javac -encoding UTF-8 -d build/host src/demo/Greeter.java src/demo/App.java

# Provider được biên dịch riêng nhưng tham chiếu contract của host.
javac -encoding UTF-8 -cp build/host -d build/plugin src/demo/HelloGreeter.java

# Đóng gói SPI descriptor và implementation vào JAR provider.
New-Item -ItemType Directory -Force build/plugin/META-INF/services | Out-Null
Copy-Item providers/META-INF/services/demo.Greeter build/plugin/META-INF/services/demo.Greeter
jar --create --file build/greeter-plugin.jar -C build/plugin .

# KHÔNG có provider trên classpath.
java -cp build/host demo.App optional
java -cp build/host demo.App fallback

# CÓ provider trên classpath (Windows dùng ; trong classpath).
java -cp 'build/host;build/greeter-plugin.jar' demo.App optional
java -cp 'build/host;build/greeter-plugin.jar' demo.App fallback
java -cp 'build/host;build/greeter-plugin.jar' demo.App required
```

Mỗi lệnh `java` dưới đây in ra stdout **riêng biệt**:

| Lệnh/chế độ | Stdout |
| --- | --- |
| Không có JAR, `optional` | `Không tìm thấy Greeter provider` |
| Không có JAR, `fallback` | Hai dòng: `[host] Tạo fallback` và `Mặc định: Java` |
| Có JAR, `optional` | `Xin chào, Java!` |
| Có JAR, `fallback` | `Xin chào, Java!` |
| Có JAR, `required` | `Xin chào, Java!` |

Chi tiết trường hợp không có provider, `optional`:

```text
Không tìm thấy Greeter provider
```

Trường hợp không có provider, `fallback`:

```text
[host] Tạo fallback
Mặc định: Java
```

Trường hợp có JAR, cả ba chế độ đều in:

```text
Xin chào, Java!
```

Quan sát: **khi đã tìm thấy provider, `fallback` không in dòng `[host] Tạo fallback`**, chứng minh supplier của `orElseGet` không được gọi.

Để thử tình huống provider **bắt buộc nhưng vắng mặt**, chạy thêm:

```powershell
java -cp build/host demo.App required
```

Lệnh kết thúc không thành công và báo `IllegalStateException` có thông điệp `Greeter provider bắt buộc nhưng chưa cài đặt`. Stack trace trên stderr phụ thuộc tên file/dòng mã biên dịch, nên không giả định có một chuỗi stderr cố định.

Trên Linux/macOS, dùng `mkdir -p` thay cho `New-Item`, `cp` thay cho `Copy-Item`, và dấu `:` trong classpath có cả host và JAR, ví dụ `java -cp 'build/host:build/greeter-plugin.jar' demo.App optional`. Mã Java và descriptor giữ nguyên.

### 4.6. Vì sao hai lần chạy khác nhau?

Khi chạy với `-cp build/host`, JVM nhìn thấy `demo.Greeter` và `demo.App` nhưng không thấy descriptor hay provider; `findFirst()` duyệt hết và trả `Optional.empty()`. Khi thêm `build/greeter-plugin.jar` vào classpath, loader thấy `META-INF/services/demo.Greeter`, tìm `demo.HelloGreeter`, khởi tạo rồi trả instance chứa trong `Optional`.

Đây là ví dụ *discovery tại lúc chạy*, không phải hot reload một class đã nạp. Nếu muốn cài/uninstall JAR sau khi host đã chạy và cô lập phụ thuộc, cần thiết kế quản lý `ClassLoader` riêng, `ServiceLoader.load(service, loader)` hoặc module layer và vòng đời tương ứng.

## 5. Phân biệt `findFirst()` trực tiếp và `stream().findFirst()`

Có hai API dễ nhầm lẫn:

| Câu lệnh | Kiểu kết quả | Ý nghĩa |
| --- | --- | --- |
| `ServiceLoader.load(Greeter.class).findFirst()` | `Optional<Greeter>` | Tìm và lấy **instance** provider đầu tiên |
| `ServiceLoader.load(Greeter.class).stream().findFirst()` | `Optional<ServiceLoader.Provider<Greeter>>` | Tìm **descriptor/handle Provider** đầu tiên trong stream |

`ServiceLoader.Provider<S>` có `type()` để xem lớp provider và `get()` để lấy/tạo instance. Ví dụ, khi cần xem lớp trước khi tạo instance:

```java
ServiceLoader<Greeter> loader = ServiceLoader.load(Greeter.class);

Optional<Greeter> selected = loader.stream()
    .filter(provider ->
        provider.type().getName().equals("demo.HelloGreeter"))
    .findFirst()
    .map(ServiceLoader.Provider::get);
```

**Đây là đoạn minh họa** sau khi `Greeter` và provider đã được định nghĩa. Mã lọc bằng tên class là cách trình diễn sự khác nhau giữa metadata và instance; trong ứng dụng thật, nên lọc theo metadata/định danh/capability công bố rõ. Với kiểu module, có thể dựa vào API và thuộc tính được thiết kế cho việc lựa chọn.

Khác biệt quan trọng:

- `loader.findFirst()` lấy instance ngay khi tìm được.
- `loader.stream().findFirst()` trả về `Provider<Greeter>`; chỉ gọi `Provider.get()` khi thực sự muốn tạo/lấy instance.
- `stream().filter(...).findFirst().map(Provider::get)` giúp chọn trước khi tạo instance, nhưng quá trình duyệt metadata vẫn có thể cần tìm/nạp class hoặc gặp lỗi cấu hình; không được coi là thao tác tuyệt đối không có tác dụng phụ.
- Với **nhiều provider**, `findFirst` chỉ lấy phần tử đầu tiên theo thứ tự duyệt, không thực hiện xếp hạng theo nghiệp vụ.
- Với **không provider nào**, cả hai cách cuối cùng đều cho `Optional.empty()`, nếu không phát sinh lỗi cấu hình.

Một lỗi kiểu dữ liệu điển hình:

```java
// Sai kiểu: stream().findFirst() trả Optional<Provider<Greeter>>,
// không phải Optional<Greeter>.
// Optional<Greeter> first = loader.stream().findFirst();

// Đúng nếu cần instance:
Optional<Greeter> first = loader.stream()
    .findFirst()
    .map(ServiceLoader.Provider::get);
```

Nếu chỉ cần instance đầu tiên, dùng trực tiếp `loader.findFirst()` ngắn và rõ hơn.

## 6. Phân biệt không có provider với provider bị lỗi

`Optional.empty()` có nghĩa **không tìm được provider** sau khi hoàn tất duyệt bình thường; nó không bảo đảm cấu hình toàn hệ thống đúng, vì người quản trị có thể quên đưa JAR lên classpath hoặc viết sai đường dẫn descriptor. Cần log classpath/module path, tên contract và nguồn artifact khi tính năng được mong đợi nhưng thiếu provider.

`ServiceConfigurationError` là lỗi khác hẳn. Ví dụ descriptor trỏ tới lớp không tồn tại, lớp không cung cấp service đúng kiểu, không thể khởi tạo provider hoặc phụ thuộc bị thiếu. Không được viết:

```java
// KHÔNG nên: biến lỗi khai báo/nạp provider thành "không có".
try {
    return ServiceLoader.load(Greeter.class).findFirst();
} catch (ServiceConfigurationError error) {
    return Optional.empty();
}
```

Đoạn trên chỉ **minh họa phản ví dụ**, không phải một phương thức đầy đủ. Nó che mất sự cố thực tế, có thể khiến host dùng fallback dù hệ thống đã cài provider sai.

Tại ranh giới của host, khi cần chuyển lỗi sang thông báo vận hành:

```java
try {
    Optional<Greeter> selected =
        ServiceLoader.load(Greeter.class).findFirst();

    selected.ifPresentOrElse(
        p -> System.out.println(p.greet("Java")),
        () -> System.out.println("Không có provider được cài")
    );
} catch (java.util.ServiceConfigurationError error) {
    throw new IllegalStateException(
        "Khai báo hoặc khởi tạo Greeter provider không hợp lệ", error);
}
```

Đây là đoạn minh họa đặt trong phương thức hoặc block hợp lệ. Khi gặp lỗi, thông điệp và nguyên nhân gốc được bảo lưu. Đừng bắt rộng `Error` rồi cho rằng có thể tiếp tục; các lỗi liên kết class như `LinkageError` cần được chẩn đoán và giải quyết dependency/version trước khi bật provider.

### Bảng chẩn đoán nhanh

| Triệu chứng | Khả năng chính | Hành động |
| --- | --- | --- |
| `Optional.empty()` dù đã đóng JAR | Không có JAR trên runtime classpath/module path; descriptor sai tên/vị trí; module thiếu `provides` | Kiểm tra lệnh khởi chạy, nội dung JAR, tên interface/provider |
| Không dùng được `findFirst()` trên `ServiceLoader` | Dùng Java quá cũ (trước Java 9) hoặc sai kiểu biến | Dùng Java 17+ như ví dụ; kiểm tra import |
| Gán `stream().findFirst()` vào `Optional<Greeter>` không biên dịch | Nhầm `Provider<Greeter>` và `Greeter` | Dùng `loader.findFirst()` hoặc thêm `map(Provider::get)` |
| `ServiceConfigurationError` | Khai báo hoặc provider không hợp lệ | Ghi lỗi cụ thể, kiểm tra constructor và phụ thuộc |
| `ClassCastException`/`LinkageError` | Trùng định nghĩa API, loader khác nhau, dependency không tương thích | Chia sẻ contract qua parent loader, kiểm soát version |
| Chọn sai provider khi có nhiều JAR | Dựa vào “đầu tiên” mà không có chính sách | Chọn theo ID/version/capability hoặc cấu hình ưu tiên |
| Sau `reload()` vẫn thấy hành vi cũ | Mong đợi thay lớp đã nạp | `reload()` chỉ xóa cache của `ServiceLoader`; muốn thay code cần chiến lược loader/instance mới |

## 7. Lưu ý khi đưa vào ứng dụng thực tế

1. **Không đồng nhất vắng mặt và thất bại.** `Optional.empty()` dành cho không tìm thấy; lỗi cấu hình phải được ghi nhận riêng. Không dùng fallback để che provider hỏng, nhất là thành phần bắt buộc.
2. **Không phụ thuộc thứ tự `findFirst` để chọn phiên bản.** Nếu hệ thống hỗ trợ nhiều provider cùng service, quản lý danh tính/phiên bản/capability và lựa chọn tường minh.
3. **Chỉ tạo provider khi cần.** Dùng `loader.findFirst()` cho yêu cầu lấy instance đầu tiên; dùng `loader.stream()` kết hợp `Provider.type()` khi muốn khảo sát hoặc lọc class trước bước `get()`.
4. **Nhớ ngữ cảnh class loader.** `ServiceLoader.load(Service.class)` sử dụng context class loader; trong plugin host có loader riêng, cân nhắc `ServiceLoader.load(Service.class, pluginLoader)`. Đảm bảo contract được nạp với danh tính kiểu tương thích.
5. **Không coi `reload()` là hot swap.** Nó xóa cache provider của một `ServiceLoader`; không tự thay thế bytecode/class loader hoặc đóng instance cũ.
6. **Đồng thời và vòng đời.** `ServiceLoader` không hỗ trợ dùng chung không đồng bộ trên nhiều thread. Phương thức `findFirst` giải quyết khám phá; host vẫn phải quản lý `start`, readiness, invocation, `stop` và việc giải phóng tài nguyên.
7. **Không coi plugin JAR là mã an toàn.** Quá trình tìm/tạo provider có thể chạy constructor/static initializer; Java class loader không là ranh giới bảo mật cho mã không tin cậy.

### Câu hỏi tự kiểm tra

- `ServiceLoader.findFirst()` trả kiểu nào, và làm gì khi không có provider?
- Vì sao `Optional.empty()` và `ServiceConfigurationError` không thể xem là cùng một sự kiện?
- Khi nào dùng `ifPresentOrElse`, `orElseGet` và `orElseThrow`?
- Vì sao `loader.stream().findFirst()` không thể gán trực tiếp vào `Optional<Greeter>`?
- Khi có hai provider, liệu `findFirst` có bảo đảm chọn phiên bản mới hơn không?
- Vì sao chạy `App` với mỗi `build/host` thì không thấy provider, nhưng thêm `greeter-plugin.jar` lại thấy?

**Tài liệu API chính thức:** [`ServiceLoader` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html), [`Optional` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html).
