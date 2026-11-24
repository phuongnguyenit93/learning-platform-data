# --initialize-at-build-time và phạm vi lớp được tác động

## 1. Vì sao cần điều khiển thời điểm khởi tạo lớp?

Trong module **SPRING_BOOT_NATIVE_IMAGE**, chúng ta dùng **Spring AOT** để chuẩn bị ứng dụng Spring Boot cho **GraalVM Native Image**, sau đó kiểm tra tính tương thích, thời gian khởi động, bộ nhớ, đóng gói container và vận hành executable. Một quyết định ảnh hưởng trực tiếp đến giai đoạn build và runtime là **thời điểm chạy class initializer**: lúc GraalVM đang tạo executable hay lúc tiến trình native bắt đầu chạy.

Java khởi tạo một class khi class được sử dụng lần đầu theo các quy tắc của JVM. Phần khởi tạo gồm static field initializers và static initializer block (phương thức khởi tạo lớp do compiler tạo). Việc nạp hoặc đọc metadata của class không nhất thiết đồng nghĩa với việc class đã được khởi tạo.

Native Image có thể chạy class initializer ngay trong quá trình tạo executable. Khi đó, các giá trị static đã được tính sẽ được lưu trong **image heap** và trở thành trạng thái ban đầu của chương trình native. Tùy chọn **--initialize-at-build-time** cho phép yêu cầu chính sách này cho class hoặc package cụ thể.

Sau bài học, người học có thể:

1. Phân biệt class loading, class initialization, build-time initialization và runtime initialization.
2. Giải thích **--initialize-at-build-time** tác động lên class/package nào.
3. Hiểu quan hệ kế thừa khiến superclass hoặc subclass liên quan cũng bị ảnh hưởng.
4. Nhận diện static initializer có phụ thuộc môi trường, thời gian, random, file, mạng hoặc thread.
5. Cấu hình class initialization có phạm vi hẹp qua GraalVM Native Build Tools với Maven/Gradle.
6. Dùng trace/report để xác định class nào được khởi tạo ở build time và vì sao.
7. Kiểm thử hành vi JVM và native sau khi thay đổi chính sách.

> **Nguyên tắc:** chỉ đưa một class sang build-time initialization khi static initialization của nó an toàn, xác định và không phụ thuộc môi trường chạy. Tùy chọn này có thể giảm công việc lúc khởi động, nhưng cũng có thể đóng băng dữ liệu hoặc side effect vào executable.

## 2. Class initialization trong Java diễn ra khi nào?

Một class thường trải qua các giai đoạn:

- **Loading:** JVM tìm bytecode và tạo đối tượng biểu diễn class.
- **Linking:** verification, preparation và resolution theo nhu cầu.
- **Initialization:** chạy static field initializers và static initializer block đúng một lần theo class initialization semantics.

Ví dụ:

~~~java
public final class CurrencyTable {
    static final Map<String, String> SYMBOLS;

    static {
        Map<String, String> values = new HashMap<>();
        values.put("USD", "$");
        values.put("EUR", "€");
        SYMBOLS = Map.copyOf(values);
    }

    private CurrencyTable() {}
}
~~~

Khi class được khởi tạo, block static chạy và tạo map. Nếu class được khởi tạo trong JVM thông thường, công việc đó diễn ra ở runtime của ứng dụng. Nếu Native Image được cấu hình để khởi tạo class này ở build time, block static chạy trong JVM đang thực hiện native build; trạng thái static sau đó được đưa vào image heap.

### 2.1. Class loading không phải class initialization

Một số thao tác chỉ nạp class mà chưa khởi tạo nó:

~~~java
Class<?> type = Class.forName(
    "com.example.CurrencyTable",
    false,
    Thread.currentThread().getContextClassLoader()
);
~~~

Tham số thứ hai là false, nên lời gọi này không yêu cầu khởi tạo class. Nếu truyền true, JVM sẽ khởi tạo class khi cần theo quy tắc của Class.forName.

Những thao tác như tạo instance, gọi static method hoặc đọc/ghi một static field không phải compile-time constant có thể kích hoạt initialization. Các biến static final có kiểu nguyên thủy/String và giá trị compile-time constant có thể được compiler inline; đọc chúng không nhất thiết kích hoạt class initialization.

