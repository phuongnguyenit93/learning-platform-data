# Kiểm thử nhị phân bằng artifact bên sử dụng đã biên dịch trước đó

Một lần nâng cấp JDK hoặc thư viện Java có thể trông hoàn hảo ở CI: mã nguồn biên dịch, unit test mới chạy qua, application startup thành công. Tuy nhiên, một plugin được phát hành từ nhiều tháng trước hoặc một ứng dụng downstream chưa được biên dịch lại có thể ném `NoSuchMethodError`, `NoSuchFieldError`, `AbstractMethodError` hay `IllegalAccessError` ngay khi dùng thư viện mới. Vấn đề là **kiểm thử mã nguồn mới không tự xác nhận tương thích với bytecode của bên sử dụng đã được phát hành**.

Trong **Java Advance Compatibility Migration**, một phép thử có giá trị đặc biệt là **giữ nguyên artifact consumer đã biên dịch với provider/library phiên bản cũ, chỉ thay provider JAR ở runtime, rồi chạy đúng artifact consumer đó**. Đây là cách mô phỏng tình huống doanh nghiệp thường gặp: nhà cung cấp thư viện nâng cấp; khách hàng, plugin hoặc dịch vụ phụ thuộc chưa nâng và không được build lại ngay.

Bài học giải thích khác biệt giữa source và binary compatibility, JVM method/field descriptors, thiết kế phép thử *compile once – run against old and new provider*, các kịch bản linkage lỗi phổ biến, cơ chế cố định artifact, tích hợp Maven/Gradle/CI và chiến lược sửa API hoặc công bố breaking migration.

## 1. Vì sao không thể chỉ chạy `mvn test` hoặc `gradlew test`?

Quy trình phổ biến:

```text
Source provider v2
        +
Source consumer hiện tại
        |
        v
   Build lại tất cả
        |
        v
      Test xanh
```

cho thấy **mã nguồn consumer có thể biên dịch và chạy khi được xây dựng lại với provider mới**. Nó chưa chứng minh các class file cũ vẫn có thể liên kết với provider v2.

Phép thử nhị phân cần:

```text
Provider v1.jar ----+
                    |
                    v
Consumer source --> javac --> consumer-old.jar
                              (đóng băng bytes)
                                  |
                +-----------------+------------------+
                |                                    |
                v                                    v
    Run với provider v1.jar              Run với provider v2.jar
       Baseline control                       Candidate test
                |                                    |
                +--------------- compare ------------+
```

Điều kiện quan trọng: **không gọi compiler lại trên consumer giữa hai lần chạy**. Nếu làm vậy, compiler có thể tạo method references mới hoặc báo lỗi trước runtime, khiến mục tiêu kiểm chứng binary bị thay đổi.

### 1.1. Khi nào phép thử này đặc biệt quan trọng?

- Nâng thư viện SDK được nhúng trong nhiều ứng dụng Java.
- Thay implementation/API mà các plugin bên thứ ba đã biên dịch chống lại.
- Nâng application server, framework extension hoặc provider do container cấp.
- Nâng JDK khi vẫn phải hỗ trợ JAR cũ.
- Di chuyển thư viện core của một hệ thống nhiều module không deploy cùng lúc.
- Kiểm tra khả năng thay JAR tại runtime mà không build lại consumer.
- Xác minh hợp đồng compatibility của một public Java library.
- Kiểm tra các batch job, desktop client, agents hoặc vendor integrations khó recompile.

### 1.2. Thí nghiệm phải có control run

Nếu `consumer-old.jar` chạy với provider v2 rồi lỗi, trước tiên phải chắc rằng nó chạy thành công với provider v1 trong cùng môi trường. Nếu baseline đã fail do thiếu dependency, JVM không phù hợp hoặc fixture sai, không thể quy kết lỗi cho v2.

## 2. Bốn lớp compatibility thường bị nhầm

| Lớp | Câu hỏi | Phép kiểm tra |
|---|---|---|
| **Source compatibility** | Consumer source cũ biên dịch được với library mới? | Recompile source với library mới |
| **Binary compatibility** | Consumer `.class`/JAR cũ liên kết được với library mới? | Giữ nguyên consumer JAR, đổi provider |
| **Behavioral compatibility** | Kết quả, ngoại lệ và side effects còn đúng? | Assertions, regression và integration tests |
| **Deployment/runtime compatibility** | JDK, provider, classpath, module path, container tương thích? | Chạy artifact cuối bằng launcher/runtime thực tế |

Một library có thể tương thích ở source nhưng không ở binary. Ngược lại, thêm một overload mới có thể khiến mã nguồn `method(null)` trở nên mơ hồ khi biên dịch lại dù lời gọi đã compile cũ vẫn trỏ tới descriptor cố định và có thể chạy.

Một API giữ đầy đủ public signatures có thể vẫn thay đổi nghiệp vụ: ví dụ từ làm tròn xuống thành làm tròn gần nhất. Do đó, **binary linkage test pass không đồng nghĩa behavioral regression pass**.

### 2.1. Hai câu hỏi cần được kiểm riêng

**Câu hỏi A:** Consumer version 1.0 đã phát hành có chạy với provider v2 mà không rebuild?

**Câu hỏi B:** Consumer source version 1.0 có còn compile với provider v2?

Đây là hai mục tiêu khác nhau. Khi báo cáo, phải ghi rõ cái nào đã được chứng minh và test nào đã chạy.

## 3. JVM liên kết lời gọi bằng symbolic references

Trong Java class file, compiler ghi tham chiếu vào constant pool và instructions. Ví dụ source:

```java
String text = new com.example.api.LabelService().format(10);
```

Bytecode có thể chứa symbolic method reference:

```text
com/example/api/LabelService.format:(I)Ljava/lang/String;
```

Tham chiếu bao gồm owner class, method name và **descriptor**. Descriptor mã hóa parameter types và return type, không chỉ tên method.

Một số descriptor cơ bản:

| Java type | JVM descriptor |
|---|---|
| `int` | `I` |
| `long` | `J` |
| `boolean` | `Z` |
| `void` | `V` |
| `java.lang.String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[]` | `[Ljava/lang/String;` |

Ví dụ:

```java
String read(int id, boolean active);
```

tương ứng descriptor:

```text
(IZ)Ljava/lang/String;
```

Nếu provider mới đổi return type thành `Object`, descriptor đổi từ `Ljava/lang/String;` sang `Ljava/lang/Object;`. Một consumer binary đã compile không tự tạo lại symbolic reference. Khi gọi method cũ, nó có thể nhận `NoSuchMethodError`.

### 3.1. Static và instance cũng là hợp đồng JVM

Với static method, compiler có thể phát lệnh `invokestatic`; với instance method là `invokevirtual` hoặc `invokeinterface` tùy ngữ cảnh. Đổi static thành instance mà giữ tên cũng có thể gây `IncompatibleClassChangeError`.

### 3.2. Field references khác method references

Với field, compiler ghi owner, field name và type descriptor. Xóa field, đổi type hoặc thay access có thể phá binary consumer. Tuy nhiên, một số compile-time constants có thể được inline vào consumer bytecode, khiến lỗi xuất hiện dưới dạng **giá trị cũ vẫn được dùng** thay vì linkage exception.

### 3.3. Lỗi có thể xuất hiện muộn

JVM có thể trì hoãn resolution tới lúc một đường code được chạy. Do đó, startup thành công không chứng minh mọi lời gọi trong consumer còn hợp lệ. Test nên kích hoạt các đường xử lý cần được hỗ trợ.

## 4. Ví dụ hoàn chỉnh: provider đổi tên một method

Giả sử project đơn giản:

```text
binary-test-demo/
├── provider-v1/
│   └── com/example/api/GreetingApi.java
├── provider-v2/
│   └── com/example/api/GreetingApi.java
├── consumer/
│   └── com/example/client/LegacyClient.java
├── build/
└── artifacts/
```

### 4.1. Provider phiên bản 1

File `provider-v1/com/example/api/GreetingApi.java`:

```java
package com.example.api;

public class GreetingApi {
    public String greeting(String name) {
        return "Hello, " + name;
    }
}
```

### 4.2. Consumer cũ dùng API v1

File `consumer/com/example/client/LegacyClient.java`:

```java
package com.example.client;

import com.example.api.GreetingApi;

public final class LegacyClient {
    public static void main(String[] args) {
        GreetingApi api = new GreetingApi();
        String message = api.greeting("Java");
        if (!"Hello, Java".equals(message)) {
            throw new AssertionError("Unexpected greeting: " + message);
        }
        System.out.println("PASS: " + message);
    }
}
```

Consumer đã gọi API có descriptor:

```text
greeting(Ljava/lang/String;)Ljava/lang/String;
```

### 4.3. Compile provider v1

Dùng shell Linux/macOS, từ thư mục gốc demo:

```bash
mkdir -p build/provider-v1 build/consumer artifacts

javac --release 11 \
  -d build/provider-v1 \
  provider-v1/com/example/api/GreetingApi.java

jar --create \
  --file artifacts/provider-v1.jar \
  -C build/provider-v1 .
```

Dùng JDK hỗ trợ `javac --release 11` cho ví dụ. Tùy hệ thống cần dùng compiler/toolchain tương ứng target thực.

### 4.4. Compile consumer **đúng một lần**

```bash
javac --release 11 \
  -cp artifacts/provider-v1.jar \
  -d build/consumer \
  consumer/com/example/client/LegacyClient.java

jar --create \
  --file artifacts/consumer-old.jar \
  -C build/consumer .
```

**Sau bước này, không xóa, sửa hoặc biên dịch lại `consumer-old.jar`** trong phần kiểm tra candidate. Có thể đặt artifact trong repository có hash cố định.

### 4.5. Chạy baseline với provider v1

```bash
java \
  -cp "artifacts/consumer-old.jar:artifacts/provider-v1.jar" \
  com.example.client.LegacyClient
```

Kết quả mong đợi:

```text
PASS: Hello, Java
```

Trên Windows PowerShell, classpath dùng dấu `;`:

```powershell
java -cp "artifacts/consumer-old.jar;artifacts/provider-v1.jar" com.example.client.LegacyClient
```

### 4.6. Provider v2 phá hợp đồng binary

File `provider-v2/com/example/api/GreetingApi.java`:

```java
package com.example.api;

public class GreetingApi {
    public String sayHello(String name) {
        return "Hello, " + name;
    }
}
```

Provider v2 đã đổi `greeting` thành `sayHello`, không còn method signature cũ.

```bash
mkdir -p build/provider-v2

javac --release 11 \
  -d build/provider-v2 \
  provider-v2/com/example/api/GreetingApi.java

jar --create \
  --file artifacts/provider-v2.jar \
  -C build/provider-v2 .
```

### 4.7. Chạy **cùng consumer-old.jar** với provider v2

```bash
java \
  -cp "artifacts/consumer-old.jar:artifacts/provider-v2.jar" \
  com.example.client.LegacyClient
```

Khi code path gọi method được thực thi, kỳ vọng một lỗi dạng:

```text
java.lang.NoSuchMethodError:
  'java.lang.String com.example.api.GreetingApi.greeting(java.lang.String)'
```

Tùy JDK, thông điệp được in có thể hơi khác. Bản chất là method descriptor mà consumer đã compile không còn trong provider v2.

Chỉ chạy `javac` lại consumer với provider v2 có thể tạo **compiler error**, nhưng không thay thế bằng chứng từ consumer artifact đã phát hành.

## 5. Khắc phục bằng compatibility method

Nếu muốn provider v2 là drop-in replacement, một hướng sửa là **giữ lại API cũ và delegate**:

```java
package com.example.api;

public class GreetingApi {
    public String sayHello(String name) {
        return "Hello, " + name;
    }

    @Deprecated
    public String greeting(String name) {
        return sayHello(name);
    }
}
```

