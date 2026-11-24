# Thiếu metadata reflection, proxy, serialization hoặc JNI

## 1. Vì sao ứng dụng chạy trên JVM nhưng lỗi trong Native Image?

Trong module **SPRING_BOOT_NATIVE_IMAGE**, Spring AOT phân tích ApplicationContext ở build time, sinh mã khởi tạo và runtime hints; GraalVM Native Image sau đó phân tích tĩnh để tạo executable. Native Image chỉ giữ lại những class, method, field và resource mà nó xác định được là cần thiết.

Một số thư viện vẫn truy cập thành phần Java bằng thông tin chỉ biết khi chạy, chẳng hạn:

- Tên class đọc từ cấu hình hoặc database rồi gọi **Class.forName**.
- Framework gọi constructor, method hoặc field qua reflection.
- Code tạo JDK dynamic proxy từ danh sách interface.
- Thư viện đọc/ghi object bằng Java serialization.
- Native code gọi ngược vào Java qua JNI.

Trên JVM thông thường, classloader và runtime có thể tìm thấy nhiều thành phần trong classpath. Native Image không thể tự suy ra mọi truy cập động đó. Nếu build thiếu reachability metadata, ứng dụng có thể khởi động bình thường nhưng lỗi khi đi vào một chức năng cụ thể.

Metadata không phải danh sách class cần giữ một cách tùy ý. Nó mô tả chính xác phần truy cập động cần được hỗ trợ: type nào được tìm bằng reflection, constructor/method/field nào được gọi, tổ hợp interface nào tạo proxy, class nào được serialize hoặc thành phần Java nào được native code truy cập.

## 2. Phân biệt các loại metadata

| Cơ chế | Ai thực hiện truy cập động? | Thông tin cần khai báo |
| --- | --- | --- |
| Reflection | Java code dùng Class, Method, Constructor, Field, MethodHandles | Type, constructor, method, field và quyền truy cập tương ứng |
| JDK dynamic proxy | Java code dùng Proxy.newProxyInstance hoặc thư viện tạo proxy interface | Danh sách interface theo đúng tổ hợp và thứ tự |
| Spring AOP/CGLIB proxy | Spring tạo proxy để áp dụng transaction, security, async hoặc advice | Spring AOT cần nhận diện bean/proxy ở build time; CGLIB proxy của Spring được xử lý theo đường AOT riêng |
| Java serialization | ObjectOutputStream/ObjectInputStream | Class Serializable và metadata serialization |
| JSON binding | Jackson hoặc codec đọc/ghi DTO qua reflection | Constructor, field, property, record component và type lồng nhau cần bind |
| JNI | C/C++ native code tìm class, method, field hoặc tạo object Java | JNI type/member access tương ứng |

Spring Framework cung cấp **RuntimeHints** cho reflection, resource, Java serialization, proxy và JNI. JNI vẫn là một nhóm metadata riêng trong output GraalVM, nhưng có thể đăng ký bằng accessor **hints.jni()** hoặc khai báo trực tiếp trong section **jni** của **reachability-metadata.json**.

## 3. Nhận diện lỗi từ triệu chứng

| Triệu chứng | Vùng cần kiểm tra đầu tiên |
| --- | --- |
| MissingReflectionRegistrationError | Reflection lookup, method invocation, constructor, field access hoặc JDK proxy |
| MissingJNIRegistrationError | Native code gọi FindClass, GetMethodID, GetFieldID hoặc thao tác object Java |
| ClassNotFoundException | Class không có trong dependency/classpath, tên class sai hoặc cấu hình nạp class sai |
| NoSuchMethodException trên native nhưng JVM chạy được | Method/constructor bị gọi động chưa được đăng ký hoặc signature không khớp |
| ClassCastException khi gọi service qua proxy | Proxy/interface được tạo khác với kiểu mà caller mong đợi |
| Lỗi chỉ xảy ra khi serialize/deserialize một loại object | Phân biệt Java serialization với JSON/XML binding; kiểm tra metadata của đúng cơ chế |
| UnsatisfiedLinkError | Không tìm thấy native library, symbol hoặc ABI không tương thích; đây không mặc nhiên là lỗi JNI metadata |
| Không đọc được file cấu hình/resource trong native | Resource chưa được đưa vào image hoặc code đang coi resource URL là file path |

MissingReflectionRegistrationError và MissingJNIRegistrationError là các lỗi đăng ký reachability. Đừng bắt rộng Throwable rồi bỏ qua chúng. Cách xử lý đó che mất lỗi và khiến ứng dụng có thể trả kết quả sai mà không báo nguyên nhân.

Một lỗi thiếu metadata thường chỉ xuất hiện khi chạy đúng đường code sử dụng thành phần động. Vì vậy, việc health endpoint hoặc ApplicationContext khởi động thành công chưa chứng minh metadata đã đầy đủ.

## 4. Quy trình chẩn đoán tổng quát

