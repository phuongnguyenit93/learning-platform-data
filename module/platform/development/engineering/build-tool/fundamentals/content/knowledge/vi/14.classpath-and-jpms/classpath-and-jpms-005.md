# Thư viện có mặt nhưng không có đúng phương thức hoặc trường cần dùng

Một lỗi khó hiểu trong ứng dụng Java là build đã tìm thấy thư viện, thậm chí mã nguồn đã biên dịch thành công, nhưng khi chạy lại xuất hiện `NoSuchMethodError` hoặc `NoSuchFieldError`. Một trường hợp khác là IDE nhận diện được class nhưng compiler báo không tìm thấy method cần gọi. Những lỗi này thường liên quan đến **phiên bản API thực tế mà compiler nhìn thấy khác với phiên bản class được nạp khi chạy**, hoặc classpath/module path không chứa đúng artifact mà ứng dụng mong đợi.

Việc một thư viện “có mặt” chỉ cho biết Gradle hoặc JVM tìm được một artifact/class nào đó. Điều đó không bảo đảm artifact chứa đúng phiên bản API, đúng variant, đúng class hay đúng module mà mã nguồn cần. Muốn xử lý tận gốc, cần lần theo dependency graph, so sánh compile-time với runtime và xác định chính xác class nào được JVM nạp.

## 1. Hai tình huống khác nhau: compiler không tìm thấy API và JVM không liên kết được API

Trước tiên hãy phân biệt lỗi xảy ra ở thời điểm nào.

### Lỗi ngay khi biên dịch

Ví dụ mã nguồn gọi:

```java
client.sendAsync(request);
```

nhưng compiler báo:

```text
cannot find symbol
  symbol:   method sendAsync(Request)
  location: variable client of type ApiClient
```

Điều này có nghĩa compiler không tìm thấy method phù hợp trong API mà nó đang sử dụng trên compile classpath. Nguyên nhân có thể là:

- Dependency đang khai báo phiên bản quá cũ.
- Mã nguồn đang dùng API của một module khác nhưng module đó chưa được thêm vào dependency.
- Import nhầm class có cùng tên từ package khác.
- Method tồn tại trong một phiên bản khác nhưng compile configuration hiện tại resolve phiên bản không có method đó.
- Method có chữ ký khác, chẳng hạn khác kiểu tham số hoặc generic type sau khi type erasure.
- Method không truy cập được do access modifier hoặc ranh giới module JPMS.

Compiler đã phát hiện vấn đề trước khi tạo bytecode, vì vậy ứng dụng chưa thể được build thành công theo cấu hình đó.

### Lỗi khi chạy sau khi đã biên dịch

Một trường hợp nghiêm trọng hơn là mã nguồn biên dịch thành công, nhưng lúc chạy JVM báo:

```text
java.lang.NoSuchMethodError: 'java.lang.String com.example.ApiClient.send(java.lang.String)'
```

`NoSuchMethodError` là một `LinkageError`. Bytecode có tham chiếu tới method với tên và descriptor nhất định, nhưng class thực tế được JVM nạp không cung cấp method tương ứng.

Ví dụ:

1. Compiler biên dịch ứng dụng với `api-client` phiên bản 2.0, trong đó có `send(String)`.
2. Khi đóng gói hoặc chạy, runtime lại nạp `api-client` phiên bản 1.5, trong đó chưa có method này.
3. JVM cố liên kết lời gọi trong bytecode với class đã nạp.
4. Không tìm thấy method có descriptor cần thiết, nên ném `NoSuchMethodError`.

Sơ đồ:

```mermaid
flowchart TD
    A[Compile classpath: api-client 2.0] --> B[Compiler sees send(String)]
    B --> C[Bytecode references send(String)]
    D[Runtime classpath: api-client 1.5] --> E[JVM loads older ApiClient]
    C --> F[Method linkage]
    E --> F
    F --> G[NoSuchMethodError]
```

Đây là biểu hiện điển hình của **binary incompatibility** giữa bytecode đã biên dịch và class được nạp lúc chạy.

## 2. Những lỗi liên kết thường gặp

Java có nhiều lỗi liên quan tới việc JVM liên kết bytecode với class, method hoặc field. Nhận diện đúng tên lỗi giúp khoanh vùng nguyên nhân.

