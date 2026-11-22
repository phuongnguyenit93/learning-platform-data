# Khai báo provider bằng META-INF/services trên classpath trong Java

Trong Java, một thư viện có thể công bố **hợp đồng dịch vụ** dưới dạng interface/abstract class, còn ứng dụng hoặc một JAR khác cung cấp các **provider implementations** mà thư viện chưa biết trước khi biên dịch. Cơ chế **Service Provider Interface (SPI)** kết hợp với `java.util.ServiceLoader` giải quyết bài toán này bằng cách đọc một **tệp cấu hình văn bản có tên chính xác**:

```text
META-INF/services/<fully.qualified.ServiceInterface>
```

Ví dụ service interface `api.Greeting` có thể được triển khai bởi `provider.VietnameseGreeting`. Tệp `META-INF/services/api.Greeting` nằm **từ root của classpath entry hoặc JAR**, chứa một dòng `provider.VietnameseGreeting`. Khi application code duyệt `ServiceLoader.load(Greeting.class)` với loader phù hợp, JVM/ServiceLoader khám phá provider, kiểm tra nó thực sự triển khai interface chung, rồi tạo instance khi cần.

Bài thuộc nhóm **Nạp dịch vụ** của Java core – classloader. Trọng tâm: cách khai báo SPI trên **classpath/unnamed module**, cách xác định đúng tên và vị trí `META-INF/services`, cơ chế `ServiceLoader` và class loader, chương trình Java 17+ chạy được từ JAR, lỗi metadata/constructor/namespace, đóng gói nhiều provider, khác biệt với `provides ... with ...` của JPMS, cùng quy trình chẩn đoán.

## 1. Service, provider và discovery là ba vai trò khác nhau

Ta tách hệ thống thành ba thành phần:

1. **Service contract:** interface/abstract class cung cấp API ổn định. Ví dụ `api.Greeting` khai báo `String message()`.
2. **Provider:** class cụ thể đáp ứng contract, ví dụ `provider.VietnameseGreeting`. Provider có thể nằm trong JAR được ứng dụng thêm lúc triển khai thay vì có sẵn trong JAR API.
3. **Discovery/consumer:** code gọi `ServiceLoader` để tìm những provider đã được đăng ký, không hard-code `new VietnameseGreeting()` trong thư viện gốc.

Sơ đồ:

```text
host-classes/                   plugins/greeting-provider.jar
  api/Greeting.class               provider/VietnameseGreeting.class
  app/Main.class                   META-INF/services/api.Greeting
           |                                     |
           | ServiceLoader.load(Greeting.class)  |
           +-------------------------------------+
                               |
                               v
                ServiceLoader đọc service descriptor
                               |
                               v
                     provider.VietnameseGreeting
                               |
                               v
                      implements api.Greeting
                               |
                               v
                       ứng dụng gọi message()
```

**Lợi ích kiến trúc:** thư viện/framework phụ thuộc **interface** thay vì phụ thuộc implementation cụ thể. Nhà cung cấp có thể thêm plugin bằng một JAR được đóng gói đúng, không bắt consumer sửa source để import từng class provider.

Cơ chế này xuất hiện trong nhiều nền tảng: JDBC driver discovery, provider cho parser/transformer, logging, serialization và plugin architectures — nhưng mỗi framework còn có chính sách riêng, không được giả định mọi framework đều dùng `ServiceLoader`.

## 2. Cấu trúc bắt buộc của tệp META-INF/services

Với service interface:

```java
package api;

public interface Greeting {
    String message();
}
```

tệp service configuration cần nằm tại đường dẫn **tính từ root của classpath/JAR**:

```text
META-INF/services/api.Greeting
```

Chú ý từng ký tự:

- Thư mục đúng chính tả **`META-INF`** (viết hoa), rồi **`services`** (chữ thường).
- Tên tệp là **binary name đầy đủ của service**: `api.Greeting`, **không** phải tên provider, không có phần mở rộng `.txt`/`.properties`.
- Nội dung là **binary name đầy đủ của từng provider**, mỗi provider trên một dòng.
- Tên class dùng dấu chấm `.` cho package, không viết path `provider/VietnameseGreeting.class`.
- Tệp phải được giải mã theo **UTF-8** theo hợp đồng `ServiceLoader`.
- Dòng trống và comment bắt đầu bằng `#` được phép; phần từ ký tự `#` đến hết dòng là comment; khoảng trắng bao quanh được bỏ.
- Tên class provider phải hợp lệ, không chứa khoảng trắng/tabs bên trong tên binary.
- Một dòng không có cú pháp `new`, dấu ngoặc, dấu bằng hay tên method; chỉ có **tên class provider**.

Tệp mẫu:

```text
# Providers for api.Greeting
provider.VietnameseGreeting
provider.EnglishGreeting # enabled by default
```

Đoạn trên giả định **cả hai class đã được compile, đóng gói và đáp ứng SPI contract**. Nếu chỉ có `VietnameseGreeting.class`, hãy khai báo **một dòng** `provider.VietnameseGreeting`. Đừng sao chép ví dụ hai dòng vào artifact chỉ có một implementation: `ServiceLoader` có thể báo `ServiceConfigurationError` khi duyệt tới provider bị thiếu.

### Tên service khác tên provider

Giả sử có:

- Service: `com.acme.spi.Codec`.
- Implementation: `com.vendor.FastCodec`.

Tên file phải là `META-INF/services/com.acme.spi.Codec` và nội dung phải có `com.vendor.FastCodec`. Việc thay hai tên cho nhau là lỗi phổ biến khiến ServiceLoader không tìm provider hoặc báo cấu hình sai.

### Nested service hoặc provider