Sau khi chỉ rebuild provider v2, chạy lại nguyên `consumer-old.jar`. Nếu API mới vẫn trả kết quả phù hợp, binary consumer có thể tiếp tục hoạt động.

Đây là mẫu **deprecate → preserve bridge → migrate consumers → remove in planned breaking release**.

### 5.1. Khi nào không thể đơn giản giữ bridge?

- Phương thức cũ dựa trên transaction hoặc data model đã bị xóa.
- Cùng tên/descriptor bị thay semantics không thể đáp ứng đồng thời.
- Hành vi cũ tạo rủi ro bảo mật.
- Interface hoặc class hierarchy thay đổi không thể được che bằng một overload đơn giản.
- Public fields/compile-time constants bị inline trong consumer.
- Provider mới đã chuyển namespace như `javax.servlet.*` sang `jakarta.servlet.*`.

Khi đó, phải công bố **breaking change** và chuẩn bị hướng consumer migration; không nên tạo phương thức giả hoạt động sai để chỉ làm test xanh.

## 6. Các lỗi linkage nên có trong test scenarios

| Thay đổi provider | Dấu hiệu consumer cũ có thể gặp | Giải thích |
|---|---|---|
| Xóa hoặc đổi method descriptor | `NoSuchMethodError` | Consumer vẫn gọi symbolic reference cũ |
| Xóa field hoặc đổi descriptor | `NoSuchFieldError` | Field reference không resolve được |
| Thu hẹp quyền method/field | `IllegalAccessError` | Bytecode cũ gọi member nay không truy cập được |
| Đổi static ↔ instance | `IncompatibleClassChangeError` | Invocation opcode/contract thay đổi |
| Class ↔ interface thay đổi | `IncompatibleClassChangeError` | Binary type kind không còn phù hợp |
| Thay hierarchy hoặc interface implementation | `AbstractMethodError`, `ClassCastException`, linkage errors | Dynamic dispatch hoặc cast không còn thỏa contract |
| Xóa/di chuyển binary class name | `NoClassDefFoundError` hoặc `ClassNotFoundException` | Class path, loader hoặc reflection lookup thiếu class |
| Đổi constructor parameters | `NoSuchMethodError` với `<init>` | Consumer đã ghi constructor descriptor cũ |
| API còn nhưng throw exception khác | Regression behavior | Link vẫn pass nhưng semantics đổi |
| Đổi constant được javac inline | Sử dụng giá trị cũ | Không nhất thiết phát sinh linkage exception |

Các lỗi cụ thể phụ thuộc đường gọi và JVM resolution; bảng không phải ánh xạ bắt buộc một-một.

### 6.1. Exception xảy ra khi nạp khác exception xảy ra khi gọi

`ClassNotFoundException` thường xuất hiện khi chương trình chủ động nạp bằng tên class, ví dụ `Class.forName`. `NoClassDefFoundError` có thể xuất hiện khi JVM không tìm được class trong quá trình linkage, hoặc do class initialization đã thất bại. Đọc `Caused by` và class loading logs thay vì kết luận mọi trường hợp là “thiếu JAR”.

### 6.2. Không sửa bằng `--add-opens` khi method đã bị xóa

`--add-opens` dùng cho deep reflection trong JPMS. Nó không khôi phục method đã xóa và không sửa descriptor. Với `NoSuchMethodError` thực sự, trước hết hãy xác định đúng provider version được nạp.

## 7. Return type, parameter type và constructor

### 7.1. Return type là một phần descriptor

Phiên bản cũ:

```java
public String status();
```

Phiên bản mới:

```java
public Object status();
```

Descriptors:

```text
v1: ()Ljava/lang/String;
v2: ()Ljava/lang/Object;
```

Consumer binary cũ có thể yêu cầu descriptor v1; v2 không cung cấp method đó. Việc kiểu mới là supertype không tự tạo một method tương thích.

### 7.2. Thay parameter overload

Provider v1:

```java
public void send(String endpoint);
```

Provider v2:

```java
public void send(URI endpoint);
```

Một consumer đã compile sẽ vẫn gọi `send(Ljava/lang/String;)V` nếu đó là API v1. Nếu provider v2 chỉ giữ overload nhận `URI`, sẽ không resolve được lời gọi cũ.

Có thể giữ overload:

```java
public void send(String endpoint) {
    send(URI.create(endpoint));
}
```

nhưng phải kiểm tra sự khác biệt về validation và error behavior.

### 7.3. Constructor là member cần giữ tương thích

Provider cũ:

```java
public Client(String host, int port);
```

Provider mới chỉ còn:

```java
public Client(URI endpoint);
```

Consumer cũ chứa lời gọi `<init>(Ljava/lang/String;I)V`. Khi method này biến mất, runtime có thể ném `NoSuchMethodError` dù class `Client` vẫn tồn tại.

## 8. Inheritance, interfaces và bridge methods

Những thay đổi ở hierarchy thường khó thấy nếu chỉ đọc public methods.

### 8.1. API interface do consumer implement

Provider v1:

```java
public interface PaymentPlugin {
    void charge(int amount);
}
```

Nhiều plugin ngoài tổ chức đã biên dịch implementation của interface này. Provider v2 thêm một abstract method:

```java
public interface PaymentPlugin {
    void charge(int amount);
    void refund(int amount);
}
```

Một plugin binary cũ không tự có implementation `refund`. Tùy cách code mới gọi method và cấu trúc hierarchy, có thể gặp `AbstractMethodError`.

Nếu semantics cho phép, default method có thể hỗ trợ compatibility:

```java
public interface PaymentPlugin {
    void charge(int amount);

    default void refund(int amount) {
        throw new UnsupportedOperationException(
                "Refund is not supported by this plugin");
    }
}
```

Nhưng việc thêm default method có thể tạo vấn đề inheritance hoặc behavior. Cần kiểm thử implementation binary cũ, không chỉ compile interface mới.

### 8.2. Thay superclass hoặc bỏ interface

Một consumer cũ có thể cast object sang interface mà provider class trước đây implements. Nếu provider mới bỏ interface đó, cast hoặc interface invocation có thể thất bại.