Vì vậy, khi điều tra một initializer, cần phân biệt:

- Class có xuất hiện trong classpath hoặc được load không?
- Static initializer có thực sự được thực thi không?
- Nó được thực thi ở JVM build hay tiến trình native runtime?

### 2.2. Điều gì được lưu vào image heap?

Với class được khởi tạo ở build time, giá trị static sau khi initializer hoàn tất có thể được lưu trong executable. Ví dụ, map bất biến trong CurrencyTable đã được tạo trong lúc build; khi native executable chạy, chương trình dùng trạng thái đã lưu thay vì chạy lại block static đó.

Điều này không có nghĩa mọi trạng thái Java đều có thể lưu tùy ý. Các object reachable từ static fields phải tương thích với image heap. Native Image có thể từ chối build nếu trạng thái chứa object hoặc tài nguyên không thể chuyển sang image. Một class được yêu cầu khởi tạo ở runtime cũng không được có instance của nó nằm sẵn trong image heap.

## 3. Chính sách mặc định của Native Image

Không nên giả định mọi class ứng dụng đều được khởi tạo ở build time hoặc mọi class đều được khởi tạo ở runtime.

Theo tài liệu GraalVM hiện hành:

- Các class ứng dụng mặc định được khởi tạo ở runtime, **trừ các class mà Native Image chứng minh là an toàn để khởi tạo ở build time**.
- Native Image phân tích static initializer và các lời gọi liên quan để tìm những class an toàn.
- Nhiều class nền tảng JDK được Native Image xử lý với chính sách build-time riêng.
- Người phát triển có thể ghi đè chính sách mặc định cho class/package bằng tùy chọn tường minh.

Một class thường được xem là an toàn nếu các relevant supertypes của nó cũng an toàn và initializer không gọi phương thức không an toàn hoặc kích hoạt class không an toàn. Phân tích này có giới hạn; ví dụ lời gọi native code hoặc virtual method khó xác định target có thể khiến initializer không được chứng minh an toàn.

**Spring AOT không đồng nghĩa với việc toàn bộ class của ứng dụng Spring Boot được khởi tạo ở build time.** Spring AOT sinh mã bootstrap và metadata để Native Image phân tích; class initialization vẫn tuân theo chính sách của Native Image và các cấu hình class-init mà dependency cung cấp.

## 4. Tùy chọn --initialize-at-build-time

Cú pháp thường dùng:

~~~bash
native-image \
  --initialize-at-build-time=com.example.catalog.ImmutableCatalog \
  -jar application.jar
~~~

Tùy chọn nhận danh sách phân tách bằng dấu phẩy, gồm tên class đầy đủ hoặc package. Ví dụ:

~~~bash
# Chỉ định một class
--initialize-at-build-time=com.example.catalog.ImmutableCatalog

# Chỉ định package
--initialize-at-build-time=com.example.catalog

# Chỉ định nhiều class/package
--initialize-at-build-time=com.example.catalog.ImmutableCatalog,com.example.format.FixedTables
~~~

Ví dụ là hình dạng cấu hình của Native Image CLI. Khi dùng Spring Boot, hãy truyền build argument qua Maven/Gradle Native Build Tools hoặc cơ chế Buildpacks phù hợp thay vì tự thay thế toàn bộ lệnh do plugin quản lý.

### 4.1. Phạm vi một class

Dùng tên đầy đủ để tác động hẹp:

~~~bash
--initialize-at-build-time=com.example.catalog.ImmutableCatalog
~~~

Đây là lựa chọn dễ review nhất khi chỉ một class có static lookup table bất biến cần tính trước. Không nên thêm toàn bộ package nếu chỉ có một initializer đã được chứng minh an toàn.

### 4.2. Phạm vi package

Có thể chỉ định package:

~~~bash
--initialize-at-build-time=com.example.catalog
~~~

Mọi class thuộc phạm vi package mà Native Image nhận diện sẽ chịu chính sách này, cùng những quan hệ kiểu liên quan. Package rộng có thể kéo theo class có static initializer phụ thuộc môi trường, logging, file, mạng hoặc trạng thái runtime.

