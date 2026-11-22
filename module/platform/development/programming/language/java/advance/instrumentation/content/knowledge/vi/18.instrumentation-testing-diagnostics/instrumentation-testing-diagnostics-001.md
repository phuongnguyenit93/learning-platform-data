# Kiểm thử bộ lọc bằng tên lớp, descriptor, class loader và module

Trong Java Instrumentation, `ClassFileTransformer` có thể nhận callback đối với rất nhiều lớp: lớp của ứng dụng, thư viện bên thứ ba, framework, JDK, lớp thuộc các plugin và các phiên bản cùng tên do những class loader khác nhau định nghĩa. Một bộ lọc sai có thể làm agent **instrument nhầm lớp**, bỏ sót method cần đo, chèn lặp probe, gây `VerifyError`/`LinkageError` hoặc tạo dữ liệu quan sát không đúng nguồn.

Muốn kiểm thử bộ lọc tin cậy, đừng chỉ hỏi “tên class có bắt đầu bằng package X không?”. Đối với mỗi method được phép, cần xét **đồng thời bốn chiều**:

1. **Tên lớp** ở dạng JVM internal name, ví dụ `com/acme/order/OrderService`.
2. **Tên method và method descriptor** JVM, ví dụ `process(Ljava/lang/String;I)Z`. Trong đề bài, “descriptor” chính là tiêu chí phân biệt đúng overload và kiểu trả về, không phải chỉ tên method.
3. **Class loader thực sự định nghĩa lớp** (defining loader), phân biệt loader instance theo identity, kể cả khi hai loader nạp cùng binary name.
4. **Module thực sự chứa lớp**, phân biệt named/unnamed module và Module object, không chỉ so tên module bằng chuỗi.

Bài này thuộc nhóm **Kiểm thử và chẩn đoán** của Java Instrumentation. Bạn sẽ thiết kế bộ lọc fail-closed, xây bảng ca dương tính/âm tính, kiểm thử classloader/module thật, đối chiếu descriptor từ class file và kết nối logic đó với callback `transform`. Ví dụ chính dùng **Java 17+ không phụ thuộc thư viện ngoài** để kiểm tra filter và method metadata. Phần nối sang agent/ASM được ghi rõ là mẫu tích hợp chứ không giả là chương trình chạy độc lập.

## 1. Xác định mục tiêu kiểm thử trước khi viết filter

Một policy đo method có thể được mô tả như sau:

```yaml
feature: order-latency
target:
  classInternalName: com/acme/order/OrderService
  methodName: submit
  methodDescriptor: (Ljava/lang/String;I)Z
  loaderIdentity: application-loader-A
  moduleIdentity: com.acme.order@boot-layer
action:
  onMatch: INSTRUMENT
  otherwise: SKIP_WITH_REASON
```

Đây là **schema minh họa**. `loaderIdentity` và `moduleIdentity` chỉ là nhãn dễ đọc trong tài liệu; trong code runtime cần đối chiếu **đối tượng `ClassLoader` và `Module` thật**, không suy identity chỉ từ chuỗi YAML.

Policy chỉ match khi **mọi điều kiện** đồng thời đúng. Nếu class có cùng tên và signature nhưng được định nghĩa bởi plugin loader khác, không tự động cho phép. Nếu đúng class/loader/module nhưng method overload khác descriptor, cũng không cho phép.

```text
Callback transform(module, loader, className, ..., classfileBuffer)
                  |
                  v
        className hợp lệ và đúng?
         | NO -> SKIP_CLASS_NAME
         v
        loader đúng instance?
         | NO -> SKIP_LOADER
         v
        module đúng Module object?
         | NO -> SKIP_MODULE
         v
      parse method name + descriptor từ class bytes
         |
         v
        method signature đúng?
         | NO -> SKIP_DESCRIPTOR
         v
       kiểm tra trạng thái, excluded/duplicate/capability
         |
         v
       tạo bytecode mới + verify + đo tác dụng
```

**Nguyên tắc fail-closed:** Thiếu thông tin để xác nhận một chiều bắt buộc thì **không** instrument. Đừng có fallback “không thấy module thì match theo tên class” hoặc “không parse được descriptor thì instrument mọi overload”.

### Bảng định nghĩa thành công

| Trạng thái | Nghĩa chính xác | Bằng chứng |
|---|---|---|
| `FILTER_MATCH` | Bộ lọc cho phép class + method theo bốn chiều | Test predicate + context/classfile metadata |
| `CLASS_TRANSFORMED` | Transformer trả class bytes mới | Callback và bytes khác bản gốc |
| `CLASS_ACCEPTED` | JVM chấp nhận định nghĩa sau chuỗi transformers | Không có lỗi load/retransform tương ứng |
| `PROBE_EXECUTED` | Method được gọi và code đo chạy | Counter/span/log sentinel chỉ xuất hiện đúng mục tiêu |
| `OUT_OF_SCOPE_UNTOUCHED` | Các lớp/method không phù hợp không bị sửa | Negative tests, bytecode diff/behavior |
| `CLASSLOADER_ISOLATED` | Cùng binary name ở loader khác không bị chọn nhầm | Hai loader instance và Class object riêng |
| `MODULE_ISOLATED` | Module khác không được match chỉ do cùng tên package | So Module identity và test module thực |
| `IDEMPOTENT` | Re-transform/transform lặp không sinh probe trùng | Kiểm bytes/counter trước–sau |

Một **FILTER_MATCH** không đồng nghĩa **PROBE_EXECUTED**. Class có thể không bao giờ được load, transformer có thể trả `null`, JVM có thể từ chối bytes, hoặc method chưa được gọi. Phải báo từng trạng thái riêng để chẩn đoán đúng.

## 2. Tên lớp: binary name, internal name và những ngoại lệ dễ nhầm

### 2.1. Tên ở callback `ClassFileTransformer`

Với Java 9+, callback có chữ ký:

```java
byte[] transform(
    Module module,
    ClassLoader loader,
    String className,
    Class<?> classBeingRedefined,
    java.security.ProtectionDomain protectionDomain,
    byte[] classfileBuffer);
```

Tham số `className` là **JVM internal name**, dùng dấu `/` phân tách package, ví dụ `"java/util/List"`, **không** phải `"java.util.List"` như `Class.getName()` đối với class thường.

| Source/ý nghĩa | Binary name / tên dùng trong reflection | Internal name |
|---|---|---|
| `com.acme.order.OrderService` | `com.acme.order.OrderService` | `com/acme/order/OrderService` |
| `com.acme.order.Outer.Inner` | `com.acme.order.Outer$Inner` | `com/acme/order/Outer$Inner` |
| `java.lang.String` | `java.lang.String` | `java/lang/String` |
| Class ở default package `Demo` | `Demo` | `Demo` |

Đừng viết `className.equals("com.acme.order.OrderService")` trong callback rồi ngạc nhiên vì bộ lọc không match. Nếu cấu hình lưu binary name có dấu chấm, **chuẩn hóa một lần ở biên cấu hình** và test quy tắc chuẩn hóa; phần hot path nên so tên internal đã chuẩn hóa.

### 2.2. So sánh chính xác trước khi dùng prefix

Nếu chỉ cần `com/acme/order/OrderService`, hãy dùng `equals`. Với một tập package được allowlist, dùng ranh giới `/`:

```java
// Snippet minh họa:
boolean inPackage = className != null
        && className.startsWith("com/acme/order/");
```

`startsWith("com/acme/order")` (không có dấu `/` cuối) cũng match `com/acme/orders` hoặc `com/acme/orderlegacy`. Đây là bug phổ biến khi đặt filter cho nhiều package.

Một filter `startsWith("java/")` để loại JDK không bao phủ mọi package do JVM/JDK sử dụng; filter `startsWith("com/")` lại rất rộng và có thể chọn library/framework. Chọn đúng phạm vi từ mục tiêu quan sát, không suy từ việc class name “trông giống application code”.

### 2.3. Tên có thể thiếu hoặc không phù hợp giả định

Viết callback theo hướng phòng thủ khi `className==null` hoặc khi class bytes không phù hợp. Không tự thay bằng `classBeingRedefined.getName()` nếu đối tượng đó `null` trong lượt class load. Không `Class.forName` bằng tên target ngay trong `transform` để cố xác minh: thao tác ấy có thể kích hoạt class loading/reentrancy khi JVM đang định nghĩa lớp.

