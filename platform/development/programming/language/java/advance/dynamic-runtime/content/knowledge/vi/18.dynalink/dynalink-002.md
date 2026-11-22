# 18.2. Mô tả Operation, namespace, tên thao tác và CallSiteDescriptor

> **Module:** Java Advance – dynamic-runtime, nhóm **18. Dynalink**, Java SE 21. Trong `jdk.dynalink`, một biểu thức động như `obj.name`, `obj[key]` hoặc `obj.method(x)` được mô tả bằng **ý định thao tác** (`Operation`), **không gian địa chỉ** (`Namespace`), **tên/index có thể được ràng buộc sẵn** (`NamedOperation`) và **chữ ký + quyền liên kết của call site** (`CallSiteDescriptor`). Các đối tượng này là *metadata*, không phải mã thực thi. Chỉ khi có linker và một relinkable call site, chúng mới tham gia tạo và gọi `MethodHandle`.

## 1. Mục tiêu và phạm vi

Sau bài này, bạn có thể:

1. Phân biệt `Operation`, `StandardOperation`, `Namespace`, `StandardNamespace`, `NamespaceOperation`, `NamedOperation` và `CallSiteDescriptor`.
2. Nhận diện năm thao tác chuẩn `GET`, `SET`, `REMOVE`, `CALL`, `NEW`; biết khi nào chúng cần namespace.
3. Hiểu `PROPERTY`, `ELEMENT`, `METHOD` và giải thích vì sao thứ tự namespace tạo ngữ nghĩa khác nhau.
4. Tạo operation bằng `withNamespace`, `withNamespaces`, `named`; dùng `NamedOperation.getName` và các helpers để bóc tách.
5. Suy ra số lượng arguments và return type của `GET/SET/REMOVE` khi địa chỉ là dynamic hoặc named, và của `CALL/NEW` khi được gắn nhãn.
6. Tạo `CallSiteDescriptor(lookup, operation, methodType)`; giải thích trách nhiệm riêng của từng tham số và hai phương thức `changeOperation`/`changeMethodType`.
7. Phân biệt equality của metadata với khả năng liên kết/khả năng truy cập runtime.
8. Tạo và chạy `DynamicLinker`, `BeansLinker` và `SimpleRelinkableCallSite` để kiểm nghiệm một operation thực.
9. Nhận diện lỗi nesting, null, wrong MethodType, quyền `Lookup`, module dependency và lỗi thiếu linker.
10. Biên dịch/chạy năm chương trình độc lập sử dụng API chuẩn Java 21.

**Chuẩn bị:** `MethodHandle`, `MethodType`, `MethodHandles.Lookup`, `invokedynamic` ở mức ý tưởng; JavaBeans, Map/List, class loader/module. Không cần compiler tạo bytecode mới, ASM, Nashorn hay API nội bộ.

## 2. Bức tranh tổng thể: metadata rồi mới linking

Dynalink hỗ trợ những ngôn ngữ/DSL có expression chỉ biết receiver type khi chạy. Bộ mô tả chứa các câu trả lời: “muốn làm gì?”, “truy cập miền dữ liệu nào?”, “key cố định hay được truyền lúc chạy?”, “lời gọi nhận/trả kiểu gì?” và “caller có quyền gì?”.

```text
Ngữ nghĩa DSL: obj.title
        |
        v
Operation: GET + PROPERTY + name "title"
        |
        +--> CallSiteDescriptor
        |    ├── Lookup: caller access context
        |    ├── Operation: GET:PROPERTY:title
        |    └── MethodType: (Object)Object
        |
        v
RelinkableCallSite (SimpleRelinkableCallSite)
        |
        v
DynamicLinker (BeansLinker và/hoặc custom linker)
        |
        v
GuardedInvocation / target MethodHandle
        |
        v
dynamicInvoker() và relink khi cần
```

`Operation` không phải `MethodHandle`. `CallSiteDescriptor` cũng không phải `java.lang.invoke.CallSite`. Chúng không tự đọc property hay gọi Java method. `DynamicLinker` tìm implementation phù hợp trong các `GuardingDynamicLinker`; `RelinkableCallSite` giữ target để các lời gọi chạy qua.

Một linker có thể kết hợp guard theo receiver class, overload resolution, conversion và switchpoint invalidation; cùng descriptor có thể liên kết các targets khác nhau cho các receiver khác nhau. Vì vậy **metadata equality không đồng nghĩa target identity**.

## 3. StandardOperation: năm thao tác chuẩn

`StandardOperation` là enum triển khai `Operation`. Java 21 có đúng năm giá trị `GET`, `SET`, `REMOVE`, `CALL`, `NEW`.

| Operation | Nhiệm vụ | Dạng chữ ký thông thường |
| --- | --- | --- |
| `GET` | Đọc giá trị từ namespace của receiver | `(receiver,name)→value` hoặc named `(receiver)→value` |
| `SET` | Ghi giá trị vào namespace | `(receiver,name,value)→void` hoặc named `(receiver,value)→void` |
| `REMOVE` | Xóa giá trị tại một địa chỉ trong namespace | `(receiver,name)→void` hoặc named `(receiver)→void` |
| `CALL` | Gọi callable object | `(callable,receiver,arguments...)→value` |
| `NEW` | Gọi constructor object | `(constructor,arguments...)→value` |

Theo Javadoc Java 21, `GET`, `SET` và `REMOVE` **phải được kết hợp với ít nhất một NamespaceOperation** để có ngữ nghĩa chuẩn. `CALL` và `NEW` hoạt động độc lập; chúng vẫn có thể được gắn tên qua `NamedOperation` để ghi nhãn chẩn đoán.

`receiver`, `name`, `value`, `callable` là các **vai trò** tham số, không phải kiểu Java cố định. `MethodType` thực tế có thể dùng `Object`, `Map`, `int`, `String` v.v. tùy frontend và khả năng adapter/linker. Chữ ký `CALL` có **callable trước receiver**; không đảo thành receiver trước chỉ vì một Java instance method bình thường thường nhận receiver đầu tiên. Với callable không có khái niệm receiver, linker có thể bỏ qua tham số đó. `NEW` nhận constructor object và các tham số, không có receiver tách riêng.

### 3.1. GET METHOD khác CALL