Tên package Java là phạm vi cấu hình; không suy luận rằng một package cha tự động bao gồm mọi package con theo cách glob của filesystem. Nếu muốn bao gồm các package con, hãy xác nhận quy tắc của GraalVM version đang dùng và xem báo cáo class initialization để biết chính xác tập class được tác động.

### 4.3. Không có danh sách class/package

Một tùy chọn không kèm danh sách có phạm vi rất rộng và có thể yêu cầu khởi tạo tất cả class trong phạm vi mà version/toolchain hỗ trợ. Cách này không phù hợp làm mặc định cho ứng dụng Spring Boot production. Luôn xem native-image --help của GraalVM đang dùng và chọn class/package cụ thể.

### 4.4. Quan hệ với superclass và superinterface

Java class initialization có quy tắc về hierarchy. Khi class được khởi tạo, các superclass liên quan phải được khởi tạo trước; các superinterface có default methods cũng có thể thuộc tập relevant supertypes.

Vì thế, khi chỉ định một class build time, Native Image có thể cần đưa các relevant supertypes/superclasses của nó vào build-time initialization để giữ đúng semantics. Tùy chọn build-time hiện hành mô tả các class/package được chỉ định và các superclass liên quan.

Đừng xem flag như một thay đổi độc lập trên một class trong chân không. Kiểm tra hierarchy nếu class kế thừa từ base class có static initializer phụ thuộc runtime.

## 5. Đối chiếu với --initialize-at-run-time

Tùy chọn đối ứng:

~~~bash
--initialize-at-run-time=com.example.config.RuntimeSettings
~~~

Nó yêu cầu Native Image trì hoãn initialization của class/package đến lúc executable chạy. Đây là lựa chọn phù hợp khi static state phải phản ánh môi trường process, chẳng hạn biến môi trường, cấu hình runtime hoặc trạng thái được tạo khi ứng dụng khởi động.

Ví dụ:

~~~java
public final class RuntimeSettings {
    static final String REGION = System.getenv("APP_REGION");
    static final Instant PROCESS_STARTED_AT = Instant.now();

    private RuntimeSettings() {}
}
~~~

Nếu class này bị khởi tạo ở build time, APP_REGION và thời điểm hiện tại có thể bị đọc từ **môi trường build**, rồi giá trị được lưu trong image heap. Khi container chạy ở môi trường khác, static fields không tự được tính lại. Nếu class được khởi tạo ở runtime, các giá trị được lấy từ môi trường của tiến trình native.

### 5.1. Scope của runtime initialization

**--initialize-at-run-time** cũng nhận class hoặc package. Chính sách runtime có thể kéo theo các subclass liên quan để giữ đúng semantics. Điều này đặc biệt quan trọng khi base class được khởi tạo runtime nhưng subclass đã bị đưa vào image heap từ build time.

Tránh cấu hình cùng một class hoặc hierarchy theo hai chính sách xung đột. Nếu GraalVM báo mâu thuẫn, hãy kiểm tra class nào được chỉ định trực tiếp, class nào bị kéo theo qua inheritance và metadata nào do dependency/plugin cung cấp.

### 5.2. Bảng so sánh

| Tiêu chí | Build-time initialization | Runtime initialization |
| --- | --- | --- |
| Thời điểm chạy class initializer | Trong JVM thực hiện native build. | Khi native executable chạy và class được dùng lần đầu. |
| Static state | Có thể được lưu trong image heap. | Được tạo trong process runtime. |
| Phụ thuộc environment | Có nguy cơ đóng băng giá trị từ build host. | Đọc giá trị của môi trường chạy. |
| Công việc lúc startup | Có thể giảm vì initializer đã chạy. | Initializer vẫn cần chạy khi class được dùng. |
| Kích thước image | Có thể tăng nếu lưu nhiều object/cache. | Không lưu trạng thái initializer đó vào image heap. |
| Phù hợp với | Dữ liệu bất biến, xác định, an toàn. | Time, random, environment, file/network, process state. |

## 6. Phạm vi lớp được tác động trong hierarchy

Chính sách class initialization chịu các ràng buộc từ quan hệ kế thừa:

- Class được khởi tạo ở build time cần các relevant supertypes được khởi tạo ở build time.
- Class được khởi tạo ở runtime kéo theo các relevant subtypes phải được khởi tạo ở runtime.
- Superinterface có default method có thể nằm trong relevant supertypes cần xét.
- Một class được khởi tạo runtime không được có instance của nó nằm sẵn trong image heap.