~~~mermaid
flowchart TD
    A["Native executable fails on a feature"] --> B["Capture full error and stack trace"]
    B --> C{"Which dynamic access?"}
    C -->|Class / method / field| R["Inspect reflection"]
    C -->|Proxy.newProxyInstance| P["Inspect ordered interfaces"]
    C -->|Object streams| S["Inspect Java serialization"]
    C -->|Native C/C++ call| J["Inspect JNI registrations"]
    C -->|Resource lookup| F["Inspect resource inclusion and URL usage"]
    R --> V["Add the smallest matching hint"]
    P --> V
    S --> V
    J --> V
    F --> V
    V --> T["Test hint registration and rebuild"]
    T --> N["Run the same scenario on native executable"]
    N --> Q{"All relevant paths pass?"}
    Q -->|No| B
    Q -->|Yes| D["Keep regression test and metadata"]
~~~

Thực hiện theo thứ tự:

1. Tái hiện lỗi bằng native executable và lưu stack trace đầy đủ.
2. Xác định thư viện và call site thực hiện truy cập động.
3. Xác định đó là reflection, JDK proxy, Java serialization, JSON binding hay JNI.
4. Kiểm tra Spring AOT và dependency đã cung cấp hint hay chưa.
5. Chỉ bổ sung metadata cho thành phần thực sự được truy cập.
6. Viết test cho hint và chạy lại đúng luồng nghiệp vụ trên native executable.

Đừng bắt đầu bằng cách đăng ký toàn bộ constructor, method và field của mọi package. Cách đó làm image lớn, che khuất nguyên nhân và có thể giữ lại nhiều thành phần không cần thiết.

## 5. Kiểm tra reflection

### 5.1. Những trường hợp thường cần reflection metadata

Reflection có thể phát sinh từ:

- Class.forName(className) khi className đến từ file cấu hình hoặc database;
- getDeclaredConstructor() rồi newInstance();
- getDeclaredMethod() rồi Method.invoke();
- truy cập field bằng Field.get()/Field.set();
- MethodHandles.Lookup;
- framework scan annotation hoặc gọi method private;
- thư viện mapping, ORM, serializer hoặc plugin loader.

Native Image có thể xử lý một số lời gọi reflection khi class và các đối số được xác định tĩnh. Ví dụ, Class.forName("com.example.InvoiceHandler") với tên class là hằng số có thể được phân tích lúc build. Nếu tên class chỉ được biết khi đọc cấu hình runtime, cần khai báo metadata tương ứng.

Hãy xác định quyền truy cập cần thiết:

- chỉ cần tìm class;
- cần liệt kê constructor hoặc method;
- cần gọi một constructor/method cụ thể;
- cần đọc/ghi field;
- cần cấp phát object mà không gọi constructor.

Các nhu cầu này không tương đương. Đăng ký type không tự động có nghĩa mọi method và field đều có thể được gọi hoặc truy cập bằng reflection.

### 5.2. Dùng RuntimeHintsRegistrar

Với thành phần do ứng dụng quản lý, có thể đăng ký hint bằng Spring API. Ví dụ thư viện cũ gọi method readPayload(String) qua reflection:

~~~java
import java.lang.reflect.Method;

import org.springframework.aot.hint.ExecutableMode;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.util.ReflectionUtils;

public class BillingRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        Method method = ReflectionUtils.findMethod(
            LegacyInvoiceAdapter.class,
            "readPayload",
            String.class
        );
        hints.reflection().registerMethod(method, ExecutableMode.INVOKE);
    }
}
~~~

Kích hoạt registrar bằng ImportRuntimeHints:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(BillingRuntimeHints.class)
class NativeHintsConfiguration {
}
~~~

Đặt ImportRuntimeHints gần component cần hint nếu có thể. Registrar được Spring AOT gọi trong build time; nó không phải đoạn code để tự chạy khi mỗi request tới.

Nếu cần đăng ký nhiều thành phần, có thể dùng API hints.reflection() để khai báo type, constructor, method hoặc field cụ thể. Chọn ExecutableMode.INVOKE khi cần gọi method/constructor; chỉ đăng ký quyền introspection nếu thư viện chỉ cần xem thông tin mà không gọi executable.

### 5.3. DTO được bind ngoài Spring MVC

Spring Boot thường suy ra reflection hints cho kiểu dữ liệu của request/response trong controller. Tuy nhiên, nếu ứng dụng gọi WebClient, RestClient, Jackson hoặc codec trực tiếp trong thân method, AOT engine có thể không suy ra đầy đủ DTO.

Dùng RegisterReflectionForBinding cho kiểu dữ liệu cần bind:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.stereotype.Component;

@Component
@RegisterReflectionForBinding(PartnerInvoiceResponse.class)
class PartnerInvoiceClient {

    PartnerInvoiceResponse fetchInvoice(String invoiceId) {
        // Gọi HTTP client và deserialize response thành DTO.
        return callPartner(invoiceId);
    }
}
~~~