Một expression `obj.run(x)` có thể được chia thành `GET:METHOD:run` để lấy callable, rồi `CALL` để gọi với receiver và đối số `x`. `GET:METHOD` không đồng nghĩa đã gọi method. Đây là quyết định modeling của ngôn ngữ/runtime: có thể tối ưu theo cách khác, nhưng phải giữ semantic contract.

### 3.2. Tạo operation bằng các factory

```java
// Đoạn minh họa trong class đã import jdk.dynalink.*.
Operation getProperty = StandardOperation.GET
        .withNamespace(StandardNamespace.PROPERTY);
Operation getElement = StandardOperation.GET
        .withNamespace(StandardNamespace.ELEMENT);
Operation setProperty = StandardOperation.SET
        .withNamespace(StandardNamespace.PROPERTY);
Operation removeElement = StandardOperation.REMOVE
        .withNamespace(StandardNamespace.ELEMENT);
Operation call = StandardOperation.CALL;
Operation create = StandardOperation.NEW;
```

Factory trả operation descriptions, chưa chạy tìm getter, map entry hoặc constructor. Nếu receiver không hỗ trợ operation, linker có thể thất bại ở giai đoạn link/invoke.

## 4. Namespace: PROPERTY, ELEMENT, METHOD

`Namespace` là giao diện mô tả **không gian địa chỉ**, `StandardNamespace` có `PROPERTY`, `ELEMENT` và `METHOD`.

| Namespace | Theo `BeansLinker` cho Java object | Ví dụ |
| --- | --- | --- |
| `PROPERTY` | Public getter/setter kiểu bean, record component accessor, public field, một số virtual properties | `obj.name` |
| `ELEMENT` | Phần tử array/list, entry Map theo index/key | `obj[key]` |
| `METHOD` | Lấy đối tượng callable đại diện cho một method, sau đó có thể CALL | `obj.work` |

Đây là các namespace **theo linker**, không phải một tuyên bố JVM rằng Java object luôn có ba vùng bộ nhớ vật lý. Một language-specific linker có thể có custom namespace; `BeansLinker` định nghĩa semantics cho JavaBeans/arrays/lists/maps.

### 4.1. NamespaceOperation mang thứ tự ưu tiên

```java
Operation propertyFirst = StandardOperation.GET.withNamespaces(
        StandardNamespace.PROPERTY, StandardNamespace.ELEMENT);
Operation elementFirst = StandardOperation.GET.withNamespaces(
        StandardNamespace.ELEMENT, StandardNamespace.PROPERTY);
```

`NamespaceOperation` yêu cầu **ít nhất một namespace**, lưu **theo đúng thứ tự**. Khi có nhiều namespace, chúng là các lựa chọn thay thế **theo thứ tự first applicable**, không phải set không có thứ tự. `getNamespace(0)` là ưu tiên thứ nhất; `getNamespaceCount()` trả số; `contains()` kiểm tra thành viên. `getNamespaces()` trả một **defensive copy**.

**First applicable không đồng nghĩa first non-null.** Linker quyết định một property/key có áp dụng cho receiver hay không. Nếu một entry tồn tại nhưng value là null, không được tự suy “thử tiếp namespace khác” mà không có hợp đồng cụ thể.

### 4.2. Ví dụ khác biệt thực

Với Map có key `"empty"` và value `"map-value"`, bản thân Map không rỗng nên `isEmpty()` trả `false`. `BeansLinker` cho phép đọc property `empty` qua Java getter `isEmpty()`, và element `empty` qua Map key.

```text
GET:PROPERTY|ELEMENT:empty  -> false
GET:ELEMENT|PROPERTY:empty  -> "map-value"
```

Lab 5 sẽ dùng **cùng receiver** và **cùng MethodType** nhưng đổi thứ tự namespace; đây là khác biệt ngữ nghĩa thật, không chỉ thay chuỗi `toString()`.

## 5. NamedOperation: tên/địa chỉ được ràng buộc sẵn

`NamedOperation` kết hợp base operation và một `Object name` không null. Địa chỉ có thể là String property name hoặc Integer index; API không giới hạn name thành String.

```java
Operation namedProperty = StandardOperation.GET
        .withNamespace(StandardNamespace.PROPERTY).named("title");
Operation namedIndex = StandardOperation.GET
        .withNamespace(StandardNamespace.ELEMENT).named(2);
Operation namedCall = StandardOperation.CALL.named("service.execute");
```

Với `GET/SET/REMOVE`, ràng buộc name/index trong metadata làm **mất một đối số name** trong expected call-site signature. Với `CALL/NEW`, name chỉ là **nhãn chẩn đoán** và không xóa tham số nào, vì CALL/NEW vốn không có tham số name riêng.

### 5.1. Cấu trúc wrapper

```text
NamedOperation
├── name: "title"
└── baseOperation: NamespaceOperation
    ├── baseOperation: StandardOperation.GET
    └── namespaces: [PROPERTY, ELEMENT]
```

Dùng factory theo thứ tự `StandardOperation → withNamespace(s) → named`:

```java
Operation op = StandardOperation.GET
        .withNamespaces(StandardNamespace.PROPERTY, StandardNamespace.ELEMENT)
        .named("title");
```

Không tự lồng `NamespaceOperation` lên base đã là `NamedOperation` hoặc `NamespaceOperation`, cũng không lồng `NamedOperation` lên một `NamedOperation` khác: constructors từ chối cấu trúc đó. Metadata có thể hợp lệ về mặt Java object nhưng không phù hợp chuẩn operation (ví dụ bare `GET` không namespace); linker vẫn cần semantic validation.

### 5.2. Bóc tách operation đúng thứ tự

```java
// Trong scope có Operation op.
Object name = NamedOperation.getName(op);
Operation withoutName = NamedOperation.getBaseOperation(op);
jdk.dynalink.Namespace[] namespaces =
        NamespaceOperation.getNamespaces(withoutName);
Operation root = NamespaceOperation.getBaseOperation(withoutName);
```

`NamedOperation.getName` trả null khi outer object không phải NamedOperation; không dùng `(String)` cast mặc định vì name có thể là Integer. `NamedOperation.getBaseOperation` bóc outer wrapper nếu có. `NamespaceOperation.getBaseOperation` chỉ bóc namespace wrapper nó nhận, **không tự đi xuyên qua NamedOperation**. Do đó tách name trước rồi tách namespace.