Ví dụ:

~~~java
class BaseCatalog {
    static final Map<String, String> LABELS = Map.of("A", "Active");
}

class RegionalCatalog extends BaseCatalog {
    static final String REGION = "north";
}
~~~

Nếu RegionalCatalog được yêu cầu khởi tạo ở build time, superclass BaseCatalog cũng phải được khởi tạo đúng theo quy tắc hierarchy. Ngược lại, nếu BaseCatalog được yêu cầu runtime, subclass liên quan không thể tùy ý được khởi tạo build time.

Hãy xem các class liên quan trong log thay vì chỉ kiểm tra tên class đã ghi trong build argument.

## 7. Khi nào nên dùng build-time initialization?

### 7.1. Ứng viên thường phù hợp

Một class có thể là ứng viên nếu initializer:

- Chỉ tính toán từ hằng số hoặc dữ liệu cố định đi cùng source/artifact.
- Tạo bảng tra cứu bất biến, map/list đã đóng băng hoặc dữ liệu chuẩn hóa xác định.
- Không đọc biến môi trường, system property thay đổi theo deployment hay thời gian hiện tại.
- Không tạo thread, executor, socket, connection pool hoặc file handle.
- Không mở kết nối mạng/database hoặc phụ thuộc secret của build host.
- Không khởi tạo framework/service có lifecycle gắn với process.

Ví dụ bảng tra cứu xác định:

~~~java
final class ImmutableCatalog {
    static final Map<String, String> LABELS = Map.of(
        "PENDING", "Pending",
        "PAID", "Paid",
        "CANCELLED", "Cancelled"
    );

    private ImmutableCatalog() {}
}
~~~

Nếu class này thực sự chỉ tạo dữ liệu bất biến, không phụ thuộc môi trường và object graph của nó tương thích với image heap, có thể thử chỉ định riêng class này. Sau đó đo thời gian build, kích thước image, startup và memory để xác nhận lợi ích.

### 7.2. Các class thường cần thận trọng

Không tự động đưa các nhóm sau vào build time:

| Nhóm | Rủi ro |
| --- | --- |
| Đọc System.getenv() hoặc System.getProperty() | Giá trị có thể đến từ build host thay vì container runtime. |
| Instant.now(), LocalDateTime.now(), timezone/locale mặc định | Thời điểm hoặc môi trường build bị đóng băng. |
| Random, SecureRandom, seed hoặc key material | Trạng thái ngẫu nhiên/bảo mật có thể bị tạo trước và dùng lại ngoài ý muốn. |
| Logger, logging backend và cấu hình logging | Có thể khởi tạo sink, path hoặc trạng thái phụ thuộc process/build environment. |
| JDBC driver, connection pool, database client | Có thể giữ trạng thái kết nối hoặc cấu hình không phù hợp runtime. |
| File watcher, thread, executor, socket | Lifecycle và tài nguyên hệ điều hành không phù hợp để đóng băng trong image heap. |
| Native library wrapper | Có thể gọi native code hoặc phụ thuộc thư viện/OS của máy build. |
| Class đọc secret hoặc chứng thư riêng môi trường | Có nguy cơ đưa dữ liệu nhạy cảm vào executable. |

Đây là nhóm cần điều tra, không phải quy tắc cấm tuyệt đối cho mọi class cùng package. Hãy đọc static initializer và các lời gọi gián tiếp trước khi quyết định.

### 7.3. Rủi ro dữ liệu nhạy cảm

Nếu static initializer đọc token, password, private key hoặc nội dung cấu hình từ build host, dữ liệu có thể được lưu vào image heap và trở thành một phần của executable. Image có thể được phát hành sang nhiều môi trường; vì vậy không dùng build-time initialization để nạp secret production hoặc secret của pipeline.

## 8. Ví dụ minh họa sự khác nhau

Giả sử có hai class:

~~~java
final class StaticCatalog {
    static final Map<String, String> VALUES = Map.of(
        "A", "Alpha",
        "B", "Beta"
    );
}

final class RuntimeRegion {
    static final String REGION = System.getenv("APP_REGION");
}
~~~

Class thứ nhất chỉ tạo map từ dữ liệu cố định; class thứ hai đọc biến môi trường. Có thể thử cấu hình:

~~~bash
native-image \
  --initialize-at-build-time=com.example.StaticCatalog \
  --initialize-at-run-time=com.example.RuntimeRegion \
  -jar application.jar
~~~

Kết quả mong muốn về mặt chính sách:

- StaticCatalog được khởi tạo trong quá trình build; map đã có trong image heap.
- RuntimeRegion được khởi tạo trong process native; giá trị APP_REGION đến từ môi trường container/host khi chạy.

Đây là ví dụ về chính sách, không phải cam kết hai class có thể build nguyên trạng nếu chúng nằm trong project khác. Hãy thay tên package/class bằng code thật, kiểm tra hierarchy và xác nhận log của GraalVM.

## 9. Cấu hình với GraalVM Native Build Tools

Trong dự án Spring Boot, ưu tiên cấu hình qua plugin native đang dùng để giữ các thiết lập khác do Spring Boot/AOT cung cấp.

### 9.1. Gradle Kotlin DSL

Trong build.gradle.kts:

~~~kotlin
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add(
                "--initialize-at-build-time=com.example.catalog.ImmutableCatalog"
            )
            buildArgs.add(
                "--initialize-at-run-time=com.example.config.RuntimeSettings"
            )
        }
    }
}
~~~

Đoạn này giả định plugin org.graalvm.buildtools.native đã được áp dụng và binary main tồn tại. Giữ các build arguments hiện có của dự án; chỉ thêm các class đã được đánh giá.

### 9.2. Gradle Groovy DSL

Trong build.gradle:

~~~groovy
graalvmNative {
    binaries {
        main {
            buildArgs.add(
                '--initialize-at-build-time=com.example.catalog.ImmutableCatalog'
            )
            buildArgs.add(
                '--initialize-at-run-time=com.example.config.RuntimeSettings'
            )
        }
    }
}
~~~

Cú pháp extension có thể khác theo version Native Build Tools. Đọc DSL reference đúng version nếu dự án dùng binary configuration khác hoặc có nhiều executable.

### 9.3. Maven

Trong cấu hình native-maven-plugin:

~~~xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--initialize-at-build-time=com.example.catalog.ImmutableCatalog</buildArg>
            <buildArg>--initialize-at-run-time=com.example.config.RuntimeSettings</buildArg>
        </buildArgs>
    </configuration>
</plugin>
~~~

Đây là phần cấu hình plugin trong POM đã khai báo version và profile phù hợp. Không thay thế toàn bộ cấu hình plugin hiện tại bằng đoạn minh họa; hợp nhất hai buildArg vào buildArgs hiện có.

### 9.4. native-image.properties

Một artifact có thể cung cấp Native Image options qua file native-image.properties trong metadata directory phù hợp trên classpath:

~~~properties
Args = --initialize-at-build-time=com.example.catalog.ImmutableCatalog
~~~

Cách này phù hợp khi một thư viện cần phân phối cấu hình gắn với chính artifact của nó. Hãy cân nhắc ảnh hưởng đến mọi ứng dụng tiêu thụ thư viện; không đóng gói chính sách rộng hoặc phụ thuộc môi trường vào dependency dùng chung.

Với Spring Boot, AOT có thể sinh metadata dưới META-INF/native-image/{groupId}/{artifactId}/. Nếu bổ sung file thủ công, chọn thư mục con riêng theo hướng dẫn Spring Boot của version đang dùng để tránh đụng file được sinh tự động. Với chính ứng dụng, cấu hình buildArgs của native plugin thường dễ thấy và dễ review hơn.

## 10. Chẩn đoán class initialization

Khi build báo class bị khởi tạo sai thời điểm hoặc có object không thể lưu trong image heap, cần biết **class nào** được khởi tạo và **vì sao**.

### 10.1. Trace một class cụ thể

Dùng tùy chọn trace của Native Image:

~~~bash
native-image \
  --trace-class-initialization=com.example.config.RuntimeSettings \
  -jar application.jar
~~~

Trace giúp xác định initializer được chạy ở đâu và đường đi nào dẫn đến việc khởi tạo. Tên tùy chọn/chức năng chi tiết có thể thay đổi theo GraalVM release; kiểm tra native-image --help-extra hoặc tài liệu đúng version.

