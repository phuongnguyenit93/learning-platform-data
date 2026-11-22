# Không để lộ kiểu phụ thuộc riêng, đối tượng nội bộ hoặc ngoại lệ của plugin qua API Java

## 1. Mục tiêu: ranh giới API ổn định giữa host và plugin

Hệ thống mở rộng Java cho phép **host** chọn và gọi **plugin** bằng một hợp đồng dùng chung. Plugin có thể chứa SDK của vendor, thư viện phiên bản riêng, class loader riêng hoặc module trong `ModuleLayer` khác. Nếu những chi tiết implementation vô tình đi qua API, host cũng bị buộc phải biết chúng. Mỗi lần đổi thư viện, đổi plugin hoặc nâng version, ta có nguy cơ làm hỏng mã của host và các plugin khác.

Phản ví dụ:

```java
// Mã minh họa API xấu, không phải chương trình hoàn chỉnh.
import vendor.sdk.VendorRequest;
import vendor.sdk.VendorResult;
import vendor.sdk.VendorException;

public interface BadPlugin {
    VendorResult process(VendorRequest input)
        throws VendorException;
}
```

Hợp đồng trên gây ba vấn đề trực tiếp:

1. **Rò kiểu dependency riêng:** client phải biết `VendorRequest` và `VendorResult` mới compile/call được. Đổi SDK có thể buộc sửa cả host.
2. **Rò object nội bộ:** `VendorResult` có thể mang cache, mutable model, session, callback hoặc reference tới class loader, khiến host vô tình giữ trạng thái mà plugin sở hữu.
3. **Rò ngoại lệ:** host phải catch `VendorException`; message/cause/stack trace có thể chứa internal path, endpoint, dữ liệu nhạy cảm và khiến client phụ thuộc vào chi tiết vendor.

**Nguyên tắc thiết kế:** public API do **host hoặc shared-api module** sở hữu, chỉ dùng **kiểu chung ổn định** và những kiểu JDK phù hợp. Plugin dùng một *adapter* để chuyển đổi giữa contract chung và implementation-specific SDK. Ngoại lệ vendor được xử lý trong adapter và chuyển thành **lỗi chung theo hợp đồng**.

```text
                     SHARED API BOUNDARY
                ┌─────────────────────────────┐
   Host ────────►│ Request / Result / ErrorCode │◄──── Plugin Adapter
                │ public Plugin interface      │          │
                └─────────────────────────────┘          ▼
                        ▲                          Private SDK / JAR
                        │                          - vendor request/model
                        │                          - vendor exception
                        └── chỉ DTO, mã lỗi chung ────────┘
```

Dấu hiệu thành công: **host compile được chỉ với shared API và JDK, không cần vendor JAR**. Khi plugin thay vendor SDK nhưng giữ nguyên semantics của API, mã host không phải đổi theo.

## 2. Những vị trí thường xuyên rò kiểu phụ thuộc

### 2.1. Public/protected signatures

Hãy kiểm tra toàn bộ bề mặt API, không chỉ kiểu trả về của một method:

```java
// Tất cả là PHẢN VÍ DỤ; các kiểu Vendor* chỉ mang tính minh họa.
VendorResult process(VendorRequest input);

List<VendorResult> processAll(List<VendorRequest> inputs);

Optional<VendorSession> openSession(String id);

CompletionStage<VendorResult> processAsync(String input);

void subscribe(Consumer<VendorEvent> listener);

Supplier<? extends VendorSession> newSessionFactory();

<T extends VendorRecord> T map(T source);
```

Những mẫu trên cũng leak qua **generic arguments và bounds**. Java type erasure không xóa việc compiler/source clients và nhiều API reflection cần nhìn thấy generic signatures. Vì vậy `List<VendorResult>` không tự trở thành contract ổn định chỉ vì runtime descriptor có thể là `List`.

Các vị trí khác phải audit: public/protected constructors, fields, getters/setters, record components, annotation types, type parameters, interface default methods, factory return types, callback event types và phương thức public trong lớp API.

**Quy tắc kiểm thử:** đặt một ứng dụng mẫu chỉ phụ thuộc vào `shared-api.jar` trên compile classpath; nếu compiler đòi `vendor.jar` để dùng interface/DTO thì đã rò dependency.

### 2.2. Trả `Object` không thật sự che object nội bộ

Phản ví dụ:

```java
// Mã minh họa không độc lập.
Object execute(Object request);

Map<String, Object> getMetadata();

Object getInternalSession();
```

Nếu object thực sự là `vendor.sdk.VendorResult`, host cuối cùng vẫn phải cast, phản chiếu hoặc truyền tiếp object private. Khi đó còn xuất hiện rủi ro class loader, data ownership và lifetime mà compiler không phát hiện được.

Cũng không nên đóng vendor object vào một DTO chung có field `Object details`; kiểu khai báo ngoài cùng không nói được nội dung thực. Phải kiểm tra **toàn bộ object graph** gồm elements trong collections, optional values, callback captures và async completion results.