Trong plugin systems, binary API gồm cả **supertype graph**, không chỉ danh sách method trong class riêng lẻ.

### 8.3. Generics, erasure và bridge methods

Generics chủ yếu được biểu diễn bằng type erasure; compiler có thể sinh **bridge methods** khi cần giữ overriding semantics.

Ví dụ:

```java
public interface Repository<T> {
    T find(String id);
}
```

Một implementation `Repository<Customer>` có thể mang bridge method để đáp ứng erased signature. Refactor generic inheritance, return covariance hoặc visibility có thể làm method bridge khác đi. Consumer binary cũ vẫn dùng descriptor từ lần compile trước.

Sử dụng `javap -s` và `javap -v` để xem method descriptors và flags, gồm bridge/synthetic khi cần.

## 9. Public constants và hiện tượng inlining

Provider v1:

```java
public final class Settings {
    public static final int RETRY_LIMIT = 3;
}
```

Consumer cũ:

```java
int retries = Settings.RETRY_LIMIT;
```

Nếu field đáp ứng điều kiện compile-time constant, javac có thể nhúng trực tiếp số `3` vào consumer class file. Khi provider v2 sửa thành:

```java
public static final int RETRY_LIMIT = 5;
```

consumer binary cũ vẫn có thể dùng giá trị 3, ngay cả khi cả hai JAR đều load được và không có linkage error.

Vì vậy, phép thử phải kiểm tra **business assertions**, không chỉ process exit code.

### 9.1. API tương thích binary nhưng behavior không tương thích

Nếu provider công bố giá trị constant mới phải có hiệu lực với tất cả ứng dụng cũ, chỉ cập nhật JAR provider có thể chưa đủ. Cần một API runtime như `retryLimit()` và kế hoạch consumer migration hoặc giữ behavior cũ tới hết compatibility window.

## 10. Vì sao artifact phải bất biến?

Để chứng minh binary compatibility, consumer candidate run phải dùng **đúng bytes consumer** đã chạy baseline. Nếu Gradle hoặc Maven tự recompile consumer vì dependency mới, phép thử mất ý nghĩa.

### 10.1. Ghi checksum SHA-256

Trên Linux/macOS:

```bash
sha256sum artifacts/consumer-old.jar
```

Trên Windows PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 artifacts/consumer-old.jar
```

Lưu checksum cùng version provider dùng khi compile. Sau candidate run, có thể xác minh artifact không đổi.

### 10.2. Artifact manifest minh họa

```yaml
consumer:
  name: legacy-checkout-client
  version: 2.3.1
  path: fixtures/consumer-old.jar
  builtAgainst: provider-1.4.0.jar
  compiledWithJdk: "17.0.x"
  releaseTarget: 11
  sha256: "<calculated-hash>"
candidate:
  artifact: provider-2.0.0-rc1.jar
  sha256: "<calculated-hash>"
runtime:
  jdk: "17.0.x"
  mode: classpath
```

Các giá trị là placeholder. Báo cáo thực tế phải dùng checksum, compiler, runtime và artifact đúng của pipeline.

### 10.3. Không dùng mutable artifact tag

Một container tag `latest`, snapshot JAR ghi đè hoặc tên `provider.jar` bị thay nội dung không phải danh tính ổn định. Ưu tiên version bất biến và digest/sha256.

### 10.4. Dùng artifact đã phát hành thật

Consumer fixture lý tưởng là bản JAR/WAR/plugin từ artifact repository, đại diện cho **installed base** cần hỗ trợ. Một demo consumer do nhóm provider tự viết hữu ích nhưng có thể bỏ sót cách client thật dùng reflection, inheritance hoặc service providers.

## 11. Classpath: tránh vô tình nạp provider v1

Một lỗi thử nghiệm rất phổ biến:

```text
consumer-old.jar
provider-v1.jar
provider-v2.jar
```

JVM có thể nạp class `com.example.api.GreetingApi` từ bản v1, khiến candidate test vẫn pass mà không dùng v2.

Chỉ dùng **một provider version** trên classpath hoặc thiết kế classloader isolation có chủ đích.

### 11.1. Kiểm tra class origin

Trong một test diagnostic:

```java
Class<?> type = com.example.api.GreetingApi.class;
System.out.println("Loader: " + type.getClassLoader());

var domain = type.getProtectionDomain();
var source = domain == null ? null : domain.getCodeSource();

System.out.println(source == null
        ? "<unknown code source>"
        : source.getLocation());
```

`CodeSource` có thể không có với custom classloaders, nested JARs hoặc runtime instrumentation, nên cần kết hợp inspect artifact và class loading log.

### 11.2. Log class loading của JDK 9+

```bash
java -Xlog:class+load=info \
  -cp "artifacts/consumer-old.jar:artifacts/provider-v2.jar" \
  com.example.client.LegacyClient
```

Output giúp kiểm tra class nào được nạp từ nguồn nào. Với Spring Boot executable JAR, servlet container hoặc plugin framework, chạy **launcher thực tế** vì classloader có thể khác lệnh classpath phẳng.

### 11.3. Không dựa vào thứ tự wildcard

```bash
java -cp "consumer-old.jar:lib/*" com.example.client.LegacyClient
```

Không nên cho `lib` chứa cả provider cũ và mới rồi dựa vào thứ tự wildcard hoặc filesystem. Tạo thư mục sạch có dependencies đã chốt.

## 12. Kiểm thử với nhiều classloader

Class identity trong JVM phụ thuộc cả binary name và defining classloader. Hai class có cùng FQCN do hai loaders khác nhau định nghĩa không phải cùng kiểu.

Ví dụ hệ thống plugin:

```text
Application Loader
  |
  +-- Plugin Loader A
  |      +-- api-legacy.jar
  |
  +-- Plugin Loader B
         +-- api-new.jar