### 10.2. In báo cáo class initialization

Một số GraalVM version cung cấp tùy chọn expert:

~~~bash
native-image -H:+PrintClassInitialization -jar application.jar
~~~

Báo cáo giúp xem class được khởi tạo ở build time/runtime và lý do Native Image phân loại chúng. Đây là tùy chọn phụ thuộc version; nếu không được nhận diện, xem native-image --expert-options-all và dùng trace class initialization tương ứng.

### 10.3. Đọc các lỗi thường gặp

| Thông báo/dấu hiệu | Ý nghĩa có thể | Hướng xử lý |
| --- | --- | --- |
| Class đáng lẽ runtime nhưng đã khởi tạo ở build time | Class bị kích hoạt gián tiếp bởi một initializer khác hoặc bị ép chính sách build-time. | Dùng trace để tìm caller; điều chỉnh chính sách cho class hoặc dependency gây kích hoạt. |
| Object của class runtime-init xuất hiện trong image heap | Một static field của class build-time giữ reference tới object cần tạo ở runtime. | Tách static state, trì hoãn việc tạo object hoặc sửa chính sách hierarchy. |
| Initializer đọc giá trị khác giữa build và runtime | Environment/system property/time đã được đọc trong build JVM. | Chuyển class sang runtime hoặc đưa giá trị vào constructor/configuration lúc app khởi động. |
| Build thất bại do side effect hoặc native call | Initializer chạy thao tác không phù hợp với build-time execution. | Trì hoãn initialization; không cố ép build time chỉ để bỏ cảnh báo. |
| Image lớn hơn sau khi bật build-time cho package | Nhiều static objects/cache được lưu vào image heap. | Thu hẹp scope về class cần thiết, đo lại image size và memory. |
| Runtime behavior sai sau khi build thành công | State từ build host bị đóng băng hoặc thứ tự initialization thay đổi. | So sánh JVM/native, kiểm tra static fields và environment tại hai giai đoạn. |

### 10.4. Trình tự khoanh vùng

~~~mermaid
flowchart TD
    A[Native build báo class initialization issue] --> B[Đọc class và thời điểm trong thông báo]
    B --> C[Trace class initialization]
    C --> D[Tìm static initializer và dependency được gọi]
    D --> E{Có phụ thuộc runtime hoặc side effect?}
    E -->|Có| F[Để class khởi tạo runtime]
    E -->|Không| G[Kiểm tra image heap và hierarchy]
    G --> H[Thử scope hẹp trên một class]
    F --> I[Build lại và chạy smoke tests]
    H --> I
    I --> J[So sánh startup, image size và behavior]
~~~

Không thêm **--initialize-at-build-time** rộng chỉ để làm build hết lỗi. Nếu một class cần runtime state, giữ nó ở runtime và sửa nơi tạo trạng thái thay vì đóng băng trạng thái đó.

## 11. Bài thực hành: chọn đúng phạm vi class initialization

**Bối cảnh:** một dịch vụ Spring Boot có bảng tra cứu trạng thái đơn hàng bất biến, đồng thời có class đọc region từ biến môi trường và class tạo timestamp khi process bắt đầu. Nhóm muốn giảm startup mà vẫn giữ hành vi đúng khi cùng một native image được triển khai ở nhiều môi trường.

### Nhiệm vụ

1. Tạo ImmutableCatalog với static lookup table được xây dựng chỉ từ dữ liệu cố định.
2. Tạo RuntimeSettings đọc APP_REGION và ProcessClock ghi nhận thời điểm process bắt đầu.
3. Đọc static initializers và phân loại class nào có thể khởi tạo build time, class nào phải runtime.
4. Build native với --initialize-at-build-time chỉ cho ImmutableCatalog, và --initialize-at-run-time cho các class phụ thuộc môi trường/thời gian.
5. Bật trace cho RuntimeSettings để xác nhận initializer không chạy trong build host.
6. Chạy cùng executable hai lần với APP_REGION khác nhau; xác nhận mỗi process nhận đúng giá trị runtime.
7. So sánh với JVM execution và ghi lại startup, image size, RSS, build duration.
8. Mở rộng thử nghiệm với package scope, sau đó kiểm tra báo cáo để liệt kê toàn bộ class bị ảnh hưởng.
9. Thử một class kế thừa để quan sát ràng buộc superclass/subclass.
10. Lưu cấu hình cuối cùng, log trace và kết quả test.