Hai operations có cùng base/name và namespace ordering so `equals` bằng nhau. Đảo namespace order sẽ khác. Dùng `equals` cho structural comparison, không dựa vào object identity của wrappers được tạo mới.

## 6. Lab 1 — mô tả, phân rã và so sánh Operation

Tạo file **`OperationAnatomyLab.java`**:

```java
import jdk.dynalink.NamedOperation;
import jdk.dynalink.NamespaceOperation;
import jdk.dynalink.Operation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;

public class OperationAnatomyLab {
    public static void main(String[] args) {
        Operation unbound = StandardOperation.GET
                .withNamespaces(StandardNamespace.PROPERTY, StandardNamespace.ELEMENT);
        Operation named = unbound.named("size");
        Operation inner = NamedOperation.getBaseOperation(named);
        Operation root = NamespaceOperation.getBaseOperation(inner);
        System.out.println("unbound=" + unbound);
        System.out.println("named=" + named);
        System.out.println("name=" + NamedOperation.getName(named));
        System.out.println("root=" + root);
        System.out.println("namespaceCount=" + NamespaceOperation.getNamespaces(inner).length);
        System.out.println("firstNamespace=" + NamespaceOperation.getNamespaces(inner)[0]);
        System.out.println("hasProperty=" + NamespaceOperation.contains(
                inner, StandardOperation.GET, StandardNamespace.PROPERTY));
        System.out.println("namedEquals=" + named.equals(
                StandardOperation.GET.withNamespaces(
                        StandardNamespace.PROPERTY, StandardNamespace.ELEMENT).named("size")));
        System.out.println("orderMatters=" + !named.equals(
                StandardOperation.GET.withNamespaces(
                        StandardNamespace.ELEMENT, StandardNamespace.PROPERTY).named("size")));
        System.out.println("indexName=" +
                StandardOperation.GET.withNamespace(StandardNamespace.ELEMENT).named(2));
        System.out.println("callName=" + StandardOperation.CALL.named("compute()"));
        System.out.println("plainName=" + NamedOperation.getName(unbound));
    }
}
```

```sh
javac --release 21 --add-modules jdk.dynalink -Xlint:all OperationAnatomyLab.java
java --add-modules jdk.dynalink OperationAnatomyLab
```

**Stdout đã kiểm chứng:**

```text
unbound=GET:PROPERTY|ELEMENT
named=GET:PROPERTY|ELEMENT:size
name=size
root=GET
namespaceCount=2
firstNamespace=PROPERTY
hasProperty=true
namedEquals=true
orderMatters=true
indexName=GET:ELEMENT:2
callName=CALL:compute()
plainName=null
```

**Giải thích:** `unbound` không ràng buộc name nên GET có thể đòi key runtime. `named` gắn `"size"` ở metadata. Sau khi bóc outer named và inner namespace, root là enum `GET`. `indexName` chứng minh index có thể là Integer. `callName` là nhãn diagnostic cho CALL, không phải phương thức đã được gọi. `plainName=null` vì `unbound` không phải NamedOperation.

## 7. CallSiteDescriptor gồm Lookup, Operation và MethodType

`CallSiteDescriptor` là mô tả một dynamic call site, không phải bản thân call site. Constructor Java 21:

```java
// Mảnh mã minh họa trong scope với import jdk.dynalink.* và java.lang.invoke.*.
CallSiteDescriptor descriptor = new CallSiteDescriptor(
        MethodHandles.lookup(),
        StandardOperation.GET.withNamespace(StandardNamespace.PROPERTY).named("name"),
        MethodType.methodType(Object.class, Object.class));
```

Ba thành phần:

| Thành phần | API | Câu hỏi nó trả lời |
| --- | --- | --- |
| `Lookup` | `getLookup()` | Caller là ai và đang có những access modes nào? |
| `Operation` | `getOperation()` | Muốn GET/SET/REMOVE/CALL/NEW trên namespace, name gì? |
| `MethodType` | `getMethodType()` | Call-site arguments và return type chính xác là gì? |

`MethodType.methodType(returnType, parameterTypes...)` nhận return type **trước**; `toString()` thường in `(parameters)returnType`. `(Object)Object` trong ví dụ là **một receiver → một result** vì `name` đã được gắn vào operation.

**Không lấy `getMethodType()` làm bằng chứng runtime target đã tồn tại.** Descriptor mô tả yêu cầu linkage. Có thể tạo descriptor có chữ ký không phù hợp với operation và chỉ phát hiện khi linker xử lý hoặc invocation; người viết compiler/DSL phải kiểm tra tính hợp lý.

### 7.1. Lookup và quyền truy cập

`MethodHandles.Lookup` có `lookupClass()`, `lookupModes()` và ngữ cảnh class loader/module. Nếu descriptor được tạo trong `invokedynamic` bootstrap method, dùng **lookup do JVM chuyển vào** để giữ đúng quyền caller. Thay bừa bằng `publicLookup()` có thể làm mất quyền tìm private/package members hoặc gặp giới hạn visibility/class loading.

Đừng biến operation name thành một cơ chế bypass Java access control. `GET:PROPERTY:secret` chỉ nói linker “hãy thử đọc”; liệu được hay không còn phụ thuộc Lookup, receiver, quyền module, linker policy và member thực tế.

## 8. Thay metadata mà không tự thay call site

`CallSiteDescriptor` có hai cách sinh descriptor mới:

- `changeOperation(newOperation)`: **chỉ thay operation**, giữ lookup và method type.
- `changeMethodType(newType)`: **chỉ thay method type**, giữ lookup và operation.

```java
// Mảnh mã minh họa; giả sử descriptor gốc là GET:PROPERTY:name, (Object)Object.
CallSiteDescriptor anotherOp = descriptor.changeOperation(
        StandardOperation.GET.withNamespace(StandardNamespace.ELEMENT).named("name"));
CallSiteDescriptor anotherType = descriptor.changeMethodType(
        MethodType.methodType(String.class, Object.class));
```