`Map<String,String>` có thể phù hợp nếu cấu trúc dữ liệu thật sự là key-value đã có schema, nhưng không nên lạm dụng `Map<String,Object>` để tránh thiết kế typed DTO. API mạnh cần **ngữ nghĩa dữ liệu rõ ràng**, không chỉ tên kiểu chung chung.

### 2.3. Rò kiểu qua exception hoặc callback

Ngay cả interface không khai báo `throws` vẫn có thể để lọt runtime exception của vendor. Callback kiểu `Consumer<Throwable>` cũng có thể gửi raw private exception sang host. `CompletionStage<Result>` có thể hoàn thành lỗi với `CompletionException` bọc vendor failure.

Một số kiểu không nên trả qua boundary chỉ vì host có thể giữ lâu: `Class<?>` của plugin, `ClassLoader`, `MethodHandle`, `Throwable` có cause là private exception, stream/session sở hữu nội bộ, thread hoặc lambda callback gắn với plugin instance. Chúng vừa rò detail vừa có thể khiến class loader cũ không được garbage collection sau khi plugin dừng.

## 3. Shared API thiết kế như thế nào?

### 3.1. Chỉ chứa hợp đồng chung

Ví dụ interface sạch:

```java
package com.example.api;

public interface TextPlugin {
    String id();
    TextResult convert(TextRequest request) throws PluginFailure;
}
```

Các kiểu chung có thể là:

```java
// Minh họa: tách các public types ra từng file trong code thật.
public record TextRequest(String requestId, String text) {}

public record TextResult(String requestId, String text) {}

public enum FailureCode {
    INVALID_INPUT,
    DEPENDENCY_FAILURE,
    INTERNAL_FAILURE
}
```

Hai snippet trên chỉ giúp đọc contract, không phải bộ file hoàn chỉnh. Mục 8 có **ví dụ chạy được Java 17+**, đúng package và đúng tên tệp.

**Đặc điểm cần có:** kiểu contract được sở hữu chung, semantics rõ, không đưa model vendor vào trường dữ liệu, không trả session/connection do plugin sở hữu. Khi plugin nâng version, host còn có thể kiểm chứng compatibility mà không biết vendor nào ở bên dưới.

### 3.2. Adapter/anti-corruption layer

```text
 Host TextRequest
         │
         ▼
  Plugin Adapter
  - validate public fields
  - map to private VendorRequest
         │
         ▼
  Private Vendor SDK
  - VendorResponse
  - VendorException
         │
         ▼
  Plugin Adapter
  - map VendorResponse -> TextResult
  - map VendorException -> PluginFailure
         │
         ▼
 Host TextResult hoặc FailureCode
```

**Chuyển đổi dữ liệu** là một thao tác thật, không chỉ ép kiểu hoặc bọc object:

- Lấy những field mà contract cần, loại dữ liệu implementation-specific.
- Chuyển đơn vị, encoding, timezone, nullable fields theo định nghĩa chung.
- Kiểm tra dải giá trị, kích thước dữ liệu và input/output schema.
- Sao chép dữ liệu cần tách ownership, thay vì trả reference tới cache nội bộ.
- Không giữ phụ thuộc vendor trong public exception, DTO hay event.

Adapter đồng thời là chỗ lý tưởng cho version/capability compatibility: plugin có thể thay thuật toán hoặc vendor SDK nhưng giữ contract không đổi.

### 3.3. Record, immutable DTO và ownership

Java record giúp mô tả dữ liệu ngắn gọn, nhưng **record chỉ bất biến nông** khi component tham chiếu mutable object.

```java
// Phản ví dụ: items có thể là list mutable của plugin.
public record BadResult(java.util.List<String> items) {}
```

Thiết kế có defensive copy:

```java
import java.util.List;

public record GoodResult(List<String> items) {
    public GoodResult {
        items = List.copyOf(items);
    }
}
```

Đây là mẫu code độc lập cho file `GoodResult.java`. `List.copyOf` cho một unmodifiable list và từ chối null elements, nhưng **không deep-copy** các phần tử mutable. Với `byte[]` cần copy; với `ByteBuffer`, read-only view không bảo đảm backing storage không bị alias khác chỉnh sửa.

Nếu API bắt buộc hỗ trợ streaming/handle, phải định nghĩa rõ lifetime, ai đóng stream/handle, ai chịu trách nhiệm cancellation, liệu đối tượng còn hợp lệ sau khi plugin `stop` và cách ngăn client giữ class loader cũ. Tránh trả nguyên `Connection`, `VendorSession`, thread, listener hoặc vendor cache.

### 3.4. API kiểu trung lập vẫn cần semantics