Với lambda, hidden classes, proxy classes, generated names, arrays và nested types, cần xác định rõ agent có thực sự thấy callback tương ứng hay không. Không lấy `Class.getName()` của một hidden class rồi mặc định nó luôn ánh xạ một-một vào `className` thông thường. Nếu thông tin đầu vào không nằm trong hợp đồng policy, báo `SKIP_UNKNOWN_NAME`; không đoán.

## 3. Method descriptor: tên method thôi không đủ

Class callback **không cung cấp một descriptor của method đơn lẻ**. `classfileBuffer` chứa cả định nghĩa class; transformer phải parse class file (ASM, thư viện class-file thích hợp, hoặc parser có kiểm soát) để nhận từng `method_info.name_index` và `method_info.descriptor_index`.

### 3.1. Descriptor mang cả tham số và kiểu trả về

Theo JVMS `4.3.3`:

```text
MethodDescriptor:
    ( ParameterDescriptor* ) ReturnDescriptor

Ví dụ:
    ()V
    (I)V
    (Ljava/lang/String;)V
    (Ljava/lang/String;I)Z
    ([I)[Ljava/lang/String;
```

Bảng ký hiệu:

| Java type | JVM descriptor |
|---|---|
| `void` | `V` — chỉ là return descriptor |
| `boolean` | `Z` |
| `byte` | `B` |
| `char` | `C` |
| `short` | `S` |
| `int` | `I` |
| `long` | `J` |
| `float` | `F` |
| `double` | `D` |
| `java.lang.String` | `Ljava/lang/String;` |
| `int[]` | `[I` |
| `String[][]` | `[[Ljava/lang/String;` |

Ví dụ source:

```java
void submit(int count) { }
void submit(String code) { }
boolean submit(String code, int count) { return true; }
String[] transform(int[] values) { return new String[0]; }
```

Tương ứng:

```text
submit(I)V
submit(Ljava/lang/String;)V
submit(Ljava/lang/String;I)Z
transform([I)[Ljava/lang/String;
```

**Không** dùng `methodName=="submit"` rồi instrument tất cả overload. Không tự bỏ kiểu trả về khỏi descriptor dù theo quy tắc Java source thông thường không thể overload chỉ bằng return type: descriptor trong class file vẫn chứa phần return, và đối chiếu chính xác giúp tránh sai policy/bridge/synthetic method.

### 3.2. Descriptor khác generic Signature

`List<String>` và `List<Integer>` có cùng **erased type descriptor** `Ljava/util/List;` trong ngữ cảnh method parameter. Thông tin generic có thể nằm trong `Signature` attribute; đó **không** phải descriptor để JVM liên kết method.

```java
// Java source minh họa:
public java.util.List<String> names(java.util.List<Integer> input) {
    return java.util.List.of();
}
```

Descriptor là:

```text
(Ljava/util/List;)Ljava/util/List;
```

Dùng chuỗi `"List<String>"` hoặc `"List<Integer>"` làm method descriptor là sai. Test nên có generic fixture để bảo đảm bộ lọc không nhầm source signature, reflection `toGenericString()` và JVM descriptor.

### 3.3. Constructor, static initializer, bridge và synthetic methods

- Constructor có tên JVM `<init>`, return `V`, ví dụ `<init>(I)V`.
- Class initializer có tên `<clinit>` và descriptor `()V` nếu tồn tại.
- Bridge/synthetic methods có thể được compiler tạo, mang access flags `ACC_BRIDGE`/`ACC_SYNTHETIC`; không dựa chỉ vào tên source.
- Lambda implementation methods có thể có tên `lambda$...` và không nhất thiết ổn định giữa các bản compile.
- Với agent chỉ muốn đo method do lập trình viên khai báo, cần rule rõ về bridge/synthetic; không tự bỏ mọi synthetic method nếu feature cần chính chúng.
- Với constructor, không chèn code đọc `this` trước khi superclass constructor hoàn thành mà không bảo đảm verifier rules; tên/descriptor match không đồng nghĩa bytecode injection an toàn.

### 3.4. Kiểm descriptor có thể dùng MethodType ở test

Java 17 có `java.lang.invoke.MethodType.toMethodDescriptorString()`:

```java
String a = java.lang.invoke.MethodType
        .methodType(void.class, int.class)
        .toMethodDescriptorString();            // "(I)V"

String b = java.lang.invoke.MethodType
        .methodType(String[].class, int[].class)
        .toMethodDescriptorString();            // "([I)[Ljava/lang/String;"
```

Đây là snippet hợp lệ trong một method Java và dùng để **kiểm tra kỳ vọng test**. Trong callback `transform`, tránh dùng reflection trên class target đang được load để trích descriptor: class có thể chưa được định nghĩa. Hãy lấy method metadata **từ bytes**, không buộc class target phải được nạp chỉ để quyết định có instrument hay không.

## 4. Class loader: so object identity, không so tên hiển thị

Theo Java, class identity bao gồm **binary name và defining class loader**. Hai loader khác nhau có thể định nghĩa hai class cùng binary name nhưng đó là **hai Class objects khác nhau**.

```text
Loader-A
  └─ sample.ProbeTarget  -> Class-A

Loader-B
  └─ sample.ProbeTarget  -> Class-B

Class-A.getName() == Class-B.getName()  // true
Class-A == Class-B                      // false
Class-A.getClassLoader() == loaderA     // true
Class-B.getClassLoader() == loaderB     // true
```

**Mấu chốt đối với bộ lọc:** `className=="sample/ProbeTarget"` không đủ. Nếu policy chỉ cho phép class từ `loaderA` mà transformer bỏ qua loader, nó có thể instrument cả bản từ `loaderB` trong môi trường plugin/application server.

### 4.1. `loader == null` là bootstrap, không phải loader hiện tại

Javadoc `ClassFileTransformer` xác định `loader` là defining loader và **có thể null nếu lớp do bootstrap loader định nghĩa**. Một filter `loader != null` sẽ bỏ qua bootstrap classes — đôi khi đó là chính sách mong muốn — nhưng đừng nhầm null với “không biết, lấy system loader thay”.

```java
// Ví dụ điều kiện rõ ràng:
boolean appOnly = loader != null
        && loader == approvedLoader;
```

Nếu thực sự cần instrument bootstrap class, policy phải **opt-in riêng**, với kiểm tra class/module/capability và helper visibility. Đừng viết `loader == null || loader == approvedLoader` theo thói quen: nó vô tình mở rộng phạm vi sang bootstrap.

### 4.2. Identity khác tên/tên class loader

`loader.getName()` (Java 9+) chỉ là tên có thể null, không phải mã định danh duy nhất. `loader.getClass().getName()` chỉ nói **kiểu implementation của loader**, không phân biệt hai instances. `System.identityHashCode(loader)` giúp log chẩn đoán nhưng có khả năng collision, không được dùng thay `==` trong phép quyết định quyền.

Nếu chỉ cần phân biệt loader trong một JVM, giữ **reference tới loader instance đã được phê duyệt** và so `==`. Nhưng agent giữ reference mạnh tới loader có thể **ngăn class loader unloading**. Với agent sống lâu trên server có redeploy, cần quản lý loader scope, weak identity mapping an toàn hoặc lifecycle release để không giữ application loader mãi mãi. Đừng chuyển từ bug instrument nhầm sang bug giữ memory.

### 4.3. Defining loader và initiating loader

Một loader có thể ủy quyền cho parent và nhận class đã được **parent định nghĩa**. Callback nhận **defining loader** của class đang được transform, không phải tùy ý loader đã gọi `loadClass` ban đầu. Test cần chứng minh class nào thật sự được định nghĩa bởi loader nào; chỉ nhìn đoạn code `child.loadClass("X")` chưa chứng minh class thuộc child nếu parent cũng có X.

Khi tạo test với hai loaders, để bảo đảm chúng định nghĩa class riêng, hãy để target class **không nằm trên parent/system classpath**, và dùng hai `URLClassLoader` có parent chỉ thấy JDK/platform classes.

## 5. Module: named/unnamed, identity và layer

Java 9+ bổ sung tham số `Module module` trong callback. Một class thuộc **đúng một runtime module**. Tên module cũng không đủ để suy identity:

- Named module có `module.isNamed()==true` và `module.getName()` không null.
- Unnamed module có `module.isNamed()==false` và `module.getName()==null`.
- **Mỗi class loader có một unnamed module riêng**, nên hai loader khác nhau thường có hai unnamed `Module` objects khác nhau.
- Named modules có thể được định nghĩa trong các `ModuleLayer` khác nhau; cùng chuỗi module name không phải lúc nào cũng là cùng runtime module.
- Không phải mọi class do một loader định nghĩa đều ở unnamed module: loader có thể định nghĩa classes thuộc named modules.

