# Giới hạn của phân tích tĩnh với reflection, cấu hình và lớp nạp động

Trong quá trình khảo sát khả năng tương thích Java, phân tích tĩnh là cách hiệu quả để tìm dependency, API deprecated, tham chiếu đến API nội bộ của JDK và những đoạn mã có nguy cơ bị ảnh hưởng khi nâng phiên bản. Tuy nhiên, kết quả phân tích tĩnh không thể hiện đầy đủ những gì ứng dụng thực sự nạp và thực thi. Reflection, cấu hình bên ngoài và cơ chế nạp class động có thể tạo ra các phụ thuộc mà công cụ không nhìn thấy từ mã nguồn hoặc bytecode thông thường.

Điều này đặc biệt quan trọng khi migration giữa các phiên bản Java. Một ứng dụng có thể không có tham chiếu trực tiếp đến một class hoặc API trong source code, nhưng vẫn tìm class bằng tên lấy từ file cấu hình, gọi method qua reflection, nạp plugin từ thư mục bên ngoài hoặc nhận implementation từ `ServiceLoader`. Nếu chỉ dựa vào báo cáo scan, nhóm phát triển có thể bỏ sót thành phần cần nâng cấp hoặc đánh giá sai khả năng tương thích runtime.

## 1. Phân tích tĩnh cho biết điều gì và không cho biết điều gì?

Phân tích tĩnh (static analysis) xem xét mã nguồn, bytecode, cấu hình hoặc dependency mà không cần thực thi ứng dụng theo luồng nghiệp vụ thực tế. Tùy công cụ, việc phân tích có thể tìm:

- Quan hệ gọi hàm và tham chiếu class/package có thể suy ra từ mã nguồn hoặc bytecode.
- Dependency trực tiếp và bắc cầu được khai báo trong build.
- Lời gọi API Java deprecated hoặc API nội bộ có tham chiếu tĩnh.
- Một số lỗi mã nguồn, luồng dữ liệu, quyền truy cập và cấu trúc module.
- Các chuỗi hoặc tên class xuất hiện trong file mã nguồn và tài nguyên được đưa vào phạm vi quét.

Kết quả phụ thuộc vào dữ liệu đầu vào và mô hình mà công cụ sử dụng. Nếu một file cấu hình không nằm trong phạm vi quét, một JAR được tải từ máy chủ bên ngoài không có trong dependency graph, hoặc tên class chỉ được ghép khi chạy, công cụ có thể không xác định được phụ thuộc đó.

Phân biệt ba khái niệm:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Tham chiếu tĩnh | Có thể nhìn thấy trực tiếp trong source hoặc bytecode | `new com.example.Driver()` hoặc lời gọi `Driver.connect()`. |
| Phụ thuộc được khai báo | Có trong build file, module descriptor hoặc metadata | Dependency Maven trong `pom.xml`, Gradle `runtimeClasspath`. |
| Phụ thuộc được nạp lúc chạy | Chỉ xuất hiện khi ứng dụng xử lý cấu hình, reflection, plugin hoặc service | Tên class lấy từ `driver.class` trong file properties. |

Ba tập hợp này có phần giao nhau nhưng không nhất thiết trùng nhau. Một class có thể được khai báo trong dependency nhưng không bao giờ được nạp; một class khác có thể được tải từ thư mục plugin hoặc repository ngoài mà dependency graph của build không mô tả.

### 1.1. Vì sao call graph có thể không đầy đủ?

Call graph tĩnh thường dựa trên những quy tắc có thể suy ra từ mã nguồn hoặc bytecode. Các lời gọi trực tiếp như `service.process()` dễ phân tích hơn lời gọi mà đối tượng đích chỉ được xác định ở runtime.

Ví dụ:

```java
PaymentService service = new CardPaymentService();
service.pay(order);
```

Trong trường hợp này, kiểu implementation có thể được suy ra từ câu lệnh khởi tạo, dù đa hình vẫn khiến việc xác định mọi implementation khả dĩ cần phân tích thêm các subtype.

Ngược lại:

```java
String implementation = settings.getProperty("payment.service.class");
Class<?> type = Class.forName(implementation);
Object instance = type.getDeclaredConstructor().newInstance();
```