| Loại public | Khả năng phù hợp | Điều phải xác định |
| --- | --- | --- |
| `String`, `int`, `boolean` | Thường tốt | Encoding, đơn vị, giới hạn, nullability |
| Public record/class chung | Tốt | Versioning, schema, defensive copy |
| `List<SharedDto>` | Tốt khi ownership rõ | Mutable element, null handling, size |
| `Optional<SharedDto>` | Có thể dùng cho return | “Không có” khác “lỗi” |
| `CompletionStage<SharedDto>` | Phù hợp API async | Cancellation, threading, error normalization |
| `Map<String,String>` | Phù hợp metadata nhỏ có schema | Quy tắc key, validation, unknown keys |
| `VendorType` | **Không** | Buộc host dùng private dependency |
| `Object` chứa vendor object | **Không** | Mất typing, leak runtime identity/lifecycle |
| Raw `Throwable`/`ClassLoader` | **Không nên** | Rò implementation và pin loader |

Không cần ép mọi API thành primitive; DTO chung rõ ràng đôi khi tốt hơn nhiều tham số `String` với nghĩa không rõ.

## 4. Phụ thuộc API, phụ thuộc implementation và vấn đề class loader

### 4.1. Dependency graph đúng hướng

```text
             ┌─────────────────┐
 Host ───────►│ shared-api.jar  │◄────── Plugin Adapter
             └─────────────────┘              │
                                              ▼
                                      vendor-private.jar
                                              │
                                              ▼
                                       vendor dependencies

Không mong muốn:
 shared-api.jar ─────────► vendor-private.jar
 Host source imports ────► vendor.internal.*
 Public method types ────► VendorRequest/VendorResponse/VendorException
```

Host compile với API chung, plugin compile với API chung **và** vendor library. Khi chạy, private dependency **vẫn phải có** trong runtime/module/classloader phù hợp. “Không để lộ dependency” không có nghĩa “xóa dependency khỏi runtime”.

Gradle `implementation` hoặc Maven scope có thể giúp giữ dependency graph sạch, nhưng những keyword build **không bảo đảm** contract không trả object vendor. Hãy kiểm tra cả Java signatures và runtime object graph.

### 4.2. Class identity: tên giống không đồng nghĩa cùng kiểu

Trong JVM, danh tính một class gồm **binary class name và defining class loader**.

```text
Host loader H  : com.example.api.TextPlugin
Plugin loader P: com.example.api.TextPlugin (bản copy)
```

Hai class cùng tên nhưng nạp bởi loader khác có thể không tương thích; provider có thể gặp `ServiceConfigurationError`, `ClassCastException` hoặc linkage error khi host dùng contract khác identity.

Cách làm:

- Đặt shared API trong loader/`ModuleLayer` ổn định mà host và plugin cùng tham chiếu.
- Không để plugin child-first class loader “shadow” `com.example.api.*` bằng một bản API riêng.
- Vendor SDK có thể được cô lập theo từng plugin loader hoặc layer khi cần chạy nhiều version.
- Luôn kiểm thử parent delegation và dependency resolution, không chỉ kiểm tra tên class/package.

**Lưu ý:** Nếu toàn bộ JAR đặt trên cùng classpath, những class vendor được khai báo `public` có thể vẫn truy cập được. Việc API không nhắc đến chúng là **ràng buộc kiến trúc**, chưa phải sandbox hoặc isolation bảo mật.

### 4.3. JPMS `exports`, `opens`, `provides`

Đối với named modules, có thể định nghĩa descriptor (mã minh họa):

```java
module com.example.api {
    exports com.example.api;
}
```

```java
module com.example.plugin {
    requires com.example.api;
    provides com.example.api.TextPlugin
        with com.example.plugin.UpperPlugin;
}
```

Host và plugin đọc cùng API module; plugin không cần `exports com.example.plugin` chỉ để dùng `provides` cho SPI. Vendor/implementation packages có thể không export. `opens` phục vụ reflective access sâu, không nên mở bừa mọi package để framework truy cập.

JPMS bảo vệ **readability/accessibility** trong mô hình module, không thay thế sandbox quyền hệ điều hành. Một plugin không tin cậy chạy trong cùng JVM có thể gây hại dù package của nó không được exports.

### 4.4. Vì sao giấu vendor khỏi API giúp upgrade?

Nếu public interface chỉ dùng `TextRequest`/`TextResult`/`PluginFailure`, plugin có thể đổi từ vendor A sang vendor B khi vẫn giữ nghĩa của dữ liệu và error codes. Host không phải chỉnh import/catch/cast. Dù vậy, **thay vendor vẫn phải test** behavior, performance, data format, concurrency và tương thích runtime.

Nếu public method đổi parameter hoặc return type vendor, Java descriptor có thể đổi và client cũ gặp `NoSuchMethodError`; nếu class phụ thuộc không còn, có thể gặp `NoClassDefFoundError`. Generic signature changes có thể ảnh hưởng source/reflection ngay cả khi erasure giống. Không được đánh đồng “biên dịch qua” với “tương thích nhị phân và hành vi”.

## 5. Ngoại lệ riêng phải dừng trong plugin

### 5.1. Checked exception trong chữ ký là coupling

Phản ví dụ:

```java
// Mã minh họa không độc lập.
public interface BadPaymentPlugin {
    Receipt charge(Order order)
        throws vendor.payment.VendorServiceException;
}
```

Bên gọi phải có vendor exception type để compile xử lý catch. Đổi vendor SDK có thể buộc đổi API. Tốt hơn:

```java
// Các type ở shared API; mã minh họa.
public interface PaymentPlugin {
    PaymentResult charge(PaymentRequest request)
        throws PluginFailure;
}
```

`PluginFailure` là checked exception ổn định của contract, không kế thừa từ vendor exception. Nên kèm `FailureCode` để host/client phân loại theo ngữ nghĩa thay vì parse message.

### 5.2. Không chỉ checked exception mới lọt ra ngoài

Những nguồn rò có thể xuất hiện dù signature không khai báo `throws`:

- `VendorRuntimeException` hoặc `IllegalStateException` mang tên endpoint/table/key nội bộ.
- `CompletionException`/`ExecutionException` bọc vendor exception trong future.
- `InvocationTargetException` từ reflection.
- `ServiceConfigurationError` trong bước khám phá SPI.
- `NoClassDefFoundError`, `NoSuchMethodError`, `LinkageError` do runtime dependencies.
- Message/stack trace chứa API token, username, path, SQL hoặc payload của request.

Boundary cần phân loại:

1. **Lỗi theo hợp đồng:** adapter tạo shared `PluginFailure` với code rõ.
2. **Runtime exception không mong đợi:** host xử lý tại ranh giới thích hợp, ghi telemetry nội bộ đã redaction, trả mã `INTERNAL_FAILURE`/message chung cho client.
3. **Lỗi nặng thuộc `Error`:** không bắt mọi `Throwable` rồi giả vờ hệ thống vẫn khỏe; cần chính sách giám sát/cô lập cấp tiến trình.

Một `ServiceLoader` không tìm được provider trả `Optional.empty()` bình thường. Provider đăng ký hỏng/không thể tạo có thể ném `ServiceConfigurationError`; không được biến cả hai thành “không có plugin”.

### 5.3. Public error envelope và internal diagnostics

Mô hình:

```text
VendorException("internal-db:443 token=...")
            │ catch trong adapter
            ▼
PluginFailure(code=DEPENDENCY_FAILURE, safe detail)
            │ host chỉ dùng error code
            ▼
Public response:
  code=DEPENDENCY_FAILURE
  message="Text service is temporarily unavailable"
  requestId=R1

Internal diagnostics:
  pluginId / instanceId / stage / requestId
  exception gốc đã kiểm soát quyền truy cập và redaction
```

**Không trả nguyên `Throwable.getMessage()`, stack trace hoặc `getCause()` cho client.** Nếu giữ vendor exception làm cause của public exception, host có thể thấy raw private type qua `getCause()` và vô tình giữ loader cũ trong cache. Có thể giữ cause chỉ trong logging/telemetry nội bộ có quyền hạn; public response nên là DTO chứa error code, safe message và correlation ID.

**Quan trọng:** Ngay cả `PluginFailure.getMessage()` do một plugin bên thứ ba tạo **không mặc nhiên an toàn**. Host nên map từ error code tin cậy sang thông điệp công khai, thay vì trả nguyên message do provider cung cấp.

### 5.4. Sync và async đều cần chuẩn hóa

Với API:

```java
CompletionStage<TextResult> convertAsync(TextRequest input);
```

đây chỉ là đoạn minh họa. Nếu provider trả failed future chứa `VendorException`, lỗi vẫn rò qua API dù generic return là `TextResult`. Plugin phải hoàn tất lỗi theo model đã quy ước, ví dụ shared `PluginFailure` (và host unwrap đúng `CompletionException`) hoặc `CompletionStage<ResultOrFailure>` chứa DTO lỗi chung.

Với callback, tránh `onError(Throwable rawVendorError)` ở boundary công khai. Một shared `PluginErrorEvent(code, requestId, safeMessage)` dễ nâng version và an toàn hơn.

### 5.5. Versioning error codes

Enum chung như:

```java
public enum FailureCode {
    INVALID_INPUT,
    DEPENDENCY_FAILURE,
    INTERNAL_FAILURE
}
```

giúp host không phải biết tên exception vendor. Tuy nhiên khi bổ sung enum constant, code có `switch` exhaustive được biên dịch từ version trước có thể cần nâng cấp; vì thế version policy phải nêu cách xử lý error code không biết. Nếu plugin ecosystem cần mã lỗi mở rộng theo từng plugin, có thể dùng mã chuỗi có namespace với registry/schema và default handling. Đừng tạo một error code public cho mỗi loại exception vendor.

## 6. Đối tượng nội bộ, vòng đời và tương thích dữ liệu

### 6.1. Ownership ngoài chữ ký Java

Một API tưởng ổn khi trả `Result` nhưng implementation đặt trong result một `VendorSession`. Host có thể giữ result sau khi plugin dừng, khiến session, connection, class loader hoặc listener sống quá thời hạn.

Quy tắc:

- Input/output của plugin nên là **snapshot** độc lập, immutable khi khả thi.
- Không trả mutable cache/collection live view từ implementation.
- Resource handles cần API chung và hợp đồng `close`/cancellation rõ nếu thật sự phải qua boundary.
- Callback/lambda/stream/publisher phải có chính sách unsubscribe, backpressure, timeout và ngừng hoạt động khi plugin stop.
- Không để registry host giữ plugin raw exception, implementation class, class loader, `ThreadLocal`, TCCL hoặc object callback sau hot reload.

### 6.2. Biên dịch được chưa đủ

Có nhiều tầng compatibility:

| Tầng | Ví dụ rủi ro | Phương pháp kiểm tra |
| --- | --- | --- |
| Source | Chữ ký mới đòi `VendorRequest` | Build host chỉ với API JAR |
| Binary | Đổi return/parameter type hoặc xóa method | `javap -s`, binary compatibility CI |
| Generic/reflection | Generic Signature nhắc vendor model | Audit generics, bounds và annotations |
| Class loader | Hai bản API hoặc vendor class từ loaders khác nhau | Test SPI/cast/module runtime |
| Behavioral | Đổi semantics field, units, nullability | Contract/integration tests |
| Wire/data | Serialize vendor class name vào payload | Schema version, codec độc lập |
| Lifecycle | Host giữ vendor handle sau plugin stop | Quiesce, close, leak checks |
| Security | Raw exception chứa secret | Redaction/negative tests |

`javap -public -s` hữu ích để nhìn public method descriptors. Tuy nhiên vì generics có thể nằm ở `Signature` metadata, đừng kết luận API hoàn toàn sạch chỉ bằng erased descriptors; cần kiểm tra signature/annotations và compile dependency graph.

### 6.3. Thay dependency là một phép thử kiến trúc

Hãy thử nâng plugin từ vendor implementation A sang B nhưng không sửa shared API và host. Nếu host vẫn compile, integration tests pass, không có cast vendor và error semantics ổn định, boundary đang hoạt động tốt. Nếu buộc host sửa imports, deserialize vendor object hoặc catch exception SDK mới, implementation detail đã lọt qua hợp đồng.

## 7. Kiến trúc đề xuất cho hệ plugin

```text
HOST
 ├─ shared-api.jar  (owner: host/team API)
 ├─ service registry / dispatcher
 ├─ error mapper + public messages
 └─ plugin lifecycle manager
       │
       ├── Plugin A loader/layer
       │     ├─ adapter A implements shared API
       │     └─ vendor A private libraries
       │
       └── Plugin B loader/layer
             ├─ adapter B implements shared API
             └─ vendor B private libraries
```

Host quyết định version contract, policy lựa chọn plugin, readiness, timeout, retry, error envelope và quyền gọi. Plugin adapter quyết định cách làm việc với SDK của nó; client không cần biết vendor object. Nếu nhiều plugin dùng vendor versions khác nhau, loader isolation đúng cách có thể giúp tách binary classes, nhưng shared API phải thống nhất identity.

Đừng ngộ nhận class loader/module layer là security sandbox. Với plugin không tin cậy, nên xét process isolation, OS permissions, resource limits và giao thức trung lập thay vì chạy toàn quyền trong JVM chính.

## 8. Ví dụ Java 17+ chạy được: host không cần vendor library để compile

Ví dụ dùng một vendor SDK **giả lập**, nên chỉ cần JDK 17+. Private vendor SDK có exception với thông điệp mô phỏng nội bộ. Plugin adapter giấu exception và kiểu vendor, chỉ trả shared `TextResult` hoặc shared `PluginFailure`. Host không import implementation hay vendor package.

### 8.1. Cấu trúc file

```text
demo/
├── src/
│   ├── com/example/api/
│   │   ├── TextRequest.java
│   │   ├── TextResult.java
│   │   ├── FailureCode.java
│   │   ├── PluginFailure.java
│   │   └── TextPlugin.java
│   ├── com/example/host/
│   │   └── Main.java
│   ├── vendor/codec/
│   │   ├── VendorFormatException.java
│   │   └── VendorCodec.java
│   └── plugin/upper/
│       └── UpperPlugin.java
├── resources/
│   └── META-INF/services/com.example.api.TextPlugin
└── build/                       (tạo khi biên dịch)
```

### 8.2. Shared contract

**`src/com/example/api/TextRequest.java`**

```java
package com.example.api;

import java.util.Objects;

public record TextRequest(String requestId, String text) {
    public TextRequest {
        Objects.requireNonNull(requestId, "requestId");
    }
}
```

**`src/com/example/api/TextResult.java`**

```java
package com.example.api;

import java.util.Objects;

public record TextResult(String requestId, String text) {
    public TextResult {
        Objects.requireNonNull(requestId, "requestId");
        Objects.requireNonNull(text, "text");
    }
}
```

**`src/com/example/api/FailureCode.java`**

```java
package com.example.api;

public enum FailureCode {
    INVALID_INPUT,
    DEPENDENCY_FAILURE,
    INTERNAL_FAILURE
}
```

**`src/com/example/api/PluginFailure.java`**