Nếu service là nested/member interface, ví dụ `com.acme.Api$Extension`, tên binary trong descriptor dùng ký tự `$`:

```text
META-INF/services/com.acme.Api$Extension
```

Tương tự provider nested member type có thể cần binary name có `$`. Chỉ nên dùng provider class đáp ứng quy tắc khởi tạo/access; static member class public với public no-arg constructor có thể đáp ứng, còn inner class yêu cầu enclosing instance thường không phù hợp cho kiểu provider classpath truyền thống.

## 3. ServiceLoader tìm provider thế nào trên classpath?

Trong tình huống classpath/unnamed module thông dụng:

1. Consumer gọi `ServiceLoader.load(Greeting.class)` hoặc overload nhận `ClassLoader` tường minh.
2. `ServiceLoader` chọn **loader dùng để discovery** theo contract của overload.
3. Khi bắt đầu **duyệt** service loader, runtime tìm những resource có tên `META-INF/services/api.Greeting` mà loader được chọn có thể nhìn thấy.
4. Service configuration files được đọc, parse tên provider và xác định provider classes.
5. Các provider được kiểm tra, ví dụ **có phải subtype của `api.Greeting` mà consumer đang dùng không**, constructor có hợp lệ không.
6. `ServiceLoader` khởi tạo provider **khi iteration/Provider.get yêu cầu**, sau đó consumer gọi API của service.
7. Những provider đã được instantiate/khám phá có thể được cache trong **đối tượng `ServiceLoader` tương ứng**; `reload()` reset cache đó theo contract.

Mô hình:

```text
ServiceLoader.load(service)
          |
          | chỉ tạo service loader, chưa phải instantiate hết
          v
Consumer bắt đầu for (Service s : loader)
          |
          v
ClassLoader.getResources("META-INF/services/<service-binary-name>")
          |
          v
Đọc resource UTF-8, parse tên provider
          |
          v
Load provider class -> kiểm tra subtype/constructor
          |
          v
Instantiate provider khi iterator.next()/Provider.get()
          |
          v
consumer gọi method của interface chung
```

Sơ đồ là cách hiểu khái quát của đường classpath provider lookup, không mô tả chi tiết mọi tối ưu, module provider hoặc cách caching nội bộ của từng JDK. **Hợp đồng quan trọng:** discovery/instantiation chủ yếu **lazy**, nên lỗi cấu hình có thể chỉ xuất hiện **khi thực sự duyệt** thay vì ngay tại lệnh `ServiceLoader.load(...)`.

### Quy tắc provider class trên classpath

Với provider nằm trong **unnamed module/classpath**, cách chuẩn là:

- Provider là **class public**, không abstract và có thể instantiate.
- Provider **implement/extend** service type được yêu cầu, trực tiếp hoặc gián tiếp.
- Provider có **public no-argument constructor** dùng để tạo instance.
- Constructor có thể thực thi logic nghiệp vụ, do vậy cần cân nhắc side effects.
- Các phụ thuộc mà provider cần cũng phải hiện diện theo loader/classpath phù hợp.

`ServiceLoader` có một hình thức provider factory qua **public static `provider()` method** đối với một số **explicit named module providers**. **Không dùng nó làm thay thế mặc định cho public no-arg constructor của provider trong unnamed module trên classpath**.

## 4. Ví dụ Java 17+ hoàn chỉnh: Provider nằm trong JAR khác ứng dụng

Ta tạo một host chứa API/consumer, một JAR chứa provider và descriptor. Có thể chạy hoàn toàn bằng JDK 17+ và không cần framework.

### 4.1 Cấu trúc thư mục

```text
spi-demo/
├── src/
│   ├── api/
│   │   └── Greeting.java
│   └── app/
│       └── Main.java
├── provider-src/
│   └── provider/
│       └── VietnameseGreeting.java
├── host-classes/                         # class output của host
├── provider-classes/
│   ├── provider/
│   │   └── VietnameseGreeting.class       # sau biên dịch
│   └── META-INF/
│       └── services/
│           └── api.Greeting               # tệp văn bản, KHÔNG có .txt
└── plugins/
    └── greeting-provider.jar              # sau bước jar
```

Tạo các directories `host-classes`, `provider-classes/META-INF/services` và `plugins` trước khi chạy các lệnh biên dịch. Nếu dùng IDE/build tool, có thể để nó tạo các output directories tương ứng.

### 4.2 Service contract

File `src/api/Greeting.java`:

```java
package api;

public interface Greeting {
    String message();
}
```

Đây là interface chung. Consumer và provider **phải resolve đúng cùng runtime `api.Greeting` class identity**; trong ví dụ, cả hai dùng API do application/system loader định nghĩa.

### 4.3 Consumer trong host

File `src/app/Main.java`:

```java
package app;

import api.Greeting;
import java.util.ServiceLoader;

public class Main {
    public static void main(String[] args) {
        System.out.println("before load");

        ServiceLoader<Greeting> services =
                ServiceLoader.load(Greeting.class);

        System.out.println("after load");

        int count = 0;
        for (Greeting g : services) {
            System.out.println(g.getClass().getName()
                    + ": " + g.message());
            count++;
        }

        System.out.println("providers=" + count);
    }
}
```

Consumer **không import `provider.VietnameseGreeting`**. Nó chỉ biết interface và đọc provider qua ServiceLoader. Trong chương trình command-line thông thường, main thread có TCCL phù hợp với application/system loader, nên `ServiceLoader.load(Greeting.class)` thấy provider JAR trên classpath.

### 4.4 Provider implementation

File `provider-src/provider/VietnameseGreeting.java`:

```java
package provider;

import api.Greeting;

public class VietnameseGreeting implements Greeting {
    public VietnameseGreeting() {
        System.out.println("provider constructor");
    }

    @Override
    public String message() {
        return "Xin chao!";
    }
}
```

Provider class và constructor đều **public**. Dòng `provider constructor` giúp chứng minh rằng lời gọi `ServiceLoader.load` chưa instantiate provider ngay; constructor chỉ in khi consumer bắt đầu iteration.

### 4.5 Tệp khai báo provider

File `provider-classes/META-INF/services/api.Greeting` (UTF-8, **nội dung chỉ một dòng**):

```text
provider.VietnameseGreeting
```

Lưu ý: đây là file trong output **của provider**, không phải file Java; `javac` **không tự tạo descriptor** và cũng không tự copy resource. Nó phải được thêm bằng tay, bằng Gradle/Maven resources processing hoặc qua tool đóng gói JAR.

### 4.6 Biên dịch host, provider và đóng gói JAR

Chạy từ thư mục `spi-demo`:

```bash
javac --release 17 -d host-classes src/api/Greeting.java src/app/Main.java
javac --release 17 -cp host-classes -d provider-classes provider-src/provider/VietnameseGreeting.java
jar --create --file plugins/greeting-provider.jar -C provider-classes .
```

Giải thích:

1. `javac -d host-classes` tạo `api/Greeting.class` và `app/Main.class` dưới root host.
2. `javac -cp host-classes` cho provider compile được vì nó implement `api.Greeting` từ host.
3. `-d provider-classes` xuất `provider/VietnameseGreeting.class` vào output riêng.
4. `jar -C provider-classes .` thêm **tất cả nội dung từ root provider-classes** vào JAR, bao gồm `META-INF/services/api.Greeting`. Đây là điểm then chốt; không được đóng gói thành `provider-classes/META-INF/services/...` bên trong JAR.

Kiểm tra JAR:

```bash
jar --list --file plugins/greeting-provider.jar
```

Ngoài manifest/directories, phải có ít nhất:

```text
provider/VietnameseGreeting.class
META-INF/services/api.Greeting
```

### 4.7 Chạy với provider JAR

**Windows (PowerShell/CMD):**

```bash
java -cp "host-classes;plugins/greeting-provider.jar" app.Main
```

**Linux/macOS:**

```bash
java -cp "host-classes:plugins/greeting-provider.jar" app.Main
```

Stdout đã được kiểm tra khi biên dịch với `javac --release 17` và thực thi Java:

```text
before load
after load
provider constructor
provider.VietnameseGreeting: Xin chao!
providers=1
```

Tại sao thứ tự quan trọng?

- `before load` in **trước** khi tạo `ServiceLoader`.
- `after load` xuất hiện **trước constructor**; chứng minh `ServiceLoader.load` không tự instantiate provider ngay.
- `provider constructor` chỉ xuất hiện khi vòng `for` bắt đầu nhận provider.
- `provider.VietnameseGreeting: Xin chao!` cho biết discovery đúng class và gọi API interface thành công.
- `providers=1` cho thấy trong classpath của ví dụ chỉ có một provider hợp lệ.

### 4.8 Thử bỏ provider khỏi classpath

Không cần sửa hoặc xóa file. Chạy lại **chỉ với host**:

```bash
java -cp host-classes app.Main
```

Stdout đã được kiểm tra:

```text
before load
after load
providers=0
```

**`ServiceLoader.load` không báo lỗi chỉ vì không có provider.** Nó trả một ServiceLoader mà khi duyệt không có phần tử. Đó là hành vi đúng và khác với việc descriptor có tên provider bị sai/hỏng, có thể phát `ServiceConfigurationError`.

Nếu đưa `plugins/greeting-provider.jar` lên classpath nhưng **không có descriptor**, class `provider.VietnameseGreeting` vẫn có thể tồn tại và gọi được qua reflection, nhưng **ServiceLoader không tự quét toàn bộ JAR để suy đoán lớp nào implements `Greeting`**. Khai báo provider là bước không thể bỏ qua trong cơ chế SPI classpath.

## 5. Vì sao đặt META-INF/services ở sai root sẽ thất bại?

Classpath là tập hợp **roots**. Đối với JAR, root là đỉnh bên trong archive; đối với directory, root là folder được thêm vào `-cp`.

**Đúng với directory:**

```text
provider-classes/
├── provider/VietnameseGreeting.class
└── META-INF/services/api.Greeting
```

Khi chạy:

```bash
java -cp "host-classes;provider-classes" app.Main
```

(Windows; Linux/macOS đổi `;` thành `:`.)

**Đúng với JAR:**

```text
greeting-provider.jar
├── provider/VietnameseGreeting.class
└── META-INF/services/api.Greeting
```

**Sai khi vô tình để thêm tầng thư mục:**

```text
greeting-provider.jar
└── provider-classes/
    ├── provider/VietnameseGreeting.class
    └── META-INF/services/api.Greeting
```

Nếu artifact như trường hợp sai được dùng làm classpath JAR, resource thực tế là `provider-classes/META-INF/services/api.Greeting` chứ không phải `META-INF/services/api.Greeting` ở root nên ServiceLoader không tìm thấy descriptor chuẩn.

Một lỗi khác là file thực tế `api.Greeting.txt` vì hệ điều hành ẩn extension `.txt`; `ServiceLoader` chỉ tìm tên **`api.Greeting` đúng nguyên văn**.

**Quy tắc chẩn đoán:** trước khi debug Java code, chạy `jar --list --file ...` và xác nhận đường dẫn descriptor ở root, sau đó xác nhận `provider/...class` và toàn bộ dependencies được đóng gói đúng.

## 6. ServiceLoader dùng class loader nào để tìm descriptor?