Class thực tế phụ thuộc vào giá trị của `payment.service.class`. Nếu giá trị đến từ file cấu hình, biến môi trường, database hoặc remote configuration service, source code không đủ để xác định implementation cụ thể.

Một công cụ có thể nhận diện lời gọi `Class.forName`, nhưng việc phát hiện lời gọi không đồng nghĩa nó biết class nào sẽ được nạp trong từng môi trường.

## 2. Reflection tạo ra phụ thuộc khó nhìn thấy

Reflection cho phép chương trình khám phá class, constructor, field, method và annotation trong runtime. Nó được sử dụng rộng rãi bởi framework, ORM, dependency injection, serializer, test framework và thư viện plugin.

### 2.1. Nạp class bằng tên dạng chuỗi

Các API thường gặp gồm:

```java
Class.forName("com.example.Driver");
ClassLoader.getSystemClassLoader().loadClass("com.example.Driver");
Thread.currentThread()
      .getContextClassLoader()
      .loadClass("com.example.Driver");
```

Tên class ở dạng chuỗi không tạo ra tham chiếu class trực tiếp như `new Driver()`. Một scanner dựa trên bytecode có thể thấy lời gọi `Class.forName`, nhưng không nhất thiết xác định được giá trị của chuỗi tại runtime.

Tên class còn có thể được tạo từ nhiều phần:

```java
String className = "com.example." + providerName + "." + "Client";
Class<?> clientType = loader.loadClass(className);
```

Nếu `providerName` được đọc từ cấu hình, database hoặc dữ liệu do hệ thống ngoài trả về, tên class hoàn chỉnh không tồn tại dưới dạng literal trong mã nguồn.

### 2.2. Gọi method và constructor qua reflection

Ứng dụng có thể tìm method theo tên rồi gọi mà không có lời gọi method trực tiếp:

```java
Class<?> type = Class.forName("com.example.LegacyAdapter");
Object adapter = type.getDeclaredConstructor().newInstance();

Method method = type.getMethod("initialize", String.class);
method.invoke(adapter, "production");
```

Phân tích tĩnh có thể tìm được chuỗi `LegacyAdapter` và tên method trong ví dụ này. Nhưng nếu các giá trị đến từ cấu hình hoặc được ghép động, việc xác định implementation và chữ ký thực tế sẽ khó hơn. Method cũng có thể được chọn theo annotation, tên operation hoặc dữ liệu đầu vào.

Các API đáng chú ý:

- `Class.forName`, `ClassLoader.loadClass`.
- `Class.getMethod`, `Class.getDeclaredMethod`.
- `Class.getConstructor`, `Class.getDeclaredConstructor`.
- `Method.invoke`, `Constructor.newInstance`.
- `Field.get`, `Field.set`, `AccessibleObject.setAccessible`.
- `MethodHandles.Lookup`, `MethodHandle.invoke` và `invokeExact`.

Không phải mọi lần dùng reflection đều nguy hiểm hoặc không phân tích được. Nếu tên class và chữ ký được cố định trong source, công cụ có thể tìm được một phần quan hệ. Giới hạn xuất hiện khi giá trị được quyết định bởi dữ liệu ngoài, nhánh runtime hoặc metadata mà scanner không hiểu.

### 2.3. Reflection thông qua framework

Ứng dụng có thể không gọi `Class.forName` trực tiếp nhưng framework vẫn làm điều đó thay ứng dụng. Ví dụ:

- ORM tìm entity, converter, listener và callback qua annotation hoặc cấu hình.
- Dependency injection container quét package và khởi tạo implementation.
- JSON/XML serializer tìm constructor, getter, setter hoặc field theo metadata.
- Framework web nạp controller, filter, interceptor và provider.
- Test framework tìm test class, extension hoặc test engine.
- Logging framework tìm implementation hoặc plugin tương ứng.

Khi nâng JDK, lỗi có thể xuất hiện trong thư viện framework chứ không ở source code nghiệp vụ. Vì vậy, việc không tìm thấy reflection trong code ứng dụng không đủ để kết luận ứng dụng không dùng reflection.

### 2.4. Proxy và class được tạo trong runtime