| Lỗi | Ý nghĩa thường gặp | Ví dụ nguyên nhân |
|---|---|---|
| `NoSuchMethodError` | Class đã được nạp nhưng không có method với tên và descriptor được bytecode yêu cầu | Compile với API mới, runtime nạp JAR cũ |
| `NoSuchFieldError` | Class đã được nạp nhưng không có field mà bytecode tham chiếu | Field bị xóa hoặc đổi tên giữa các version |
| `AbstractMethodError` | Một lời gọi cần implementation nhưng class thực tế không cung cấp implementation tương thích | Interface/abstract API thay đổi nhưng implementation cũ vẫn được nạp |
| `IncompatibleClassChangeError` | Cấu trúc class/interface hoặc cách truy cập thành viên không tương thích với bytecode | Một kiểu đổi từ class thành interface hoặc ngược lại; static/instance thay đổi |
| `IllegalAccessError` | Bytecode cố truy cập class/member mà runtime không cho phép | Quyền truy cập hoặc ranh giới module không còn phù hợp |
| `NoClassDefFoundError` | JVM cần một class nhưng không thể tìm/nạp định nghĩa class đó lúc chạy | Dependency có lúc compile nhưng bị thiếu ở runtime; hoặc class khởi tạo trước đó thất bại |
| `ClassNotFoundException` | Một API tải class tường minh không tìm thấy tên class được yêu cầu | `Class.forName()` hoặc class loader không tìm được class |

`NoSuchMethodError` và `NoSuchFieldError` đặc biệt phù hợp với chủ đề thư viện có mặt nhưng API không đúng. Các lỗi còn lại có thể xuất hiện trong cùng nhóm sự cố dependency/classpath nhưng cần cách chẩn đoán riêng.

### Phân biệt lỗi liên kết với lỗi reflection

Nếu dùng reflection:

```java
ApiClient.class.getMethod("sendAsync", Request.class);
```

API reflection có thể ném `NoSuchMethodException` nếu không tìm thấy method theo tên và tham số yêu cầu. Đây là checked exception của API reflection, khác với `NoSuchMethodError` khi JVM không liên kết được lời gọi đã được ghi trong bytecode.

Nếu method tồn tại nhưng module không mở package cho reflection, có thể gặp `InaccessibleObjectException` hoặc lỗi truy cập phản chiếu tương ứng. Khi đó vấn đề là quyền truy cập, không phải method bị thiếu.

## 3. Vì sao compile classpath và runtime classpath có thể khác nhau?

Gradle phân giải dependency theo từng configuration. Một project Java thường có những configuration như:

- `compileClasspath`: dependency cần để biên dịch mã nguồn chính.
- `runtimeClasspath`: dependency cần để chạy ứng dụng chính.
- `testCompileClasspath`: dependency cần để biên dịch mã kiểm thử.
- `testRuntimeClasspath`: dependency cần để chạy kiểm thử.

Các configuration có quan hệ kế thừa nhưng không nhất thiết giống hệt nhau. Ví dụ:

- `compileOnly` có thể có trên compile classpath nhưng không được đưa vào runtime classpath.
- `runtimeOnly` có trên runtime classpath nhưng không có trên compile classpath.
- Một custom configuration có thể dùng dependency hoặc constraint khác với configuration chính.
- Một dependency được thay thế hoặc phân giải khác theo variant, attribute hoặc rule.
- Một ứng dụng có thể đóng gói runtime dependency theo cách riêng, khiến nội dung gói không khớp với runtime classpath Gradle đã resolve.

Ví dụ:

```groovy
dependencies {
    compileOnly 'com.example:api-client:2.0.0'
    runtimeOnly 'com.example:api-client:1.5.0'
}
```

Đoạn cấu hình này có thể cho compiler nhìn thấy API ở version 2.0.0 nhưng lúc chạy chỉ đưa version 1.5.0 vào runtime. Nếu ứng dụng gọi method chỉ có ở 2.0.0, lỗi liên kết có thể xuất hiện khi chạy.

Đây là một cấu hình không phù hợp nếu hai dependency cùng đại diện cho một module API mà ứng dụng cần dùng thống nhất. Trong dự án thực tế, cần xác định dependency nào cung cấp API và dùng một version tương thích ở cả compile và runtime.

### Phạm vi dependency trong Java Plugin