Đây là chủ đề gắn trực tiếp với **classloader**:

```java
ServiceLoader<Greeting> services =
        ServiceLoader.load(Greeting.class);
```

Theo hợp đồng Java SE 17, overload `load(Class<S>)` dùng **thread context class loader (TCCL)**:

```java
ClassLoader tccl =
        Thread.currentThread().getContextClassLoader();

ServiceLoader<Greeting> services =
        ServiceLoader.load(Greeting.class, tccl);
```

Đoạn trên là **mã minh họa**, giả định `Greeting` đã có. Hai cách tương đương về lựa chọn loader tại thời điểm tạo loader.

Có thể chọn loader một cách tường minh:

```java
ClassLoader pluginLoader = /* loader của plugin đã tạo */;

ServiceLoader<Greeting> services =
        ServiceLoader.load(Greeting.class, pluginLoader);
```

Đây là **mã minh họa**, cần khai báo giá trị thực cho `pluginLoader`. Đặc biệt hữu ích khi provider JAR được một child `URLClassLoader` quản lý, còn interface `Greeting` ở parent loader.

### Đồ thị nhìn thấy thường gặp

```text
Application/System loader
    ├── api.Greeting
    └── app.Main
          ^
          | parent-first delegation
Plugin URLClassLoader
    ├── provider.VietnameseGreeting
    └── META-INF/services/api.Greeting
```

Nếu consumer do parent loader định nghĩa, nó không tự thấy resource/class chỉ nằm ở loader con. Nhưng nếu dùng:

```java
ServiceLoader.load(Greeting.class, pluginLoader)
```

thì discovery được thực hiện theo plugin loader, có thể tìm descriptor và provider class của child. Plugin loader cần delegate **api.Greeting** tới parent để provider và consumer dùng **cùng interface runtime type**.

**Không nhầm TCCL với `Class.forName(String)`.** Lời gọi `Class.forName("provider.VietnameseGreeting")` mặc định dùng **defining loader của class chứa call site**, không tự chọn TCCL. Vì thế việc đổi TCCL có thể khiến `ServiceLoader.load` phát hiện provider, nhưng không nhất thiết khiến một helper ở parent gọi `Class.forName(String)` tìm được provider class.

### Khi nào cần set TCCL?

Framework/app server có thể thiết lập context loader riêng cho thread đang chạy service discovery:

```java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    for (Greeting g : ServiceLoader.load(Greeting.class)) {
        System.out.println(g.message());
    }
} finally {
    thread.setContextClassLoader(previous);
}
```

Đây là **đoạn minh họa**, giả định `pluginLoader` và `Greeting` tồn tại. `try/finally` bắt buộc quan trọng khi dùng thread pool: nếu để lại TCCL của plugin A trên worker thread, request B có thể khám phá provider sai hoặc giữ plugin loader A sống quá hạn.

**Không phải API nào cũng đọc TCCL.** Chỉ dùng hoặc set TCCL khi hợp đồng của API thực sự sử dụng nó; khi có loader cụ thể, overload `ServiceLoader.load(service, loader)` rõ ràng và dễ kiểm soát.

## 7. Cơ chế lazy và cache của ServiceLoader

Trong Java 17:

```java
ServiceLoader<Greeting> loader =
        ServiceLoader.load(Greeting.class);
```

dòng này chủ yếu thiết lập đối tượng discovery. Khi duyệt:

```java
for (Greeting provider : loader) {
    System.out.println(provider.message());
}
```

`ServiceLoader` khám phá và khởi tạo provider khi cần. Một số chi tiết:

- `iterator()` là **lazy**: không cần instantiate mọi provider từ đầu.
- `iterator.hasNext()` có thể cần tìm/read metadata hoặc load provider class để biết còn phần tử; đừng coi nó như phép kiểm tra hoàn toàn không side effect.
- `iterator.next()` trả provider instance và có thể gọi constructor; exception có thể chỉ xuất hiện tại đây.
- `stream()` trả `Stream<ServiceLoader.Provider<S>>`. `Provider.type()` cho biết class provider; `Provider.get()` mới yêu cầu instance (theo contract tương ứng).
- Một `ServiceLoader` có thể **cache** providers đã được khởi tạo; duyệt lần sau trên cùng object thường thấy cached instances.
- `reload()` xóa cache để các lần duyệt sau khám phá lại theo loader/source phù hợp; **không tải lại bytecode đã định nghĩa hoặc cập nhật JAR đã bị class loader giữ ở namespace cũ**.
- `ServiceLoader` không đảm bảo **thread-safe** khi chia sẻ cùng một đối tượng giữa nhiều thread. Cần đồng bộ hoặc tạo service loader riêng theo scope.

Ví dụ code minh họa:

```java
ServiceLoader<Greeting> services =
        ServiceLoader.load(Greeting.class);
for (Greeting g : services) {
    System.out.println(g.getClass().getName());
}
services.reload();
```

Đây là **đoạn minh họa**, không phải chương trình đầy đủ. Gọi `reload()` có ý nghĩa khi trạng thái discovery thay đổi theo cách loader thực sự có thể nhìn thấy; nó không “ép” một `URLClassLoader` đã closed tìm lại JAR mới.

### Có thể có 0, 1 hoặc nhiều providers

Hợp đồng `ServiceLoader` không buộc chỉ có một implementation. Nếu nhiều JAR trên classpath có cùng service descriptor, `ServiceLoader` có thể đọc nhiều configuration resources và trả về nhiều providers. Ứng dụng phải quyết định chính sách: dùng tất cả, chọn một theo cấu hình/priority riêng hay báo lỗi nếu không duy nhất.