Annotation này đăng ký các thành phần cần cho binding như constructor, field, property và record component; các kiểu được dùng lồng bên trong cũng được xem xét. Kiểm tra API annotation theo Spring Boot/Spring Framework version của dự án.

Nếu DTO chứa kiểu lồng nhau không được suy ra từ cấu trúc đã biết, đăng ký kiểu đó hoặc bổ sung annotation binding phù hợp. Không nhầm hint cho JSON binding với metadata Java serialization ở phần sau.

### 5.4. Metadata JSON cho reflection

Nếu cần khai báo tĩnh hoặc thư viện không tích hợp Spring RuntimeHints, dùng reachability-metadata.json. Ví dụ chỉ cho phép gọi một method và constructor cần thiết:

~~~json
{
  "reflection": [
    {
      "type": "com.example.billing.LegacyInvoiceAdapter",
      "allDeclaredConstructors": true,
      "methods": [
        {
          "name": "readPayload",
          "parameterTypes": ["java.lang.String"]
        }
      ]
    }
  ]
}
~~~

Khai báo field nếu code thực sự đọc/ghi field qua reflection:

~~~json
{
  "reflection": [
    {
      "type": "com.example.billing.LegacyInvoice",
      "fields": [
        {"name": "internalCode"}
      ]
    }
  ]
}
~~~

Các lựa chọn allDeclaredMethods, allPublicMethods, allDeclaredFields và allPublicFields tiện cho thư viện có contract rộng, nhưng có thể làm image tăng kích thước. Ưu tiên danh sách member cụ thể nếu đã biết call site.

## 6. Kiểm tra proxy

### 6.1. Phân biệt JDK dynamic proxy và CGLIB

Spring có thể dùng hai cơ chế proxy:

| Cơ chế | Cách tạo | Hướng kiểm tra |
| --- | --- | --- |
| JDK dynamic proxy | Tạo class proxy từ một danh sách interface bằng Proxy.newProxyInstance | Đăng ký đúng danh sách interface theo đúng thứ tự |
| CGLIB proxy | Tạo subclass của class đích | Kiểm tra Spring AOT đã nhận diện bean và sinh proxy bytecode chưa |

Spring AOT có thể sinh bytecode cho proxy mà Spring cần khi xử lý ApplicationContext. Spring ProxyHints đăng ký JDK interface proxy. Class-based CGLIB proxy đi theo đường AOT riêng: Spring cần nhận diện bean/proxy khi phân tích context và sinh bytecode tương ứng. ClassHintUtils hỗ trợ suy ra hint cho các kiểu proxy Spring quản lý. Proxy JDK được tạo động bởi thư viện khác vẫn có thể cần proxy hints riêng; không dùng JDK proxy hint để chữa lỗi CGLIB.

Với CGLIB, class final, method final hoặc method private không thể được override để áp dụng advice. Nếu proxy do thư viện tự tạo bằng code generation lúc runtime, cần kiểm tra khả năng tương thích AOT của thư viện; chỉ thêm danh sách interface không giải quyết được việc tạo subclass động.

### 6.2. Đăng ký JDK proxy bằng Spring

Ví dụ một client tạo proxy cho hai interface:

~~~java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class PartnerProxyHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.proxies().registerJdkProxy(
            PartnerGateway.class,
            AutoCloseable.class
        );
    }
}
~~~

Khai báo registrar qua ImportRuntimeHints như ví dụ ở phần reflection. Danh sách interface phải phản ánh đúng tổ hợp được truyền vào Proxy.newProxyInstance.

### 6.3. Metadata JSON cho JDK proxy

Ví dụ reachability metadata:

~~~json
{
  "reflection": [
    {
      "type": {
        "proxy": [
          "com.example.partner.PartnerGateway",
          "java.lang.AutoCloseable"
        ]
      }
    }
  ]
}
~~~

Thứ tự interface là một phần của định nghĩa proxy. Nếu code tạo proxy theo tổ hợp hoặc thứ tự khác, entry này có thể không khớp. Ghi nhận danh sách interface ngay tại call site của Proxy.newProxyInstance.

### 6.4. Kiểm tra proxy do Spring AOT tạo

Nếu lỗi liên quan đến Transactional, Async, method security hoặc advisor:

1. Xác định bean đang dùng JDK proxy hay class-based proxy.
2. Xác nhận bean definition có mặt trong AOT context.
3. Kiểm tra kiểu trả về của Bean có đủ cụ thể để Spring AOT nhận diện class đích.
4. Kiểm tra generated proxy bytecode đã được compile và đóng gói.
5. Xác nhận method cần advice có thể được proxy theo quy tắc của JDK/CGLIB.

Nếu Bean trả về một interface quá chung trong khi AOT cần phân tích annotation hoặc lifecycle method trên implementation, hãy cân nhắc khai báo kiểu trả về cụ thể hơn.

## 7. Kiểm tra serialization

### 7.1. Phân biệt Java serialization và JSON binding