**So sánh cho policy chặt:** `module == allowedModule`. Đối chiếu `module.getName().equals("demo.feature")` không đủ nếu bạn cần phân biệt instances/layers. Với unnamed module, `module.getName()==null` phải được xử lý rõ, không gọi `equals` trên null.

### 5.1. Đừng gộp module với package

`module.getName()` có thể là `"demo.feature"`, còn `className` là `"demo/feature/NamedTarget"`. Hai chuỗi không ở cùng một namespace. Package `demo.feature` trong tên class không chứng minh class thuộc module `demo.feature`; chỉ `Class.getModule()`/callback module và metadata runtime mới cho biết.

Thêm nữa, `module==someModule` match đúng module object nhưng **không** làm helper class tự khả kiến trong target loader. JPMS readability/exports/opens và class-loader visibility là những yêu cầu riêng để instrument bytecode gọi helper hoặc deep-reflect sau đó.

### 5.2. Không tìm lại Module bằng tên mỗi callback

Một code kiểu:

```java
ModuleLayer.boot().findModule("demo.feature")
```

có thể phù hợp trong **test cố định với module nằm ở boot layer**, nhưng không phải cách tìm mọi module trong framework/plugin layers. Nếu test/production có nhiều layers, cần lấy module từ callback hoặc `Class<?>` thực tế, không suy module identity từ chuỗi tên.

### 5.3. Null và edge cases

Với callback Java 9+ bình thường, JVM cung cấp `module` của class. Dẫu vậy, một pure filter được gọi từ unit test hoặc adapter có thể nhận null; chính sách nên **fail-closed** khi không xác minh được module bắt buộc, thay vì đoán là unnamed module. `null` không phải một unnamed `Module`; unnamed module vẫn là **Module object có thật**.

## 6. Thiết kế bộ lọc fail-closed, có thể kiểm thử độc lập

Tách **quy tắc quyết định** khỏi **việc biến đổi bytecode**. Ví dụ model:

```java
// Mô hình code thiết kế, chỉ những trường cần cho match.
record Seen(
    String internalName,
    String methodName,
    String descriptor,
    ClassLoader loader,
    Module module
) {}

record Rule(
    String internalName,
    String methodName,
    String descriptor,
    ClassLoader allowedLoader,
    Module allowedModule
) {
    boolean accepts(Seen s) {
        return s != null
            && java.util.Objects.equals(internalName, s.internalName())
            && java.util.Objects.equals(methodName, s.methodName())
            && java.util.Objects.equals(descriptor, s.descriptor())
            && allowedLoader == s.loader()
            && allowedModule == s.module();
    }
}
```

Đoạn là **mẫu thiết kế hợp lệ Java 17+** nhưng chưa có class chứa record; phần 7 đưa chương trình runnable đầy đủ.

Điểm cần đọc:

- `Objects.equals` xử lý null không ném exception. Với policy thật, hãy xác minh **expected names/descriptor không null** khi khởi tạo để null input không vô tình match null expected.
- Dùng `==` cho loader và module để đảm bảo runtime identity.
- Nếu `allowedLoader == null` được dùng để biểu diễn **bootstrap được phép**, phải có policy xác nhận rõ rằng đây là opt-in; không tự diễn giải null expected là “any loader”.
- So descriptor **nguyên chuỗi**, không dùng `contains`, `startsWith` hoặc số lượng tham số.
- Với method name `<init>`/`<clinit>`, cần rule/guard riêng nếu feature không chủ ý instrument constructors/initializers.

### 6.1. Định nghĩa lý do từ chối

Một API giàu khả năng chẩn đoán có thể trả enum:

```text
ALLOW
SKIP_UNKNOWN_CONTEXT
SKIP_CLASS_NAME
SKIP_LOADER
SKIP_MODULE
SKIP_METHOD_NAME
SKIP_DESCRIPTOR
SKIP_SYNTHETIC_OR_BRIDGE
SKIP_ALREADY_INSTRUMENTED
SKIP_CAPABILITY
ERROR_INVALID_CLASSFILE
```

Đây là **đề xuất trạng thái**, không phải một enum của JDK. Hãy dùng reason codes hữu hạn cho metrics, không đưa full class names/method signatures từ tất cả classes vào nhãn có cardinality vô hạn. Chỉ ghi thông tin chi tiết trong diagnostic sampling hoặc môi trường test.

### 6.2. Thứ tự lọc ảnh hưởng hiệu năng và an toàn

Lớp có thể có hàng trăm methods. Trước khi parse sâu:

1. Kiểm `className` null/allowlist (rẻ).
2. Kiểm identity loader/module (rẻ).
3. Nếu class bị loại, **return `null` sớm**, tránh parse buffer.
4. Với class đã qua gate, parse method list/descriptors.
5. Kiểm target method and descriptor.
6. Chỉ sau cùng mới tạo bytecode mới/frames/stack-map và kiểm idempotency.

Không nên gọi logger, reflection, classloader loading hay JSON serializer trong hot path của transformer để “đoán” class metadata. Transformer đang được JVM gọi trong chu kỳ định nghĩa/retransform class, nên dependency loading/reentrancy rất nhạy cảm.

## 7. Chiến lược kiểm thử: ba tầng độc lập

### Tầng A — Pure predicate unit tests

Tạo context giả/real objects và kiểm từng chiều filter. Chứng minh đúng + sai cho từng field, kể cả `null`, namespace sai định dạng, overloaded descriptor, nhiều loader, named vs unnamed module.

**Ưu điểm:** nhanh, deterministic, không cần JVM attach/instrument class bytes.  
**Giới hạn:** chưa chứng minh transformer thực sự nhận đúng callback hay chèn được bytecode.

### Tầng B — Classfile metadata tests

Dùng **class file bytes đã biên dịch** để kiểm method name/descriptor. Tạo fixture có overloads, arrays, generic erasure, constructors, bridge/synthetic khi cần. Không lấy method descriptor bằng việc gọi `Class.forName` từ transformer: ở load-time target class có thể chưa được define.

**Ưu điểm:** phát hiện nhầm `Signature` với `descriptor` và lỗi parser/method visitor.  
**Giới hạn:** parser có thể đúng nhưng bytecode được sinh vẫn sai verifier rules.

### Tầng C — Integration tests trên JVM thật

- Khởi động JVM với `-javaagent` và target lớp trong classpath/module path có kiểm soát.
- Ghi số lượt `transform` cho **allow** và **deny**, không log mọi class quá rộng.
- Có hai loaders định nghĩa cùng binary name nhưng chỉ một loader allow.
- Có named module và unnamed module, hoặc hai layers nếu policy cần phân biệt layer.
- Gọi đúng method, kiểm một probe marker; gọi overload/instance từ loader khác, bảo đảm không có marker.
- Nếu có `retransformClasses`, kiểm behavior khi class đã load, class modifiability và không nhân đôi probe.
- Test class/constructor/synthetic exclusions, không chỉ happy path.
- Kiểm lỗi linkage/helper visibility/JPMS access khi code được chèn thực sự chạy.

Không tuyên bố integration test đã được thực hiện chỉ vì unit tests của predicate pass.

## 8. Ví dụ Java 17+ chạy được: overload, hai class loaders, named module

Ví dụ này có **bốn file Java**: một class fixture không thuộc runtime classpath của harness, một named module chứa class khác, và một test harness thực hiện filter. Nó kiểm các tiêu chí trên **đối tượng ClassLoader/Module thật**, đồng thời có những ca synthetic context để cô lập từng nhánh predicate.

Test sử dụng một class-file reader **tối giản chỉ dành cho test fixture**, hỗ trợ các constant-pool tags cần thiết để đọc tên/descriptors của method; không dùng nó để sinh/sửa classfile production. Một JVM transformer thực nên dùng ASM/JDK Class-File API hoặc parser đáng tin cậy phù hợp runtime.

### 8.1. Thư mục

```text
filter-lab/
  src-target/
    sample/ProbeTarget.java
  src-module/
    demo.feature/module-info.java
    demo.feature/demo/feature/NamedTarget.java
  src-main/
    FilterHarness.java
```