Đừng mặc định thứ tự providers giữa các JAR là một hợp đồng business ổn định. Thứ tự tìm resources/classpath có thể phụ thuộc launcher, build tool, loader policy và cách artifact được đóng gói. Nếu ưu tiên quan trọng, ứng dụng nên có metadata chọn provider rõ ràng.

## 8. Khai báo nhiều providers

Giả sử có hai class thật:

- `provider.VietnameseGreeting`
- `provider.EnglishGreeting`

Một descriptor có thể chứa:

```text
# Greeting implementations
provider.VietnameseGreeting
provider.EnglishGreeting
```

Mỗi provider phải là class hợp lệ, public, triển khai `api.Greeting` và có public zero-argument constructor theo classpath SPI rules.

### Nhiều JAR cùng cung cấp service

```text
providers-a.jar:
    META-INF/services/api.Greeting
      -> provider.VietnameseGreeting

providers-b.jar:
    META-INF/services/api.Greeting
      -> other.EnglishGreeting
```

Nếu cả hai JAR trên classpath phù hợp, `ServiceLoader` có thể thấy cả hai. Nếu cùng **một provider class name** được lặp nhiều lần trong cùng một hoặc nhiều configuration files, ServiceLoader bỏ qua **duplicate provider names** theo đặc tả.

Tuy nhiên, **duplicate binary class name** trong hai JAR không phải lỗi “duplicate descriptor”: classpath loader có thể chọn một class definition theo lookup order. Khi có version conflict, cùng tên `provider.FastCodec` nhưng bytecode khác nhau có thể khiến `ServiceLoader` chạy nhầm bản hoặc lỗi linkage.

### Khi tạo fat/uber JAR

Maven Shade, Gradle Shadow hoặc một công cụ đóng gói khác có thể **hợp nhất nhiều provider JAR thành một JAR**. Nếu công cụ chỉ copy một file `META-INF/services/api.Greeting` và ghi đè file còn lại, **các provider bị mất khai báo** dù class files vẫn được giữ.

Cần dùng chức năng **merge/transform service descriptor files**, không chỉ copy class files. Nếu relocate package/class name, phải cập nhật **nội dung service descriptors và tên service descriptor** cho khớp binary names mới.

Kết quả cuối cần kiểm tra bằng `jar --list` và xem **nội dung** file `META-INF/services/...` trong artifact, không chỉ kiểm tra class files. Một JAR fat với nhiều class provider nhưng descriptor chỉ còn một dòng sẽ chỉ đăng ký một provider ở đường classpath SPI.

## 9. Những lỗi phổ biến và thông báo thường gặp

| Triệu chứng | Nguyên nhân phổ biến | Kiểm tra |
| --- | --- | --- |
| `ServiceLoader` duyệt ra **0 provider** | Không có descriptor trong classpath/JAR; resource path sai; loader không nhìn thấy provider JAR | `jar --list`, `getResources`, classpath/TCCL |
| `ServiceConfigurationError: Provider ... not found` | Descriptor nêu binary name nhưng class không có trong loader/dependency | Tên class, package, JAR entries, loader |
| `ServiceConfigurationError: ... not a subtype` | Provider không implement **đúng runtime service interface** hoặc có hai bản interface do hai loaders định nghĩa | `isAssignableFrom`, `getClassLoader()` |
| `ServiceConfigurationError: Unable to get public no-arg constructor` | Provider classpath thiếu constructor public không tham số hoặc class không instantiate được | Visibility, constructors, abstract class |
| `ServiceConfigurationError` khi tạo provider | Constructor ném exception, lỗi initialization/linking hoặc có dependency thiếu | Stack trace, cause, runtime classpath |
| Một provider xuất hiện nhưng provider khác không | Descriptor chỉ còn một entry do fat JAR merger, hoặc provider lỗi khi duyệt tới | Nội dung toàn bộ `META-INF/services` |
| IDE chạy được nhưng `java -cp` không | IDE đã add resource root / runtime JAR nhưng script không | So classpath, build output roots |
| Provider hoạt động với `-cp` nhưng không với `--module-path` | Chuyển semantics sang named/automatic modules, `uses`/`provides`, resolution và module layers | Định vị artifact và module graph |
| Provider mới không xuất hiện sau hot deploy | ClassLoader cũ/cached ServiceLoader cũ không thấy artifact mới | New loader, `reload()` chỉ khi nguồn mới nhìn thấy, plugin lifecycle |
| `ClassCastException` giữa API và provider | Hai classloader định nghĩa bản sao interface cùng tên | Shared API parent loader và class identity |

Quan trọng: `ServiceConfigurationError` là **`Error`**, không phải `Exception` checked như `ClassNotFoundException`. Lỗi provider discovery có thể phát từ `iterator.hasNext()`, `next()` hoặc stream operation. Đừng bọc toàn bộ logic `ServiceLoader` trong `catch (ClassNotFoundException)` rồi nghĩ sẽ bắt mọi lỗi SPI.

Cũng đừng dựa vào kiểu thông báo lỗi chính xác để xác định root cause; nhiều JDK/module/classloader configurations có thể tạo message khác nhau. Luôn đọc **cause** và đường tìm thực tế.

## 10. Chẩn đoán descriptor có được nhìn thấy không

Trong một classpath application, có thể kiểm tra tên resource **trực tiếp qua loader**:

```java
ClassLoader context =
        Thread.currentThread().getContextClassLoader();

java.util.Enumeration<java.net.URL> descriptors =
        context.getResources("META-INF/services/api.Greeting");

while (descriptors.hasMoreElements()) {
    System.out.println(descriptors.nextElement());
}
```