Hai cơ chế thường bị gọi chung là “serialization”, nhưng metadata khác nhau:

| Cơ chế | Ví dụ | Hint phù hợp |
| --- | --- | --- |
| Java object serialization | ObjectOutputStream, ObjectInputStream, class implements Serializable | Serialization metadata |
| JSON binding | Jackson serialize/deserialize DTO | Reflection/binding hints |
| XML binding | JAXB hoặc XML mapper | Reflection và metadata theo thư viện |
| Message codec | Codec chuyển payload thành object | Kiểm tra contract của codec và kiểu được bind |

RegisterReflectionForBinding dành cho binding kiểu dữ liệu như JSON. hints.serialization().registerType(...) dành cho Java serialization. Hai cơ chế không thay thế lẫn nhau.

### 7.2. Đăng ký Java serialization trong Spring

Ví dụ ứng dụng ghi/đọc một class cũ implement Serializable:

~~~java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class LegacySerializationHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.serialization().registerType(
            LegacyInvoiceEnvelope.class
        );
    }
}
~~~

Đăng ký registrar bằng ImportRuntimeHints. Spring Framework cung cấp RuntimeHints.serialization() để khai báo Java serialization; dùng accessor này thay vì reflection hints.

~~~java
hints.serialization().registerType(LegacyInvoiceEnvelope.class);
~~~

Đoạn trên phù hợp với API Spring Framework 6.x. Trong Javadoc Spring Framework mới hơn, SerializationHints và RuntimeHints.serialization() được đánh dấu deprecated để chuyển sang reflection type hint với cờ Java serialization:

~~~java
hints.reflection().registerType(
    LegacyInvoiceEnvelope.class,
    typeHint -> typeHint.withJavaSerialization(true)
);
~~~

Chọn một cách theo Spring Framework version thực tế của dự án; không gọi API deprecated chỉ vì ví dụ cũ vẫn còn trong tài liệu khác.

Thực hiện tương tự cho từng class thực sự được serialize; kiểm tra cả class con, class chứa field và kiểu được tham chiếu trong object graph.

### 7.3. Metadata JSON cho Java serialization

Với class thông thường:

~~~json
{
  "reflection": [
    {
      "type": "com.example.legacy.LegacyInvoiceEnvelope",
      "serializable": true
    }
  ]
}
~~~

Nếu proxy class cũng được serialize, cần metadata proxy có trường serializable:

~~~json
{
  "reflection": [
    {
      "type": {
        "proxy": [
          "com.example.partner.PartnerGateway",
          "java.io.Serializable"
        ]
      },
      "serializable": true
    }
  ]
}
~~~

### 7.4. Không nới lỏng ObjectInputFilter để chữa lỗi

Nếu ứng dụng nhận Java serialized object từ nguồn bên ngoài, hãy dùng ObjectInputFilter để giới hạn loại class được phép deserialize. GraalVM có thể nhận diện các class được nêu trong filter hằng số để đăng ký serialization metadata.

Không dùng wildcard quá rộng hoặc cho phép mọi class chỉ để tránh lỗi native. Metadata càng rộng thì image càng lớn và bề mặt deserialize càng khó kiểm soát.

## 8. Kiểm tra JNI

### 8.1. JNI metadata dùng cho chiều truy cập nào?

JNI cho phép native code truy cập Java:

- FindClass tìm class theo tên;
- GetMethodID/GetStaticMethodID tìm method;
- GetFieldID/GetStaticFieldID tìm field;
- NewObject tạo object;
- Call<Type>Method gọi method Java;
- AllocObject cấp phát object mà không gọi constructor.

Native Image không thể dự đoán mọi tên class/member mà C/C++ code sẽ tra cứu. Các type và member đó phải được khai báo trong JNI metadata.

### 8.2. Phân biệt lỗi JNI metadata với lỗi nạp thư viện

| Lỗi | Ý nghĩa | Việc cần kiểm tra |
| --- | --- | --- |
| MissingJNIRegistrationError | Native code truy cập Java type/member chưa được đăng ký | JNI reachability metadata |
| UnsatisfiedLinkError: no ... in java.library.path | Không tìm thấy native library | Đóng gói .so/.dll/.dylib, đường dẫn và cấu hình loader |
| undefined symbol | Native library thiếu symbol hoặc ABI không khớp | Phiên bản thư viện, linker và native dependencies |
| wrong ELF class hoặc lỗi architecture | Binary native không đúng kiến trúc | Build artifact theo OS/CPU target |

JNI metadata không đóng gói file native library và không sửa ABI. Trước khi thêm hint, xác nhận native library thực sự được nạp thành công.

### 8.3. Ví dụ JNI tìm class và gọi method

Giả sử C code gọi Java callback:

~~~c
jclass callbackClass = (*env)->FindClass(
    env,
    "com/example/nativebridge/NativeCallback"
);

jmethodID callbackMethod = (*env)->GetMethodID(
    env,
    callbackClass,
    "onComplete",
    "(Ljava/lang/String;)V"
);
~~~