**Không đưa `build/target` vào `-cp` runtime**. Nếu để fixture target trên parent classpath, hai `URLClassLoader` có thể ủy quyền rồi nhận cùng class từ parent, khiến phép thử loader identity mất ý nghĩa.

### 8.2. `src-target/sample/ProbeTarget.java`

```java
package sample;

public final class ProbeTarget {
    public void execute(int value) {
        // Một overload cần chọn.
    }

    public void execute(String text) {
        // Overload khác phải bị loại khi chọn (I)V.
    }

    public String[] transform(int[] values) {
        return new String[] {"ok"};
    }
}
```

Method descriptors đáng chú ý:

```text
execute(I)V
execute(Ljava/lang/String;)V
transform([I)[Ljava/lang/String;
<init>()V
```

Dù class source có tên `sample.ProbeTarget`, callback filter của Java agent sẽ dùng internal name `sample/ProbeTarget`.

### 8.3. `src-module/demo.feature/module-info.java`

```java
module demo.feature {
    // Không cần exports package để harness chỉ kiểm metadata.
}
```

Module này không export package `demo.feature`. Harness chỉ dùng `Class.forName(Module,String)` và đọc method metadata được phép, **không gọi method nghiệp vụ**. Test `Module` identity không đồng nghĩa cố gắng vượt qua module encapsulation.

### 8.4. `src-module/demo.feature/demo/feature/NamedTarget.java`

```java
package demo.feature;

public final class NamedTarget {
    public void execute(int value) {
    }
}
```

Named fixture có method descriptor `execute(I)V` giống fixture unnamed, nhưng class/loader/module context khác. Mục tiêu là tạo **một module thật đã resolve trong boot layer**, không chỉ dựng fake string `"demo.feature"`.

### 8.5. `src-main/FilterHarness.java` — test đầy đủ

```java
import java.io.DataInputStream;
import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class FilterHarness {
    private static int checks;

    record Seen(
            String internalName,
            String methodName,
            String descriptor,
            ClassLoader loader,
            Module module) {
    }

    record Rule(
            String internalName,
            String methodName,
            String descriptor,
            ClassLoader approvedLoader,
            Module approvedModule) {

        Rule {
            Objects.requireNonNull(internalName);
            Objects.requireNonNull(methodName);
            Objects.requireNonNull(descriptor);
            Objects.requireNonNull(approvedModule);
        }

        boolean accepts(Seen seen) {
            return seen != null
                    && seen.internalName() != null
                    && seen.methodName() != null
                    && seen.descriptor() != null
                    && seen.module() != null
                    && internalName.equals(seen.internalName())
                    && methodName.equals(seen.methodName())
                    && descriptor.equals(seen.descriptor())
                    && approvedLoader == seen.loader()
                    && approvedModule == seen.module();
        }
    }

    record MethodKey(String name, String descriptor) {
    }

    private static void check(String label, boolean expected,
            boolean actual) {
        if (actual != expected) {
            throw new AssertionError(
                    label + " expected=" + expected
                    + " actual=" + actual);
        }
        checks++;
        System.out.println("PASS " + label);
    }

    private static void requireMethod(
            List<MethodKey> keys, String name, String descriptor) {
        if (!keys.contains(new MethodKey(name, descriptor))) {
            throw new AssertionError(
                    "Method missing: " + name + descriptor);
        }
    }

    private static void skipAttributes(
            DataInputStream in, int count) throws IOException {
        for (int i = 0; i < count; i++) {
            in.readUnsignedShort(); // attribute_name_index
            long length = Integer.toUnsignedLong(in.readInt());
            in.skipNBytes(length);
        }
    }

    // Parser nhỏ cho test. KHÔNG dùng làm bytecode library production.
    private static List<MethodKey> readMethods(Path classFile)
            throws IOException {
        try (DataInputStream in = new DataInputStream(
                Files.newInputStream(classFile))) {

            if (in.readInt() != 0xCAFEBABE) {
                throw new IOException("Not a class file");
            }
            in.readUnsignedShort(); // minor_version
            in.readUnsignedShort(); // major_version

            int constantPoolCount = in.readUnsignedShort();
            String[] utf8 = new String[constantPoolCount];

            for (int index = 1; index < constantPoolCount; index++) {
                int tag = in.readUnsignedByte();
                switch (tag) {
                    case 1 -> utf8[index] = in.readUTF();
                    case 3, 4 -> in.skipNBytes(4);
                    case 5, 6 -> {
                        in.skipNBytes(8);
                        index++; // long/double chiếm 2 cp slots
                    }
                    case 7, 8, 16, 19, 20 -> in.skipNBytes(2);
                    case 9, 10, 11, 12, 17, 18 ->
                            in.skipNBytes(4);
                    case 15 -> in.skipNBytes(3);
                    default -> throw new IOException(
                            "Unsupported cp tag=" + tag);
                }
            }

            in.readUnsignedShort(); // access_flags
            in.readUnsignedShort(); // this_class
            in.readUnsignedShort(); // super_class

            int interfaces = in.readUnsignedShort();
            in.skipNBytes((long) interfaces * 2);

            int fields = in.readUnsignedShort();
            for (int i = 0; i < fields; i++) {
                in.readUnsignedShort(); // access_flags
                in.readUnsignedShort(); // name_index
                in.readUnsignedShort(); // descriptor_index
                skipAttributes(in, in.readUnsignedShort());
            }

            int methods = in.readUnsignedShort();
            List<MethodKey> result = new ArrayList<>();
            for (int i = 0; i < methods; i++) {
                in.readUnsignedShort(); // access_flags
                int nameIndex = in.readUnsignedShort();
                int descriptorIndex = in.readUnsignedShort();
                result.add(new MethodKey(
                        utf8[nameIndex], utf8[descriptorIndex]));
                skipAttributes(in, in.readUnsignedShort());
            }
            return result;
        }
    }

    private static Seen seen(
            Class<?> type, String method, String descriptor) {
        return new Seen(
                type.getName().replace('.', '/'),
                method,
                descriptor,
                type.getClassLoader(),
                type.getModule());
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: FilterHarness <build/target>");
        }

        Path targetDir = Path.of(args[0]);
        List<MethodKey> keys = readMethods(
                targetDir.resolve("sample/ProbeTarget.class"));

        requireMethod(keys, "execute", "(I)V");
        requireMethod(
                keys, "execute", "(Ljava/lang/String;)V");
        requireMethod(
                keys, "transform", "([I)[Ljava/lang/String;");
        requireMethod(keys, "<init>", "()V");

        URL url = targetDir.toUri().toURL();

        try (URLClassLoader first = new URLClassLoader(
                     new URL[] {url},
                     ClassLoader.getPlatformClassLoader());
             URLClassLoader second = new URLClassLoader(
                     new URL[] {url},
                     ClassLoader.getPlatformClassLoader())) {

            Class<?> classA = Class.forName(
                    "sample.ProbeTarget", false, first);
            Class<?> classB = Class.forName(
                    "sample.ProbeTarget", false, second);

            if (classA == classB
                    || classA.getClassLoader() != first
                    || classB.getClassLoader() != second
                    || classA.getModule() == classB.getModule()) {
                throw new AssertionError(
                        "Fixture class loaders are not isolated");
            }

            Module moduleA = classA.getModule();
            Module moduleB = classB.getModule();

            Rule rule = new Rule(
                    "sample/ProbeTarget", "execute", "(I)V",
                    first, moduleA);

            Seen a = seen(classA, "execute", "(I)V");
            Seen b = seen(classB, "execute", "(I)V");

            check("BASELINE_ALLOWED", true, rule.accepts(a));
            check("OVERLOAD_DENIED", false,
                    rule.accepts(seen(
                            classA, "execute",
                            "(Ljava/lang/String;)V")));
            check("RETURN_DESCRIPTOR_DENIED", false,
                    rule.accepts(seen(
                            classA, "execute", "(I)I")));
            check("METHOD_NAME_DENIED", false,
                    rule.accepts(seen(
                            classA, "transform", "(I)V")));
            check("CONSTRUCTOR_DENIED", false,
                    rule.accepts(seen(
                            classA, "<init>", "()V")));
            check("CLASS_NAME_DENIED", false,
                    rule.accepts(new Seen(
                            "sample/Other", "execute", "(I)V",
                            first, moduleA)));
            check("DOT_NAME_DENIED", false,
                    rule.accepts(new Seen(
                            "sample.ProbeTarget", "execute", "(I)V",
                            first, moduleA)));
            check("SECOND_LOADER_DENIED", false, rule.accepts(b));
            check("WRONG_MODULE_DENIED", false,
                    rule.accepts(new Seen(
                            "sample/ProbeTarget", "execute", "(I)V",
                            first, moduleB)));
            check("BOOTSTRAP_LOADER_DENIED", false,
                    rule.accepts(new Seen(
                            "sample/ProbeTarget", "execute", "(I)V",
                            null, String.class.getModule())));
            check("NULL_CLASS_NAME_DENIED", false,
                    rule.accepts(new Seen(
                            null, "execute", "(I)V",
                            first, moduleA)));
            check("NULL_MODULE_DENIED", false,
                    rule.accepts(new Seen(
                            "sample/ProbeTarget", "execute", "(I)V",
                            first, null)));

            Rule arrayRule = new Rule(
                    "sample/ProbeTarget",
                    "transform",
                    "([I)[Ljava/lang/String;",
                    first, moduleA);
            check("ARRAY_DESCRIPTOR_ALLOWED", true,
                    arrayRule.accepts(
                            seen(classA, "transform",
                                    "([I)[Ljava/lang/String;")));
            check("ARRAY_DESCRIPTOR_DENIED", false,
                    arrayRule.accepts(
                            seen(classA, "transform",
                                    "([Ljava/lang/String;)V")));

            Module namedModule = ModuleLayer.boot()
                    .findModule("demo.feature")
                    .orElseThrow();
            Class<?> namedClass = Class.forName(
                    namedModule, "demo.feature.NamedTarget");
            if (namedClass == null) {
                throw new AssertionError(
                        "Named fixture not found");
            }
            Rule namedRule = new Rule(
                    "demo/feature/NamedTarget", "execute", "(I)V",
                    namedClass.getClassLoader(),
                    namedModule);

            check("NAMED_MODULE_ALLOWED", true,
                    namedRule.accepts(
                            seen(namedClass, "execute", "(I)V")));
            check("UNNAMED_MODULE_DENIED", false,
                    namedRule.accepts(a));
            check("NAMED_WRONG_MODULE_DENIED", false,
                    namedRule.accepts(new Seen(
                            "demo/feature/NamedTarget",
                            "execute", "(I)V",
                            namedClass.getClassLoader(),
                            moduleA)));
        }

        System.out.println("ALL_TESTS_PASSED=" + checks);
    }
}
```