```

Nếu cả hai plugin dùng riêng class `com.example.api.Event`, việc chuyển object qua ranh giới loader có thể gây `ClassCastException`, kể cả khi class definitions trông giống nhau.

Một binary compatibility test đúng cần mô phỏng:

- Shared API classes ở parent loader nếu framework yêu cầu.
- Plugin implementation ở child loader theo plugin isolation contract.
- Delegation policy (parent-first/child-first) của runtime.
- Version của API được expose từ container.
- Việc chuyển object qua boundary.

Nếu chạy mọi JAR trong application classloader phẳng mà production dùng plugin classloader, test có thể bỏ sót vấn đề.

## 13. JPMS/module path và public API contract

Từ Java 9, module descriptor còn là một phần deployment compatibility.

Provider:

```java
module com.example.api {
    exports com.example.api;
}
```

Nếu provider v2 bỏ export của package public, consumer named module có thể không truy cập được dù method/class trong bytecode vẫn tồn tại.

Các yếu tố cần xét:

- `requires` và module readability.
- `exports` cho compile-time/runtime access.
- `opens` cho deep reflection.
- `uses`/`provides` cho ServiceLoader.
- Module names và duplicate/split packages.
- Automatic modules và classpath/unnamed module.

**Test đúng mode của production.** Nếu production chạy `--module-path`, một phép thử chỉ dùng `-cp` không bao phủ module resolution.

Thêm `--add-exports`/`--add-opens` có thể là giải pháp chuyển tiếp trong một số ca encapsulation, nhưng **không sửa method descriptor bị xóa**.

## 14. Reflection, SPI và runtime metadata

Không phải mọi contract nằm ở lời gọi Java tĩnh.

### 14.1. Reflection

Consumer cũ có thể làm:

```java
Class<?> type =
        Class.forName("com.example.api.MessagePlugin");

var method = type.getMethod("create", String.class);
```

Nếu provider v2 đổi class hoặc method, test có thể gặp `ClassNotFoundException` hay `NoSuchMethodException`, dù API diff tool chỉ kiểm tra một subset public API.

### 14.2. ServiceLoader

Provider có thể có metadata:

```text
META-INF/services/com.example.spi.Parser
```

Nếu SPI interface name, provider implementation, constructor hoặc descriptor thay đổi, runtime service discovery có thể lỗi hoặc không tìm thấy provider.

Test cần gọi `ServiceLoader.load(...)` trong consumer fixture thật, không chỉ xác nhận class có mặt trong JAR.

### 14.3. Annotations và framework integration

Một framework có thể đọc annotation, generic signature, persistence mapping, validation constraints hoặc component metadata. Đổi retention, annotation package hoặc provider lookup có thể gây regression dù method references vẫn tồn tại.

### 14.4. Java serialization

Một artifact consumer cũ có thể phải đọc Java serialized data tạo từ library v1. Thay class structure hoặc `serialVersionUID` có thể khiến dữ liệu cũ không đọc được (`InvalidClassException`) hoặc đọc với semantics khác.

Để kiểm tra, cần **fixture serialized bytes được tạo từ phiên bản cũ**, không tạo lại dữ liệu bằng provider mới.

## 15. Class file version khác binary API compatibility

Giả sử:

```text
Consumer old.jar:  major 55  (Java 11)
Provider new.jar:  major 65  (Java 21)
Runtime JVM:       Java 17
```

JVM 17 không thể nạp provider class file major 65. Đây là lỗi **runtime class file level**, không nhất thiết do public API thay đổi.

### 15.1. Kiểm tra major version

```bash
javap -verbose \
  -classpath artifacts/provider-v2.jar \
  com.example.api.GreetingApi
```

Tìm dòng:

```text
major version: 65
```

Các mốc thường gặp:

| Release | Major |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

### 15.2. Kiểm tra dependencies cũng có thể compile cho JDK mới

`javac --release 11` giới hạn bytecode/API Java SE của source đang compile, không chuyển đổi class file trong dependencies đã có. Một JAR chính major 55 vẫn có thể phụ thuộc JAR major 65 khi chạy.

Nên test trên JDK minimum mà provider cam kết hỗ trợ và xem toàn bộ runtime artifact graph.

## 16. Kỹ thuật dùng `javap` để tìm binary break

Sử dụng:

```bash
javap -classpath artifacts/provider-v1.jar \
  -s com.example.api.GreetingApi

javap -classpath artifacts/provider-v2.jar \
  -s com.example.api.GreetingApi