```java
package com.example.api;

import java.util.Objects;

public final class PluginFailure extends Exception {
    private final FailureCode code;

    public PluginFailure(FailureCode code, String internalDetail) {
        super(internalDetail);
        this.code = Objects.requireNonNull(code, "code");
    }

    public FailureCode code() {
        return code;
    }
}
```

**`src/com/example/api/TextPlugin.java`**

```java
package com.example.api;

public interface TextPlugin {
    String id();
    TextResult convert(TextRequest request) throws PluginFailure;
}
```

Shared API chỉ dùng `String`, record, enum và exception của API chung. `TextRequest.text` có thể là blank để demo kiểm tra nghiệp vụ; implementation sẽ trả lỗi `INVALID_INPUT`. `PluginFailure.internalDetail` không phải văn bản dành cho client, host chỉ dùng `code()` để map public message.

### 8.3. Thư viện vendor private giả lập

**`src/vendor/codec/VendorFormatException.java`**

```java
package vendor.codec;

public final class VendorFormatException extends Exception {
    public VendorFormatException(String message) {
        super(message);
    }
}
```

**`src/vendor/codec/VendorCodec.java`**

```java
package vendor.codec;

import java.util.Locale;

public final class VendorCodec {
    public String toUpper(String input)
            throws VendorFormatException {
        if ("fail".equals(input)) {
            throw new VendorFormatException(
                "endpoint=private.local:443; token=FAKE_SECRET");
        }
        return input.toUpperCase(Locale.ROOT);
    }
}
```

Chuỗi `FAKE_SECRET` chỉ dùng để kiểm tra không leak error message, **không phải credential thật**. `VendorCodec`/`VendorFormatException` public để plugin adapter ở package khác gọi được, nhưng không được đưa vào contract. Với classpath, public class vendor có thể nạp được từ host nếu cố ý truy cập; ví dụ chỉ chứng minh ranh giới **API**, không phải runtime security isolation.

### 8.4. Adapter plugin

**`src/plugin/upper/UpperPlugin.java`**

```java
package plugin.upper;

import com.example.api.FailureCode;
import com.example.api.PluginFailure;
import com.example.api.TextPlugin;
import com.example.api.TextRequest;
import com.example.api.TextResult;
import vendor.codec.VendorCodec;
import vendor.codec.VendorFormatException;

public final class UpperPlugin implements TextPlugin {
    private final VendorCodec codec = new VendorCodec();

    public UpperPlugin() {
    }

    @Override
    public String id() {
        return "uppercase";
    }

    @Override
    public TextResult convert(TextRequest request)
            throws PluginFailure {
        if (request == null
                || request.text() == null
                || request.text().isBlank()) {
            throw new PluginFailure(
                FailureCode.INVALID_INPUT, "Invalid text input");
        }
        try {
            String converted = codec.toUpper(request.text());
            return new TextResult(request.requestId(), converted);
        } catch (VendorFormatException vendorError) {
            // Không trả vendorError, không nối raw message/cause.
            throw new PluginFailure(
                FailureCode.DEPENDENCY_FAILURE,
                "Vendor dependency is unavailable");
        }
    }
}
```

**Điểm quan trọng:** private field `VendorCodec` và exception `VendorFormatException` chỉ tồn tại trong plugin implementation. Public method do `TextPlugin` định nghĩa hoàn toàn dùng shared types. Host không cần catch vendor exception; nếu plugin thay SDK, adapter chịu trách nhiệm ánh xạ lỗi và DTO.

### 8.5. Host gọi qua SPI và chuẩn hóa message

**`src/com/example/host/Main.java`**

```java
package com.example.host;

import com.example.api.FailureCode;
import com.example.api.PluginFailure;
import com.example.api.TextPlugin;
import com.example.api.TextRequest;
import com.example.api.TextResult;
import java.util.ServiceLoader;

public final class Main {
    private static String publicMessage(FailureCode code) {
        return switch (code) {
            case INVALID_INPUT -> "Input text is required";
            case DEPENDENCY_FAILURE ->
                "Text service is temporarily unavailable";
            case INTERNAL_FAILURE -> "Plugin execution failed";
        };
    }

    public static void main(String[] args) {
        if (args.length > 1) {
            System.out.println("Usage: Main [text]");
            return;
        }

        TextPlugin plugin = ServiceLoader.load(TextPlugin.class)
            .findFirst()
            .orElse(null);

        if (plugin == null) {
            System.out.println("NO_PLUGIN");
            return;
        }

        String input = args.length == 0 ? "hello" : args[0];
        TextRequest request = new TextRequest("R1", input);

        try {
            TextResult result = plugin.convert(request);
            System.out.println(
                "OK " + result.requestId() + " " + result.text());
        } catch (PluginFailure error) {
            // Không xuất error.getMessage() của plugin cho client.
            System.out.println("ERROR " + error.code()
                + " " + publicMessage(error.code()));
        } catch (RuntimeException unexpected) {
            // Log nội bộ đã redaction trong ứng dụng production.
            System.out.println(
                "ERROR INTERNAL_FAILURE Plugin execution failed");
        }
    }
}
```