**Về parser trong test:** `DataInputStream.readUTF` đủ dùng với constant-pool strings trong fixture ASCII ở đây; mã này minh họa việc truy cập `method_info`/`descriptor_index`, không phải một thư viện class-file parsing hoàn chỉnh để xử lý dữ liệu classfile không tin cậy. Production cần parser đáng tin và kiểm tra classfile structure/attributes/version/byte offsets đầy đủ. Test parser không tự tạo hoặc sửa bytecode, nên không có rủi ro làm hỏng verifier frames trong demo.

**Về ca synthetic context:** `WRONG_MODULE_DENIED` và `NAMED_WRONG_MODULE_DENIED` cố ý trộn context để **cô lập nhánh module của predicate**, không giả là một cặp class–module thực tế do JVM tạo. Các ca `SECOND_LOADER_DENIED`, `NAMED_MODULE_ALLOWED` và `UNNAMED_MODULE_DENIED` dựa vào **Class/Loader/Module objects thật**. Cả hai loại test đều hữu ích, nhưng phải được ghi nhãn rõ.

### 8.6. Lệnh biên dịch và chạy (Bash/macOS/Linux)

Từ `filter-lab`:

```shell
mkdir -p build/target build/main mods/demo.feature

# Biên dịch fixture chỉ vào thư mục target.
javac -d build/target src-target/sample/ProbeTarget.java

# Biên dịch named module độc lập.
javac -d mods/demo.feature \
  src-module/demo.feature/module-info.java \
  src-module/demo.feature/demo/feature/NamedTarget.java

# Harness không phụ thuộc compile-time vào hai fixture.
javac -d build/main src-main/FilterHarness.java

# Chỉ build/main nằm trên classpath.
# Fixture 1 nạp qua hai URLClassLoader riêng.
# Fixture 2 là named module đã resolve bằng --add-modules.
java --module-path mods --add-modules demo.feature \
  -cp build/main FilterHarness build/target
```

Với Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force build/target, build/main, mods/demo.feature | Out-Null
javac -d build/target src-target/sample/ProbeTarget.java
javac -d mods/demo.feature src-module/demo.feature/module-info.java src-module/demo.feature/demo/feature/NamedTarget.java
javac -d build/main src-main/FilterHarness.java
java --module-path mods --add-modules demo.feature -cp build/main FilterHarness build/target
```

Trong hai trường hợp, `build/target` **không** nằm trên `-cp`. Nếu bạn thêm nó vào classpath, loader parent có thể tìm được `sample.ProbeTarget` và cả hai `URLClassLoader` nhận cùng class, làm hỏng điều kiện thử hai defining loaders.

### 8.7. Stdout dự kiến

```text
PASS BASELINE_ALLOWED
PASS OVERLOAD_DENIED
PASS RETURN_DESCRIPTOR_DENIED
PASS METHOD_NAME_DENIED
PASS CONSTRUCTOR_DENIED
PASS CLASS_NAME_DENIED
PASS DOT_NAME_DENIED
PASS SECOND_LOADER_DENIED
PASS WRONG_MODULE_DENIED
PASS BOOTSTRAP_LOADER_DENIED
PASS NULL_CLASS_NAME_DENIED
PASS NULL_MODULE_DENIED
PASS ARRAY_DESCRIPTOR_ALLOWED
PASS ARRAY_DESCRIPTOR_DENIED
PASS NAMED_MODULE_ALLOWED
PASS UNNAMED_MODULE_DENIED
PASS NAMED_WRONG_MODULE_DENIED
ALL_TESTS_PASSED=17
```

Nếu `ALL_TESTS_PASSED` không bằng 17 hoặc có `AssertionError`, phải điều tra fixture/compiler/classpath/module path và predicate, **không** xóa test âm tính cho pass. Kết quả trên là **kỳ vọng đã suy ra từ source**; khi học trên máy, hãy chạy lệnh để xác nhận. Bài này không tuyên bố đã quan sát stdout trong môi trường của người đọc.

### 8.8. Vì sao đây là bài test, chưa phải Java agent hoàn chỉnh?

`FilterHarness` kiểm **quy tắc** và **metadata thật**. Nó không đăng ký `ClassFileTransformer` và không tạo probe bytes. Đó là lựa chọn để khoanh vùng lỗi: nếu bộ lọc sai, ta phát hiện trước khi phải debug `VerifyError`, module readability, class loading recursion hay bytecode frameworks.

Integration agent còn cần `premain`/`agentmain`, `Instrumentation.addTransformer`, việc parse class file đầu vào trong callback, sinh bytecode hợp lệ, kiểm tra retransformation capability khi áp lớp đã nạp và xác minh lời gọi method thật.

## 9. Nối bộ lọc vào ClassFileTransformer

Trong Java 9+ nên **override overload sáu tham số có `Module`**. Overload cũ năm tham số vẫn dùng được, nhưng nếu chỉ override bản đó rồi dựa vào context không truyền module, rất khó test đúng policy theo module trong callback.

### 9.1. Callback skeleton Java 17+ (chưa phải agent chạy độc lập)

```java
import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;

// Skeleton; thiếu policy/bytecode parser cụ thể.
final class FilteringTransformer implements ClassFileTransformer {
    private final ClassLoader approvedLoader;
    private final Module approvedModule;

    FilteringTransformer(ClassLoader approvedLoader, Module approvedModule) {
        this.approvedLoader = approvedLoader;
        this.approvedModule = approvedModule;
    }