Một số framework tạo implementation hoặc proxy khi chạy:

```java
Object proxy = Proxy.newProxyInstance(
    interfaceType.getClassLoader(),
    new Class<?>[] { interfaceType },
    invocationHandler
);
```

JVM tạo class proxy để thực thi interface. Các thư viện như Byte Buddy, CGLIB, Javassist hoặc ASM cũng có thể sinh bytecode và nạp class mới trong runtime.

Scanner bytecode chỉ xem những class đã có trong artifact đầu vào. Nó không thể phân tích đầy đủ class được sinh ra sau khi ứng dụng khởi động nếu không có thông tin về generator, cấu hình và dữ liệu đầu vào. Một lỗi tương thích có thể nằm trong cách generator tạo bytecode hoặc cách class được định nghĩa bởi class loader.

## 3. Cấu hình bên ngoài có thể che giấu dependency

### 3.1. Tên class và implementation trong file cấu hình

Nhiều ứng dụng cho phép thay implementation mà không sửa source code:

```properties
storage.provider.class=com.example.storage.S3StorageProvider
database.driver.class=com.vendor.jdbc.Driver
serializer.class=com.example.json.LegacySerializer
```

Trong môi trường phát triển, cấu hình có thể dùng implementation giả lập; production lại dùng driver hoặc adapter khác. Nếu chỉ quét source code và file build, scanner có thể không biết toàn bộ class cần kiểm tra.

Các nguồn cấu hình cần khảo sát gồm:

- `.properties`, YAML, XML, JSON và file cấu hình riêng của ứng dụng.
- Biến môi trường và Java system properties.
- Tham số dòng lệnh và JVM options.
- Config map, secret, volume mount và environment trong container.
- Database, bảng cấu hình, feature flag và remote configuration service.
- Cấu hình do application server, plugin manager hoặc hệ thống triển khai cung cấp.

Không nên giả định file cấu hình trong repository là cấu hình duy nhất được dùng ở production. Hãy xác định nguồn cấu hình cuối cùng và thứ tự ưu tiên khi nhiều nguồn cùng khai báo một giá trị.

### 3.2. Profile và nhánh cấu hình

Một ứng dụng có thể có profile `dev`, `test`, `staging`, `production`, hoặc profile riêng cho từng khách hàng. Mỗi profile có thể bật implementation và dependency khác nhau.

Ví dụ:

```yaml
storage:
  provider: local

---
spring:
  config:
    activate:
      on-profile: production
storage:
  provider: cloud
```

Đây chỉ là ví dụ về cấu hình theo profile. Cấu hình thực tế có thể được ghép từ nhiều file hoặc nguồn bên ngoài. Nếu chỉ scan file mặc định, các class chỉ được dùng ở production có thể bị bỏ sót.

Hãy lập danh sách các tổ hợp profile được hỗ trợ và ghi lại giá trị cấu hình hiệu lực của từng tổ hợp. Nếu không thể truy cập một nguồn cấu hình nhạy cảm, có thể dùng bản đã che secret nhưng vẫn giữ nguyên tên class, tên provider và các giá trị ảnh hưởng đến việc nạp thành phần.

### 3.3. Cấu hình XML và tên class trong framework

Một số framework cũ khai báo class trong XML:

```xml
<bean id="paymentGateway"
      class="com.example.payment.LegacyGateway" />
```

Tên class không nhất thiết xuất hiện ở source Java. Cấu hình có thể nằm trong JAR, thư mục triển khai hoặc được sinh trong quá trình build. Khi migration, cần quét cả resource trong artifact và cấu hình ở môi trường triển khai.

### 3.4. Cấu hình đến từ database hoặc dịch vụ từ xa

Một số hệ thống lưu tên implementation trong bảng cấu hình hoặc nhận từ remote configuration. Static scan repository không thể biết chắc giá trị hiện hành của các bản ghi đó.

Quy trình khảo sát nên:

1. Xác định bảng, API hoặc dịch vụ cung cấp cấu hình.
2. Lấy danh sách các giá trị class/provider đang được sử dụng trong từng môi trường.
3. Loại bỏ hoặc che thông tin nhạy cảm nhưng giữ dữ liệu cần cho phân tích.
4. Liên kết mỗi giá trị với artifact hoặc dependency cung cấp class đó.
5. Xác minh các giá trị hiếm khi được sử dụng nhưng vẫn nằm trong phạm vi hỗ trợ.