Metadata cần cho phép JNI truy cập class và method onComplete(String):

~~~json
{
  "jni": [
    {
      "type": "com.example.nativebridge.NativeCallback",
      "jniAccessible": true,
      "methods": [
        {
          "name": "onComplete",
          "parameterTypes": ["java.lang.String"]
        }
      ]
    }
  ]
}
~~~

Nếu native code đọc field nativeHandle, bổ sung field cụ thể:

~~~json
{
  "jni": [
    {
      "type": "com.example.nativebridge.NativeCallback",
      "jniAccessible": true,
      "fields": [
        {"name": "nativeHandle"}
      ]
    }
  ]
}
~~~

jniAccessible cho phép native code truy cập type qua JNI. Nó không tự động cấp quyền cho mọi method và field; khai báo member mà native code thực sự tìm bằng ID.

### 8.4. Đăng ký JNI bằng Spring RuntimeHints

Spring Framework có accessor RuntimeHints.jni(). Accessor này trả về ReflectionHints được xuất thành JNI metadata, tách biệt với reflection metadata thông thường.

Ví dụ native code gọi public method và đọc public field:

~~~java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class NativeBridgeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.jni().registerType(
            NativeCallback.class,
            MemberCategory.INVOKE_PUBLIC_METHODS,
            MemberCategory.PUBLIC_FIELDS
        );
    }
}
~~~

Nếu native code cần method hoặc field private/package-private, chọn category declared tương ứng, chẳng hạn INVOKE_DECLARED_METHODS hoặc DECLARED_FIELDS. Không thêm toàn bộ member categories nếu JNI chỉ dùng một vài member. Đăng ký registrar bằng ImportRuntimeHints như các ví dụ trước.

API RuntimeHints.jni() có trong Spring Framework 6.x; kiểm tra Javadoc đúng version mà Spring Boot của dự án đang quản lý. Nếu không dùng API này hoặc metadata thuộc một thư viện bên thứ ba, khai báo trực tiếp section jni trong GraalVM reachability metadata.

Nếu native code dùng AllocObject, khai báo unsafeAllocated cho type tương ứng. Nếu native code gọi constructor qua NewObject, khai báo constructor cần thiết trong JNI metadata.

## 9. Đặt reachability metadata đúng vị trí

Với metadata do ứng dụng quản lý, có thể đặt file trong classpath dưới META-INF/native-image. Ví dụ:

~~~text
src/main/resources/
└── META-INF/
    └── native-image/
        └── com.example/
            └── billing-service-additional-hints/
                └── reachability-metadata.json
~~~

Thư mục metadata tĩnh nên tránh trùng với vị trí mà Spring AOT sinh hint tự động:

~~~text
META-INF/native-image/{groupId}/{artifactId}/
~~~

Không chỉnh sửa file generated trong target/ hoặc build/ để chữa lỗi. Các file đó có thể bị ghi đè ở lần build sau. Hãy sửa RuntimeHintsRegistrar, annotation hoặc metadata nguồn trong src/main/resources.

Ví dụ một file kết hợp các cơ chế:

~~~json
{
  "reflection": [
    {
      "type": "com.example.billing.LegacyInvoiceAdapter",
      "methods": [
        {
          "name": "readPayload",
          "parameterTypes": ["java.lang.String"]
        }
      ]
    },
    {
      "type": {
        "proxy": [
          "com.example.partner.PartnerGateway",
          "java.io.Closeable"
        ]
      }
    },
    {
      "type": "com.example.legacy.LegacyInvoiceEnvelope",
      "serializable": true
    }
  ],
  "jni": [
    {
      "type": "com.example.nativebridge.NativeCallback",
      "jniAccessible": true,
      "methods": [
        {
          "name": "onComplete",
          "parameterTypes": ["java.lang.String"]
        }
      ]
    }
  ]
}
~~~

Đây là ví dụ minh họa. Thay class, member và interface bằng các tên thực tế; xác thực JSON bằng schema đi cùng GraalVM Native Image version đang dùng. Không trộn schema cũ và schema mới chỉ vì tên file cùng là metadata.

## 10. Thu thập hint bằng GraalVM Tracing Agent

Khi chưa biết thư viện nào thực hiện truy cập động, Tracing Agent có thể quan sát ứng dụng trên JVM và tạo metadata tương ứng.

### 10.1. Chạy ứng dụng cùng agent

Dùng GraalVM JDK có Native Image Tracing Agent:

~~~bash
java \
  -Dspring.aot.enabled=true \
  -agentlib:native-image-agent=config-output-dir=target/native-agent \
  -jar target/billing-service.jar
~~~

Sau khi ứng dụng khởi động:

1. Gọi các endpoint sử dụng reflection và JSON binding.
2. Chạy các luồng tạo JDK proxy hoặc khởi tạo integration adapter.
3. Gọi nghiệp vụ có Java serialization hoặc JNI.
4. Thực hiện cả nhánh thành công và nhánh lỗi có sử dụng các thành phần đó.
5. Dừng ứng dụng bình thường để agent ghi các file cấu hình.