    @Override
    public byte[] transform(
            Module module,
            ClassLoader loader,
            String className,
            Class<?> classBeingRedefined,
            ProtectionDomain domain,
            byte[] classfileBuffer) {

        if (!"sample/ProbeTarget".equals(className)) {
            return null;
        }
        if (loader != approvedLoader || module != approvedModule) {
            return null;
        }

        // Bước kế tiếp trong transformer THỰC:
        // 1. Parse classfileBuffer thành các method_info.
        // 2. Chỉ match name "execute" và descriptor "(I)V".
        // 3. Nếu không có target method, return null.
        // 4. Nếu có, dùng bytecode library sửa body hợp lệ.
        // 5. Return new class bytes; nếu không sửa, return null.
        return null; // Skeleton chỉ chứng minh class gate.
    }
}
```

**Không đưa đoạn skeleton vào production và báo đã instrument.** Nó luôn `return null`, không thay bytecode. Nó cũng giữ reference mạnh tới `approvedLoader`; nếu app có lifecycle redeploy, cần quản lý lifetime hoặc kiến trúc scope/weak identity an toàn. Phần này chỉ cho thấy **đúng nơi dùng bốn tiêu chí** khi triển khai thật.

### 9.2. ASM method visitor (minh họa, phụ thuộc ASM 9+)

Nếu ứng dụng đã có dependency ASM phù hợp, transformer có thể duyệt method descriptor:

```java
// Snippet minh họa dùng ASM; không biên dịch độc lập.
// import org.objectweb.asm.*; cần dependency ASM tương thích.
ClassReader reader = new ClassReader(classfileBuffer);