```

Khi kiểm tra method:

```text
greeting(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;
```

Nếu v2 không còn descriptor này, consumer binary có khả năng không resolve được lời gọi.

Có thể dùng `javap -v` để xem:

- Constant pool references.
- `ACC_PUBLIC`, `ACC_STATIC`, synthetic/bridge flags.
- Superclass/interfaces.
- Method handles, invokedynamic và bootstrap metadata.
- Class file version.

### 16.1. Đọc consumer bytecode cũng có ích

```bash
javap -c -v \
  -classpath artifacts/consumer-old.jar \
  com.example.client.LegacyClient
```

Mục tiêu là xác định consumer thật sự gọi descriptor nào. Nếu provider v2 có method tên giống nhưng return type khác, so sánh descriptor ở cả hai phía.

### 16.2. Phân biệt binary method lỗi với một provider JAR bị nạp nhầm

Nếu v2 đã giữ method nhưng vẫn có `NoSuchMethodError`, phải kiểm tra artifact source/classloader. Có thể runtime đang nạp provider v1 hoặc v3 từ shared library directory.

## 17. Maven workflow: build fixture một lần, candidate chạy riêng

Một ví dụ `pom.xml` của consumer cũ:

```xml
<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>greeting-api</artifactId>
        <version>1.4.0</version>
    </dependency>
</dependencies>
```

Ở **stage tạo fixture**:

```bash
mvn -B clean package
```

Sau đó lưu output JAR consumer vào repository hoặc thư mục fixtures bất biến.

Ở **stage kiểm thử provider v2**:

1. Tải `consumer-old.jar` từ artifact repository.
2. Tải `provider-v1.jar` để chạy control.
3. Tải `provider-v2.jar` để chạy candidate.
4. Xây classpath không có provider trùng.
5. Chạy consumer cũ với hai provider riêng và so sánh kết quả.

Không chạy `mvn package` trên consumer source ở candidate stage. Nếu nó được build lại, đó là một test khác.

### 17.1. Maven dependency tree chưa chứng minh classpath production

Có thể dùng:

```bash
mvn dependency:tree
```

để khảo sát dependency resolution, nhưng một container hoặc custom packaging task có thể thêm JAR ngoài tree. Cần kiểm tra WAR/JAR cuối và class loading source.

### 17.2. Plugin classpath và application classpath khác nhau

Nếu lỗi xảy ra trong Maven plugin, dependency của plugin có class realm riêng. Nâng một dependency trong phần `<dependencies>` của ứng dụng có thể không tác động tới binary component mà plugin đang nạp.

## 18. Gradle workflow: tránh tự recompile consumer

Nếu consumer là project module `:consumer` phụ thuộc `:provider`, chạy `build` có thể tự recompile nó với provider mới. Vì vậy nên dùng **JAR đã đóng băng**.

Ví dụ Groovy DSL:

```groovy
tasks.register('binaryCompatibilityRun', JavaExec) {
    group = 'verification'

    classpath = files(
        'fixtures/consumer-old.jar',
        'candidate/provider-v2.jar'
    )

    mainClass = 'com.example.client.LegacyClient'
}
```

Ví dụ chỉ đủ cho consumer không có external runtime dependencies. Ứng dụng thật phải thêm dependencies được chốt, nhưng không để `provider-v1.jar` xuất hiện trong candidate classpath.

### 18.1. Chọn JVM chạy thử nghiệm

```groovy
tasks.named('binaryCompatibilityRun', JavaExec) {
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Điều này chọn JVM của `JavaExec`, **không biên dịch lại consumer**. Daemon JVM và JavaCompile toolchain có thể khác.

### 18.2. Không lấy test fixture từ compiled classes vừa tạo

Tránh:

```groovy
classpath = sourceSets.main.runtimeClasspath
```

nếu source set chứa consumer mới và tự rebuild. Tập classpath cho test binary nên dùng artifact consumer đã đóng băng cùng dependency candidates có danh tính rõ.

### 18.3. Gradle dependency graph hỗ trợ điều tra

Các lệnh:

```bash
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency greeting-api \
  --configuration runtimeClasspath
```

giúp hiểu version resolution. Tuy nhiên `JavaExec.classpath` do `files(...)` tạo có thể khác resolved configuration; cần kiểm tra đường chạy thật.

## 19. CI/CD nên chia thành hai stage tách biệt

Một pipeline có thể bố trí:

```text
Stage A — Fixture preparation (chạy khi phát hành consumer)
  Read released consumer source/tag
  Compile against released provider v1
  Package consumer-old.jar
  Record JDK, --release, dependency versions
  Store immutable artifact and SHA-256

Stage B — Provider candidate validation (chạy mỗi provider PR)
  Download consumer-old.jar
  Verify checksum
  Download provider v1 and provider candidate
  Run baseline
  Run candidate
  Collect exit codes, logs, class origins
  Publish compatibility report
```

Trong stage B, nên **không chứa lệnh `javac`, Maven/Gradle build target của consumer**, hoặc bất kỳ thao tác nào thay bytes của fixture.

### 19.1. Test job báo fail đúng cách

- Assertion/uncaught exception phải trả exit code khác 0.
- CI phải kiểm tra exit code, không chỉ grep chuỗi “PASS” trong log.
- Thu thập stack trace và class loading source.
- Cần tách kết quả baseline fail với candidate fail.
- Không bỏ qua lỗi bằng `|| true` hoặc config tương đương.
- Test environment cần có JDK và OS phù hợp.
- Nếu consumer cần database/service, dùng environment có contract giống production.

### 19.2. Quản lý artifact release và provenance

Ghi artifact filename, version, checksum và nguồn repository. Nếu JAR được ký, xem cả signature verification khi áp dụng. Không tải artifact ngoài nguồn đáng tin rồi coi là fixture chính thức.

## 20. API diff tools bổ sung, không thay thử nghiệm consumer thật

Có thể dùng các công cụ như:

- **japicmp:** so sánh thay đổi API/JAR và nhiều khía cạnh binary/source compatibility.
- **Revapi:** phân tích differences theo API model và extensions.
- **`javap`:** xem public members, descriptors và bytecode.
- **`jdeps`:** xem dependency tĩnh giữa packages/modules.

Một pipeline hiệu quả:

```text
Provider v1.jar ----> Static API diff <---- Provider v2.jar
                                                  |
                                                  v
                                     Potential binary break report
                                                  |
                                                  v
Consumer-old.jar + Provider v2.jar ----> Runtime compatibility test
                                                  |
                                                  v
                                         Behavioral assertions
```

### 20.1. Vì sao static API diff không đủ?

- Classpath runtime có thể nạp artifact khác.
- Consumer dùng reflection/string-based class lookup.
- ServiceLoader descriptors bị thay đổi.
- Behavior thay đổi nhưng signatures giữ nguyên.
- External API/serialization format thay đổi.
- Provider có native dependencies hoặc agent.
- Different classloader hoặc module configuration.
- Bài test có thể cần chính path nghiệp vụ của consumer.

### 20.2. Vì sao runtime consumer test không đủ?

Nó chỉ thử các API mà consumer fixture dùng. Một public method bị xóa có thể chưa được fixture gọi nhưng vẫn là breaking change cho người dùng bên ngoài chưa biết. Vì vậy cần thêm static API checks nếu thư viện cam kết public binary compatibility rộng.

## 21. Nhiều consumer artifact: ma trận tương thích

Nếu provider phục vụ nhiều sản phẩm, nên chạy matrix.

| Consumer đã compile | Provider baseline | Provider candidate | Runtime | Kết quả giả định |
|---|---|---|---|---|
| Desktop 1.9 | 1.2 | 2.0 | JDK 17 | Pass |
| Batch 2.1 | 1.4 | 2.0 | JDK 17 | `NoSuchMethodError` |
| Plugin 3.0 | 1.5 | 2.0 | JDK 21 | Pass |
| Web app 4.2 | 1.5 | 2.0 | JDK 17 | Semantic regression |

Các hàng chỉ là minh họa. Khi chạy thật, báo cáo cần ghi chính xác artifacts và bằng chứng.

### 21.1. Chọn consumer nào để kiểm thử?

- Bản lâu đời nhất vẫn được hỗ trợ.
- Bản đang được cài phổ biến.
- Bản mới nhất.
- Consumer dùng APIs đã deprecated.
- Plugin có custom classloader.
- Consumer dùng reflection, SPI hoặc serialization.
- Ứng dụng chạy ở các JDK/OS/container khác nhau theo hợp đồng.

Không nhất thiết test mọi commit lịch sử, nhưng phải có ma trận hỗ trợ được phê duyệt và cập nhật định kỳ.

### 21.2. Khi một consumer bị ngừng hỗ trợ

Không tự thay fixture vì nó fail. Nếu doanh nghiệp quyết định drop support, cần ghi deadline, phiên bản thay thế, thông báo migration và thay đổi compatibility gate rõ ràng. Xóa fixture là một quyết định chính sách phiên bản, không phải mẹo làm CI pass.

## 22. Javax → Jakarta là ví dụ phá contract lớn

Khi Java EE APIs chuyển từ `javax.servlet.Filter` sang `jakarta.servlet.Filter`, JVM xem chúng là **hai kiểu khác nhau**. Một filter đã compile implements Javax interface không tự động implements Jakarta interface chỉ vì method names tương tự.

Nếu provider/container mới chỉ nhận Jakarta types, artifact Javax cũ có thể không còn link hoặc tích hợp đúng.

Một binary test có thể chạy:

1. Plugin/filter JAR cũ đã compile với Javax.
2. Container/framework Javax baseline.
3. Container/framework Jakarta candidate.
4. So sánh classloading, registration, lifecycle và behavior.

Nếu không có bridge hoặc transformer được hỗ trợ, breaking migration có thể là điều bắt buộc; không nên hứa drop-in binary compatibility.

### 22.1. Không nhầm JDK nâng cấp với Jakarta namespace

Một ứng dụng Javax có thể chạy trên JDK mới trong container Javax được hỗ trợ. Ngược lại, một ứng dụng Jakarta có thể cần container/framework mới dù JDK đã đủ phiên bản. Đây là hai chiều khác nhau cần test riêng.

## 23. Agent, JNI và dữ liệu serialized: các biên ngoài ABI Java thuần

### 23.1. Java agents

Agent đã compile trước đó có thể sử dụng ASM/Byte Buddy cũ và không đọc được bytecode mới. Lỗi `Unsupported class file major version` thường phát sinh ở parser/instrumentation, không hẳn do public API class bị xóa.

Cần kiểm tra agent startup, transformation, classload và chức năng monitoring/security trên đúng JDK mục tiêu.

### 23.2. JNI/native libraries

Một thư viện Java giữ nguyên method signatures vẫn có thể không tương thích với `.dll`, `.so` hoặc `.dylib` mới vì architecture, native ABI, symbol names hoặc driver. Binary test cần chạy trên OS/architecture thật nếu library có JNI.

### 23.3. Persisted Java data

Nếu ứng dụng ghi serialized objects hoặc cache entries theo class structure cũ, việc provider mới link được không bảo đảm đọc được dữ liệu cũ. Phải giữ byte fixtures tạo bởi old version và thử đọc bằng provider mới.

## 24. Các hiểu nhầm phổ biến

### “Recompile consumer pass chứng minh không breaking binary”

Sai. Recompile có thể thay symbolic references. Test nhị phân phải giữ consumer bytecode cũ.

### “Method cùng tên nghĩa là hợp đồng không đổi”

Chưa đủ. Descriptor gồm parameter và return types; access, staticness và declaring type cũng quan trọng.

### “Không thấy linkage error ở startup nghĩa là pass”

Chưa đủ. JVM có thể chỉ resolve method khi code path được thực thi.

### “Thêm cả v1 và v2 vào classpath để an toàn”

Ngược lại, dễ che regression vì classloader nạp bản không mong đợi. Phải cô lập một provider cho mỗi test run.

### “Static diff báo sạch nghĩa là behavior đúng”

Không đúng. Constant inlining, exception semantics, serialization và external state có thể khác.

### “Chỉ cần sửa `--release`”

Không. `--release` không khôi phục API methods đã xóa và không chuyển đổi binary references trong consumer cũ.

### “`UnsupportedClassVersionError` là API breaking change”

Không nhất thiết. Có thể provider được compile với Java release cao hơn runtime; phải kiểm tra major class file và runtime target.

### “Có thể dùng một dummy consumer duy nhất”

Một dummy chỉ bao phủ ít APIs. Với library dùng rộng, cần fixture từ những consumers thật và static API diff.

### “Build đỏ thì chỉ cần cập nhật fixture sang bản mới”

Nếu requirement là giữ binary compatibility, cập nhật fixture làm mất bằng chứng regression. Phải sửa provider hoặc thay đổi compatibility policy có chủ đích.

## 25. Hướng xử lý khi binary test fail

Trước hết phân loại:

**Nhóm A — API bị thay đổi nhưng có thể tương thích ngược.** Giữ method/constructor cũ, cung cấp bridge/delegation, đánh dấu deprecated và test lại consumer binary.

**Nhóm B — API phải breaking theo thiết kế.** Công bố minimum consumer version, compatibility matrix, migration guide và rollout có thể quay lui; không gọi provider mới là drop-in.

**Nhóm C — Runtime/classpath mismatch.** Sửa classpath, module path, JDK version hoặc classloader để test đúng artifact. Không sửa API khi thực tế nạp sai JAR.

**Nhóm D — Behavioral regression.** Xác định contract bị đổi, sửa logic hoặc lên kế hoạch versioning/feature flag, rồi chạy regression tests.

**Nhóm E — Security break.** Nếu API cũ không thể giữ vì rủi ro bảo mật, ưu tiên thiết kế migration có kiểm soát thay vì đưa trở lại hành vi không an toàn chỉ để đạt compatibility.

### 25.1. Quy trình chẩn đoán lỗi

1. Xác định class/method/field ở exception.
2. Đọc complete stack trace và nested causes.
3. Xác định JVM version, launch command, classpath/module path.
4. Xác định provider class được nạp từ artifact nào.
5. So sánh `javap -s` giữa provider v1 và v2.
6. Kiểm tra consumer bytecode và descriptor mà nó gọi.
7. Đối chiếu API diff và behavior assertions.
8. Quyết định giữ compatibility hay công bố breaking change.
9. Chạy lại cùng consumer fixture bất biến.
10. Lưu artifact hashes và report để tái hiện.

## 26. Rollout và rollback cho provider mới

Một binary compatibility test nên là **gate trước phát hành**, nhưng production vẫn có thể có consumers chưa biết hoặc đường chạy hiếm.

Nếu provider là shared library trong application server hoặc plugin platform, cần:

- Giữ artifact provider v1 để rollback.
- Cố định runtime image/container version.
- Xác định classloader nào cung cấp API.
- Kiểm tra in-flight tasks và state.
- Không đổi database/event schema trong cùng bước nếu có thể.
- Quan sát lỗi linkage theo release và consumer version.
- Có cơ chế đảo candidate khi error rate vượt ngưỡng.

Khi provider v2 đã ghi dữ liệu mà v1 không đọc được, chỉ thay ngược JAR không bảo đảm rollback an toàn. Cần xem data versioning và compatibility window.

### 26.1. Rollback khác recompile

Nếu consumer đã được phát hành ở nhiều nơi, provider rollback có thể nhanh hơn yêu cầu mọi consumer rebuild. Đây là một lý do quan trọng để giữ binary compatibility khi có thể.

Tuy nhiên, không giữ một API nguy hiểm hoặc đã hết hỗ trợ vĩnh viễn chỉ vì sợ breaking change; cần công bố thời hạn và lộ trình consumer upgrade.

## 27. Mẫu báo cáo binary compatibility test

```text
TEST:
  provider-binary-regression-2026-11

CONSUMER:
  name: checkout-client
  version: 2.3.1
  compiled-against: greeting-api-1.4.0.jar
  binary: consumer-old.jar
  sha256: <recorded-hash>
  recompiled-in-candidate-stage: NO

BASELINE:
  provider: greeting-api-1.4.0.jar
  runtime: JDK 17
  outcome: PASS

CANDIDATE:
  provider: greeting-api-2.0.0-rc1.jar
  runtime: JDK 17
  outcome: FAIL
  error: NoSuchMethodError
  reference: GreetingApi.greeting(String):String

EVIDENCE:
  provider-class-origin: provider-v2.jar
  consumer-checksum-unchanged: YES
  descriptor-diff: captured

DECISION:
  Restore compatibility method, or declare breaking release.
```

Đây là báo cáo minh họa, không phải dữ liệu đo trong một hệ thống thật.

## 28. Checklist trước khi công bố binary compatibility

- [ ] Đã phân biệt source, binary, behavioral và runtime compatibility.
- [ ] Đã xác định tập consumers còn được hỗ trợ.
- [ ] Đã giữ consumer artifact **đã compile với provider cũ**.
- [ ] Đã xác minh consumer checksum không đổi giữa baseline/candidate.
- [ ] Đã ghi compiler JDK, `--release` và dependency versions của consumer.
- [ ] Đã giữ provider v1 baseline và v2 candidate có version/hash rõ.
- [ ] Đã chạy baseline bằng consumer cũ + provider v1.
- [ ] Đã chạy chính consumer cũ + provider v2, không recompile.
- [ ] Đã dùng classpath/module path sạch và đúng launch mode.
- [ ] Đã kiểm tra classloader và code source thực sự.
- [ ] Đã thử các public methods, constructors, fields và type hierarchy quan trọng.
- [ ] Đã kiểm tra reflection, SPI, annotations và serialization nếu liên quan.
- [ ] Đã xem return/parameter descriptors và bridge methods khi có lỗi.
- [ ] Đã kiểm tra constant inlining và behavioral semantics.
- [ ] Đã xác nhận class file major versions phù hợp JVM mục tiêu.
- [ ] Đã tích hợp API diff tools như kiểm tra bổ sung.
- [ ] Đã có matrix nhiều consumer versions và runtime targets phù hợp.
- [ ] Đã phân loại kết quả fail thành ABI break, runtime mismatch hoặc semantic change.
- [ ] Đã quyết định compatibility bridge hoặc breaking-release migration rõ ràng.
- [ ] Đã lưu stack traces, logs, hashes, build metadata và CI report.
- [ ] Đã có chiến lược rollout/rollback trước khi thay provider production.

## 29. Kết luận

**Kiểm thử nhị phân bằng artifact bên sử dụng đã biên dịch trước đó** kiểm chứng một cam kết rất cụ thể: consumer đã phát hành có thể tiếp tục liên kết và hoạt động khi provider/library được thay mà không build lại consumer. JVM resolution dựa trên binary names, method/field descriptors, visibility, staticness và classloader; những chi tiết này có thể thay đổi dù source trông giống nhau.

Trong Java Advance Compatibility Migration, hãy **đóng băng consumer JAR và hash, chạy baseline với provider cũ, chỉ thay provider candidate, kiểm soát classpath và thực thi các đường nghiệp vụ thật**. Kết hợp static API diff với runtime tests và behavior assertions. Khi phát hiện incompatibility, hoặc giữ compatibility bridges có kiểm soát hoặc công bố breaking change cùng kế hoạch nâng consumer, rollout và rollback. Không giải quyết regression bằng cách âm thầm recompile artifact đã phát hành: làm như vậy chỉ che mất rủi ro mà phép thử được tạo ra để phát hiện.