Agent ghi nhận những truy cập động đã xảy ra trong lần chạy. Nó không thể tự tìm ra một plugin, serializer hoặc nhánh nghiệp vụ chưa được thực thi.

### 10.2. Chạy agent qua test suite

Có thể gắn agent vào JVM chạy integration tests để tái lập các kịch bản. Cách này giúp thu thập metadata có hệ thống, nhưng test framework cũng tạo ra nhiều reflection/proxy/resource access không cần thiết trong ứng dụng production.

Nếu dùng test suite:

- ưu tiên test nghiệp vụ thực sự chạy trong native application;
- dùng access-filter/caller-filter của agent để loại các truy cập chỉ thuộc test infrastructure;
- tách metadata ứng dụng với metadata của test;
- không sao chép toàn bộ output mà chưa review.

### 10.3. Review metadata do agent sinh

Sau khi agent kết thúc:

- xác định entry nào thuộc thư viện ứng dụng và entry nào thuộc JUnit/mock framework;
- kiểm tra class và method có thực sự tồn tại trong dependency version đang pin;
- loại entry quá rộng hoặc không liên quan;
- gộp vào metadata nguồn đúng vị trí;
- rebuild native image và chạy lại kịch bản đã tạo ra entry.

Tên file và định dạng agent output có thể thay đổi theo GraalVM release. Giữ schema được phiên bản agent tạo ra hoặc chuyển đổi theo schema mà Native Image version hiện tại hỗ trợ; không đổi tên file một cách máy móc rồi giả định builder sẽ đọc được.

## 11. Bật chế độ chẩn đoán reachability metadata

Các GraalVM release mới cung cấp chế độ kiểm tra metadata chặt hơn. Có thể bật --exact-reachability-metadata lúc build để phát hiện thiếu registration sớm:

~~~bash
native-image \
  --exact-reachability-metadata \
  -jar target/billing-service.jar \
  billing-service
~~~

Nếu muốn giới hạn phạm vi kiểm tra, một số release hỗ trợ chỉ định package:

~~~bash
native-image \
  --exact-reachability-metadata=com.example.billing,com.example.partner \
  -jar target/billing-service.jar \
  billing-service
~~~

Khi chạy executable, dùng chế độ báo cáo:

~~~bash
./billing-service \
  -XX:MissingRegistrationReportingMode=Warn
~~~

Warn giúp quan sát các truy cập thiếu metadata trong quá trình test. Khi muốn CI thất bại ngay cả khi code có catch(Throwable) vô tình nuốt lỗi đăng ký, có thể dùng:

~~~bash
./billing-service \
  -XX:MissingRegistrationReportingMode=Exit
~~~

Các option này phụ thuộc GraalVM version. Kiểm tra native-image --help và tài liệu của distribution trước khi đưa vào pipeline. Không bật chế độ chẩn đoán chỉ trên JVM rồi kết luận metadata của native image đã đầy đủ; phải chạy chính executable native.

## 12. Kiểm thử custom hints

### 12.1. Unit test cho RuntimeHintsRegistrar

Spring cung cấp RuntimeHintsPredicates để xác nhận registrar đã đăng ký đúng hint. Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class BillingRuntimeHintsTests {

    @Test
    void registersLegacyMethodInvocation() {
        RuntimeHints hints = new RuntimeHints();
        new BillingRuntimeHints().registerHints(
            hints,
            getClass().getClassLoader()
        );

        assertThat(
            RuntimeHintsPredicates.reflection()
                .onMethod(LegacyInvoiceAdapter.class, "readPayload")
                .invoke()
        ).accepts(hints);
    }
}
~~~

Test này kiểm tra registrar tạo hint đúng. Nó không chứng minh native executable đã đóng gói metadata hoặc tất cả đường chạy đều được bao phủ.

### 12.2. Kiểm tra executable JAR

Sau khi package, xác nhận generated/static hints nằm trong artifact:

~~~bash
jar tf target/billing-service.jar | grep META-INF/native-image
~~~

Kiểm tra:

- generated hints của Spring AOT có trong JAR;
- file reachability-metadata.json của ứng dụng có trong classpath;
- không có file cũ bị đặt nhầm ngoài thư mục metadata;
- dependency chứa reachability metadata đúng version đã được đóng gói.

Đừng chỉ kiểm tra thư mục source. Native Image đọc metadata từ classpath của lần build; file không được package sẽ không có tác dụng.

### 12.3. Chạy contract test trên native executable

Chọn các kịch bản đại diện:

| Nhóm | Kịch bản cần chạy |
| --- | --- |
| Reflection | Load class theo tên, gọi constructor/method, đọc/ghi field |
| Proxy | Tạo đúng tổ hợp JDK proxy; gọi method qua proxy; kiểm tra Spring AOP advice |
| JSON binding | Deserialize request/response DTO có field lồng nhau, record và custom serializer |
| Java serialization | Ghi và đọc lại từng class legacy được phép |
| JNI | Gọi native method, callback từ C/C++ về Java, truy cập field/method qua JNI |
| Integration | Chạy endpoint hoặc message flow sử dụng thư viện bên thứ ba |