| Configuration | Vai trò | Có mặt ở đâu? |
|---|---|---|
| `implementation` | Dependency cần cho biên dịch và runtime nội bộ của project | Compile và runtime classpath tương ứng |
| `api` | Dependency công khai qua API của Java Library | Compile/runtime của project và có thể được công bố cho consumer |
| `compileOnly` | Cần khi biên dịch nhưng không tự đưa vào runtime | Compile classpath |
| `runtimeOnly` | Chỉ cần khi chạy | Runtime classpath |
| `testImplementation` | Dependency dùng cho mã test | Test compile và test runtime theo configuration |
| `testRuntimeOnly` | Chỉ cần khi chạy test | Test runtime classpath |

Ví dụ `compileOnly` hợp lý khi API được cung cấp bởi container hoặc môi trường chạy đã cam kết có sẵn, chẳng hạn một số API servlet. Nó không phù hợp nếu ứng dụng tự cần thư viện đó khi chạy mà không có nơi nào khác cung cấp.

## 4. Xung đột phiên bản và dependency bắc cầu

Một dependency trực tiếp có thể kéo theo dependency bắc cầu. Ví dụ:

```text
application
├── reporting-client:1.0
│   └── api-client:1.5
└── api-client:2.0
```

Cả hai nhánh yêu cầu cùng module `api-client` nhưng khác version. Gradle giải quyết xung đột theo quy tắc dependency resolution. Với quy tắc mặc định, Gradle thường chọn version cao hơn trong các version được yêu cầu, trừ khi có constraint, rich version, force, substitution hoặc rule khác thay đổi kết quả.

Tuy nhiên, “version cao hơn” không đồng nghĩa “tương thích với mọi thư viện”. Một thư viện có thể yêu cầu API cũ, phụ thuộc vào hành vi đã thay đổi hoặc không tương thích nhị phân với version được chọn. Quá trình resolve thành công chỉ cho biết Gradle đã tìm được một graph hợp lệ theo metadata và quy tắc resolution; nó không chứng minh mọi lời gọi method/field trong bytecode đều tương thích.

### Xem ai yêu cầu phiên bản nào

Dùng `dependencyInsight`:

```bash
./gradlew dependencyInsight \
    --dependency api-client \
    --configuration runtimeClasspath
```

Để so sánh compile và runtime:

```bash
./gradlew dependencyInsight --dependency api-client --configuration compileClasspath
./gradlew dependencyInsight --dependency api-client --configuration runtimeClasspath
```

Lệnh này giúp xác định:

- Dependency trực tiếp hoặc bắc cầu nào yêu cầu module.
- Những version nào đã được yêu cầu.
- Version cuối cùng được chọn.
- Constraint, conflict resolution hoặc rule nào ảnh hưởng kết quả.
- Đường dependency nào kéo module vào graph.

Có thể xem toàn bộ graph của một configuration:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
```

Đừng chỉ xem `build.gradle` của module đang lỗi. Phiên bản thực tế có thể được quyết định bởi một dependency bắc cầu được khai báo ở project khác hoặc bởi platform/constraint ở cấp build.

## 5. API compatibility và binary compatibility

Một thư viện có thể giữ nguyên tên artifact nhưng thay đổi API giữa các phiên bản. Cần phân biệt hai khái niệm:

- **Source compatibility:** mã nguồn cũ có còn biên dịch được khi dùng phiên bản thư viện mới không?
- **Binary compatibility:** bytecode đã biên dịch với phiên bản trước có tiếp tục liên kết và chạy với phiên bản mới không?

Hai khái niệm có liên hệ nhưng không đồng nhất. Một thay đổi có thể khiến mã nguồn phải sửa dù bytecode cũ vẫn chạy; ngược lại, một thay đổi có thể khiến bytecode cũ không liên kết được dù một phần mã nguồn mới vẫn biên dịch.

Ví dụ thư viện phiên bản 1:

```java
package com.example;

public class ApiClient {
    public String send(String request) {
        return request;
    }
}
```

Ứng dụng biên dịch với API trên:

```java
ApiClient client = new ApiClient();
String result = client.send("hello");
```

Sau đó thư viện phiên bản 2 đổi chữ ký:

```java
package com.example;