Các method này **không** sửa descriptor cũ, không gọi `DynamicLinker.link`, không tự đổi target `MethodHandle` và cũng không thực hiện bất kỳ property access nào. Nếu đổi từ named sang unnamed operation, method type không tự chèn thêm name parameter.

```text
Ban đầu:
  Operation  = GET:PROPERTY:name
  MethodType = (Object)Object

Chỉ gọi changeOperation(GET:PROPERTY):
  Operation  = GET:PROPERTY
  MethodType = (Object)Object      <-- vẫn thiếu name argument

Để biểu diễn GET dynamic name:
  Operation  = GET:PROPERTY
  MethodType = (Object,Object)Object
```

### 8.1. Equality của CallSiteDescriptor

Javadoc mô tả equality theo **exact descriptor class**, operation, method type, và `Lookup.lookupClass()` + `Lookup.lookupModes()`. Hai descriptors dựng riêng vẫn có thể bằng nhau nếu các thuộc tính ấy tương đương. Tuy nhiên equality của description không chứng minh hai receiver objects, target handles hay guards là một; đó là chuyện của runtime linking.

## 9. Lab 2 — xây, thay Operation và MethodType

Tạo **`DescriptorMetadataLab.java`**:

```java
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import jdk.dynalink.CallSiteDescriptor;
import jdk.dynalink.Operation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;

public class DescriptorMetadataLab {
    public static void main(String[] args) {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        Operation op = StandardOperation.GET
                .withNamespace(StandardNamespace.PROPERTY).named("name");
        MethodType type = MethodType.methodType(Object.class, Object.class);
        CallSiteDescriptor desc = new CallSiteDescriptor(lookup, op, type);
        CallSiteDescriptor otherType =
                desc.changeMethodType(MethodType.methodType(String.class, Object.class));
        CallSiteDescriptor otherOp = desc.changeOperation(StandardOperation.GET
                .withNamespace(StandardNamespace.ELEMENT).named("name"));
        CallSiteDescriptor reconstructed = new CallSiteDescriptor(lookup, op, type);
        System.out.println("operation=" + desc.getOperation());
        System.out.println("type=" + desc.getMethodType());
        System.out.println("lookupClass=" + desc.getLookup().lookupClass().getSimpleName());
        System.out.println("changedType=" + otherType.getMethodType());
        System.out.println("keepsOp=" + otherType.getOperation().equals(op));
        System.out.println("changedOp=" + otherOp.getOperation());
        System.out.println("keepsType=" + otherOp.getMethodType().equals(type));
        System.out.println("valueEquals=" + desc.equals(reconstructed));
        System.out.println("originalStill=" + desc.getMethodType());
        System.out.println("sameLookupClass=" +
                (otherOp.getLookup().lookupClass() == desc.getLookup().lookupClass()));
    }
}
```

```sh
javac --release 21 --add-modules jdk.dynalink -Xlint:all DescriptorMetadataLab.java
java --add-modules jdk.dynalink DescriptorMetadataLab
```

**Stdout:**

```text
operation=GET:PROPERTY:name
type=(Object)Object
lookupClass=DescriptorMetadataLab
changedType=(Object)String
keepsOp=true
changedOp=GET:ELEMENT:name
keepsType=true
valueEquals=true
originalStill=(Object)Object
sameLookupClass=true
```

**Phân tích:** `changeMethodType` đổi return type thành String nhưng giữ operation. `changeOperation` đổi PROPERTY sang ELEMENT nhưng giữ type. `valueEquals=true` vì hai descriptors có cùng ba thành phần và lookup context. `originalStill` khẳng định descriptor cũ không bị thay đổi.

## 10. Suy ra các chữ ký GET/SET/REMOVE/CALL/NEW

Một linker cần MethodType đúng với role arguments; đặc biệt named operation tác động khác nhau lên GET/SET/REMOVE so với CALL/NEW.

| Operation | Chữ ký Object-based minh họa | Argument roles |
| --- | --- | --- |
| `GET:PROPERTY` | `(Object,Object)Object` | receiver, runtime name |
| `GET:PROPERTY:title` | `(Object)Object` | receiver; name đã bound |
| `SET:PROPERTY` | `(Object,Object,Object)void` | receiver, runtime name, value |
| `SET:PROPERTY:title` | `(Object,Object)void` | receiver, value |
| `REMOVE:ELEMENT` | `(Object,Object)void` | receiver, runtime index/key |
| `REMOVE:ELEMENT:0` | `(Object)void` | receiver; index đã bound |
| `CALL` | `(Object,Object,Object)Object` | callable, receiver, 1 arg |
| `CALL:service.execute` | `(Object,Object,Object)Object` | giống CALL; nhãn chỉ diagnostic |
| `NEW` | `(Object,Object)Object` | constructor, 1 arg |
| `NEW:Widget` | `(Object,Object)Object` | giống NEW; nhãn chỉ diagnostic |

Đây là **shape điển hình** theo `StandardOperation`. Tùy linker, parameter/return types có thể hẹp hơn hoặc là primitive. Đừng nhầm một `MethodType` được in ra với dấu hiệu rằng linker thực sự đã hỗ trợ operation trên mọi receiver.

### 10.1. Cách nhớ named vs dynamic

`GET:PROPERTY` nhận `(receiver,name)`. `GET:PROPERTY:title` nhận `(receiver)` vì `title` nằm trong metadata. `SET` thêm value sau name nếu name runtime; khi named chỉ còn receiver+value. `REMOVE` có kiểu return `void`, khi named chỉ còn receiver. `CALL` nhận callable và receiver kể cả khi được named; `NEW` nhận constructor object và arguments, không có receiver tách riêng.

Lưu ý `MethodHandle.invokeExact` nhìn cả **return type** của call site. Trong một đoạn gọi thực, cast `(Object)` và biến kiểu Object thường cần thiết để khớp descriptor `(Object)Object`; không được đổi thành `(String)` tùy tiện rồi hy vọng JVM tự điều chỉnh.

## 11. Lab 3 — in chữ ký cho cả năm nhóm

Tạo file **`OperationSignaturesLab.java`**:

```java
import java.lang.invoke.MethodType;
import jdk.dynalink.Operation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;

public class OperationSignaturesLab {
    private static void display(String label, Operation operation, MethodType type) {
        System.out.println(label + "=" + operation + " " + type);
    }

    public static void main(String[] args) {
        Operation get = StandardOperation.GET.withNamespace(StandardNamespace.PROPERTY);
        Operation set = StandardOperation.SET.withNamespace(StandardNamespace.PROPERTY);
        Operation remove = StandardOperation.REMOVE.withNamespace(StandardNamespace.ELEMENT);
        display("getDynamic", get,
                MethodType.methodType(Object.class, Object.class, Object.class));
        display("getNamed", get.named("title"),
                MethodType.methodType(Object.class, Object.class));
        display("setDynamic", set,
                MethodType.methodType(void.class, Object.class, Object.class, Object.class));
        display("setNamed", set.named("title"),
                MethodType.methodType(void.class, Object.class, Object.class));
        display("removeDynamic", remove,
                MethodType.methodType(void.class, Object.class, Object.class));
        display("removeNamed", remove.named(0),
                MethodType.methodType(void.class, Object.class));
        display("call", StandardOperation.CALL,
                MethodType.methodType(Object.class, Object.class, Object.class, Object.class));
        display("namedCall", StandardOperation.CALL.named("service.execute"),
                MethodType.methodType(Object.class, Object.class, Object.class, Object.class));
        display("new", StandardOperation.NEW,
                MethodType.methodType(Object.class, Object.class, Object.class));
        display("namedNew", StandardOperation.NEW.named("Widget"),
                MethodType.methodType(Object.class, Object.class, Object.class));
    }
}
```

```sh
javac --release 21 --add-modules jdk.dynalink -Xlint:all OperationSignaturesLab.java
java --add-modules jdk.dynalink OperationSignaturesLab
```

**Stdout:**

```text
getDynamic=GET:PROPERTY (Object,Object)Object
getNamed=GET:PROPERTY:title (Object)Object
setDynamic=SET:PROPERTY (Object,Object,Object)void
setNamed=SET:PROPERTY:title (Object,Object)void
removeDynamic=REMOVE:ELEMENT (Object,Object)void
removeNamed=REMOVE:ELEMENT:0 (Object)void
call=CALL (Object,Object,Object)Object
namedCall=CALL:service.execute (Object,Object,Object)Object
new=NEW (Object,Object)Object
namedNew=NEW:Widget (Object,Object)Object
```

**Giới hạn lab:** code này in Operation và MethodType do lập trình viên **tự dựng**, chưa liên kết vào đối tượng thực. Nó giúp đối chiếu expected signatures; Lab 5 mới cho thấy linker áp dụng operation lên JavaBean/Map ở runtime.

## 12. Hợp lệ cấu trúc và lỗi nesting

`NamespaceOperation` cho phép một **base Operation không phải Named/NamespaceOperation** và ít nhất một namespace. `NamedOperation` không chấp nhận base đã là NamedOperation; cả hai không chấp nhận các thành phần null theo hợp đồng constructor.

| Input | Kỳ vọng |
| --- | --- |
| `new NamespaceOperation(GET, PROPERTY)` | Hợp lệ |
| `new NamespaceOperation(GET)` | `IllegalArgumentException` vì thiếu namespace |
| `new NamespaceOperation(GET.withNamespace(PROPERTY), ELEMENT)` | `IllegalArgumentException` vì base đã là NamespaceOperation |
| `new NamedOperation(GET.named("a"),"b")` | `IllegalArgumentException` vì base đã named |
| `new NamedOperation(GET,null)` | `NullPointerException` |
| `new NamespaceOperation(GET,(Namespace)null)` | `NullPointerException` |

**Hai mức kiểm tra khác nhau:** `NamedOperation(GET,"x")` có thể là object được xây về mặt wrapper, nhưng bare `GET` vẫn thiếu namespace theo semantic contract của `StandardOperation.GET`. Vì vậy đừng suy construction success = linker supports it.

### 12.1. Mảng namespace là bản sao

`NamespaceOperation.getNamespaces()` trả array mới. Thay `copy[0]` không sửa operation. Điều này cho phép bạn introspect mà không thay đổi priority được cấu hình khi operation sinh ra. `getNamespace(0)` đọc namespace đầu tiên. Khi cần cấu hình priority mới, xây một `NamespaceOperation` mới.

## 13. Lab 4 — test các cấu trúc lỗi và copy

Tạo file **`ValidationLab.java`**:

```java
import jdk.dynalink.NamedOperation;
import jdk.dynalink.Namespace;
import jdk.dynalink.NamespaceOperation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;

public class ValidationLab {
    public static void main(String[] args) {
        try {
            new NamespaceOperation(StandardOperation.GET);
            System.out.println("noNamespaces=unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("noNamespaces=IllegalArgumentException");
        }
        try {
            new NamespaceOperation(
                    StandardOperation.GET.withNamespace(StandardNamespace.PROPERTY),
                    StandardNamespace.ELEMENT);
            System.out.println("nestedNamespace=unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("nestedNamespace=IllegalArgumentException");
        }
        try {
            new NamedOperation(StandardOperation.GET.named("a"), "b");
            System.out.println("nestedName=unexpected");
        } catch (IllegalArgumentException expected) {
            System.out.println("nestedName=IllegalArgumentException");
        }
        try {
            new NamedOperation(StandardOperation.GET, null);
            System.out.println("nullName=unexpected");
        } catch (NullPointerException expected) {
            System.out.println("nullName=NullPointerException");
        }
        try {
            new NamespaceOperation(StandardOperation.GET, (Namespace) null);
            System.out.println("nullNamespace=unexpected");
        } catch (NullPointerException expected) {
            System.out.println("nullNamespace=NullPointerException");
        }
        NamespaceOperation good = new NamespaceOperation(
                StandardOperation.GET,
                StandardNamespace.PROPERTY, StandardNamespace.ELEMENT);
        Namespace[] copy = good.getNamespaces();
        copy[0] = StandardNamespace.METHOD;
        System.out.println("defensiveCopy=" +
                (good.getNamespace(0) == StandardNamespace.PROPERTY));
        System.out.println("containsElement=" + good.contains(StandardNamespace.ELEMENT));
        System.out.println("namespaceEquals=" + good.equals(new NamespaceOperation(
                StandardOperation.GET, StandardNamespace.PROPERTY,
                StandardNamespace.ELEMENT)));
    }
}
```