Native test cần gọi đúng nhánh nghiệp vụ. Nếu chỉ gọi health endpoint, test sẽ không phát hiện metadata thiếu trong serializer hoặc JNI adapter chỉ được dùng ở một chức năng khác.

## 13. Những nguyên nhân khác dễ bị nhầm với thiếu metadata

| Triệu chứng | Nguyên nhân khác có thể xảy ra | Cách xác minh |
| --- | --- | --- |
| Class không tìm thấy | Dependency không có trong artifact hoặc tên class sai | Kiểm tra dependency graph và nội dung JAR |
| Bean không tồn tại | Profile hoặc Conditional được đánh giá khác khi AOT | Kiểm tra profile/property lúc AOT processing |
| Proxy không hoạt động | Bean definition không được AOT xử lý hoặc kiểu bean khai báo quá chung | Kiểm tra generated context và kiểu trả về Bean |
| JSON thiếu field | Naming strategy, constructor binding hoặc custom serializer sai | Test JSON contract trên JVM và native |
| Java serialization thất bại | Class không implement Serializable, serialVersionUID hoặc object graph không hợp lệ | Kiểm tra contract serialization độc lập |
| JNI không load được | Thiếu native library, symbol hoặc sai ABI | Kiểm tra file native và linker/runtime |
| Resource không đọc được | Đường dẫn sai hoặc dùng URL như file system path | Dùng getResourceAsStream và kiểm tra resource metadata |
| Chỉ lỗi ở một OS/CPU | Native library hoặc build artifact không đúng target | Kiểm tra OS, architecture, libc và dependency native |

Nếu một class không có trong dependency hoặc một bean đã bị loại bởi condition ở build time, thêm reflection hint không thể đưa nó trở lại. Phải sửa classpath hoặc cấu hình AOT trước.

## 14. Troubleshooting theo từng nhóm

| Triệu chứng | Kiểm tra | Cách xử lý |
| --- | --- | --- |
| MissingReflectionRegistrationError tại Class.forName | Tên class có đến từ runtime property/database không? | Đăng ký type hoặc chuyển sang registry class tĩnh nếu phù hợp |
| Lỗi tại Method.invoke | Method name và parameter types có khớp không? | Đăng ký đúng method signature với quyền INVOKE |
| Lỗi tại Field.get/Field.set | Field có được truy cập động không? | Đăng ký đúng field hoặc binding hint cho DTO |
| JDK proxy không tạo được | Tổ hợp interface và thứ tự có đúng không? | Bổ sung JDK proxy hint cho đúng interface list |
| Spring transaction/security proxy lỗi | Spring AOT có nhận diện bean/proxy không? | Kiểm tra bean type, proxy strategy và generated bytecode |
| JSON codec lỗi trên DTO từ WebClient | DTO có nằm trong kiểu Spring suy ra được không? | Dùng RegisterReflectionForBinding hoặc custom hints |
| ObjectInputStream lỗi trên native | Class có được đăng ký Java serialization không? | Dùng registerJavaSerialization hoặc metadata serializable |
| MissingJNIRegistrationError | Native code gọi class/member nào? | Khai báo type, method và field trong jni metadata |
| UnsatisfiedLinkError | Native library và symbol có sẵn không? | Sửa packaging, library path hoặc ABI; không chỉ thêm JNI hint |
| Agent không ghi entry mong muốn | Kịch bản có thực sự chạy qua code đó không? | Thêm test/call path và chạy lại agent |
| Hint có trong source nhưng native vẫn lỗi | File có nằm trong artifact classpath không? | Kiểm tra JAR, build output và native build command |
| JVM test pass nhưng native test fail | Dynamic feature có được thực thi trên JVM test không? | Bật exact metadata mode và chạy cùng scenario trên native |

## 15. Quy trình thực hành với dịch vụ billing

Giả sử dịch vụ billing dùng một thư viện cũ để load handler theo tên class, gọi partner gateway qua JDK proxy, deserialize payload legacy và nhận callback từ native SDK.

**Bước 1 — tái hiện từng lỗi**

- Gọi endpoint sử dụng handler được cấu hình bằng class name.
- Thực hiện request qua partner gateway proxy.
- Đọc một payload legacy bằng Java serialization.
- Gọi native SDK để nhận callback.
- Lưu stack trace của native executable.

**Bước 2 — phân loại truy cập**

- Handler theo class name: reflection.
- Partner gateway: xác định JDK proxy hay CGLIB.
- Payload legacy: Java serialization.
- Callback native SDK: JNI.

**Bước 3 — bổ sung hint đúng cơ chế**