Đây là **đoạn minh họa** đặt trong method xử lý `java.io.IOException`, giả định `context` không null. URL có thể là `file:/...` hoặc `jar:file:/...!/META-INF/services/api.Greeting`. Nếu không có kết quả, hãy kiểm tra TCCL, classpath và việc đóng gói JAR.

Lưu ý:

- `ClassLoader.getResources(name)` tìm **resource**, không khẳng định class provider đã compile đúng hoặc constructor hoạt động.
- Với Java 9+ named modules, resource encapsulation/exports/opens và lookup rules có thể khác đường classpath thông thường.
- Khi context loader là `null`, cần chọn loader thay thế **theo contract API và kiến trúc** trước khi gọi method trên reference null; `ServiceLoader.load(service)` có xử lý loader semantics riêng của nó.
- Kết quả tìm được descriptor chỉ là **bước đầu**, cần duyệt `ServiceLoader` để kiểm tra provider class thực tế.

Nếu muốn debug class identity:

```java
Class<?> providerClass =
        Class.forName("provider.VietnameseGreeting",
                      false, pluginLoader);

System.out.println(Greeting.class.isAssignableFrom(providerClass));
System.out.println(Greeting.class.getClassLoader());
System.out.println(providerClass.getClassLoader());
```

Đây là **mã minh họa**, giả định `Greeting` và `pluginLoader` đã có, method xử lý `ClassNotFoundException`. Nếu `isAssignableFrom` trả `false` dù provider source có `implements Greeting`, nghi ngờ plugin tự định nghĩa lại một bản `api.Greeting` khác với host.

### Một quy trình gỡ lỗi ngắn gọn

1. **Xác minh service binary name.** `Greeting.class.getName()` phải đúng `api.Greeting`, không nhầm provider name.
2. **Xác minh descriptor path.** Trong JAR cần có đúng `META-INF/services/api.Greeting` tại root.
3. **Xác minh nội dung descriptor.** Một tên binary provider hợp lệ mỗi dòng, UTF-8, không thêm `.class` hoặc dấu slash.
4. **Xác minh bytecode provider.** `provider/VietnameseGreeting.class` phải nằm trong JAR hoặc classpath root loader nhìn thấy.
5. **Xác minh visibility/constructor.** Class public, concrete, constructor public no-arg, đúng service subtype.
6. **Xác minh runtime loader.** `ServiceLoader.load(service)` dùng TCCL; khi plugin ở child, truyền đúng loader explicit.
7. **Xác minh runtime dependencies.** Class provider có thể load được nhưng khởi tạo lỗi vì thư viện khác không có hoặc static initializer thất bại.
8. **Xác minh đóng gói fat JAR.** Service descriptor có bị ghi đè bởi merging/shading không?
9. **Xác minh JPMS mode.** Artifact ở classpath/unnamed hay module path/automatic/explicit? Cách khai báo provider khác nhau.
10. **Thử chương trình tối thiểu.** Chạy dạng `-cp` với interface, provider JAR và descriptor để tách lỗi framework khỏi lỗi SPI metadata.

## 11. Phân biệt SPI classpath với khai báo provider của JPMS

Trên **classpath/unnamed module**, provider thường đăng ký bằng tệp:

```text
META-INF/services/api.Greeting
```

và `ServiceLoader` đọc resource tương ứng.

Với **explicit named modules** từ Java 9, service consumption/provider registration thường được mô tả ngay trong `module-info.java`:

```java
module m.consumer {
    requires m.api;
    uses api.Greeting;
}
```

```java
module m.provider {
    requires m.api;
    provides api.Greeting with provider.VietnameseGreeting;
}
```

Đây là **hai tệp `module-info.java` minh họa riêng biệt**, không ghép hai `module` declarations vào một file. Module `m.api` phải công bố API package phù hợp. Với named module, `uses` thường bắt buộc cho code trực tiếp gọi `ServiceLoader` với service; `provides ... with ...` là khai báo provider trong descriptor module. Provider của explicit named module có thể dùng public constructor hoặc **provider method** theo yêu cầu API và ngữ cảnh.

**Automatic module** là named module suy ra từ non-modular JAR trên module path. Các service configuration files `META-INF/services` trong JAR này có thể được module finder dùng để tạo khai báo `provides` phù hợp; automatic module còn có các quy tắc readability/exports riêng. Không nói rằng automatic module giống hệt classpath unnamed module, dù JAR content ban đầu là legacy.

### So sánh ngắn

| Tiêu chí | Classpath/unnamed module | Explicit named module |
| --- | --- | --- |
| Đăng ký provider | `META-INF/services/<service>` | `provides Service with Provider;` |
| Consumer khai báo dùng service | Không có `module-info` | `uses Service;` |
| Provider constructor | Public zero-arg constructor theo classpath provider form | Có thêm provider factory method form theo hợp đồng |
| Tìm lớp | Theo classpath loader và delegation | Theo module resolution, module-to-loader mapping và service discovery |
| TCCL | `ServiceLoader.load(Class)` dùng TCCL | API overload cũng có semantics module/service resolution; chọn module/layer phù hợp |
| Đóng gói | JAR/classpath root phải có descriptor file | Modular JAR chứa `module-info.class`, `provides` metadata |

Đừng đồng thời để **bản trùng class** của cùng provider trên cả classpath và module path rồi mong chỉ có một runtime type. Đường nạp cụ thể, module graph và class loader có thể khiến namespace/identity khác với dự kiến.

## 12. ServiceLoader trong plugin có class loader riêng

Plugin frameworks thường có service interface do host định nghĩa và provider do plugin loader định nghĩa:

```text
Host/system loader
  ├── api.Greeting
  └── host.PluginManager
           ^
           |
           | parent delegation
           |
Plugin URLClassLoader
  ├── provider.VietnameseGreeting
  └── META-INF/services/api.Greeting
```