```sh
javac --release 21 --add-modules jdk.dynalink -Xlint:all ValidationLab.java
java --add-modules jdk.dynalink ValidationLab
```

**Stdout:**

```text
noNamespaces=IllegalArgumentException
nestedNamespace=IllegalArgumentException
nestedName=IllegalArgumentException
nullName=NullPointerException
nullNamespace=NullPointerException
defensiveCopy=true
containsElement=true
namespaceEquals=true
```

**Giải thích:** constructor ngăn nesting và null theo các quy tắc. `defensiveCopy=true` xác nhận sửa mảng kết quả không thay priority bên trong operation. `namespaceEquals=true` khẳng định hai wrappers có cùng base và cùng ordered namespaces được so bằng nhau.

## 14. Nối CallSiteDescriptor vào một linker thật

Một ứng dụng Dynalink cần một `DynamicLinkerFactory`, `DynamicLinker`, `RelinkableCallSite` và linkers xử lý object model thực tế.

- `DynamicLinkerFactory` tạo bộ linker có ưu tiên/fallback. Trong lab dùng `setFallbackLinkers(new BeansLinker())`.
- `BeansLinker` đọc properties, elements, methods của Java objects; có những quy tắc đặc thù cho JavaBean, array, List, Map và record.
- `SimpleRelinkableCallSite` trong **package `jdk.dynalink.support`** là implementation `RelinkableCallSite` dựa trên `MutableCallSite`, hỗ trợ **monomorphic inline caching**.
- `linker.link(site)` khởi tạo target relink-and-invoke; lần đầu gọi với arguments thực sẽ chọn guarded invocation.
- `site.dynamicInvoker()` cung cấp `MethodHandle` để gọi theo type của site.

**Tên cần ghi chính xác:** Java 21 cung cấp `jdk.dynalink.support.SimpleRelinkableCallSite`. Không tồn tại class API `jdk.dynalink.MonomorphicCallSite`; “monomorphic” là mô tả chiến lược cache chứ không phải tên class chuẩn. `ChainedCallSite` là giải pháp hỗ trợ chuỗi guarded invocations cho receiver đa dạng hơn.

Không nhầm “metadata có thể in” với “hành vi đã link”. Operation như `GET:PROPERTY:name` tự nó không thể `invokeExact()`; chỉ linked site hoặc MethodHandle mới thực thi.

## 15. Lab 5 — BeansLinker và ưu tiên PROPERTY/ELEMENT

Tạo **`BeansLinkLab.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.HashMap;
import java.util.Map;
import jdk.dynalink.CallSiteDescriptor;
import jdk.dynalink.DynamicLinker;
import jdk.dynalink.DynamicLinkerFactory;
import jdk.dynalink.Operation;
import jdk.dynalink.StandardNamespace;
import jdk.dynalink.StandardOperation;
import jdk.dynalink.beans.BeansLinker;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class BeansLinkLab {
    public static class Bean {
        public String getName() { return "Ada"; }
    }

    private static MethodHandle invoker(DynamicLinker linker, Operation operation) {
        CallSiteDescriptor desc = new CallSiteDescriptor(
                MethodHandles.lookup(), operation,
                MethodType.methodType(Object.class, Object.class));
        SimpleRelinkableCallSite site = new SimpleRelinkableCallSite(desc);
        linker.link(site);
        return site.dynamicInvoker();
    }

    public static void main(String[] args) throws Throwable {
        DynamicLinkerFactory factory = new DynamicLinkerFactory();
        factory.setFallbackLinkers(new BeansLinker());
        DynamicLinker linker = factory.createLinker();

        MethodHandle beanGetter = invoker(linker,
                StandardOperation.GET.withNamespace(StandardNamespace.PROPERTY).named("name"));
        System.out.println("beanName=" + (Object) beanGetter.invokeExact((Object) new Bean()));

        Map<String, Object> map = new HashMap<>();
        map.put("empty", "map-value");
        MethodHandle propertyFirst = invoker(linker, StandardOperation.GET.withNamespaces(
                StandardNamespace.PROPERTY, StandardNamespace.ELEMENT).named("empty"));
        MethodHandle elementFirst = invoker(linker, StandardOperation.GET.withNamespaces(
                StandardNamespace.ELEMENT, StandardNamespace.PROPERTY).named("empty"));
        System.out.println("propertyFirst=" +
                (Object) propertyFirst.invokeExact((Object) map));
        System.out.println("elementFirst=" +
                (Object) elementFirst.invokeExact((Object) map));
        System.out.println("mapStillHasKey=" + map.containsKey("empty"));
    }
}
```

```sh
javac --release 21 --add-modules jdk.dynalink -Xlint:all BeansLinkLab.java
java --add-modules jdk.dynalink BeansLinkLab
```

**Stdout kiểm chứng:**

```text
beanName=Ada
propertyFirst=false
elementFirst=map-value
mapStillHasKey=true
```

**Diễn giải:**

1. `Bean.getName()` được `BeansLinker` nhìn như property `name`, nên `beanName=Ada`.
2. Map có entry `empty=map-value`, vì thế `map.isEmpty()` trả false; `GET:PROPERTY|ELEMENT:empty` chọn property trước và trả false.
3. `GET:ELEMENT|PROPERTY:empty` chọn entry Map trước và trả `map-value`.
4. Hai invokers cùng `MethodType=(Object)Object` nhưng khác namespace order. `mapStillHasKey=true` chứng minh đây là các read operations, không có xóa Map key.
5. Cast `(Object)` tại `invokeExact` giữ đúng call-site argument/return signature. Nếu dùng `(String)` return cast khi handle có return Object, có thể nhận `WrongMethodTypeException`.

Đây là **thí nghiệm thực thi liên kết**, không chỉ in metadata. Nó cũng cho thấy khi thiết kế DSL, cần chọn priority theo ý nghĩa của `obj.name` so với `obj[key]`.

## 16. Workflow dùng trong interpreter/compiler động

Một frontend có thể chuyển các biểu thức DSL thành metadata và call site như sau:

```text
[1] Phân tích source expression:
      obj.title / obj[key] / obj.method(x) / new Widget(x)
        |
[2] Xác định Operation:
      GET / SET / REMOVE / CALL / NEW
        |
[3] Xác định namespace(s) nếu cần:
      PROPERTY, ELEMENT, METHOD; giữ priority
        |
[4] Tên cố định hay dynamic?
      NamedOperation để bind sẵn, hoặc name argument runtime
        |
[5] Dựng MethodType:
      receiver/name/value/callable/args và return type
        |
[6] Gắn Lookup:
      new CallSiteDescriptor(lookup, operation, type)
        |
[7] Tạo RelinkableCallSite, gọi DynamicLinker.link(site)
        |
[8] Thực thi qua dynamicInvoker(), guards/relink khi cần
```

### 16.1. Gợi ý mapping vài expression

| Cú pháp | Operation minh họa | MethodType minh họa |
| --- | --- | --- |
| `obj.title` | `GET:PROPERTY:title` | `(Object)Object` |
| `obj[key]` | `GET:ELEMENT|PROPERTY` | `(Object,Object)Object` |
| `obj.title=x` | `SET:PROPERTY:title` | `(Object,Object)void` |
| `delete obj[key]` | `REMOVE:ELEMENT` | `(Object,Object)void` |
| `obj.work(x)` | `GET:METHOD:work` rồi `CALL` | GET `(Object)Object`; CALL `(Object,Object,Object)Object` |
| `new Thing(x)` | `NEW` (optional label) | `(Object,Object)Object` |

Các mappings là **lựa chọn thiết kế DSL**, không phải một bộ quy tắc duy nhất cho mọi ngôn ngữ. Một language có thể ưu tiên ELEMENT ở `obj[key]`, PROPERTY ở `obj.x`; compiler cần thống nhất semantics và kiểm tra chúng bằng tests.

### 16.2. Lưu ý relink, caching và quyền

`DynamicLinker` có thể relink theo receiver class và invalidation. `CallSiteDescriptor.equals` không đủ điều kiện để dùng lại `GuardedInvocation` cho tất cả receivers. Khi cache, cân nhắc lookup, method type, ordered namespaces, name, guard, class loader, module context và invalidation. Không biến metadata thành capability bypass: `BeansLinker` có thể gọi Java methods có side effects.

## 17. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Hướng sửa |
| --- | --- | --- |
| `IllegalArgumentException` khi tạo NamespaceOperation | Zero namespaces hoặc base đã named/namespace | Dùng base operation đơn giản và ≥1 namespace. |
| `IllegalArgumentException` khi tạo NamedOperation | Base đã là NamedOperation | Đặt tên đúng một lần sau namespace. |
| `NullPointerException` ở wrapper | Name hoặc namespace null | Validate trước khi tạo operation. |
| `WrongMethodTypeException` ở `invokeExact` | Sai arity/return type so với MethodType | In `desc.getMethodType()`, đặt casts đúng kiểu. |
| `NoSuchDynamicMethodException` khi link | Linker không giải được operation cho runtime receiver | Kiểm tra namespace, name, receiver và conversion. |
| Quyền truy cập bị từ chối | Lookup/module/class/member access không phù hợp | Dùng caller Lookup đúng, không thay bằng publicLookup tùy tiện. |
| Thay descriptor nhưng call site vẫn hoạt động như cũ | `changeOperation`/`changeMethodType` không tự relink | Tạo/relink site theo giao thức linker. |
| Với Map `empty` lấy false thay vì entry | PROPERTY có ưu tiên cao hơn ELEMENT | Chọn namespace order theo DSL. |
| Lỗi compile không tìm thấy module Dynalink | Chưa resolve `jdk.dynalink` | Dùng `--add-modules jdk.dynalink` hoặc JPMS requires. |
| Dùng sai tên relinkable class | Gõ `MonomorphicCallSite` không có trong API | Dùng `jdk.dynalink.support.SimpleRelinkableCallSite`. |
| Named GET vẫn có name parameter thừa | Dựng MethodType như unnamed operation | Bỏ name argument và kiểm tra type. |
| Named CALL lại bị bỏ một argument | Lẫn với GET/SET/REMOVE | CALL name chỉ diagnostic, arguments giữ nguyên. |

### 17.1. Đừng parse `Operation.toString()` như giao thức chung

`NamedOperation` name là Object có thể có `toString` tùy biến. Dạng hiển thị `GET:PROPERTY|ELEMENT:key` có ích khi debug nhưng không nên thay thế API `NamedOperation.getName` và `NamespaceOperation.getNamespaces`, đặc biệt với custom operations và keys chứa dấu phân cách. Khi cần serialize metadata cho DSL, định nghĩa schema có validation riêng cho operation, namespace order, name type và MethodType.

## 18. Module jdk.dynalink và thiết kế an toàn

Dynalink thuộc module chuẩn JDK **`jdk.dynalink`**, khác `java.base`. Khi compile/run trên classpath, dùng rõ ràng:

```sh
javac --release 21 --add-modules jdk.dynalink MyRuntime.java
java --add-modules jdk.dynalink MyRuntime
```

Với named module tự xây:

```java
// module-info.java minh họa.
module my.runtime {
    requires jdk.dynalink;
}
```

Không dùng `jdk.internal.*`. `jdk.dynalink` là JDK module công khai có tài liệu API, nhưng runtime image tối giản có thể thiếu module; kiểm tra image và `java --list-modules`. Module dependency khác với quyền truy cập vào các private members của application.

### 18.1. Chính sách liên kết cho code không tin cậy

`Operation` chỉ mô tả ý định, không phải chứng thực quyền. Một DSL nhận tên property hoặc method từ người dùng không tin cậy không nên liên kết tùy ý tới mọi Java method: dùng allowlist receivers/operations/members, giới hạn reflection/Lookup, sandbox cấp process khi thực thi code không tin cậy, quản lý quota, và không để user tự cung cấp privileged Lookup. `BeansLinker` có thể dẫn tới gọi Java code có side effects.

### 18.2. Caching và hiệu năng

`SimpleRelinkableCallSite` dùng monomorphic inline cache; `ChainedCallSite` hỗ trợ polymorphic cache. Chọn theo workload receiver classes và benchmark, không lấy một operation name làm runtime cache key duy nhất. Nếu update/invalidate thường xuyên, cần nghĩ tới switchpoints, guarded invocations và churn. Description equality không đồng nghĩa target có cùng độ hợp lệ với mọi receiver.