public class ApiClient {
    public String send(Object request) {
        return String.valueOf(request);
    }
}
```

Method `send(Object)` không có cùng descriptor với `send(String)`. Bytecode cũ vẫn tham chiếu `send(String)`. Nếu runtime nạp class phiên bản 2, JVM không tự động xem method `send(Object)` là method thay thế cho lời gọi đã biên dịch, nên có thể ném `NoSuchMethodError`.

Một số thay đổi API có thể gây binary incompatibility:

- Xóa method hoặc field public/protected.
- Đổi tên method/field.
- Đổi kiểu tham số hoặc kiểu trả về theo cách làm thay đổi descriptor.
- Đổi một method instance thành static hoặc ngược lại.
- Đổi class thành interface hoặc interface thành class.
- Thay đổi hierarchy theo cách làm bytecode cũ không còn hợp lệ.
- Thay đổi abstract/concrete method khiến implementation cũ không đáp ứng contract mới.
- Chuyển class sang package/module khác mà không duy trì tương thích.

Không phải mọi thay đổi source-level đều phá binary compatibility. Ví dụ, thêm một overload mới thường không phá các lời gọi cũ nếu method cũ vẫn được giữ. Nhưng thay đổi default method, generic signature, bridge method hoặc hierarchy có thể có hệ quả phức tạp; cần dựa vào quy tắc tương thích JVM và kiểm tra thực tế.

### Field có một chi tiết đặc biệt

`NoSuchFieldError` có thể xảy ra khi bytecode tham chiếu field mà class runtime không còn cung cấp. Tuy nhiên, một số hằng số `static final` có giá trị compile-time constant được compiler nhúng trực tiếp vào bytecode của client. Khi thư viện đổi giá trị hoặc xóa hằng số, client cũ có thể tiếp tục dùng giá trị đã được nhúng mà không ném `NoSuchFieldError`. Vì vậy, không phải mọi thay đổi field đều biểu hiện giống nhau.

## 6. Class trùng tên và nạp nhầm JAR

Một nguyên nhân khác là có nhiều JAR chứa class cùng tên đầy đủ (fully qualified class name). Ví dụ, hai thư viện hoặc hai version của cùng một thư viện đều chứa:

```text
com/example/ApiClient.class
```

Class loader chỉ nạp một định nghĩa class cho một tên class trong một namespace/class loader nhất định. Với classpath truyền thống, thứ tự và cơ chế delegation của class loader có thể khiến JVM nạp bản từ JAR khác với bản người phát triển dự đoán.

Hậu quả có thể là:

- Runtime nạp class cũ dù JAR mới cũng có trong classpath.
- Một thư viện shaded hoặc fat JAR chứa bản class đã đóng gói từ trước.
- Server/application container cung cấp một class khác qua parent class loader.
- Plugin hoặc module dùng class loader riêng, dẫn tới các bản class khác nhau trong các namespace khác nhau.
- Class trùng tên được đóng gói từ nhiều dependency, tạo hành vi phụ thuộc thứ tự.

Không nên xử lý bằng cách chỉ thêm một JAR nữa vào classpath mà không xác định class nào được nạp. Việc có nhiều bản cùng class name có thể làm vấn đề phức tạp hơn.

### Xác định nguồn class được JVM nạp

Trên Java hiện đại, có thể bật log class loading:

```bash
java -Xlog:class+load=info -jar app.jar
```

Log cho biết class được nạp từ nguồn nào (tùy loại class loader và cách chạy). Với môi trường cũ hơn, có thể dùng:

```bash
java -verbose:class -jar app.jar
```

Nếu chạy trong application server hoặc container, cần xem cấu hình class loader của chính môi trường đó; lệnh `java -jar` ở máy local có thể không tái hiện chính xác class loading trong production.

## 7. Kiểm tra API thực sự có trong JAR

Khi biết class runtime đến từ JAR nào, hãy kiểm tra nội dung và chữ ký của class.

Liệt kê nội dung archive:

```bash
jar tf api-client-1.5.0.jar
```

Xem method và field public bằng `javap`:

```bash
javap -classpath api-client-1.5.0.jar -public com.example.ApiClient
```

Có thể xem bytecode của client đã biên dịch:

```bash
javap -classpath build/classes/java/main -c -verbose com.example.App
```

Tìm lời gọi method và descriptor trong output. Nếu bytecode tham chiếu một chữ ký không có trong class runtime, đã xác định được chỗ không tương thích.

Một cách điều tra hữu ích:

1. Lấy đường dẫn JAR mà JVM thực sự nạp class.
2. Dùng `javap` kiểm tra API của class trong JAR đó.
3. Kiểm tra class file của ứng dụng để xác định descriptor được tham chiếu.
4. So sánh với JAR trên compile classpath.
5. Xác định dependency hoặc bước đóng gói nào đã đưa version khác vào runtime.

## 8. Dependency substitution, exclusions và cách sửa phiên bản

Khi xác định đúng module gây lỗi, hãy sửa dependency graph có chủ đích.

### Dùng version thống nhất

Nếu ứng dụng và dependency bắc cầu cần cùng một thư viện, khai báo version đã được xác minh và dùng constraint/platform để quản lý:

```groovy
dependencies {
    implementation('com.example:api-client:2.0.0')

    constraints {
        implementation('com.example:api-client:2.0.0') {
            because 'The application uses methods introduced in API client 2.0.'
        }
    }
}
```

Nếu nhiều module cần cùng bộ version, dùng Gradle platform hoặc BOM phù hợp. Dependency constraints không tự thêm module vào graph; dependency declaration vẫn cần thiết nếu project trực tiếp sử dụng thư viện.

### Exclude dependency bắc cầu khi cần

Nếu một dependency kéo vào module không mong muốn và đã có cách cung cấp tương thích khác, có thể loại trừ dependency bắc cầu ở đúng edge:

```groovy
dependencies {
    implementation('com.example:legacy-integration:1.4.0') {
        exclude group: 'com.example', module: 'api-client'
    }

    implementation('com.example:api-client:2.0.0')
}
```

Chỉ exclude khi hiểu rõ thư viện `legacy-integration` cần API nào và có thể chạy với version được giữ lại. Exclude không làm cho một thư viện tự nhiên tương thích với API mới; nó chỉ thay đổi graph. Nếu thư viện cũ gọi method đã bị xóa, lỗi vẫn có thể xảy ra.

### Thay thế module (dependency substitution)

Trong một số trường hợp, cần thay một module bằng module khác, chẳng hạn chuyển từ artifact cũ sang artifact mới có API tương thích:

```groovy
configurations.configureEach {
    resolutionStrategy.dependencySubstitution {
        substitute module('com.example:old-client') using module('com.example:new-client:2.0.0')
    }
}
```

Substitution là quy tắc có phạm vi rộng nếu đặt trên nhiều configuration. Chỉ sử dụng khi hai module thực sự có thể thay thế nhau về API và runtime behavior. Việc thay tọa độ thành công không bảo đảm binary compatibility.

### Không dùng `force` như cách sửa mặc định

Có thể ép version bằng `resolutionStrategy.force`, nhưng đây thường là biện pháp mạnh và khó diễn tả chính sách lâu dài. Trước tiên nên xem `dependencyInsight`, xác định nguồn version và dùng constraint/platform phù hợp. Nếu vẫn cần `force`, giới hạn scope và ghi rõ lý do.

## 9. Kiểm tra artifact cuối cùng, không chỉ dependency graph

Ngay cả khi `runtimeClasspath` đã resolve đúng version, gói được triển khai vẫn có thể chứa JAR khác. Điều này có thể xảy ra khi:

- Task đóng gói tùy chỉnh sao chép dependency từ thư mục cũ.
- Fat JAR/shaded JAR được tạo từ một tập input khác.
- Docker image dùng một artifact cũ đã tồn tại trong build context.
- Pipeline tải artifact từ lần build trước hoặc tag container không bất biến.
- Application server cung cấp thư viện ở parent class loader.
- Script deploy trỏ tới thư mục hoặc version khác với output vừa build.

Vì vậy, sau khi kiểm tra Gradle graph, cần xác nhận nội dung gói và môi trường thực thi.

Với JAR thông thường:

```bash
jar tf build/libs/application.jar
```

Nếu dependency được đóng gói dạng nested JAR (ví dụ executable JAR của một số framework), xem cấu trúc archive và các thư mục chứa thư viện bên trong. Với container image, kiểm tra image digest, tag, filesystem và lệnh chạy. Không chỉ dựa vào tag mutable như `latest` để xác nhận version.

Đảm bảo pipeline build một artifact, kiểm tra artifact đó rồi triển khai chính artifact đó qua các môi trường. Cách này giúp tránh việc staging và production chạy hai gói khác nhau dù cùng hiển thị một số version label.

## 10. Classpath và JPMS module path

Từ Java 9, Java Platform Module System (JPMS) bổ sung khái niệm module path bên cạnh classpath truyền thống.

### Classpath

Trên classpath, các JAR và thư mục được đưa vào class loader theo cơ chế classpath. Những class không thuộc named module thường nằm trong unnamed module. Classpath vẫn được dùng rộng rãi cho ứng dụng và thư viện chưa modular hóa.

### Module path

Trên module path, JVM tìm các module có tên. Một module có thể khai báo:

- `requires`: module mà nó cần đọc.
- `exports`: package công khai cho module khác truy cập.
- `opens`: package cho phép truy cập phản chiếu sâu theo quy tắc JPMS.
- `uses` và `provides`: khai báo service consumer/provider.

Ví dụ:

```java
module com.example.application {
    requires com.example.api;
    exports com.example.application;
}
```

Nếu module `com.example.api` không export package chứa class cần dùng, code ở module ứng dụng có thể không truy cập được dù JAR đã nằm trên module path. Nếu thiếu `requires`, module hiện tại không có readability edge tới module kia.

Đây là vấn đề về **readability/accessibility**, khác với việc method không tồn tại trong class.

### Ví dụ module descriptor

```java
module com.example.api {
    exports com.example.api.client;
}
```

Module consumer:

```java
module com.example.application {
    requires com.example.api;
}
```

Nếu package đã export và module đã được require, code có thể truy cập public type/member theo quy tắc Java. Nhưng nếu API `send(String)` không tồn tại trong version JAR đang dùng, JPMS không thể tự tạo ra method đó. `requires` và `exports` không sửa được `NoSuchMethodError` do lệch phiên bản.

### Automatic module

Một JAR không có `module-info.class` nhưng được đặt trên module path có thể trở thành automatic module. Tên module có thể được xác định từ manifest `Automatic-Module-Name` hoặc suy ra từ tên JAR. Với thư viện dùng trong hệ thống modular, tên module ổn định trong manifest thường hữu ích hơn tên suy luận từ tên file.

Automatic module có các quy tắc khác named module: nó đọc các module khác và export các package của chính nó theo cơ chế automatic module. Dù vậy, tên module và split package vẫn cần được quản lý cẩn thận.

## 11. Lỗi API và lỗi JPMS không nên nhầm lẫn

Một thư viện có mặt trên module path nhưng không truy cập được có thể gây lỗi khác với trường hợp method không tồn tại.

| Triệu chứng | Nhóm nguyên nhân | Hướng kiểm tra |
|---|---|---|
| `NoSuchMethodError` | Class được nạp nhưng method descriptor không tồn tại | So sánh JAR compile/runtime, kiểm tra version và class loading |
| `NoSuchFieldError` | Field được bytecode tham chiếu không tồn tại trong class runtime | So sánh API/field giữa các JAR |
| `package ... is not visible` lúc compile | Module không export package hoặc module không được đọc | Kiểm tra `requires` và `exports` |
| `module ... does not read ...` hoặc module resolution failure | Thiếu quan hệ module hoặc module không resolve được | Kiểm tra `module-info.java` và module path |
| `IllegalAccessError` | Runtime access bị cấm theo access control hoặc module boundary | Kiểm tra public access, exports và module graph |
| `InaccessibleObjectException` | Reflection sâu bị module không mở package | Kiểm tra `opens` hoặc cơ chế mở package có chủ đích |
| `ClassNotFoundException` | API tải class không tìm được class | Kiểm tra classloader và runtime artifact |
| `NoClassDefFoundError` | JVM không thể định nghĩa/nạp class cần thiết | Kiểm tra runtime dependencies, class initialization và classloader |

Nếu lỗi nói rằng package không được export, thêm dependency version mới có thể không giải quyết được. Nếu lỗi là `NoSuchMethodError`, thêm `--add-exports` cũng không tạo method còn thiếu. Hãy đọc đúng exception đầu tiên và nguyên nhân gốc trong stack trace.

### `exports` và `opens`

`exports` cho phép module khác truy cập các public type trong package theo quy tắc JPMS. `opens` cho phép reflection sâu vào package trong những tình huống được module cho phép. Ví dụ:

```java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.internal to com.example.serializer;
}
```

Chỉ mở package cần thiết. Không nên mở toàn bộ module bằng các tùy chọn JVM rộng nếu không có lý do, vì điều đó làm suy yếu ranh giới module.

## 12. Cấu hình module path với Gradle

Với Gradle Java Plugin, có thể bật suy luận module path để Gradle nhận diện các module và đặt dependency phù hợp trên module path:

```kotlin
java {
    modularity.inferModulePath.set(true)
}
```

Dự án modular cần có `module-info.java` trong source set và module dependencies phù hợp. Ví dụ cấu trúc:

```text
src/main/java/
├── module-info.java
└── com/example/application/Main.java
```

Một `module-info.java` đơn giản:

```java
module com.example.application {
    requires java.net.http;
    requires com.example.api;
    exports com.example.application;
}
```

Bật module path inference không thay thế việc khai báo `requires`, `exports` hoặc kiểm tra module name. Gradle có thể đặt dependency trên module path, nhưng module descriptor vẫn quyết định readability và package visibility.

Nếu dự án kết hợp modular JAR và thư viện cũ không modular, cần xác định thư viện nào là named module, automatic module hoặc được đưa vào classpath. Cấu hình nhất quán giữa compile, test và runtime giúp tránh lỗi chỉ xuất hiện ở một giai đoạn.

## 13. Quy trình chẩn đoán từ exception tới dependency

Khi gặp lỗi “thư viện có nhưng thiếu method/field”, hãy làm theo trình tự:

1. **Xác định thời điểm:** compiler báo `cannot find symbol`, hay JVM ném `NoSuchMethodError`/`NoSuchFieldError` khi chạy?
2. **Ghi lại class và chữ ký:** đọc đầy đủ exception, bao gồm class, method/field và descriptor nếu có.
3. **Xác định class runtime:** dùng class-loading log hoặc kiểm tra classloader để biết class được nạp từ JAR nào.
4. **Kiểm tra API trong JAR:** dùng `javap -public` để xem method/field thực sự có mặt.
5. **So sánh configuration:** dùng `dependencyInsight` cho `compileClasspath`, `runtimeClasspath`, `testCompileClasspath` và `testRuntimeClasspath` khi cần.
6. **Tìm dependency bắc cầu:** xem đường nào kéo version cũ hoặc artifact khác vào graph.
7. **Kiểm tra package cuối cùng:** xem JAR/fat JAR/container được triển khai có chứa đúng artifact không.
8. **Kiểm tra JPMS:** nếu lỗi liên quan visibility hoặc readability, xem `module-info.java`, module path và exports/opens.
9. **Sửa nguồn gốc:** thống nhất version, điều chỉnh constraint/platform, loại dependency không phù hợp hoặc cập nhật thư viện phụ thuộc.
10. **Build và chạy lại trong cùng môi trường:** xác nhận artifact mới thực sự được dùng.

Các lệnh thường hữu ích:

```bash
./gradlew dependencyInsight --dependency api-client --configuration compileClasspath
./gradlew dependencyInsight --dependency api-client --configuration runtimeClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew clean test
./gradlew build
```

Khi cần biết class được nạp từ đâu:

```bash
java -Xlog:class+load=info -jar build/libs/application.jar
```

Khi cần kiểm tra API trong JAR:

```bash
javap -classpath path/to/api-client.jar -public com.example.ApiClient
```

`clean` có thể hữu ích khi nghi ngờ output cũ bị dùng lại, nhưng xóa build output không sửa dependency graph sai. Hãy xử lý nguyên nhân trước và dùng clean như một bước tái tạo output khi cần.

## 14. Phòng tránh lỗi bằng quản lý dependency rõ ràng

Có thể giảm nguy cơ lệch API bằng các thực hành sau:

- Dùng version xác định cho dependency trực tiếp.
- Dùng BOM hoặc Gradle platform khi một hệ sinh thái cần version alignment.
- Dùng dependency constraints để đặt version được chấp nhận cho module quan trọng.
- Bật dependency locking khi cần build tái lập và review thay đổi version.
- Tránh version động trong build phát hành nếu không có chính sách kiểm soát rõ.
- Hạn chế `compileOnly` cho thư viện thực sự cần có ở runtime.
- Không để compile classpath và runtime classpath cố ý dùng các version API không tương thích.
- Dùng `dependencyInsight` khi có xung đột thay vì đoán theo file khai báo trực tiếp.
- Kiểm tra artifact cuối cùng và image digest trước khi deploy.
- Kiểm thử tương thích thư viện ở runtime, không chỉ dựa vào compile thành công.
- Với JPMS, duy trì `module-info.java` và module names rõ ràng.
- Tránh đóng gói nhiều phiên bản hoặc nhiều bản class cùng tên trong một ứng dụng.

Với thư viện nội bộ, nên có chính sách semantic versioning và kiểm tra binary compatibility trước khi phát hành. Một thay đổi phá binary compatibility cần được xem là thay đổi lớn hoặc có kế hoạch migration phù hợp.

## 15. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| Gradle resolve thành công nghĩa là API chắc chắn tương thích | Resolve chỉ tạo graph hợp lệ theo metadata và rule; JVM linkage vẫn có thể thất bại. |
| Có dependency trong `build.gradle` nghĩa là JVM sẽ nạp đúng JAR đó | Runtime classpath, fat JAR, container và classloader của môi trường có thể khác. |
| `NoSuchMethodError` là lỗi thiếu dependency hoàn toàn | Class thường đã được nạp, nhưng không có method descriptor mà bytecode yêu cầu. |
| Thêm JAR mới vào classpath luôn sửa được lỗi | JVM có thể vẫn nạp class khác; cần xác định nguồn class thực tế và tránh duplicate class. |
| `compileOnly` tương đương `implementation` | `compileOnly` không tự đưa dependency vào runtime classpath. |
| Exclude một dependency luôn làm thư viện cũ tương thích | Exclude chỉ thay graph; thư viện vẫn có thể gọi API không còn tồn tại. |
| `requires` trong JPMS thêm method hoặc thay version | `requires` chỉ thiết lập readability giữa module; nó không thay đổi API của class. |
| `exports` và `opens` giống nhau | `exports` cho truy cập kiểu thông thường; `opens` cho deep reflection theo quy tắc module. |
| Tăng version là luôn an toàn | Version mới có thể thay đổi API hoặc hành vi; cần kiểm tra compatibility. |

## 16. Ví dụ tổng hợp: compile thành công nhưng runtime thất bại

Giả sử project có dependency như sau:

```groovy
dependencies {
    compileOnly 'com.example:api-client:2.0.0'
    runtimeOnly 'com.example:api-client:1.5.0'
}
```

Ứng dụng gọi API mới:

```java
package com.example.app;