Host chỉ import `com.example.api.*` và `java.util.ServiceLoader`. Host không phụ thuộc vào `vendor.codec` ở source level, không cast object sang vendor type và không xuất raw exception detail. Trong hệ thống lớn hơn, lỗi tạo provider ở bước `ServiceLoader` cũng cần được xử lý riêng; không coi nó là `NO_PLUGIN` nếu SPI descriptor/class loading lỗi.

### 8.6. SPI descriptor

**`resources/META-INF/services/com.example.api.TextPlugin`**

```text
plugin.upper.UpperPlugin
```

Tên tệp trùng fully qualified name của service interface; nội dung là provider class. Tệp phải nằm trong plugin JAR tại đúng `META-INF/services` để `ServiceLoader` phát hiện provider.

### 8.7. Biên dịch, đóng JAR và chạy bằng Windows PowerShell

Đứng trong thư mục `demo` với JDK 17+:

```powershell
New-Item -ItemType Directory -Force build/host, build/vendor, build/plugin | Out-Null

# Host compile chỉ với shared API + JDK, KHÔNG cần vendor jar.
javac -encoding UTF-8 -d build/host src/com/example/api/*.java src/com/example/host/Main.java

# Vendor private library được compile/đóng gói riêng.
javac -encoding UTF-8 -d build/vendor src/vendor/codec/VendorFormatException.java src/vendor/codec/VendorCodec.java
jar --create --file build/vendor-private.jar -C build/vendor .

# Provider adapter phụ thuộc cả API và vendor library.
javac -encoding UTF-8 -cp 'build/host;build/vendor-private.jar' -d build/plugin src/plugin/upper/UpperPlugin.java

# SPI descriptor được đóng trong plugin JAR.
New-Item -ItemType Directory -Force build/plugin/META-INF/services | Out-Null
Copy-Item resources/META-INF/services/com.example.api.TextPlugin build/plugin/META-INF/services/com.example.api.TextPlugin
jar --create --file build/text-plugin.jar -C build/plugin .

# Runtime có plugin và private dependency.
java -cp 'build/host;build/text-plugin.jar;build/vendor-private.jar' com.example.host.Main
java -cp 'build/host;build/text-plugin.jar;build/vendor-private.jar' com.example.host.Main '   '
java -cp 'build/host;build/text-plugin.jar;build/vendor-private.jar' com.example.host.Main fail

# Không có provider JAR -> không khám phá được plugin.
java -cp build/host com.example.host.Main
```

**PowerShell/Windows** dùng dấu chấm phẩy `;` giữa các classpath entries. **Linux/macOS** dùng dấu hai chấm `:` và thay lệnh tạo/copy file bằng `mkdir -p`/`cp` tương ứng; ví dụ runtime `java -cp 'build/host:build/text-plugin.jar:build/vendor-private.jar' com.example.host.Main`.

Lệnh compile host chạy **trước** khi build thư viện vendor; đây là kiểm chứng trực tiếp rằng host không cần private vendor dependency ở compile time.

### 8.8. Stdout chính xác

**Lệnh chạy mặc định** với input `"hello"`:

```text
OK R1 HELLO
```

**Input chỉ gồm khoảng trắng**:

```text
ERROR INVALID_INPUT Input text is required
```

**Input `"fail"`**, vendor SDK ném exception riêng:

```text
ERROR DEPENDENCY_FAILURE Text service is temporarily unavailable
```

**Không có plugin JAR**:

```text
NO_PLUGIN
```

Không kết quả nào chứa `vendor.codec.VendorFormatException`, `private.local` hoặc `FAKE_SECRET`. Host ánh xạ mã lỗi sang public message do chính host quyết định. Nếu loại bỏ `vendor-private.jar` mà vẫn để plugin JAR, có thể gặp lỗi nạp/liên kết class; đây là **thiếu dependency**, không phải trường hợp `NO_PLUGIN` bình thường.

### 8.9. Điều ví dụ có và chưa có

Ví dụ chứng minh kiểu vendor không rò qua public API, object được chuyển sang shared DTO, exception vendor được giữ ở adapter và host không cần vendor để compile. Nó sử dụng classpath chung để đơn giản hóa việc chạy; **không** giả định isolation classloader, dependency graph hay hot reload.

Mã thử chạy tuần tự, chưa quản lý plugin lifecycle start/stop, timeout hoặc nhiều thread. Một plugin manager production cần kiểm soát provider selection, version compatibility, số phiên, cleanup/callback và giám sát. Không dùng class loader/module như sandbox cho mã không đáng tin cậy.

## 9. Kiểm tra ranh giới API trong CI và runtime

### 9.1. Kiểm tra source, bytecode, dependency

- Build shared API và host **không có vendor-private.jar** trên compile classpath.
- Dùng `javap -public -s` hoặc công cụ so API/ABI để phát hiện kiểu không mong muốn trong public method descriptors.
- Audit cả generic `Signature`, bound, annotation, record component và exception types; JVM erasure không làm biến mất coupling ở source/reflection.
- Có rule chặn API package import các namespace `vendor.*`, `plugin.internal.*`.
- Build một fake plugin từ API chung, không cần vendor.
- Thử nâng vendor version hoặc đổi vendor và xác nhận không cần sửa mã host.