Nếu code `PluginManager` chỉ gọi:

```java
ServiceLoader.load(Greeting.class, Greeting.class.getClassLoader())
```

thì discovery bắt đầu từ **loader của interface**, thường là parent/system. Loader cha không mặc nhiên thấy descriptor chỉ ở child loader, nên có thể nhận **0 provider**.

Để chọn đúng vùng plugin, dùng:

```java
ServiceLoader<Greeting> services =
        ServiceLoader.load(Greeting.class, pluginLoader);
```

Code trên là **đoạn minh họa**, `pluginLoader` phải là loader đã tạo đúng cho deployment. API `Greeting` cần được parent/shared loader định nghĩa để host/provider cùng identity. Tránh copy interface vào child theo child-first policy khiến plugin tự define một `api.Greeting` khác.

### TCCL và thread pool

Một thread pool worker có thể mang TCCL khác thread gọi submit. Nếu `ServiceLoader.load(service)` được gọi trong worker, hãy kiểm tra TCCL **tại chính worker**. Khi đổi context tạm thời, restore trong `finally`:

```java
Thread worker = Thread.currentThread();
ClassLoader before = worker.getContextClassLoader();
try {
    worker.setContextClassLoader(pluginLoader);
    // ServiceLoader.load(Greeting.class) trong phạm vi này.
} finally {
    worker.setContextClassLoader(before);
}
```

Đây là **đoạn minh họa**, không phải file chạy độc lập. Nếu worker giữ TCCL trỏ vào plugin loader sau khi plugin đã “undeploy”, vừa có nguy cơ khám phá nhầm provider, vừa có thể giữ class loader sống và gây metaspace leak.

**`ServiceLoader` không phải cơ chế sandbox**. Đọc và khởi tạo provider có nghĩa chương trình có thể **chạy code từ constructor/static initializer** của provider. Chỉ sử dụng provider artifacts từ nguồn được tin cậy, kiểm tra version/signature/dependencies và áp dụng biện pháp cô lập phù hợp.

## 13. Cách kiểm thử descriptor tự động trong dự án thực

Dù dùng Maven, Gradle hay IDE, bạn nên có test xác nhận **artifact đã build** chứ không chỉ source tree.

### 13.1 Kiểm tra resource

```java
var resources = Thread.currentThread()
        .getContextClassLoader()
        .getResources("META-INF/services/api.Greeting");

if (!resources.hasMoreElements()) {
    throw new AssertionError("SPI descriptor missing");
}
```

Đây là **đoạn minh họa trong method xử lý IOException**, giả định TCCL phù hợp và non-null. Test này chỉ đảm bảo resource được tìm thấy, chưa khẳng định provider class hợp lệ.

### 13.2 Kiểm tra có ít nhất một provider

```java
boolean found = ServiceLoader.load(Greeting.class)
        .iterator()
        .hasNext();

if (!found) {
    throw new AssertionError("No Greeting provider discovered");
}
```

Đây là **đoạn minh họa** trong môi trường đã có `Greeting` và runtime loader phù hợp. Nếu metadata hỏng, thao tác `hasNext()` có thể phát `ServiceConfigurationError` thay vì chỉ trả `false`.

### 13.3 Kiểm tra class identity và gọi method

```java
for (Greeting greeting : ServiceLoader.load(Greeting.class)) {
    if (!Greeting.class.isInstance(greeting)) {
        throw new AssertionError("Provider type mismatch");
    }
    System.out.println(greeting.message());
}
```

Đây cũng là **đoạn minh họa**. Nếu ServiceLoader đã trả về `Greeting` instance hợp lệ, `isInstance` thường hiển nhiên true; đoạn code thể hiện tiêu chí contract trong test. Với provider phức tạp, thêm assert về hành vi thực của service (kết quả, configuration, lifecycle).

### 13.4 Kiểm tra JAR sau packaging

Chạy:

```bash
jar --list --file plugins/greeting-provider.jar
```

Sau đó nếu dùng Maven Shade/Gradle Shadow, kiểm tra nội dung `META-INF/services/api.Greeting` trong **final artifact**. Đối với provider multi-JAR, đảm bảo resource merge chính xác. Không suy từ việc `src/main/resources/META-INF/services/...` tồn tại rằng nó chắc chắn đã được copy vào JAR cuối.

## 14. Checklist ứng dụng đúng ngay lần đầu

1. **Service interface** có binary name nào? Trong ví dụ: `api.Greeting`.
2. **Provider implementation** có tên binary đầy đủ nào? `provider.VietnameseGreeting`.
3. Descriptor có ở đúng **`META-INF/services/<ServiceBinaryName>`** tại classpath/JAR root không?
4. Nội dung file UTF-8, một provider name mỗi dòng, không có extension/path/constructor syntax không?
5. Provider class public, concrete, implement đúng service runtime type và có public no-arg constructor chưa?
6. JAR chứa provider có mặt **trên runtime classpath hoặc loader thực sự được dùng để discovery** không?
7. Nếu dùng TCCL, context của **thread đang gọi ServiceLoader** có đúng loader không?
8. Parent/child loaders có dùng **cùng interface `Class<?>`** hay đang có bản sao API trong plugin?
9. Đã **duyệt ServiceLoader** chưa? Không có provider không nhất thiết gây lỗi khi chỉ gọi `load`.
10. Có `ServiceConfigurationError` xảy ra tại `iterator`/`stream` không? Đã log stack/cause?
11. Nếu là fat JAR, descriptor nhiều providers đã được merge chưa?
12. Nếu chuyển lên module path, đã xét automatic/explicit modules, `uses`/`provides`, resolution và access chưa?
13. Nếu cần hot reload, có loader/ServiceLoader mới và cleanup TCCL/cache/instances đúng scope chưa?
14. Đã có integration test chạy **artifact đã đóng gói** thay vì chỉ code trong IDE chưa?