Nếu không thể thu thập cấu hình production, ghi rõ đây là vùng chưa được xác minh và yêu cầu chủ sở hữu hệ thống xác nhận trước khi kết luận migration hoàn tất.

## 4. Lớp nạp động và dependency ngoài build

### 4.1. ClassLoader và context class loader

Java dùng class loader để nạp class vào JVM. Các class loader có thể được tổ chức thành quan hệ cha/con và có chính sách delegation khác nhau.

Ứng dụng có thể dùng:

- Bootstrap/platform/application class loader của JVM.
- Class loader do application server hoặc servlet container quản lý.
- `URLClassLoader` để nạp JAR từ thư mục plugin.
- Custom class loader để tải class từ mạng, kho lưu trữ hoặc byte array.
- Thread context class loader (TCCL) để thư viện tìm implementation trong ngữ cảnh thread.

Ví dụ:

```java
URL[] pluginUrls = {
    Path.of("plugins/payment-plugin.jar").toUri().toURL()
};

try (URLClassLoader pluginLoader = new URLClassLoader(
        pluginUrls,
        Thread.currentThread().getContextClassLoader())) {
    Class<?> pluginType = pluginLoader.loadClass("com.example.PaymentPlugin");
    Object plugin = pluginType.getDeclaredConstructor().newInstance();
}
```

JAR trong `plugins/` có thể không được khai báo trong Maven/Gradle. Nếu scanner chỉ đọc dependency graph, plugin này sẽ không xuất hiện. Cần kiểm tra thư mục plugin, quy trình cài đặt, manifest, cấu hình class loader và nguồn tải JAR.

### 4.2. Service Provider Interface và ServiceLoader

SPI cho phép một API sử dụng implementation được phát hiện tại runtime. Với classpath, provider thường được khai báo trong resource `META-INF/services/<service-interface>`.

Ví dụ sử dụng:

```java
ServiceLoader<PaymentProvider> providers =
    ServiceLoader.load(PaymentProvider.class);

for (PaymentProvider provider : providers) {
    provider.initialize();
}
```

Mã nguồn chỉ tham chiếu `PaymentProvider`; implementation có thể được khai báo trong một JAR khác. Vì vậy, cần kiểm tra:

- File `META-INF/services/*` trong các JAR runtime.
- Dependency cung cấp provider.
- TCCL được truyền vào `ServiceLoader` nếu ứng dụng dùng overload tương ứng.
- `uses` và `provides` trong `module-info.java` nếu dùng named module.
- Provider thực sự được chọn khi nhiều implementation cùng tồn tại.

Một provider có thể có mặt trên classpath nhưng không được tìm thấy nếu class loader hoặc resource visibility không đúng. Ngược lại, một JAR plugin được thêm vào runtime có thể làm xuất hiện provider mới mà scan build không biết.

### 4.3. Plugin directory và thư viện được tải ngoài

Các hệ thống có kiến trúc plugin thường nạp JAR từ thư mục cấu hình như `plugins/`, `extensions/`, `lib/custom/` hoặc từ một repository nội bộ. Những JAR này có thể được cập nhật độc lập với artifact ứng dụng.

Hãy xác định:

- Thư mục plugin và quy tắc tìm kiếm JAR.
- Cách xác định phiên bản plugin và dependency của plugin.
- Class loader cha/con và khả năng chia sẻ class giữa plugin.
- Plugin có thể được cài, gỡ hoặc cập nhật khi ứng dụng đang chạy hay không.
- Quy trình kiểm soát nguồn gốc và tính toàn vẹn của JAR.

Mỗi plugin cần có compatibility contract: phiên bản Java tối thiểu, phiên bản API host mà plugin dùng, phiên bản dependency và phạm vi test. Nếu plugin được tải sau khi ứng dụng khởi động, kiểm tra startup log một lần có thể không đủ.

### 4.4. Nạp thư viện native và JNI

Mã Java có thể gọi:

```java
System.loadLibrary("nativecodec");
```