### 9.2. Kiểm tra runtime và ownership

- Chạy provider qua class loader hoặc module layer dự kiến; xác minh host/plugin dùng **cùng API type identity**.
- Không có raw vendor object trong returned DTO, callback, future hoặc event.
- Result list/buffer/array phải tuân thủ copy/immutability policy.
- Sau plugin stop/hot reload, host không giữ raw `Throwable`, `Class<?>`, callback, thread hoặc handle của plugin làm pin loader cũ.
- Với nhiều plugin dùng version vendor khác nhau, test classloader isolation và data interchange theo shared DTO.
- Lỗi provider SPI/config không bị báo thành “không có provider” nếu thực tế có metadata sai hoặc runtime dependency bị lỗi.

### 9.3. Test không rò lỗi hoặc secrets

Tạo vendor failure giả với chuỗi như:

```text
endpoint=internal.example:443 token=FAKE_TOKEN
```

Kiểm tra public response không chứa endpoint, token, tên class vendor, stack trace hoặc raw SQL; đồng thời hệ thống log nội bộ phải có request ID và quyền truy cập thích hợp. Test các nhánh: invalid input, vendor checked exception, unexpected runtime exception, async completion failure, callback error và provider initialization failure.

Tách riêng exception **được public contract quy định** khỏi lỗi vận hành chưa xác định. Không bắt mọi `Throwable` để “bảo đảm ổn định”; lỗi JVM nghiêm trọng có thể khiến tiếp tục xử lý trong cùng tiến trình là không an toàn.

## 10. Sai lầm thường gặp và cách khắc phục

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| `VendorResult method(VendorRequest)` | Host buộc biết SDK riêng | Shared DTO + adapter |
| `throws VendorException` | Host compile/catch theo SDK | Shared `PluginFailure`/error code |
| `Object getState()` trả raw vendor object | Leak implementation và class loader | Snapshot DTO, không trả private handles |
| `List<VendorResult>` | Generic signatures còn coupling | `List<SharedResult>` |
| `Map<String,Object>` chứa vendor values | Contract mơ hồ, cast runtime | Typed DTO/schema |
| Trả `Throwable`/cause/stack trace | Lộ internal data, giữ loader | Error DTO + correlation ID, logging có redaction |
| Host in `PluginFailure.getMessage()` | Plugin có thể cung cấp secret | Map error code sang safe message ở host |
| Async future hoàn thành bằng vendor error | Exception leak gián tiếp | Normalize async failure |
| API JAR được copy/nạp bằng plugin loader | Hai type identity khác nhau | Shared API loader/module |
| Trả mutable cache hoặc vendor session | Sai ownership/lifetime, leak resource | Defensive copy hoặc common facade có close |
| Tưởng private Gradle dependency đủ để bảo vệ API | Public signature vẫn có thể leak | Audit Java API và runtime object graph |
| Tưởng JPMS/classloader là sandbox | Không chặn quyền process | Process isolation và OS policy khi cần |

## 11. Checklist phát hành plugin API

- [ ] API artifact/module do host sở hữu, version và semantics rõ ràng.
- [ ] Không có kiểu vendor/private trong public/protected parameters, returns, generics, records, callbacks, annotations hoặc checked exceptions.
- [ ] Host compile được chỉ với shared API + JDK.
- [ ] Plugin adapter chuyển riêng sang shared DTO, không trả raw vendor objects dù ép thành `Object`.
- [ ] Result/data ownership rõ; copy các giá trị mutable theo contract.
- [ ] Không trả internal session/connection/classloader/Throwable vượt lifetime plugin.
- [ ] Ngoại lệ vendor được map thành shared error code; client không thấy message/stack/cause nội bộ.
- [ ] Host chọn public message theo code; có quy tắc unknown code/versioning.
- [ ] Đồng bộ API type identity giữa host và provider loader/module layer.
- [ ] Vendor runtime dependency được đóng gói/resolve đầy đủ, nhưng không nằm trong API public graph.
- [ ] Có ABI/source compatibility checks, integration tests, leak tests, error-redaction tests.
- [ ] Hot reload dọn callback, stream, thread, exception cache và provider references.
- [ ] Không nhầm API encapsulation với bảo mật sandbox của plugin không tin cậy.

**Kết luận:** Giữ **API chỉ gồm shared types**, **dữ liệu trả về không mang object nội bộ** và **ngoại lệ vendor không vượt adapter** là nền tảng để nâng cấp plugin độc lập, giảm xung đột class loader và tránh lộ thông tin kỹ thuật. Sự tách biệt này phải được bảo vệ cả ở **source signatures, runtime object graph, error handling và lifecycle** — không chỉ ở tên package hay từ khóa `private`.

**Tài liệu tham khảo Java SE 17:** [`ServiceLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html), [`ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html), [`Throwable`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Throwable.html), [`CompletionStage`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletionStage.html), [`List.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)), [`Module`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html).