import com.example.client.ApiClient;

public class Main {
    public static void main(String[] args) {
        ApiClient client = new ApiClient();
        System.out.println(client.sendAsync("hello"));
    }
}
```

Nếu `sendAsync(String)` chỉ có trong version 2.0.0, compiler nhìn thấy method và tạo bytecode. Khi chạy, runtime chỉ có version 1.5.0; JVM nạp `ApiClient` cũ và không tìm thấy method. Kết quả là `NoSuchMethodError`.

Cách sửa phù hợp có thể là:

```groovy
dependencies {
    implementation 'com.example:api-client:2.0.0'
}
```

Sau đó kiểm tra:

```bash
./gradlew dependencyInsight --dependency api-client --configuration compileClasspath
./gradlew dependencyInsight --dependency api-client --configuration runtimeClasspath
```

Hai configuration cần thể hiện version API phù hợp. Tiếp theo build lại artifact, xác nhận JAR hoặc container chứa đúng dependency và chạy lại ứng dụng trong môi trường đích.

Nếu dependency bắc cầu tiếp tục kéo một version khác, cần xem `dependencyInsight`, platform/constraint và compatibility của thư viện kéo dependency đó. Không nên chỉ ép version mà bỏ qua việc thư viện tiêu thụ có thực sự tương thích hay không.

## 17. Nguyên tắc cần ghi nhớ

Khi compiler không tìm thấy method hoặc field, hãy xem compile classpath và API mà compiler đang nhìn thấy. Khi ứng dụng đã biên dịch nhưng JVM ném `NoSuchMethodError` hoặc `NoSuchFieldError`, hãy nghi ngờ binary incompatibility hoặc class runtime khác với class đã dùng khi biên dịch. So sánh compile/runtime configurations, lần theo dependency bắc cầu bằng `dependencyInsight`, kiểm tra JAR thực tế bằng `javap` và xác định class được nạp bằng class-loading log.

Classpath và JPMS module path còn có khác biệt về module readability, package exports và reflection opens. Lỗi thiếu method là vấn đề API/linkage; lỗi package không visible hoặc module không đọc được là vấn đề module access. Phân biệt đúng hai nhóm này giúp chọn đúng cách sửa: thống nhất artifact/version khi API lệch, hoặc sửa module descriptor và cấu hình module path khi ranh giới JPMS không cho phép truy cập.