### Biên bản kết quả

| Bằng chứng | Nội dung cần ghi |
| --- | --- |
| Class được chỉ định build time | Tên đầy đủ, lý do an toàn, static state sau initialization. |
| Class được chỉ định runtime | Tên đầy đủ, nguồn environment/time và lý do trì hoãn. |
| Phạm vi thực tế | Danh sách class trực tiếp, superclass/subclass liên quan. |
| Trace/report | GraalVM version, lệnh, output và lý do initialization. |
| Maven/Gradle config | File cấu hình, plugin version và build arguments. |
| JVM/native behavior | Giá trị static, profile và environment trong mỗi lần chạy. |
| Hiệu năng | Build duration, startup-to-ready, image size, RSS và điều kiện đo. |

### Tiêu chí hoàn thành

- [ ] Phân biệt được class loading với class initialization.
- [ ] Giải thích được static state của build-time initialized class được lưu trong image heap.
- [ ] Chỉ định được một class riêng bằng --initialize-at-build-time.
- [ ] Giải thích được ảnh hưởng tới superclass và subclass liên quan.
- [ ] Không đóng băng environment, timestamp, secret hoặc process resource vào image.
- [ ] Maven/Gradle truyền đúng build arguments cho Native Image.
- [ ] Trace/report chứng minh class được khởi tạo đúng thời điểm.
- [ ] JVM và native có cùng behavior theo môi trường chạy.
- [ ] Có số đo để đánh giá lợi ích và chi phí của lựa chọn.

## 12. Câu hỏi tự đánh giá

1. Class loading khác class initialization ở điểm nào?
2. Vì sao static fields của class khởi tạo build time có thể xuất hiện trong image heap?
3. --initialize-at-build-time=com.example.Foo có thể ảnh hưởng tới superclass nào của Foo?
4. --initialize-at-run-time=com.example.Base có thể ảnh hưởng tới subclass nào?
5. Vì sao đọc System.getenv() trong static initializer có thể gây lỗi khi một native image được triển khai ở nhiều môi trường?
6. Vì sao package scope có rủi ro cao hơn chỉ định một class?
7. Khi nào nên để logging, database client hoặc random generator khởi tạo ở runtime?
8. Dùng --trace-class-initialization để xác định điều gì?
9. Vì sao build thành công chưa chứng minh class initialization policy là đúng?
10. Làm thế nào để đánh giá trade-off giữa startup time, build time và image size?

## 13. Tài liệu chính thức

Class initialization options và các diagnostic flags có thể thay đổi theo GraalVM release. Đối chiếu đúng phiên bản toolchain của dự án:

- [GraalVM Native Image — Specify Class Initialization Explicitly](https://www.graalvm.org/latest/reference-manual/native-image/guides/specify-class-initialization/): class/package scope và hai tùy chọn build-time/runtime.
- [GraalVM Native Image — Class Initialization](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/ClassInitialization/): image heap, automatic initialization of safe classes và hierarchy constraints.
- [GraalVM Native Image — Command-line Options](https://www.graalvm.org/latest/reference-manual/native-image/overview/Options/): cú pháp và tùy chọn theo phiên bản.
- [GraalVM Native Build Tools — Gradle Plugin](https://graalvm.github.io/native-build-tools/latest/gradle-plugin): cấu hình buildArgs cho native binary.
- [GraalVM Native Build Tools — Maven Plugin](https://graalvm.github.io/native-build-tools/latest/maven-plugin.html): cấu hình native build arguments trong Maven.
- [Spring Boot — Advanced Native Image Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html): lưu ý AOT, metadata và cách tích hợp native image.
- [Spring Boot — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html): closed-world assumptions và vai trò của Spring AOT.

**Điểm cần nhớ:** **--initialize-at-build-time** chuyển công việc static initialization sang giai đoạn tạo executable và lưu trạng thái phù hợp vào image heap. Hãy chỉ định class cụ thể đã chứng minh an toàn, hiểu ảnh hưởng hierarchy, giữ dữ liệu phụ thuộc môi trường ở runtime và xác minh bằng trace cùng test trên executable thật.