## 19. Bài tập và tự kiểm tra

**Bài 1 – Phân rã wrapper.** Tạo `GET:ELEMENT|PROPERTY:code` và dùng static helpers để tách name, root, namespaces theo đúng thứ tự. Giải thích vì sao `NamespaceOperation.getNamespaces(named)` trực tiếp trả array rỗng.

**Bài 2 – Dynamic vs fixed key.** So `GET:ELEMENT` và `GET:ELEMENT:2`. Viết MethodType Object-based phù hợp. Đáp án: `(Object,Object)Object` và `(Object)Object`.

**Bài 3 – SET/REMOVE.** Xác định MethodType cho `SET:PROPERTY`, `SET:PROPERTY:title`, `REMOVE:ELEMENT`, `REMOVE:ELEMENT:0`. Tại sao `SET` vẫn cần value argument khi đã named?

**Bài 4 – CALL/NEW.** So `CALL` với `CALL.named("service.run")`. Dùng cùng method type và giải thích vì sao tên này là nhãn chẩn đoán chứ không phải address argument được xóa.

**Bài 5 – Thứ tự namespace.** Chạy lại Lab 5 với Map chứa key `"empty"`. Vì sao property-first và element-first trả khác nhau dù `CallSiteDescriptor.getMethodType` giống hệt?

**Bài 6 – Lỗi nesting.** Tạo new NamespaceOperation với zero namespaces; thử wrap NamedOperation hai lần. Dự đoán `IllegalArgumentException` và phân biệt với null `NullPointerException`.

**Bài 7 – changeOperation.** Tạo `GET:PROPERTY:title` với `(Object)Object`, gọi `changeOperation(GET:PROPERTY)`. Nêu vấn đề method type; sửa bằng `changeMethodType((Object,Object)Object)`.

**Bài 8 – Lookup.** Tạo descriptors ở hai caller classes khác nhau cùng operation/type. Vì sao `CallSiteDescriptor.equals` có thể false và vì sao lookup quyền khác biệt ảnh hưởng việc link private member?

**Bài 9 – GET METHOD.** Mô tả cách `obj.work(7)` có thể dùng `GET:METHOD:work` rồi `CALL`. Trong CALL, vị trí callable và receiver ở đâu?

**Bài 10 – Runtime receiver.** Sửa Lab 5 gọi cùng named GET:PROPERTY:name trên các Bean classes có getter khác nhau. Quan sát relink khi receiver class thay; không dùng kết quả một run làm bảo đảm số lần relink cố định.

**Bài 11 – Security.** Một DSL cho phép `GET:METHOD:deleteEverything` trên mọi object mà caller cung cấp. Hãy nêu rủi ro và chính sách giới hạn operation, receiver, Lookup/linker.

**Bài 12 – Thiết kế frontend.** Chọn operation, namespace priority, name policy và MethodType cho `obj.x`, `obj[key]`, `obj.x=value`, `obj.x()` và `new Foo(x)`, giải thích chỗ nào do semantics của ngôn ngữ quyết định.

### 19.1. Checklist

- [ ] Biết Operation và CallSiteDescriptor là metadata, không phải MethodHandle.
- [ ] Nhận diện năm StandardOperation và ba StandardNamespace.
- [ ] Phân biệt PROPERTY/ELEMENT/METHOD và hiểu priority theo first applicable.
- [ ] Tạo NamedOperation sau NamespaceOperation; không wrap sai thứ tự.
- [ ] Tách name, namespaces và root bằng đúng helpers.
- [ ] Suy số lượng tham số của GET/SET/REMOVE khi named và khi dynamic.
- [ ] Hiểu tên CALL/NEW không làm đổi MethodType.
- [ ] Xây CallSiteDescriptor từ Lookup, Operation, MethodType và hiểu các change APIs.
- [ ] Dùng đúng `SimpleRelinkableCallSite`, link rồi invoke.
- [ ] Chạy được năm chương trình cùng stdout; phân tích Map priority và lỗi wrappers.

## 20. Tài liệu Java SE 21 chính thức

- [JDK 21 – module jdk.dynalink](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.dynalink/module-summary.html): mô hình dynamic linking, call sites, operations, guard.
- [JDK 21 – Operation](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.dynalink/jdk/dynalink/Operation.html): `named`, `withNamespace(s)`.
- [JDK 21 – StandardOperation](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.dynalink/jdk/dynalink/StandardOperation.html): GET, SET, REMOVE, CALL, NEW và chữ ký.
- [JDK 21 – StandardNamespace](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.dynalink/jdk/dynalink/StandardNamespace.html): PROPERTY, ELEMENT, METHOD.
- [JDK 21 – NamespaceOperation](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.dynalink/jdk/dynalink/NamespaceOperation.html): namespace ordering, base, arrays, helper methods.
- [JDK 21 – NamedOperation](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.dynalink/jdk/dynalink/NamedOperation.html): name binding và diagnostic label.
- [JDK 21 – CallSiteDescriptor](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.dynalink/jdk/dynalink/CallSiteDescriptor.html): Lookup, MethodType, operation và transformations.
- [JDK 21 – DynamicLinkerFactory](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinkerFactory.html) và [DynamicLinker](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinker.html): linking/relinking.
- [JDK 21 – BeansLinker](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.dynalink/jdk/dynalink/beans/BeansLinker.html): JavaBean, Map/List/array linking.
- [JDK 21 – SimpleRelinkableCallSite](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.dynalink/jdk/dynalink/support/SimpleRelinkableCallSite.html): monomorphic cache implementation.
- [Java 21 – MethodType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodType.html) và [MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): signature, caller quyền.

**Điểm ghi nhớ:** `Operation` xác định **ý định**, `NamespaceOperation` xác định **không gian và thứ tự ưu tiên**, `NamedOperation` ràng buộc **tên/key biết trước**, còn `CallSiteDescriptor` gắn chúng với **MethodType và Lookup**. Chỉ khi được liên kết qua `DynamicLinker` và `RelinkableCallSite`, mô tả mới trở thành hành vi gọi động thật.