## 15. Tự kiểm tra có đáp án

**Câu 1.** File nào đăng ký `provider.VietnameseGreeting` như một implementation của `api.Greeting`?

**Đáp án:** `META-INF/services/api.Greeting`, trong file chứa `provider.VietnameseGreeting` ở một dòng UTF-8.

**Câu 2.** Nếu file nằm ở `src/META-INF/services/api.Greeting` nhưng runtime chỉ có `-cp out` và không copy file vào `out`, ServiceLoader có tự tìm ở `src` không?

**Đáp án:** Không. Loader chỉ tìm resource từ những classpath entries nó thấy. Cần copy descriptor vào đúng output/resource root hoặc đóng gói trong JAR phù hợp.

**Câu 3.** `ServiceLoader.load(Greeting.class)` có luôn tạo instance ngay không?

**Đáp án:** Không. Service loading lazy; provider thường được instantiate trong lúc duyệt hoặc khi gọi `Provider.get()`. Ví dụ đã chứng minh dòng `after load` in trước `provider constructor`.

**Câu 4.** Provider class có private no-arg constructor dùng được cho SPI trên classpath không?

**Đáp án:** Không theo classpath provider constructor form thông thường. Provider cần public class với public zero-argument constructor và subtype phù hợp.

**Câu 5.** Nếu descriptor ghi `provider/VietnameseGreeting.class`, có hợp lệ không?

**Đáp án:** Không. Nội dung phải là **binary class name**: `provider.VietnameseGreeting`, không phải filesystem/JAR entry path.

**Câu 6.** Vì sao có provider class trên classpath nhưng `ServiceLoader` trả 0?

**Đáp án:** Có thể thiếu descriptor, descriptor path/name sai, runtime loader không thấy descriptor, hoặc class chỉ ở vị trí khác; `ServiceLoader` không tự quét mọi class để tìm subtype.

**Câu 7.** Nếu plugin provider chỉ có trong child loader, nhưng host gọi `ServiceLoader.load(Greeting.class, Greeting.class.getClassLoader())`, chuyện gì có thể xảy ra?

**Đáp án:** Nếu interface ở parent/system loader và descriptor chỉ ở child, parent không tự tìm xuống child, nên discovery có thể không thấy provider. Truyền explicit child loader hoặc dùng TCCL phù hợp.

**Câu 8.** Vì sao cùng tên interface `api.Greeting` vẫn có thể khiến provider bị báo không phải subtype?

**Đáp án:** Host và plugin có thể đã định nghĩa **hai runtime interfaces khác nhau** qua hai defining class loaders. JVM identity dựa binary name + defining loader; cần chia sẻ API ở parent/shared loader.

**Câu 9.** Nếu nhiều JAR đều có descriptor cho `api.Greeting`, có bắt buộc chỉ chọn provider đầu tiên không?

**Đáp án:** Không. `ServiceLoader` có thể phát hiện nhiều providers; consumer phải có chính sách chọn/sử dụng. Tránh dựa vào classpath order như một cơ chế priority business ổn định.

**Câu 10.** Chuyển non-modular provider JAR từ classpath sang module path nhưng không sửa code, có thể gọi nó là unnamed module tiếp không?

**Đáp án:** Không theo mặc định. JAR non-modular trên module path có thể trở thành automatic **named** module nếu được resolve; semantics JPMS/service discovery thay đổi so với classpath unnamed module.

**Câu 11.** Vì sao provider trong fat JAR bị mất dù `.class` vẫn tồn tại?

**Đáp án:** Build/shading tool có thể ghi đè `META-INF/services` thay vì merge descriptors. Khi ấy ServiceLoader chỉ biết những provider names còn lại trong final resource.

**Câu 12.** `reload()` có đổi class bytes của `provider.VietnameseGreeting` đã load sang version mới không?

**Đáp án:** Không. `reload()` xóa cache của `ServiceLoader`; class identity/bytecode còn do defining loader quyết định. Hot reload thực sự thường cần plugin loader mới, registry/TCCL cleanup và quản lý lifecycle.

## Kết luận

Đối với SPI trên **classpath**, cần đồng thời đúng **service interface**, **public provider implementation**, **tệp `META-INF/services/<service-binary-name>` ở classpath/JAR root** và **ClassLoader dùng cho discovery**. `ServiceLoader` dựa vào các file cấu hình này để tìm provider một cách lazy, chứ không tự quét mọi class trong JAR và cũng không tự bắc cầu từ loader cha xuống mọi plugin loader con.

Muốn hệ thống dễ mở rộng và dễ debug, hãy giữ shared API ở loader chung, đảm bảo descriptor được copy/merge vào artifact cuối, truyền loader/TCCL theo hợp đồng rõ ràng, và thử nghiệm ít nhất cả hai trường hợp **có JAR provider** (tìm được một implementation) và **không có JAR** (0 provider, không phải cấu hình hỏng).

**Tài liệu chính thức Java 17:**

- [`java.util.ServiceLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html) — provider configuration files, public no-arg constructor trên classpath, lazy discovery, caching, `load`/`loadInstalled`/`reload` và `ServiceConfigurationError`.
- [`java.lang.ClassLoader` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html) — parent delegation và resource lookup.
- [`java.lang.Thread` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html) — context class loader.
- [Java SE 17 JAR File Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/jar/jar.html) — JAR entry/root/manifest layout.
- [`java.lang.Module` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html) — module boundaries cho SPI ở module path.