reader.accept(new ClassVisitor(Opcodes.ASM9) {
    @Override
    public MethodVisitor visitMethod(
            int access,
            String name,
            String descriptor,
            String signature,
            String[] exceptions) {

        boolean target =
                "execute".equals(name)
                && "(I)V".equals(descriptor);

        if (target) {
            // Kiểm ACC_NATIVE/ACC_ABSTRACT/ACC_BRIDGE/ACC_SYNTHETIC
            // tùy feature, rồi mới tạo MethodVisitor sửa bytecode.
        }
        return super.visitMethod(
                access, name, descriptor, signature, exceptions);
    }
}, 0);
```

**Điểm chính:** `descriptor` (tham số thứ ba của `visitMethod`) mới là JVM method descriptor. `signature` (tham số tiếp) là optional generic signature, có thể `null`. Không lấy `signature` làm điều kiện primary match cho method resolution.

Một transformer thật còn phải tạo `ClassWriter`/writer visitor chain, xử lý stack maps/frames, local variables, exception handlers, verifier compatibility, và chỉ trả bytes nếu có biến đổi. Nếu sử dụng `COMPUTE_FRAMES`, cần hiểu cách resolver của ASM tìm common superclass để tránh vô tình load classes/khác loader; đó là rủi ro riêng ngoài filter.

### 9.3. Java Class-File API theo phiên bản JDK

Java Class-File API chuẩn hóa trong JDK 24 (JEP 484). **Không** copy code `java.lang.classfile` JDK 24/25 vào chương trình Java 17 rồi tuyên bố runnable; Java 17–23 không có final API đó. Bài này dùng mã Java 17+ và chỉ mô tả việc thay parser bằng API phù hợp khi runtime/toolchain hỗ trợ.

Đừng sử dụng `jdk.internal.org.objectweb.asm` từ JDK như một dependency mặc định: đó là internal API, có rủi ro encapsulation/compatibility; dùng thư viện bytecode được quản lý/versioned hoặc API chuẩn tương ứng.

## 10. Kiểm thử bằng agent thật: ma trận dương tính và âm tính

Khi đã có transformer sinh code, cần chạy **một test matrix đầy đủ** chứ không chỉ tìm một dòng log `TRANSFORMED`.

| Ca thử | Class/internal name | Descriptor | Loader | Module | Kỳ vọng |
|---|---|---|---|---|---|
| Target chính xác | Target | `execute(I)V` | A | UA | **ALLOW** |
| Overload string | Target | `execute(Ljava/lang/String;)V` | A | UA | DENY |
| Đổi kiểu trả về | Target | `execute(I)I` | A | UA | DENY |
| Constructor | Target | `<init>()V` | A | UA | DENY nếu chỉ đo `execute` |
| Class gần tên | `sample/ProbeTargets` | `execute(I)V` | A | UA | DENY |
| Tên dạng dấu chấm | `sample.ProbeTarget` | `execute(I)V` | A | UA | DENY (sai format callback) |
| Cùng tên ở loader B | Target | `execute(I)V` | B | UB | DENY |
| Sai module | Target | `execute(I)V` | A | module khác | DENY (pure predicate) |
| Bootstrap null loader | Target | `execute(I)V` | null | bootstrap module | DENY |
| Tên lớp null | null | `execute(I)V` | A | UA | DENY |
| Module null | Target | `execute(I)V` | A | null | DENY |
| Array descriptor đúng | Target | `transform([I)[Ljava/lang/String;` | A | UA | ALLOW theo rule array riêng |
| Named target đúng | `demo/feature/NamedTarget` | `execute(I)V` | loader named | named module | ALLOW theo named rule riêng |
| Named/unnamed hoán đổi | Context named so với rule UA | `execute(I)V` | bất kỳ | module khác | DENY |
| Duplicate instrument | Target đã có probe marker | `execute(I)V` | A | UA | SKIP/IDEMPOTENT |
| Không tìm thấy method | Target chỉ còn signature khác | không có descriptor target | A | UA | SKIP |
| Class không modifiable | Target đã load, retransform không hỗ trợ | target | A | UA | SKIP_WITH_REASON |
| Bytecode parser lỗi | `classfileBuffer` hỏng | unknown | A | UA | FAIL/SKIP theo policy, không instrument bừa |

Trong bảng, UA và UB là unnamed modules **khác nhau** của loader A và B. Những hàng có kết hợp loader/module không thể do JVM thực tạo được dùng để kiểm **logic predicate**; integration tests phải dùng object context hợp lệ.

### 10.1. Test cả sự *vắng mặt* của instrumentation

Nếu mục tiêu chỉ instrument `execute(I)V`, hãy gọi:

- `execute(int)` trên class A: probe marker tăng đúng một lần mỗi invocation.
- `execute(String)` trên class A: marker không tăng.
- `execute(int)` trên class B: marker không tăng.
- Class cùng prefix nhưng khác internal name: marker không tăng.
- Method cùng tên trong named module khác: marker không tăng khi không nằm trong policy.

Kiểm output/behavior của method vẫn giống trước khi agent bật. Chỉ có log `SKIP` không đủ; cần đo **bytecode/effect không đổi** hoặc xác minh marker vắng mặt cho excluded cases. Nhưng đừng tạo hàng triệu log cho mọi excluded JDK class trong production.

### 10.2. Kiểm thử class đã load trước khi agent đăng ký

`addTransformer` chỉ áp cho những class definitions/lifecycle events liên quan theo hợp đồng; một class đã load trước khi agent đăng ký không tự chạy qua `transform` chỉ vì agent xuất hiện. Nếu muốn áp lại cho class đã load, cần kiểm:

```java
// Snippet trong agent, không phải file độc lập.
if (inst.isRetransformClassesSupported()
        && inst.isModifiableClass(targetClass)) {
    inst.retransformClasses(targetClass);
}
```

Đây là bước **retransformation**, có giới hạn class schema, ordering và canRetransform. Khi retransform, `classBeingRedefined` thường là đối tượng `Class<?>` đang được thay; khi load mới, nó là `null`. Test cả hai đường nếu feature tuyên bố hỗ trợ.

### 10.3. Đừng bỏ qua overload cũ khi override module overload

Trong `ClassFileTransformer`, implementation mặc định của overload sáu tham số gọi phiên bản năm tham số; nếu bạn chỉ override năm tham số, vẫn có callback nhưng mất khả năng dựa vào `Module` trực tiếp trong method đó. Ngược lại nếu bạn chỉ override sáu tham số theo Java 9+, JVM sẽ gọi đúng overload mới trong môi trường chuẩn. Unit test nên bắt lỗi adapter vô tình gọi overload không có module khi production policy yêu cầu module identity.

## 11. Đặt test fixtures theo ranh giới thực sự có giá trị

### 11.1. Một tên lớp, hai loaders khác nhau

**Bắt buộc** với agent chạy trong application server, servlet containers, plugin environments hoặc OSGi-like module boundaries. Không dùng hai biến trỏ tới **cùng URLClassLoader instance** rồi coi là hai loaders. Phải thật sự `new URLClassLoader(...)` hai lần và kiểm:

```java
classA != classB
classA.getName().equals(classB.getName())
classA.getClassLoader() != classB.getClassLoader()
```

Các biểu thức trên chỉ là đoạn biểu thức minh họa; trong `FilterHarness` ở phần 8 các đối tượng cụ thể được tạo và kiểm tra.

### 11.2. Một loader, nhiều named modules

Một class loader có thể liên quan tới nhiều modules, nhất là ở module layer/framework phức tạp. Vì vậy policy chỉ so loader không đủ. Nếu feature chỉ hợp lệ với module `foo`, test cùng loader nhưng class ở module khác để bảo đảm module guard hoạt động.

Với nhu cầu phân biệt **hai layers có module name giống nhau**, dựng hai `ModuleLayer` instances trong integration test và so Module identity. Một predicate chỉ dùng `module.getName()` sẽ match sai cả hai. Đây là edge case nên ưu tiên khi agent của bạn hỗ trợ dynamic plugin layers.

### 11.3. Loader bootstrap

Nếu policy không được phép chạm JDK classes, test `loader==null` cùng một internal name kiểu `java/lang/String`. Callback bootstrap thật có thể xuất hiện nếu JVM/agent cấu hình cho phép; helper phải khả kiến ở bootstrap khi cần. **Không** tạo policy `loader==null` như một wildcard cho “bất kỳ loader”.

### 11.4. Nested classes, arrays, generics và bridge

- Nested: `Outer$Inner` chứ không phải `Outer.Inner` trong binary name.
- Arrays: `[I`, `[Ljava/lang/String;` là type descriptors; chúng không phải những method-bearing class files có thể xử lý y hệt class bình thường.
- Generics: match **erased JVM descriptor**, không phải `Signature`.
- Bridge/synthetic: nếu instrument cả bridge và implementation có thể đo **hai lần** một lời gọi Java source vì bridge forward sang implementation. Test exact access flags để quyết định cố ý.
- Records: accessors, constructors và synthetic details phải được kiểm theo output classfile compiler thực tế.
- Interface methods/default methods: descriptor vẫn là JVM descriptor, nhưng cách chèn bytes/call paths khác class method thông thường.
- Lambdas/hidden classes: không dựa vào tên sinh tự động như một API ổn định; test policy theo quan sát thực và fallback an toàn.

## 12. Chẩn đoán không gây quá tải hệ thống

### 12.1. Log một quyết định gọn, có dấu vết đủ để tái hiện

Một bản ghi test mẫu:

```json
{
  "operation": "CLASS_FILTER",
  "classInternalName": "sample/ProbeTarget",
  "methodName": "execute",
  "descriptor": "(I)V",
  "loaderTag": "A",
  "moduleName": null,
  "moduleKind": "UNNAMED",
  "decision": "ALLOW",
  "reason": "EXACT_FOUR_DIMENSION_MATCH",
  "bytecodeChanged": false
}
```

**Đây là schema chẩn đoán minh họa**, không phải output tự động của Java agent. `loaderTag=A` là tag từ test fixture; trong production không dùng tag ngẫu nhiên làm căn cứ cấp quyền. `bytecodeChanged=false` phù hợp với predicate harness: nó chỉ quyết định, chưa sinh probe.

### 12.2. Kết nối lời gọi với hiệu ứng

Một report kiểm thử nên có:

```text
targetCount=1
matchedMethodCount=1
transformedClassCount=1
verifiedProbeCallCount=1
unexpectedTransformCount=0
wrongLoaderMatchCount=0
wrongModuleMatchCount=0
verifyErrorCount=0
```

Đây là **mẫu tiêu chí** cho một test có một target, không phải con số mặc định của mọi application. Nếu mục tiêu chưa được load/call, `verifiedProbeCallCount=0` có thể hoàn toàn đúng; không giả báo test pass chỉ dựa trên matcher.

### 12.3. Tránh log nhãn động không giới hạn

Một agent thấy hàng chục nghìn class names và loader identities. Không đưa mọi `className`, `descriptor`, full classloader `toString` hay protection domain URL vào metric labels: có thể tạo cardinality cao, tăng memory/CPU và lộ deployment paths.

Nên dùng reason codes hữu hạn, sampling và debug logging có thời hạn. Khi cần chẩn đoán chi tiết, lưu tên class/loader/module theo policy có giới hạn, không serialize `ClassLoader` hoặc `ProtectionDomain` thành object graph.

### 12.4. Những exception cần phân loại

| Triệu chứng | Bước phân tích |
|---|---|
| Target không bao giờ match | Kiểm dạng internal name, method descriptor, loader/module identity |
| Target match nhiều lần | Kiểm retransform, nhiều transformers, probe idempotency |
| `ClassNotFoundException` từ helper | Có thể helper không khả kiến, không phải rule filter |
| `NoClassDefFoundError` khi gọi probe | Linkage/helper class loader/module readability, kiểm cài bytecode |
| `ClassCastException: X cannot be cast to X` | Có thể cùng tên nhưng hai defining loaders |
| `IllegalAccessError` | Module/loader/package runtime access không phù hợp |
| `VerifyError` | Bytecode frames/stack/locals sai sau transform |
| `ClassFormatError` | Class bytes cuối không hợp lệ |
| `UnsupportedOperationException` trong retransform | Capability/schema limitation |
| Probe vào overload sai | Dùng method name nhưng bỏ descriptor |
| Probe vào app ở plugin khác | Dùng class name nhưng bỏ loader/module identity |
| No probe dù filter allow | Bytecode transform trả `null`, class chưa load hoặc method chưa invoke |

## 13. Tránh lỗi do concurrent instrumentation hoặc redeploy

Bộ lọc được gọi bởi JVM trong những hoàn cảnh khác nhau, có thể trên nhiều threads khi class loading diễn ra đồng thời. Một policy tốt là **immutable** sau khi tạo, hoặc dùng cơ chế cập nhật cấu hình có memory visibility rõ ràng.

- Không dùng `HashMap` mutable không đồng bộ cho runtime allowlist bị ghi từ thread khác.
- Không dùng `loader.getName()` thay cho loader identity, kể cả trong cache.
- Không giữ strong references tới application classloaders trong cache agent suốt JVM nếu classloaders phải được giải phóng khi redeploy.
- Không gọi `Class.forName` từ transformer để xác định method signature, tránh class-loading recursion.
- Không phản chiếu vào target class đang trong quá trình define; parse `classfileBuffer`.
- Không giữ nguyên `classfileBuffer` của mọi class trong static list để debug; bytecode histories có thể rất lớn.
- Với nhiều transformer instances, test thứ tự biến đổi và loại bỏ một plugin không làm filter của plugin khác vô tình đổi phạm vi.
- Nếu policy được reload runtime, cần test cả cấu hình cũ, mới, và thời điểm preflight trước retransform.
- Với hidden/generated classes, chỉ instrument khi thông tin chính xác đã được xác minh và agent có mục đích cụ thể.

**Tính nguyên tử của filter:** Predicate với năm trường trong một immutable record/rule giúp tránh một request thấy kết hợp name rule mới nhưng loader rule cũ. Nếu cập nhật policy, có thể công bố **một Rule/RuleSet immutable mới** bằng volatile reference; không thay từng map/set rời rạc không đồng bộ.

## 14. Những sai lầm thường gặp

1. **So `"com.acme.Foo"` với callback `className`.** Sai định dạng; callback dùng `com/acme/Foo`.
2. **Filter chỉ bằng package prefix không có dấu `/` cuối.** Có thể match package gần tên.
3. **Chỉ so method name.** Có thể instrument nhầm overload.
4. **Dùng generic `Signature` thay cho `descriptor`.** Sai đối với erased JVM method types.
5. **Bỏ return type khỏi descriptor.** Không còn đối chiếu descriptor đầy đủ.
6. **So class loader theo `getClass().getName()`.** Nhiều instances của cùng loader class có thể định nghĩa cùng binary name.
7. **Coi null loader là system loader.** Callback null đại diện bootstrap.
8. **Chỉ so tên module.** Không phân biệt nhiều layers/module objects cùng tên.
9. **Coi unnamed module là null.** Unnamed cũng là `Module` object; chỉ `getName()` trả null.
10. **Dùng `Class.forName` trong `transform` để tìm metadata.** Có thể gây recursive loading/deadlock và target chưa define.
11. **Dùng `classBeingRedefined` trong load-time callback mà không null-check.** Ở lượt load thường null.
12. **Không có negative tests.** Happy path pass không chứng minh không instrument nhầm.
13. **Tin `transform` trả bytes nghĩa là probe chạy.** JVM còn phải chấp nhận class và method phải được invoke.
14. **Cho phép khi thiếu module/descriptor.** Không fail-closed.
15. **Giữ ClassLoader strong reference vô thời hạn trong agent.** Có thể gây retention/class unloading leak.
16. **Log toàn bộ class names ở mọi callback.** Có thể gây overhead/cardinality rất lớn.
17. **Dùng `getMethods()` trên reflection trong transform path.** Không phù hợp với class chưa load và có thể bỏ sót private/declaration semantics.
18. **Bỏ qua access flags bridge/synthetic/constructor.** Có thể instrument hai lần hoặc sai bytecode.
19. **Kiểm loader bằng cách gọi `child.loadClass` mà không xem defining loader.** Parent delegation có thể trả parent-defined class.
20. **Tưởng JDK 17 có Java Class-File API chuẩn.** API chuẩn được giới thiệu ở JDK 24; Java 17 cần library/reader khác.
21. **Không kiểm tra idempotency khi retransform.** Có thể tạo nhiều layers probe hoặc cùng method bị đo hai lần.
22. **Sửa format/source cells chỉ để xem kết quả dễ hơn.** Với một nhiệm vụ điền nội dung, chỉ thao tác chính xác vùng đích được giao.
23. **Nhầm module visibility với filter.** Policy match đúng nhưng helper chưa chắc link được qua JPMS/loader boundary.
24. **Dùng regex tổng quát để match mọi class thay vì policy đã phê duyệt.** Có thể chạm framework/JDK/plugin không thuộc phạm vi.

## 15. Checklist QA trước khi bật agent

### Filter definition

- [ ] Tên class trong cấu hình đã được chuẩn hóa sang internal form và kiểm exact/prefix boundary?
- [ ] Rule có tên method và **full descriptor**?
- [ ] Đã xác định bootstrap policy khi `loader==null`?
- [ ] Khi cần loader-specific scope, so đúng `ClassLoader` instance và không pin loader vô hạn?
- [ ] Khi cần module-specific scope, so đúng `Module` object, xử lý named/unnamed?
- [ ] Missing class name/module/descriptor được deny có reason?
- [ ] Constructor/initializer, bridge/synthetic được xử lý có chủ đích?

### Unit tests

- [ ] Happy path một class+method chính xác.
- [ ] Overloads cùng tên nhưng khác argument descriptors.
- [ ] Sai return descriptor.
- [ ] Sai binary/internal name format và prefix gần tên.
- [ ] Hai distinct defining loaders cho cùng binary name.
- [ ] Named module, unnamed module và Module identity khác nhau.
- [ ] Bootstrap null loader/unknown inputs.
- [ ] Methods có arrays, objects, generics erasure.
- [ ] Classfile fixture parser đọc đúng `method_info`, không dùng reflection để thay thế bytes của class chưa define.

### Integration tests

- [ ] Java agent đăng ký callback đúng với `Module` param.
- [ ] Chỉ class+method allow được sửa; test cả absence của marker.
- [ ] Probe vẫn giữ nguyên business behavior/return/exception.
- [ ] Class load mới và retransform (nếu có) đều được kiểm.
- [ ] Bytecode hợp lệ theo verifier JVM thực, không có `VerifyError`/`LinkageError`.
- [ ] Không instrument helper/dependencies của agent gây recursion.
- [ ] Classloader unload/redeploy không tạo stale policy hoặc memory leak.
- [ ] Log lý do từ chối có giới hạn, không chứa user data nhạy cảm.

## 16. Câu hỏi tự kiểm tra

1. **Callback `ClassFileTransformer` đưa tên `java.lang.String` theo dạng nào?** `java/lang/String`.
2. **Vì sao `className` không đủ để định danh duy nhất class?** Hai defining loaders có thể định nghĩa cùng binary name.
3. **Descriptor của `void execute(int)` là gì?** `(I)V`.
4. **Descriptor của `void execute(String)` là gì?** `(Ljava/lang/String;)V`.
5. **Descriptor của `String[] transform(int[])` là gì?** `([I)[Ljava/lang/String;`.
6. **Generic `List<String>` có hiện trực tiếp trong method descriptor không?** Không; descriptor dùng erased class type.
7. **`loader==null` trong callback có nghĩa gì?** Bootstrap loader, không phải wildcard hoặc system loader.
8. **Tên class loader khác nhau có chứng minh Class identity khác không?** Không; phải xác định defining loader object.
9. **Hai URLClassLoader khác nhau nạp cùng file class có thể tạo hai Class objects khác nhau không?** Có, nếu mỗi loader tự định nghĩa và không delegate target lên parent.
10. **`Module.getName()==null` có nghĩa module argument null không?** Không, đó có thể là unnamed Module object.
11. **So `module.getName()` có đủ khi có nhiều module layers không?** Không, dùng Module identity khi scope đòi hỏi.
12. **Method descriptor lấy từ tham số nào của callback class-level?** Không có tham số trực tiếp; phải parse `classfileBuffer`.
13. **Vì sao không dùng `Class.forName` ngay trong transformer để kiểm method?** Có thể kích hoạt reentrant class loading và target chưa được define.
14. **`classBeingRedefined` khi load class mới thường là gì?** `null`.
15. **Predicate pass nhưng transformer trả `null`: class có bị sửa không?** Không bởi bước transformer đó.
16. **Một method bị instrument nhưng chưa bao giờ được gọi: probe effect đã chứng minh chưa?** Chưa; cần kiểm tác dụng khi invoke.
17. **Vì sao cần test overload phủ định?** Để bảo đảm không instrument nhầm các signatures cùng tên.
18. **Vì sao cần test cả lớp có cùng tên ở loader B?** Để chứng minh boundary loader-specific đúng.
19. **Dùng `isNamed()` thay identity module được không?** Không; nó chỉ cho biết named/unnamed.
20. **Nếu thiếu module info trong pure test thì nên làm gì?** Deny theo chính sách fail-closed và báo `SKIP_UNKNOWN_CONTEXT`.
21. **Nếu classloaders cần được unload, giữ mạnh approvedLoader trong singleton agent có rủi ro gì?** Classloader retention; phải quản lý lifecycle.
22. **Trong demo `ALL_TESTS_PASSED=17` chứng minh điều gì?** Chỉ chứng minh các predicate/metadata/loader/module test được viết đã pass; chưa chứng minh bytecode probe đã được chèn.
23. **Một package-prefix rule `"com/acme/pay"` có thể match nhầm gì?** `com/acme/payment` hoặc package/class khác cùng prefix.
24. **Khi module đúng mà helper không load được, có nên nới filter không?** Không; phải giải quyết class-loader visibility/linkage riêng.

## 17. Tài liệu tham khảo chính thức

- [Java SE 21 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): callback `transform(Module,ClassLoader,String,Class<?>,ProtectionDomain,byte[])`, internal class name, defining loader, `classBeingRedefined` và nguyên tắc trả `null`.
- [Java SE 17 — `ClassFileTransformer`](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html): hợp đồng tương thích với ví dụ Java 17+.
- [Java SE 21 — `Instrumentation`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/Instrumentation.html): `addTransformer`, `retransformClasses`, `isModifiableClass`, capability và thứ tự biến đổi.
- [Java SE 21 — `ClassLoader`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): defining loaders, parent delegation, unnamed module cho từng loader.
- [Java SE 21 — `Module`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html): named/unnamed, `getName`, `getLayer` và runtime module identity.
- [Java SE 21 — `Class`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): `getName`, `getModule`, `getClassLoader`, `Class.forName(Module,String)`.
- [Java SE 21 — `MethodType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodType.html): `toMethodDescriptorString` và JVM descriptor.
- [JVMS SE 21 — `4.3 Descriptors`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.3): type descriptors và method descriptor grammar.
- [JVMS SE 21 — `4.6 Methods`](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.6): `method_info`, `name_index`, `descriptor_index` và method access flags.
- [Java SE 21 — `java.lang.instrument`](https://docs.oracle.com/en/java/javase/21/docs/api/java.instrument/java/lang/instrument/package-summary.html): agent startup, class transformations và JPMS read edges.
- [JEP 484 — Class-File API](https://openjdk.org/jeps/484): Java Class-File API chuẩn hóa trong JDK 24 (không phải Java 17).

**Kết luận:** Kiểm thử bộ lọc Instrumentation là **kiểm thử đúng lớp, đúng method signature, đúng class loader và đúng module**, không chỉ một phép `startsWith` trên tên class. Dùng **internal class name**, **full JVM descriptor**, **identity `ClassLoader`/`Module`**, ca kiểm thử âm tính và kiểm thử hiệu ứng probe sau biến đổi. Khi một tiêu chí không xác minh được, **deny có báo cáo** an toàn hơn instrument theo suy đoán.