Thư viện native không phải class Java nhưng vẫn là thành phần runtime bắt buộc. Khả năng tương thích phụ thuộc vào hệ điều hành, kiến trúc, ABI, cách build native và cơ chế tìm thư viện.

Static analysis Java có thể phát hiện lời gọi `System.loadLibrary`, nhưng không xác định đầy đủ file native nào sẽ được tìm thấy nếu đường dẫn được cấu hình bên ngoài. Kiểm tra cả native library đi kèm JAR, thư mục cài đặt, biến môi trường và image triển khai.

### 4.5. Bytecode được sinh hoặc tải từ xa

Một số hệ thống sinh class từ schema, expression, script hoặc dữ liệu runtime. Một số khác tải plugin hoặc bytecode từ kho lưu trữ. Các class này không có sẵn trong source tree để scanner phân tích.

Trong quá trình migration, cần xác định:

- Thành phần nào sinh bytecode và phiên bản của nó.
- Phiên bản class file được sinh ra.
- API nền tảng mà bytecode sinh ra tham chiếu.
- Cách class được định nghĩa và gắn với class loader/module.
- Quy trình cache, cập nhật và vô hiệu hóa class được sinh.

Nếu generator hoặc thư viện bytecode chưa hỗ trợ JDK 11, lỗi có thể chỉ xuất hiện ở một nhánh nghiệp vụ cụ thể sau khi class được tạo.

## 5. Vì sao các công cụ phân tích tĩnh có thể bỏ sót những phụ thuộc này?

### 5.1. Không biết giá trị cấu hình tại runtime

Một scanner có thể tìm thấy `Class.forName(config.get("adapter.class"))`, nhưng không biết giá trị của `adapter.class` trong production nếu cấu hình nằm trong database hoặc remote service. Ngay cả khi file cấu hình nằm trong repository, giá trị hiệu lực có thể bị ghi đè bởi environment variable hoặc JVM property.

### 5.2. Không thể suy ra mọi tên class được tạo động

Tên class có thể được ghép từ package, tenant, loại driver hoặc feature flag. Static scanner thường không mô phỏng đầy đủ mọi giá trị có thể đi qua hệ thống. Reflection còn có thể được bọc trong thư viện bên thứ ba nên source code ứng dụng không có lời gọi trực tiếp.

### 5.3. Dependency graph không bao phủ mọi nguồn JAR

Maven/Gradle mô tả dependency mà build biết đến. JAR được copy thủ công vào server, mount từ volume, tải khi chạy hoặc cài bởi plugin manager có thể nằm ngoài graph này.

### 5.4. Phân tích bytecode chỉ xem artifact đầu vào

`jdeps` và các scanner bytecode phân tích được những class có trong artifact và dependency được cung cấp cho công cụ. Chúng không tự biết các class sẽ được sinh trong runtime, tải từ mạng hoặc thêm sau khi triển khai.

### 5.5. Không thực thi mọi profile và luồng nghiệp vụ

Một nhánh cấu hình hiếm khi chạy có thể chứa dependency không tương thích. Static scan có thể bỏ sót class name lấy từ cấu hình; dynamic test cũng có thể bỏ sót nếu không kích hoạt profile, plugin hoặc nghiệp vụ tương ứng.

### 5.6. Phát hiện lời gọi không đồng nghĩa xác định được implementation

Tìm thấy `ServiceLoader.load`, `Class.forName` hoặc `Method.invoke` chỉ cho biết có cơ chế nạp/gọi động. Muốn biết class nào thực sự được sử dụng, cần kết hợp cấu hình hiệu lực, metadata provider, runtime log và test trên các cấu hình hỗ trợ.

## 6. Kết hợp phân tích tĩnh với kiểm tra runtime

Không nên loại bỏ phân tích tĩnh vì có giới hạn. Phân tích tĩnh vẫn giúp thu hẹp phạm vi điều tra và phát hiện nhiều lỗi sớm. Cách phù hợp là dùng nó để tạo danh sách điểm cần xác minh, sau đó bổ sung bằng chứng từ cấu hình và runtime.

### 6.1. Lập danh sách điểm nạp động

Tìm các API và mẫu sử dụng phổ biến:

```bash
rg -n "Class\.forName|loadClass\(|getDeclaredMethod|getDeclaredField|setAccessible|Method\.invoke|ServiceLoader|URLClassLoader|defineClass|loadLibrary|ScriptEngineManager|Proxy\.newProxyInstance" .
```

Tìm thêm tên class hoặc provider trong resource:

```bash
rg -n "\.class|provider|driver|adapter|implementation|plugin|className" config src resources
```

Điều chỉnh đường dẫn theo repository. Tìm kiếm văn bản có thể trả về kết quả không liên quan và không phát hiện giá trị được lưu ngoài repository; cần phân loại từng kết quả.

### 6.2. Kiểm tra cấu hình hiệu lực theo môi trường

Với mỗi môi trường hoặc profile, lập bảng:

| Trường cấu hình | Nguồn | Giá trị hiệu lực | Class/implementation cần kiểm tra |
| --- | --- | --- | --- |
| `payment.provider.class` | File cấu hình / environment | Tên class thực tế | Payment provider |
| `database.driver` | Secret / config service | Tên driver | JDBC driver |
| `serializer.type` | Profile ứng dụng | Loại serializer | Serializer implementation |
| `plugin.directory` | JVM property / mount | Đường dẫn thư mục | Các plugin JAR được nạp |

Không ghi secret hoặc credential vào báo cáo. Chỉ lưu các giá trị cần thiết để xác định class, dependency, profile và đường dẫn artifact.

### 6.3. Kiểm tra SPI và metadata trong JAR

Liệt kê resource provider trong các JAR runtime, kiểm tra `META-INF/services`, manifest, `Automatic-Module-Name` và module descriptor nếu có. Với JAR cụ thể, có thể dùng:

```bash
jar tf path/to/library.jar
jar --describe-module --file path/to/library.jar
```

Đối chiếu provider được khai báo với implementation thực sự được chọn. Nếu nhiều JAR cung cấp cùng service, thứ tự classpath và class loader có thể ảnh hưởng kết quả.

### 6.4. Quan sát class được nạp khi chạy

JDK 11 hỗ trợ unified JVM logging. Có thể bật log class loading trong môi trường kiểm thử:

```bash
java -Xlog:class+load=info -jar application.jar
```

Log giúp xác định class được nạp và nguồn nạp trong lần chạy đó. Có thể lọc log theo package hoặc class sau khi thu thập để giảm lượng dữ liệu.

Với JDK 8, cách phổ biến là:

```bash
java -verbose:class -jar application.jar
```

So sánh log JDK 8 và JDK 11 để tìm class không còn được tìm thấy, class đến từ JAR khác hoặc khác biệt class loader. Lưu ý log runtime chỉ phản ánh các đường chạy đã thực hiện; nó không chứng minh mọi profile, plugin hoặc nhánh nghiệp vụ đều đã được kích hoạt.

### 6.5. Ghi nhận nguồn gốc class trong ứng dụng

Khi cần điều tra sâu hơn, có thể ghi nhận class loader và `CodeSource` của implementation:

```java
static void printClassOrigin(Class<?> type) {
    ClassLoader loader = type.getClassLoader();
    var protectionDomain = type.getProtectionDomain();
    var codeSource = protectionDomain == null
            ? null
            : protectionDomain.getCodeSource();

    System.out.println("class=" + type.getName());
    System.out.println("loader=" + loader);
    System.out.println("source=" +
            (codeSource == null ? "unknown" : codeSource.getLocation()));
}
```

Đây là kỹ thuật chẩn đoán, không nên bật log chi tiết này vô điều kiện trong production nếu nó làm lộ đường dẫn hoặc tạo quá nhiều log. Với class được tạo động hoặc nạp từ nguồn đặc biệt, `CodeSource` có thể không có giá trị; cần kết hợp log của custom class loader.

## 7. Cách đánh giá kết quả và giới hạn của bằng chứng

Kết quả phân tích nên được phân loại theo mức độ chắc chắn, tránh biến một cảnh báo thành kết luận lỗi hoặc biến một lần chạy thành cam kết tương thích.