- Dùng RuntimeHintsRegistrar cho method reflection, JDK proxy và JNI hints do ứng dụng quản lý.
- Dùng RegisterReflectionForBinding nếu partner response là DTO được deserialize bằng JSON.
- Dùng hints.serialization().registerType (Spring Framework 6.x) hoặc reflection type hint với withJavaSerialization(true) ở API mới hơn cho class legacy.
- Dùng hints.jni().registerType hoặc reachability-metadata.json có section jni cho callback được native code gọi.

**Bước 4 — kiểm tra hint**

Viết unit test dùng RuntimeHintsPredicates cho registrar. Xác nhận JSON hợp lệ và nằm trong classpath của executable JAR.

**Bước 5 — chạy Tracing Agent**

Chạy ứng dụng trên JVM với AOT bật, gắn Tracing Agent và thực hiện các luồng trên. Review output, lọc entry thuộc test infrastructure rồi hợp nhất metadata cần thiết.

**Bước 6 — build và chạy native**

Bật --exact-reachability-metadata theo GraalVM version, chạy executable với MissingRegistrationReportingMode=Exit trong test environment và gọi lại toàn bộ kịch bản.

**Bước 7 — giữ regression test**

Mỗi loại metadata thiếu từng gây lỗi phải có một test tái hiện đường truy cập tương ứng. Khi nâng Spring Boot, GraalVM hoặc dependency JNI/serializer, chạy lại bộ test này.

## 16. Checklist trước khi kết luận đã sửa lỗi

- [ ] Đã lưu stack trace và xác định call site truy cập động.
- [ ] Đã phân biệt reflection, JDK proxy, CGLIB proxy, Java serialization, JSON binding và JNI.
- [ ] Đã kiểm tra Spring AOT có tự sinh hint cho contract đó hay không.
- [ ] Đã xác minh class/member có thực sự nằm trong dependency và classpath.
- [ ] Reflection hint chỉ bao gồm constructor, method và field cần thiết.
- [ ] JDK proxy hint dùng đúng interface list và thứ tự.
- [ ] Không dùng JDK proxy metadata để xử lý CGLIB proxy một cách máy móc.
- [ ] DTO JSON dùng binding hints phù hợp.
- [ ] Java serialization class có metadata serialization riêng.
- [ ] JNI metadata khai báo đúng class/member được native code truy cập.
- [ ] Native library và ABI đã được kiểm tra riêng với JNI metadata.
- [ ] Tracing Agent đã chạy qua các luồng nghiệp vụ cần thiết.
- [ ] Agent output đã được review và loại metadata chỉ thuộc test infrastructure.
- [ ] Metadata nằm trong source resource và có trong executable artifact.
- [ ] RuntimeHintsRegistrar có unit test bằng RuntimeHintsPredicates.
- [ ] Native executable đã chạy các contract test reflection/proxy/serialization/JNI.
- [ ] Đã thử chế độ báo cáo thiếu registration trong CI hoặc môi trường test.
- [ ] Không có đoạn code bắt Throwable rồi bỏ qua lỗi đăng ký.

**Ghi nhớ:** metadata phải mô tả đúng kiểu truy cập động. Reflection cần type/member; JDK proxy cần danh sách interface; Java serialization cần đăng ký class serialize; JSON binding cần binding hints; JNI cần khai báo riêng những type/member mà native code tra cứu. Hãy xác định call site, thêm hint tối thiểu, kiểm thử hint và chạy lại đúng đường nghiệp vụ trên native executable.

## Tài liệu tham khảo

- [Spring Framework — Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html): RuntimeHints, RuntimeHintsRegistrar, ImportRuntimeHints, reflection, serialization, proxy và kiểm thử hints.
- [Spring Boot — Advanced Native Images Topics](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html): tracing agent, custom hints, RegisterReflectionForBinding và vị trí static hint files.
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): khác biệt JDK dynamic proxy và CGLIB.
- [Spring Framework — RuntimeHints API](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/aot/hint/RuntimeHints.html): các accessor reflection, proxy, serialization và JNI.
- [Spring Framework — TypeHint.Builder API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aot/hint/TypeHint.Builder.html): khai báo member và Java serialization trong type hints.
- [Spring Framework — ProxyHints API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/ProxyHints.html): đăng ký JDK interface proxy.
- [Spring Framework — ClassHintUtils API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/aot/hint/support/ClassHintUtils.html): suy ra hints cho JDK proxy và CGLIB subclass do Spring quản lý.
- [GraalVM Native Image — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): reflection, proxy, serialization, JNI, JSON schema và exact reachability metadata.
- [GraalVM Native Image — Collect Metadata with the Tracing Agent](https://www.graalvm.org/latest/reference-manual/native-image/metadata/AutomaticMetadataCollection/): thu thập metadata từ ứng dụng JVM và lọc output của agent.
- [Spring Framework — RuntimeHintsPredicates API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/aot/hint/predicate/RuntimeHintsPredicates.html): kiểm thử reflection, resource, serialization và proxy hints.