| Mức bằng chứng | Ý nghĩa | Cách ghi nhận |
| --- | --- | --- |
| Đã xác định tĩnh | Có tham chiếu rõ trong source/bytecode hoặc dependency metadata | Ghi class/API, vị trí tham chiếu và artifact liên quan. |
| Đã xác định qua cấu hình | Tên class/provider có trong cấu hình hiệu lực của môi trường | Ghi nguồn cấu hình, profile và giá trị đã che secret. |
| Đã quan sát runtime | Class thực sự được nạp trong một lần chạy cụ thể | Ghi log, JDK, profile, luồng nghiệp vụ và nguồn class. |
| Đã xác minh theo kịch bản | Build/test hoặc kiểm thử nghiệp vụ chạy thành công với cấu hình xác định | Ghi phiên bản JDK, artifact, môi trường và kết quả test. |
| Chưa xác minh | Không có đủ cấu hình, artifact hoặc kịch bản để kết luận | Ghi rõ dữ liệu còn thiếu và người sở hữu cần xác nhận. |

Một kết quả `jdeps` không có cảnh báo chỉ cho thấy công cụ không phát hiện loại phụ thuộc mà nó đang tìm trong đầu vào được cung cấp. Nó không chứng minh không có reflection, class loading động, dependency từ cấu hình hoặc API nội bộ được truy cập qua một đường khác.

Tương tự, log class loading không có class đáng ngờ chỉ chứng minh class đó không được nạp trong lần chạy đã ghi log. Cần chạy các profile và luồng nghiệp vụ thuộc phạm vi hỗ trợ, đồng thời kiểm tra các plugin có thể được cài hoặc kích hoạt sau thời điểm khởi động.

## 8. Quy trình điều tra thực tế trong dự án migration

### Bước 1: Xác định phạm vi runtime

Liệt kê service, artifact, module, profile, môi trường, application server, plugin directory và thành phần vận hành. Làm rõ đâu là thành phần bắt buộc, đâu là tuỳ chọn và đâu chỉ được dùng trong test.

### Bước 2: Thu thập source, dependency và cấu hình

Lấy dependency tree của runtime configuration, resource đóng gói trong JAR/WAR, file `META-INF/services`, module descriptor, manifest, file cấu hình và các giá trị hiệu lực theo môi trường. Nếu cấu hình nằm ngoài repository, phối hợp với chủ sở hữu môi trường để lấy bản đã che secret.

### Bước 3: Tìm điểm reflection và nạp động

Tìm `Class.forName`, `loadClass`, `Method.invoke`, `setAccessible`, `MethodHandles`, `ServiceLoader`, `URLClassLoader`, `defineClass`, `System.loadLibrary` và các framework thực hiện component scanning. Đối chiếu từng điểm với cấu hình và thư viện thực tế.

### Bước 4: Xác định nguồn của class

Với mỗi implementation được cấu hình hoặc quan sát, ghi tên class, class loader, nguồn JAR, phiên bản artifact, profile và thành phần sở hữu. Kiểm tra xem JAR đó có nằm trong dependency graph hay được tải từ một nguồn ngoài.

### Bước 5: Kiểm tra tương thích JDK đích

Phân tích bytecode, API nền tảng, module access, dependency và yêu cầu runtime. Với thành phần bên ngoài, kiểm tra tài liệu hỗ trợ của đúng phiên bản. Đặc biệt lưu ý framework dùng reflection, plugin, provider và native library.

### Bước 6: Bổ sung kiểm thử cho đường chạy còn thiếu

Kích hoạt từng profile và provider, chạy nghiệp vụ sử dụng plugin hoặc implementation ít gặp, kiểm tra class loading log và xác minh kết quả. Nếu không thể kích hoạt một nhánh, ghi rõ giới hạn thay vì đánh dấu đã xác minh.

### Bước 7: Duy trì danh sách phụ thuộc động

Đưa các class/provider được nạp động vào tài liệu dependency của dự án. Khi thêm plugin hoặc thay đổi cấu hình class name, cập nhật danh sách và test tương ứng để kết quả khảo sát không nhanh chóng lỗi thời.

## 9. Mẫu báo cáo cho một phát hiện

Một phát hiện về reflection hoặc dynamic loading nên chứa đủ thông tin để người khác tái hiện và xử lý:

| Trường | Nội dung |
| --- | --- |
| Mã phát hiện | ID hoặc mã ticket |
| Thành phần | Service, module hoặc plugin |
| Điểm nạp | API reflection, ServiceLoader, custom class loader hoặc framework |
| Class/provider | Tên implementation được xác định hoặc giá trị cấu hình |
| Nguồn | JAR, dependency, plugin directory, remote config hoặc nguồn khác |
| Cấu hình | Môi trường/profile đã kích hoạt |
| Bằng chứng | Source location, cấu hình đã che secret, dependency metadata, runtime log |
| JDK kiểm tra | Phiên bản JDK và vendor |
| Kết quả | Đã chạy, lỗi, cảnh báo hoặc chưa xác minh |
| Hành động | Nâng thư viện, sửa cấu hình, thêm test hoặc điều tra tiếp |
| Chủ sở hữu | Nhóm chịu trách nhiệm và thời điểm cập nhật |

Ví dụ về cách ghi kết luận:

> Service thanh toán nạp `com.vendor.payment.FastProvider` qua `ServiceLoader`. Provider nằm trong `payment-fast-provider.jar`, được mount vào thư mục plugin ở production và không có trong dependency tree của build. Class đã được quan sát trong log class loading khi chạy profile production trên JDK 11. Cần xác minh phiên bản plugin với nhà cung cấp và thêm nó vào ma trận kiểm thử triển khai.

Kết luận cần mô tả điều đã quan sát, phạm vi quan sát và phần còn chưa xác minh. Không suy rộng từ một profile sang tất cả môi trường.

## 10. Rủi ro bảo mật khi nạp class động

Nạp class theo tên từ cấu hình giúp mở rộng ứng dụng, nhưng cũng tạo ra rủi ro nếu người không đáng tin cậy có thể thay đổi giá trị hoặc nội dung JAR.

Các biện pháp nên cân nhắc:

- Chỉ cho phép implementation trong danh sách package/class đã được phê duyệt.
- Kiểm tra nguồn gốc, chữ ký hoặc checksum của plugin theo chính sách tổ chức.
- Phân quyền ghi thư mục plugin và cấu hình runtime.
- Không lấy class name trực tiếp từ input người dùng rồi nạp tùy ý.
- Ghi log class, nguồn JAR và phiên bản khi plugin được nạp.
- Có quy trình kiểm duyệt và kiểm thử tương thích trước khi triển khai plugin mới.

Class loading không phải sandbox bảo mật. Nếu plugin chạy trong cùng JVM với ứng dụng, cần xem nó như mã có quyền thực thi trong tiến trình và quản lý nguồn gốc của nó tương ứng.

## 11. Tiêu chí hoàn thành khảo sát

- [ ] Đã xác định các điểm reflection và nạp class động trong mã nguồn và framework.
- [ ] Đã thu thập cấu hình hiệu lực theo môi trường/profile có liên quan.
- [ ] Đã kiểm tra dependency runtime, `META-INF/services`, module descriptor và JAR plugin ngoài build.
- [ ] Đã xác định class loader và nguồn artifact của các implementation quan trọng.
- [ ] Đã kết hợp kết quả static scan với log class loading và kiểm thử runtime.
- [ ] Đã kích hoạt các profile, provider và luồng nghiệp vụ thuộc phạm vi hỗ trợ.
- [ ] Đã phân biệt phát hiện tĩnh, cấu hình, quan sát runtime và xác minh theo kịch bản.
- [ ] Đã ghi rõ những nhánh chưa thể xác minh và người sở hữu dữ liệu còn thiếu.
- [ ] Đã cập nhật danh sách phụ thuộc động và test khi thêm hoặc thay plugin/provider.

Phân tích tĩnh vẫn là nền tảng hữu ích để khảo sát migration, nhưng không thể thay thế việc hiểu cấu hình và quan sát runtime. Khi reflection, cấu hình và class loading động được đưa vào phạm vi điều tra, nhóm phát triển sẽ có bức tranh sát hơn về các class thực sự tham gia vào ứng dụng và những dependency cần được xác minh trên phiên bản Java đích.
