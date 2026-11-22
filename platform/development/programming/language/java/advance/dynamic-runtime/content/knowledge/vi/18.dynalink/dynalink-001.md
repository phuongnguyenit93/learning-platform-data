# 18.1 Vai trò của `jdk.dynalink` trong bộ thực thi ngôn ngữ động trên JVM

## 1. Dynalink giải quyết vấn đề gì?

Khi một ngôn ngữ có kiểu động chạy trên JVM, biểu thức nguồn như:

~~~text
user.name
~~~

có thể xuất hiện tại một vị trí mà **compiler chưa biết `user` sẽ là object loại gì**. Ở lần chạy thứ nhất, `user` có thể là một Java bean với field `name`; lần thứ hai là Java bean có getter `getName()`; lần thứ ba là một object của ngôn ngữ tự xây, lưu thuộc tính trong dictionary. Cùng một biểu thức *đọc thuộc tính* nhưng cách truy cập cụ thể phụ thuộc **receiver thực tế tại runtime**.

Với Java tĩnh, compiler thường biết target đủ sớm để sinh `getfield` hoặc `invokevirtual`. Với ngôn ngữ động, một thiết kế tốt cần:

- Diễn tả **ý định trừu tượng** của biểu thức: `GET PROPERTY "name"`, `SET ELEMENT`, `CALL`, `NEW`...
- **Chọn đúng method handle** để thực hiện thao tác sau khi nhìn thấy object runtime.
- Gắn target vào một **call site có thể liên kết lại** (*relinkable call site*).
- Tự kiểm tra điều kiện áp dụng target cũ bằng **guard**; khi object đổi kiểu hoặc assumptions hết hiệu lực thì yêu cầu liên kết lại.
- Tối ưu trường hợp nhiều lần gặp cùng dạng object, tránh reflection và phân nhánh kiểu trên mọi lần gọi.
- Cho phép nhiều **object models** và **quy tắc chuyển đổi kiểu** cùng tồn tại, đặc biệt khi giao tiếp giữa ngôn ngữ động và Java.

Module **`jdk.dynalink`** là một thư viện trong JDK, có từ Java 9, hỗ trợ chính những công việc liên kết cấp cao đó. Nó xây dựng trên `java.lang.invoke` và thường phối hợp với bytecode `invokedynamic`.

**Định nghĩa ngắn:** Dynalink là **thư viện liên kết động các thao tác cấp cao trên object**, không phải một scripting language, interpreter hoàn chỉnh, bộ biên dịch Java source, bytecode generator hay cơ chế thay JVM method dispatch. Nó cung cấp *linker architecture* để runtime ngôn ngữ động tự định nghĩa phép toán và học cách thực hiện chúng cho receiver runtime.

## 2. Dynalink nằm ở đâu trong JVM dynamic invocation?

Phân biệt ba tầng:

| Tầng | Cung cấp | Vai trò |
| --- | --- | --- |
| **JVM/`invokedynamic`** | Instruction, bootstrap method protocol, `CallSite` | Khi lần đầu resolve call site, JVM gọi bootstrap; những lần invocation sau sử dụng target do call site cung cấp |
| **`java.lang.invoke`** | `MethodHandle`, `MethodType`, `CallSite`, `MethodHandles.Lookup`, combinators | Biểu diễn, kết nối, chuyển kiểu và thực thi target method handles |
| **`jdk.dynalink`** | `Operation`, `DynamicLinkerFactory`, `DynamicLinker`, `GuardingDynamicLinker`, `GuardedInvocation`, `RelinkableCallSite` | Hiểu thao tác cấp cao và lựa chọn, guard, cache, relink target phù hợp với object runtime |

Sơ đồ thường gặp của trình biên dịch ngôn ngữ động:

~~~text
Nguồn của ngôn ngữ:
    user.name
         |
         v
Compiler ngôn ngữ tự định nghĩa operation:
    GET:PROPERTY:name
         |
         v
Sinh invokedynamic site: (Object)Object
         |
         v
JVM gọi bootstrap method của runtime ngôn ngữ
         |
         v
DynamicLinker.link(RelinkableCallSite)
         |
         v
Site ban đầu giữ relink-and-invoke fallback
         |
         v
Lần chạy thật: receiver = Person("Ada")
         |
         v
Các GuardingDynamicLinker xem LinkRequest
         |
         v
BeansLinker/Linker tùy biến trả GuardedInvocation
         |
         v
Lắp target + guard + fallback vào call site
         |
         v
Đọc thuộc tính, trả "Ada"
         |
         +-- Receiver phù hợp guard? -> gọi nhanh target đã link
         |
         +-- Guard không khớp? -> yêu cầu relink với receiver mới
~~~

**Quan trọng:** `jdk.dynalink` **không tự biến mọi Java expression thành `invokedynamic`**. Compiler hoặc interpreter của **ngôn ngữ đang được xây dựng** phải tạo `CallSiteDescriptor`/`Operation` và chọn khi nào gọi Dynalink. Nếu compiler tạo Java class file có opcode `invokedynamic`, bootstrap method có thể gọi `DynamicLinker.link(...)`; nếu xây interpreter, ta cũng có thể tạo call sites từ Java source để phục vụ AST interpreter mà không sinh instruction mới.

## 3. Module, package và thành phần cốt lõi

Java 17 đưa API Dynalink vào **named JDK module `jdk.dynalink`**. Các package quan trọng:

| Package | Thành phần | Bạn dùng khi nào? |
| --- | --- | --- |
| `jdk.dynalink` | `DynamicLinkerFactory`, `DynamicLinker`, `CallSiteDescriptor`, `Operation`, `StandardOperation`, `StandardNamespace`, `NamedOperation`, `NamespaceOperation`, `RelinkableCallSite` | Thiết kế operation, xây và liên kết dynamic sites |
| `jdk.dynalink.support` | `SimpleRelinkableCallSite`, `ChainedCallSite` | Chọn chiến lược cache ở site |
| `jdk.dynalink.linker` | `GuardingDynamicLinker`, `TypeBasedGuardingDynamicLinker`, `LinkRequest`, `LinkerServices`, `GuardedInvocation`, `GuardingDynamicLinkerExporter` | Tạo linker cho object model ngôn ngữ riêng, chuẩn hóa target/guards, cross-language interoperability |
| `jdk.dynalink.beans` | `BeansLinker`, `StaticClass` | Java interop: fields, getters/setters, methods, arrays, List, Map, constructors |

Nếu chương trình đặt trên **class path** với JDK đầy đủ, ví dụ dưới đây dùng các imports trên và đã chạy trong môi trường kiểm tra. Nếu mã nằm trong **named module**, module-info cần khai báo dependency:

~~~java
module my.dynamic.runtime {
    requires jdk.dynalink;
}
~~~

Đây là **snippet module-info**, chưa phải chương trình chạy độc lập. `requires` làm module của bạn đọc được module API, **không tự mở mọi package của ứng dụng cho reflection/BeansLinker**. Access control Java và JPMS vẫn áp dụng.

API JavaDoc chính thức: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/module-summary.html

### Vai trò các đối tượng chính

- **`DynamicLinkerFactory`:** cấu hình các linkers ưu tiên, linkers fallback, class loader dùng để discover exporters, chính sách relink/đồng bộ; sau đó `createLinker()`.
- **`DynamicLinker`:** điều phối các linkers và gắn cơ chế **relink-and-invoke** vào call site qua `link(...)`.
- **`CallSiteDescriptor`:** lưu `Lookup`, `Operation`, `MethodType` của site để linker biết “ai hỏi, muốn làm gì, và type contract ra sao”.
- **`RelinkableCallSite`:** hợp đồng cho một site có thể nhận target được liên kết lại. Hai lớp tích hợp sẵn là `SimpleRelinkableCallSite` và `ChainedCallSite`.
- **`GuardingDynamicLinker`:** một bộ xử lý biết liên kết operation cho một số loại receiver/logic ngôn ngữ.
- **`GuardedInvocation`:** target MethodHandle kèm điều kiện guard và tùy chọn invalidation mechanisms như `SwitchPoint`.
- **`LinkRequest`:** thông tin yêu cầu liên kết cụ thể, gồm descriptor và arguments hiện tại.
- **`LinkerServices`:** dịch vụ chuyển đổi kiểu và các hỗ trợ liên kết do Dynalink cung cấp.
- **`BeansLinker`:** linker cho Java objects theo hành vi public Java thường dùng, làm nền tảng interop.

## 4. Biểu diễn thao tác cấp cao bằng `Operation`

Một compiler ngôn ngữ không nên mã hóa mọi logic vào tên Java method. Dynalink cho phép biểu diễn **operation** như một giá trị:

~~~java
Operation op = StandardOperation.GET
    .withNamespace(StandardNamespace.PROPERTY)
    .named("name");
~~~

Đây là **snippet**, cần imports `jdk.dynalink.*`. `StandardOperation.GET` có nghĩa “đọc”; `PROPERTY` nói ta đang đọc **namespace thuộc tính**; `named("name")` cố định tên property.

### Các operation tiêu chuẩn

| Operation | Ý nghĩa | Signature cấp cao thường gặp |
| --- | --- | --- |
| `GET` | Lấy giá trị property/element/method theo namespace | `(receiver, name) -> value`, hoặc `(receiver) -> value` nếu tên được `named(...)` |
| `SET` | Ghi property/element | `(receiver, name, value) -> void`, hoặc `(receiver, value) -> void` nếu tên cố định |
| `REMOVE` | Xóa phần tử/entry theo namespace | `(receiver, name) -> void` hoặc `(receiver) -> void` nếu tên cố định |
| `CALL` | Gọi callable/dynamic method | `(callable, receiver, args...) -> result` |
| `NEW` | Gọi constructor-like object | `(constructor, args...) -> newObject` |

Lưu ý `GET` và `SET` **phải có namespace** theo contract Dynalink. Không mô tả `StandardOperation.GET` trơ trọi rồi mặc định rằng đó là getter Java bean; cần ít nhất `PROPERTY` hoặc `ELEMENT`/`METHOD` thích hợp.

### Namespace mô tả không gian tên truy cập

| Namespace | Ví dụ ý nghĩa |
| --- | --- |
| `StandardNamespace.PROPERTY` | `obj.color`, Java bean getter/field hoặc property của object ngôn ngữ |
| `StandardNamespace.ELEMENT` | `array[i]`, `list[i]`, `map[key]` |
| `StandardNamespace.METHOD` | Truy xuất callable biểu diễn một method, có thể gọi sau đó qua `CALL` |

Một ngôn ngữ có thể cho `obj["name"]` thử property trước rồi element sau. Khi đó dùng `withNamespaces(PROPERTY,ELEMENT)` để diễn tả **nhiều namespace theo thứ tự**, thay vì tự viết logic `if` lặp lại trong interpreter. Một linker cụ thể quyết định namespace nào nó hỗ trợ và cách xử lý trường hợp thiếu member.

### `NamedOperation` khác tên được truyền runtime

Hai cách biểu diễn:

~~~text
GET PROPERTY với tên cố định:
    operation = GET.withNamespace(PROPERTY).named("name")
    site type = (Object)Object

GET PROPERTY với tên lấy lúc chạy:
    operation = GET.withNamespace(PROPERTY)
    site type = (Object,Object)Object
                   ^    ^
                receiver key
~~~

`NamedOperation` **loại bỏ tham số tên khỏi signature tại site** cho GET/SET. Điều này có thể tối ưu operation lặp lại có cùng property name. Nhưng **compiler phải bảo đảm đúng tên và đúng site descriptor**, không tự thay một site nhận key runtime thành named site mà vẫn truyền thêm argument.

Đối với `CALL` và `NEW`, đặt tên qua `NamedOperation` chủ yếu giúp chẩn đoán và **không tự xóa tham số khỏi signature**; hãy xem đúng contract của từng operation.

### Tên operation trong bytecode không phải parser có sẵn

Một bootstrap method có thể nhận String `"GET:PROPERTY:name"` và tự parse thành operation, nhưng `jdk.dynalink` **không ép một cú pháp encoding tên duy nhất**. Mỗi language runtime có trách nhiệm định nghĩa và validate cách chuyển metadata/name sang `Operation`.

Ví dụ từ JavaDoc:
`StandardOperation.GET.withNamespace(StandardNamespace.PROPERTY).named("color")`.

## 5. Kết nối site: `DynamicLinkerFactory`, `DynamicLinker`, `CallSiteDescriptor`

Thủ tục cơ bản:

~~~java
DynamicLinker linker = new DynamicLinkerFactory().createLinker();

CallSiteDescriptor descriptor = new CallSiteDescriptor(
    MethodHandles.lookup(),
    StandardOperation.GET
        .withNamespace(StandardNamespace.PROPERTY)
        .named("name"),
    MethodType.methodType(Object.class, Object.class)
);

CallSite site = linker.link(
    new SimpleRelinkableCallSite(descriptor)
);
~~~

Đây là **snippet**, muốn biên dịch cần imports `java.lang.invoke.*`, `jdk.dynalink.*`, `jdk.dynalink.support.SimpleRelinkableCallSite`. Chương trình hoàn chỉnh có ở phần 6.

**Ba dữ kiện trong descriptor:**

1. **`Lookup`:** ngữ cảnh caller để thực hiện member lookups; không phải giấy phép vượt Java access checks.
2. **`Operation`:** tên/namespace của thao tác ngôn ngữ.
3. **`MethodType`:** chữ ký của call site; ví dụ `(Object)Object` nhận một receiver Object và trả Object.

`DynamicLinker.link(...)` nhận một `RelinkableCallSite`. Nó **cài đặt target ban đầu để khi thực thi thì thử link theo arguments thực tế**. Đừng hiểu lời gọi `link(...)` là nó luôn biết trước kiểu receiver; receiver thậm chí có thể chưa xuất hiện đến khi invocation đầu tiên.

**Một phân biệt về Java type system:** `RelinkableCallSite` là **interface riêng**, không kế thừa class `java.lang.invoke.CallSite`. Các implementation có sẵn như `SimpleRelinkableCallSite` và `ChainedCallSite` đồng thời là subclass của `CallSite`, nên muốn gọi `dynamicInvoker()` dùng biến với static type `CallSite` hoặc concrete class. Đoạn sai:

~~~java
RelinkableCallSite site = new SimpleRelinkableCallSite(descriptor);
// site.dynamicInvoker(); // KHÔNG COMPILE: interface không có method này
~~~

Đây là snippet minh họa lỗi compiler, **không phải mã chạy độc lập**. Có thể sửa thành `CallSite site = linker.link(new SimpleRelinkableCallSite(...))` hoặc giữ concrete type; method `dynamicInvoker()` thuộc `CallSite`.

## 6. Ví dụ 1 — Java objects: field, getter và Map element

`DynamicLinkerFactory` mặc định tạo linker có **`BeansLinker`** làm fallback, cho phép thao tác với nhiều object Java thông thường mà bạn không phải tự viết `GuardingDynamicLinker`.

Lưu **`DynalinkBeansDemo.java`**:

~~~java
import java.lang.invoke.*;
import java.util.*;
import jdk.dynalink.*;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class DynalinkBeansDemo {
    public static class Person {
        public String name;

        public Person(String name) {
            this.name = name;
        }
    }

    public static class Contact {
        private final String name;

        public Contact(String name) {
            this.name = name;
        }

        public String getName() {
            return name;
        }
    }

    public static void main(String[] args) throws Throwable {
        DynamicLinker linker = new DynamicLinkerFactory().createLinker();

        Operation op = StandardOperation.GET
                .withNamespace(StandardNamespace.PROPERTY)
                .named("name");

        CallSiteDescriptor d = new CallSiteDescriptor(
                MethodHandles.lookup(), op,
                MethodType.methodType(Object.class, Object.class));

        CallSite site = linker.link(
                new SimpleRelinkableCallSite(d));
        MethodHandle getter = site.dynamicInvoker();

        System.out.println("siteType=" + site.type());

        System.out.println("field=" + (Object)
                getter.invokeExact((Object) new Person("Ada")));

        System.out.println("getter=" + (Object)
                getter.invokeExact((Object) new Contact("Lin")));

        System.out.println("fieldAgain=" + (Object)
                getter.invokeExact((Object) new Person("Binh")));

        Operation elementOp = StandardOperation.GET
                .withNamespace(StandardNamespace.ELEMENT)
                .named("language");

        CallSite mapSite = linker.link(
                new SimpleRelinkableCallSite(
                    new CallSiteDescriptor(
                        MethodHandles.lookup(),
                        elementOp,
                        MethodType.methodType(
                            Object.class, Object.class))));

        Object map = Map.of("language", "Java");
        System.out.println("map=" + (Object)
                mapSite.dynamicInvoker().invokeExact(map));
    }
}
~~~

Chạy trên JDK 17+:

~~~sh
javac --release 17 DynalinkBeansDemo.java
java DynalinkBeansDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
siteType=(Object)Object
field=Ada
getter=Lin
fieldAgain=Binh
map=Java
~~~

**Giải thích:**

- `Person.name` là `public field`, trong khi `Contact.name` là `private field` có public getter `getName()`. `BeansLinker` có thể đáp ứng **cùng GET PROPERTY name** theo hai đường truy cập công khai khác nhau.
- `site.type()` luôn là `(Object)Object`, dù type receiver runtime đổi giữa `Person` và `Contact`.
- `SimpleRelinkableCallSite` giữ cache **monomorphic**; khi receiver không còn thỏa guard của target trước, nó relink. Không cần tự phân nhánh `if (user instanceof Person)` trong Java source trên mọi lần gọi.
- `Map` dùng **namespace ELEMENT**: `Map.of("language","Java")` có key `"language"`, nên `GET ELEMENT language` trả `"Java"`.
- `getter.invokeExact((Object) value)` ép kiểu tĩnh argument thành Object và ép return thành Object; điều này **quan trọng với `MethodHandle.invokeExact`**. Nếu gọi exact với return cast String hoặc argument static type Person trong khi site là `(Object)Object`, có thể gặp `WrongMethodTypeException`.
- Ví dụ một thread dùng site sau khi đã link thành công; không suy ra chính xác JVM gọi bao nhiêu linker callbacks chỉ từ stdout, vì phần đó là chi tiết cache. Ví dụ kiểm thử số lượt link của custom linker ở phần 7.

`BeansLinker` còn hỗ trợ Java arrays, `List`, `Map`, public getters/setters, public methods và `StaticClass` để gọi static members/constructors theo quy tắc của API. Không mặc định mọi private member đều đọc được qua BeansLinker.

## 7. Tại sao cần `GuardingDynamicLinker` tùy biến?

Một ngôn ngữ động có thể có object model riêng: object là map field values, prototype chain, proxy, shape table hoặc bảng property không tương ứng Java bean. Khi gặp object như vậy, `BeansLinker` không thể tự biết `obj.name` nghĩa là gì.

Giải pháp là tạo **language-specific linker**:

~~~text
LinkRequest(op=GET PROPERTY "name", receiver=DynRecord)
                     |
                     v
GuardingDynamicLinker của ngôn ngữ:
    - Kiểm tra receiver thuộc object model của mình?
    - Kiểm tra operation có hỗ trợ?
    - Tạo target MethodHandle tương ứng
    - Tạo guard kiểm tra assumption
                     |
          +----------+----------+
          |                     |
       Có handler             Không xử lý
          |                     |
          v                     v
    GuardedInvocation        return null
          |                     |
          v                     v
     Dynalink cache       Linker tiếp theo / BeansLinker
~~~

`GuardingDynamicLinker.getGuardedInvocation(LinkRequest,LinkerServices)` trả:

- Một `GuardedInvocation` khi hiểu operation và có thể tạo target.
- **`null`** khi linker **không xử lý** receiver/operation này, nhường quyền cho linker kế tiếp.
- Exception khi liên kết gặp lỗi không thể khắc phục theo contract.

`GuardedInvocation` có thể chứa **guard**, target, `SwitchPoint` để invalidation, hoặc loại exception làm tín hiệu relink theo API. Trong ví dụ dưới, chỉ dùng một guard `instanceof DynRecord` để tập trung vào ý tưởng.

### Ví dụ 2 — Custom object model + monomorphic/polymorphic cache

Lưu **`DynalinkCustomDemo.java`**:

~~~java
import java.lang.invoke.*;
import java.util.*;
import jdk.dynalink.*;
import jdk.dynalink.linker.*;
import jdk.dynalink.support.*;

public class DynalinkCustomDemo {
    public static class DynRecord {
        final Map<String, Object> values;

        DynRecord(Map<String, Object> values) {
            this.values = values;
        }
    }

    public static class JavaBean {
        private final String name;

        public JavaBean(String name) {
            this.name = name;
        }

        public String getName() {
            return name;
        }
    }

    public static Object get(DynRecord r, String key) {
        return r.values.get(key);
    }

    public static boolean isDynRecord(Object obj) {
        return obj instanceof DynRecord;
    }

    static class RecordLinker implements GuardingDynamicLinker {
        int customLinks;

        @Override
        public GuardedInvocation getGuardedInvocation(
                LinkRequest request,
                LinkerServices services) throws Exception {

            if (!(request.getReceiver() instanceof DynRecord)) {
                return null;
            }

            Operation operation =
                    request.getCallSiteDescriptor().getOperation();
            Object key = NamedOperation.getName(operation);
            Operation unwrapped =
                    NamedOperation.getBaseOperation(operation);

            if (!(key instanceof String) ||
                !NamespaceOperation.contains(
                    unwrapped, StandardOperation.GET,
                    StandardNamespace.PROPERTY)) {
                return null;
            }

            customLinks++;

            MethodHandles.Lookup lookup = MethodHandles.lookup();
            MethodHandle mh = lookup.findStatic(
                    DynalinkCustomDemo.class, "get",
                    MethodType.methodType(
                        Object.class, DynRecord.class, String.class));

            MethodHandle target = MethodHandles.insertArguments(
                    mh, 1, (String) key)
                    .asType(request.getCallSiteDescriptor().getMethodType());

            MethodHandle guard = lookup.findStatic(
                    DynalinkCustomDemo.class, "isDynRecord",
                    MethodType.methodType(boolean.class, Object.class));

            return new GuardedInvocation(target, guard);
        }
    }

    static void run(boolean chain) throws Throwable {
        RecordLinker custom = new RecordLinker();

        DynamicLinkerFactory factory = new DynamicLinkerFactory();
        factory.setPrioritizedLinker(custom);
        DynamicLinker linker = factory.createLinker();

        Operation operation = StandardOperation.GET
                .withNamespace(StandardNamespace.PROPERTY)
                .named("name");

        CallSiteDescriptor descriptor = new CallSiteDescriptor(
                MethodHandles.lookup(), operation,
                MethodType.methodType(Object.class, Object.class));

        CallSite site = chain
                ? new ChainedCallSite(descriptor)
                : new SimpleRelinkableCallSite(descriptor);

        linker.link((RelinkableCallSite) site);
        MethodHandle mh = site.dynamicInvoker();

        Object one = mh.invokeExact(
                (Object) new DynRecord(Map.of("name", "neo")));
        Object two = mh.invokeExact(
                (Object) new JavaBean("Ada"));
        Object three = mh.invokeExact(
                (Object) new DynRecord(Map.of("name", "trinity")));

        System.out.println((chain ? "chain" : "simple") +
                "=" + one + "," + two + "," + three);
        System.out.println((chain ? "chainLinks" : "simpleLinks") +
                "=" + custom.customLinks);
    }

    public static void main(String[] args) throws Throwable {
        run(false);
        run(true);
    }
}
~~~

~~~sh
javac --release 17 DynalinkCustomDemo.java
java DynalinkCustomDemo
~~~

**Stdout của chương trình tuần tự này:**

~~~text
simple=neo,Ada,trinity
simpleLinks=2
chain=neo,Ada,trinity
chainLinks=1
~~~

**Cách đọc chương trình:**

1. Runtime định nghĩa `DynRecord` có dictionary `Map<String,Object>`. Đây là một object model tối giản, khác JavaBeans; muốn đọc `name` thì gọi `get(DynRecord,String)`.
2. `RecordLinker` được đặt vào **danh sách ưu tiên** bằng `setPrioritizedLinker`. Khi receiver là `DynRecord`, nó xử lý; với `JavaBean`, nó trả null để `BeansLinker` mặc định xử lý tiếp.
3. `request.getCallSiteDescriptor().getOperation()` mô tả `GET PROPERTY name`. Vì operation đã `named(...)`, nó là **`NamedOperation` bọc `NamespaceOperation`**. `NamedOperation.getName(...)` lấy key và `NamedOperation.getBaseOperation(...)` **gỡ lớp NamedOperation** trước khi gọi `NamespaceOperation.contains(...)`. Nếu gọi `NamespaceOperation.contains` trực tiếp lên outer NamedOperation, điều kiện này không phù hợp và custom linker có thể bỏ qua đúng operation.
4. Method handle ban đầu `get(DynRecord,String):Object` được bind key `"name"` bằng `insertArguments` thành `(DynRecord)Object`; `asType((Object)Object)` thích nghi receiver cho descriptor của site.
5. Guard `isDynRecord(Object):boolean` đảm bảo target trên chỉ được dùng khi receiver thuộc object model DynRecord. Guard không match thì callback relink có cơ hội chọn linker khác.
6. `SimpleRelinkableCallSite` chỉ giữ **một guarded invocation**: lần gặp DynRecord đầu liên kết một lần; gặp JavaBean thay target; gặp DynRecord lần nữa phải gọi custom linker lại ⇒ `simpleLinks=2`.
7. `ChainedCallSite` giữ **một chuỗi guarded invocations** (mặc định tối đa 8). Sau khi gặp DynRecord và JavaBean, lần DynRecord thứ ba có thể trúng target cũ trong chain ⇒ `chainLinks=1` với sequence này.

**Chú ý:** số đếm trên là số lần **custom linker tạo GuardedInvocation**, không phải số lần JVM gọi method `get`. Đừng lấy ví dụ này chứng minh `ChainedCallSite` luôn nhanh hơn. Nếu có quá nhiều shapes, guard chain dài, invalidation, contention hoặc memory pressure, chiến lược tốt nhất có thể khác.

### Giới hạn của guard trong ví dụ

`instanceof DynRecord` là đủ **chỉ vì** tất cả `DynRecord` trong ví dụ đều đọc field trong map theo cùng một method `get`. Nếu runtime có nhiều **shape/version/prototype** với layouts khác nhau, guard chỉ theo class có thể không đủ. Cần guard thêm identity/version của shape hoặc dùng `SwitchPoint` để invalidate target khi giả định bị thay đổi. Cache sai điều kiện bảo vệ dẫn đến trả dữ liệu sai, một lỗi logic khó phát hiện hơn lỗi exception.

## 8. Bootstrap method: nơi `invokedynamic` giao việc cho Dynalink

Trong class file sinh bởi compiler ngôn ngữ, một instruction có thể mang tên tùy chọn:

~~~text
invokedynamic "GET:PROPERTY:name" (Object)Object
~~~

Khi resolve site, JVM cung cấp `MethodHandles.Lookup caller`, `String name` và `MethodType type` cho BSM. BSM **tự parse name** thành `Operation`, tạo `CallSiteDescriptor` rồi nhờ `DynamicLinker.link(...)`.

Đây là một mẫu BSM đơn giản:

~~~java
public static CallSite bootstrap(
        MethodHandles.Lookup caller,
        String name,
        MethodType type) {
    Operation op = parseOperation(name);
    return LINKER.link(new SimpleRelinkableCallSite(
            new CallSiteDescriptor(caller, op, type)));
}
~~~

**Đây là snippet, không chạy độc lập**, vì `LINKER` và `parseOperation` chưa được khai báo. Ví dụ hoàn chỉnh bên dưới định nghĩa chúng.

### Ví dụ 3 — Gọi trực tiếp phương thức BSM-shaped để quan sát contract

Lưu **`DynalinkBootstrapDemo.java`**:

~~~java
import java.lang.invoke.*;
import jdk.dynalink.*;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class DynalinkBootstrapDemo {
    public static class Item {
        private final String name;

        public Item(String name) {
            this.name = name;
        }

        public String getName() {
            return name;
        }
    }

    private static final DynamicLinker LINKER =
            new DynamicLinkerFactory().createLinker();

    public static CallSite bootstrap(
            MethodHandles.Lookup caller,
            String name,
            MethodType type) {
        if (!name.equals("GET:PROPERTY:name")) {
            throw new IllegalArgumentException("Unsupported: " + name);
        }

        Operation op = StandardOperation.GET
                .withNamespace(StandardNamespace.PROPERTY)
                .named("name");

        return LINKER.link(new SimpleRelinkableCallSite(
                new CallSiteDescriptor(caller, op, type)));
    }

    public static void main(String[] args) throws Throwable {
        CallSite site = bootstrap(
                MethodHandles.lookup(),
                "GET:PROPERTY:name",
                MethodType.methodType(Object.class, Object.class));

        System.out.println("type=" + site.type());
        System.out.println("value=" + (Object)
                site.dynamicInvoker().invokeExact(
                    (Object) new Item("demo")));

        try {
            bootstrap(MethodHandles.lookup(),
                "GET:PROPERTY:unknown",
                MethodType.methodType(Object.class, Object.class));
        } catch (IllegalArgumentException ex) {
            System.out.println("unsupported=" +
                    ex.getClass().getSimpleName());
        }
    }
}
~~~

~~~sh
javac --release 17 DynalinkBootstrapDemo.java
java DynalinkBootstrapDemo
~~~

**Stdout:**

~~~text
type=(Object)Object
value=demo
unsupported=IllegalArgumentException
~~~

**Phân biệt demo với bytecode thực tế:** chương trình này **gọi `bootstrap(...)` bằng Java source thông thường** để thử wiring giữa BSM, descriptor và Dynalink. Nó **không tự sinh instruction `invokedynamic`**. Trong hệ thống thực, bytecode generator phải tạo `CONSTANT_InvokeDynamic` và `BootstrapMethods` trỏ tới BSM; JVM mới là bên gọi BSM tại thời điểm linking. Việc gọi BSM trực tiếp hữu ích cho unit test một compiler/runtime nhưng không thay thế test bytecode `invokedynamic`.

### `DynamicLinker.link` không giống `MethodHandle.invokeExact`

- `link(...)` **thiết lập call site để biết cách link/relink**.
- `site.dynamicInvoker()` là một MethodHandle đại diện lời gọi thông qua site.
- `invokeExact(...)` **thực thi** qua site với descriptor chính xác, lúc này target có thể link lần đầu hoặc relink.

Ở site `(Object)Object`, type tĩnh của đối số và kết quả `invokeExact` đều phải là `Object`. Đó là lý do ví dụ viết `(Object) new Item(...)` và cast return `(Object)`; nếu cast return sang `String`, `WrongMethodTypeException` có thể xảy ra **trước cả khi target được gọi**.

## 9. Khi không ai liên kết được: chẩn đoán lỗi

Dynalink có thể nhận receiver không hợp lệ cho operation đã mô tả. Nếu không linker nào tạo được `GuardedInvocation` phù hợp, site sẽ báo **`NoSuchDynamicMethodException`** khi invocation. Đây là failure của **dynamic operation resolution**, không giống `NoSuchMethodException` của Java Reflection.

### Ví dụ 4 — Sai return type và không có linker phù hợp

Lưu **`DynalinkErrorsDemo.java`**:

~~~java
import java.lang.invoke.*;
import jdk.dynalink.*;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class DynalinkErrorsDemo {
    public static class Bean {
        public String color = "blue";
    }

    public static void main(String[] args) throws Throwable {
        DynamicLinker linker =
                new DynamicLinkerFactory().createLinker();

        Operation op = StandardOperation.GET
                .withNamespace(StandardNamespace.PROPERTY)
                .named("color");

        CallSite site = linker.link(
                new SimpleRelinkableCallSite(
                    new CallSiteDescriptor(
                        MethodHandles.lookup(), op,
                        MethodType.methodType(
                            Object.class, Object.class))));

        MethodHandle getter = site.dynamicInvoker();
        Object bean = new Bean();

        System.out.println("exists=" +
                (Object) getter.invokeExact(bean));

        try {
            String unused = (String) getter.invokeExact(bean);
        } catch (WrongMethodTypeException ex) {
            System.out.println("wrongReturn=" +
                    ex.getClass().getSimpleName());
        }

        try {
            Object unknown = new Object();
            Object unused = getter.invokeExact(unknown);
            System.out.println("unknown=" + unused);
        } catch (NoSuchDynamicMethodException ex) {
            System.out.println("unknown=" +
                    ex.getClass().getSimpleName());
        }
    }
}
~~~

~~~sh
javac --release 17 DynalinkErrorsDemo.java
java DynalinkErrorsDemo
~~~

**Stdout:**

~~~text
exists=blue
wrongReturn=WrongMethodTypeException
unknown=NoSuchDynamicMethodException
~~~

Hai vấn đề độc lập:

1. `WrongMethodTypeException` là mismatch với **`MethodHandle.invokeExact`**: site trả Object mà source yêu cầu String. Sửa call site/cast hoặc dùng `invoke` thích nghi phù hợp; lỗi này **không chứng minh** Dynalink không tìm được `Bean.color`.
2. `NoSuchDynamicMethodException` xuất hiện khi site nhận `new Object()` không có property `color` và không linker nào xử lý được. Site vẫn tồn tại; runtime có thể định nghĩa policy riêng cho property missing (trả null, tạo object sentinel, ném exception cụ thể...), nhưng nếu không có fallback thích hợp thì exception Dynalink là kết quả hợp lý.

**Không đặt `try/catch(NoSuchDynamicMethodException)` quanh mọi operation rồi im lặng trả null** nếu ngôn ngữ có khác biệt giữa member không tồn tại và member có giá trị null. Đây là quyết định semantic của ngôn ngữ, cần phân biệt ở linker/fallback một cách nhất quán.

## 10. Cơ chế guard, relink và inline cache

Một `GuardedInvocation` gói:

~~~text
target: (Object)Object  // method handle thực hiện operation
guard:  (Object)boolean // điều kiện target còn phù hợp
fallback: relink-and-invoke do DynamicLinker quản lý
~~~

Tại mỗi lần call:

~~~text
Receiver mới đi qua site
            |
            v
     Guard phù hợp?
       /       \
     Có         Không
     |           |
     v           v
 Call target   Relink callback
                 |
                 v
          GuardingDynamicLinker(s)
                 |
                 v
        GuardedInvocation mới
                 |
                 v
         Site cập nhật target
                 |
                 v
        Thử thực hiện thao tác
~~~

**Đây là sơ đồ ý nghĩa, không phải cam kết thứ tự instruction cụ thể**. JVM/JIT có thể inline/optimize method handles. Mục tiêu là giữ **guard conditions + fallback** đúng.

### Monomorphic và polymorphic cache

- **`SimpleRelinkableCallSite`:** một guarded invocation ở một thời điểm. Receiver không còn match ⇒ thay linkage hiện tại. Phù hợp các sites chủ yếu gặp một shape/type.
- **`ChainedCallSite`:** lưu một chuỗi guarded invocations, mặc định **tối đa tám**, mới nhất ở đầu. Receiver từng gặp trước đó có thể trúng guard trong chain mà không cần tạo linkage mới. Đổi lại chain dài hơn có chi phí guard checks.
- **`RelinkableCallSite` interface:** định nghĩa cách nhận `relink(...)` và `resetAndRelink(...)`; có thể tự implement chiến lược cache riêng khi hai lớp trên không phù hợp.
- **`DynamicLinkerFactory.setUnstableRelinkThreshold(...)`:** giúp đánh dấu site được coi là unstable sau số lượt relink để linkers có thể chọn chính sách phù hợp, ví dụ target generic.
- **`DynamicLinkerFactory.setSyncOnRelink(...)`:** điều chỉnh việc gọi `MutableCallSite.syncAll(...)` khi cập nhật site, liên quan visibility giữa threads.

Không chọn “PIC luôn tốt” hay “monomorphic luôn tốt” chỉ theo số lượng classes trong toàn bộ chương trình. Quan trọng là **phân bố types tại từng site**, tần suất thay đổi, tốc độ guard checks, biến đổi shapes và memory pressure. Với site megamorphic (rất nhiều types), cần chiến lược generic hoặc cache tối ưu theo profile.

### Invalidation qua `SwitchPoint`

Đối với runtime có object shapes/prototypes thay đổi, guard chỉ kiểm tra `instanceof` thường quá yếu. Dynalink hỗ trợ `GuardedInvocation` kèm `SwitchPoint` hoặc exception types làm tín hiệu invalidation để callback relink có thể tái tạo target sau khi giả định lỗi thời.

Ví dụ dữ liệu prototype bị sửa: target cũ từng trả field ở slot 2, nhưng shape mới chuyển field sang slot 4. Nếu guard vẫn true và không invalidation, chương trình có thể trả **sai kết quả âm thầm**. Vì vậy thiết kế *guard validity* trước khi tối ưu tốc độ.

## 11. Cấu hình pipeline linker và khả năng tương tác nhiều ngôn ngữ

`DynamicLinkerFactory` cho phép cấu hình ba nhóm linkers:

~~~text
1. Prioritized linkers do runtime cài
          |
          v
2. Autodiscovered linkers từ các language runtimes khác
          |
          v
3. Fallback linkers (mặc định có BeansLinker)
          |
          v
     Không ai xử lý => lỗi / policy fallback
~~~

Trong phần 7, `RecordLinker` được thêm bằng `setPrioritizedLinker(custom)` nên nó nhận `DynRecord` trước. Khi không nhận, trả null; `BeansLinker` giải quyết Java bean. **Một factory không phải chỉ có một linker**; chính việc phối hợp nhiều linker khiến Dynalink hữu ích cho ngôn ngữ hỗn hợp.

### Cross-language interop

`GuardingDynamicLinkerExporter` là API để một language runtime xuất các guarding linkers của nó cho runtime khác tự phát hiện bằng cơ chế dịch vụ. `DynamicLinkerFactory.setClassLoader(...)` ảnh hưởng tới việc discover exporters, thường qua class loader của runtime/context. Một hệ thống nhiều scripting languages có thể cấu hình mỗi runtime với class loader phù hợp, để các linkers của ngôn ngữ khác được đưa vào pipeline.

**Không khẳng định chỉ cần import `jdk.dynalink` là mọi ngôn ngữ tự hiểu object của nhau**. Mỗi language runtime cần:

- Viết exporter/linker cho object model của nó.
- Đóng gói và công bố service providers đúng class loader/module.
- Định nghĩa cách chuyển giá trị và kiểu cho interop.
- Thống nhất namespace và semantic của operations.
- Phân xử ưu tiên/fallback linkers tránh một linker nhận nhầm object của ngôn ngữ khác.

### `LinkerServices`

Bên cạnh `MethodHandle.asType`, Dynalink có `LinkerServices` để linkers đề nghị **type adaptations** trong ngữ cảnh những converter mà runtime hỗ trợ, cũng như các dịch vụ khác. Đừng tự giả định phép chuyển từ object ngôn ngữ riêng sang Java type luôn giống primitive boxing/reference cast chuẩn; custom language runtimes có thể định nghĩa conversions khác.

Một custom linker nên tạo `GuardedInvocation` có type compatible với descriptor và dùng `LinkerServices` khi muốn tôn trọng conversion policy thống nhất. Trong ví dụ học tập, `asType((Object)Object)` đủ vì chỉ thích nghi receiver reference.

## 12. JPMS và Java access vẫn áp dụng với `BeansLinker`

Có `requires jdk.dynalink` cho phép **gọi API Dynalink** từ named module. Nhưng operation `GET PROPERTY` trên public bean thuộc package **không exported** có thể không liên kết được do Java module encapsulation. Dynalink không phải đặc quyền phá visibility.

### Ví dụ named module tối giản

Cấu trúc:

~~~text
src/
  dyn.demo/
    module-info.java
    app/Main.java
~~~

File **`src/dyn.demo/module-info.java`**:

~~~java
module dyn.demo {
    requires jdk.dynalink;
    exports app;
}
~~~

File **`src/dyn.demo/app/Main.java`**:

~~~java
package app;

import java.lang.invoke.*;
import jdk.dynalink.*;
import jdk.dynalink.support.SimpleRelinkableCallSite;

public class Main {
    public static class Bean {
        public String name = "module-ok";
    }

    public static void main(String[] args) throws Throwable {
        DynamicLinker linker = new DynamicLinkerFactory().createLinker();
        Operation op = StandardOperation.GET
                .withNamespace(StandardNamespace.PROPERTY)
                .named("name");

        CallSite site = linker.link(
                new SimpleRelinkableCallSite(
                    new CallSiteDescriptor(
                        MethodHandles.lookup(), op,
                        MethodType.methodType(
                            Object.class, Object.class))));

        System.out.println("module=" +
                Main.class.getModule().getName());
        System.out.println("property=" + (Object)
                site.dynamicInvoker().invokeExact((Object) new Bean()));
    }
}
~~~

Từ thư mục chứa `src`:

~~~sh
javac --release 17 --module-source-path src -d mods -m dyn.demo
java --module-path mods -m dyn.demo/app.Main
~~~

**Stdout khi package `app` được export:**

~~~text
module=dyn.demo
property=module-ok
~~~

Ở cấu hình được kiểm chứng, nếu bỏ `exports app;` mà chỉ giữ `requires jdk.dynalink;`, việc đọc property bằng `BeansLinker` **không liên kết được** và site ném `NoSuchDynamicMethodException`. `requires` chỉ tạo module readability; nó không tự mở package cho access từ linker library. Phần chính của ví dụ là chứng minh **đọc được API Dynalink khác với quyền nhìn vào bean member**.

**Lựa chọn thiết kế:** không xuất cả package nội bộ một cách bừa bãi chỉ để tiện scripting. Nếu runtime cần truy cập tài nguyên không public, hãy cung cấp API public/DTO được thiết kế rõ ràng hoặc linker tùy biến tuân thủ `Lookup`/JPMS; không đưa `--add-opens` vào deployment như một “bypass” mặc định mà chưa đánh giá security boundary.

## 13. Những gì Dynalink không làm thay language runtime

Dynalink **giải quyết linkage**, không thay toàn bộ triển khai ngôn ngữ.

| Trách nhiệm | Ai giải quyết? | Ghi chú |
| --- | --- | --- |
| Parse token, grammar, build AST | Compiler/parser ngôn ngữ | Dynalink không parse script |
| Kiểm tra semantics ngôn ngữ, scope, closures | Compiler/interpreter | Quyết định tên operation, object model và kết quả |
| Sinh Java bytecode `invokedynamic` | Bytecode generator/ngôn ngữ | Dynalink không phải class file emitter |
| Định nghĩa object representation | Runtime ngôn ngữ | Object shapes, dynamic properties, prototypes |
| Liên kết operation tới MethodHandle | **Dynalink cùng custom/Beans linkers** | Core value của thư viện |
| Cache/guard/relink ở site | **Dynalink + RelinkableCallSite implementation** | Có chiến lược monomorphic/polymorphic |
| Chuyển kiểu đặc biệt của ngôn ngữ | Runtime + `LinkerServices`/linkers | Cần semantic rõ ràng |
| Chạy native JVM bytecode và JIT | JVM | Dynalink dựa vào Java method handles |
| Chạy script an toàn trong sandbox | **Ngoài phạm vi Dynalink** | Cần isolation, resource limits và trust policy |
| Cấp quyền truy cập private/JDK internals | Java/JPMS/access control | Dynalink không tự bypass quyền |

Vì vậy, đưa `jdk.dynalink` vào classpath không tạo ra ngay một ngôn ngữ động. Trước tiên phải thiết kế **ngữ nghĩa của operation**: đọc property thiếu key thì trả `null`, `undefined` hay ném lỗi? Number + String có coerce không? Setter hoạt động trên immutable object thế nào? Lúc gọi method có overload, overload resolution tuân theo quy tắc nào? Các lựa chọn ấy thuộc language runtime.

## 14. Thiết kế một bộ thực thi ngôn ngữ động: từng bước hợp lý

Giả sử muốn hỗ trợ biểu thức `obj.color` và `obj["color"]` trong một DSL. Một quy trình tối giản:

1. **Định nghĩa semantic:** `GET PROPERTY` và `GET ELEMENT` có cùng nghĩa hay khác? Nếu lookup không tồn tại, dùng sentinel hay exception?
2. **Chuẩn hóa operations:** dùng `StandardOperation.GET.withNamespace(PROPERTY).named("color")` cho site biết tên tĩnh; dùng `GET.withNamespace(ELEMENT)` nhận key runtime cho subscript.
3. **Định nghĩa site descriptors:** tên operation, `Lookup`, type `(Object)Object` hoặc `(Object,Object)Object` theo input runtime. Cẩn thận return type của `MethodHandle.invokeExact`.
4. **Chọn object model:** dùng Java beans/Map nếu tương ứng semantic ngôn ngữ; nếu có `DynRecord`/prototype/shape cần `GuardingDynamicLinker` riêng.
5. **Tạo linker:** thêm custom linker bằng `setPrioritizedLinker`; giữ `BeansLinker` fallback nếu muốn Java interop; cân nhắc custom type conversions.
6. **Chọn call site strategy:** `SimpleRelinkableCallSite` nếu site ổn định một shape; `ChainedCallSite` nếu site gặp vài shapes; benchmark mới quyết định.
7. **Tích hợp interpreter/bytecode:** interpreter lưu `CallSite` trong AST node, hoặc bytecode generator sinh `invokedynamic` với BSM gọi Dynalink.
8. **Guard mọi giả định quan trọng:** không chỉ class, còn shape/version/prototype, visibility và invalidate khi thay.
9. **Quyết định error policy:** nếu thiếu field/method, tạo fallback return/exception đúng semantic; tránh bắt hết lỗi thành null.
10. **Thiết kế isolation/security:** đừng để script tự động truy cập Java internals/reflective APIs mà language policy không cho phép; kiểm soát class loaders, modules và libraries được exposed.
11. **Đo lường hành vi:** số lần relink/site, guard hit/miss, số shapes/site, latency, allocation và memory/cache size. Đừng chỉ benchmark một dạng receiver.
12. **Kiểm thử đa kiểu/đa luồng:** receiver đổi loại, giá trị property thay đổi, object model invalidation, concurrent relink và startup; xác minh correctness trước performance.

### Kịch bản phát triển có kiểm soát

Bắt đầu bằng một site `GET PROPERTY name` cho hai Java bean types như ví dụ 1. Sau đó thêm custom `DynRecord` (ví dụ 2). Cuối cùng mới thêm compiler phát `invokedynamic` (ví dụ 3 giải thích bootstrap wiring). Đi từ đơn giản đến phức tạp giúp phân biệt ba loại lỗi: operation semantic sai, linkers/guards sai, và bytecode/bootstrap descriptor sai.

## 15. Chẩn đoán lỗi: site, operation, linker, guard hay target?

Khi có lỗi trong bộ thực thi:

| Dấu hiệu | Nguyên nhân thường gặp | Nơi cần xem |
| --- | --- | --- |
| `NoSuchDynamicMethodException` | Không linker nào nhận receiver/operation, hoặc namespace/member không phù hợp | `LinkRequest`, operation, receiver class, fallback order, access |
| `WrongMethodTypeException` | Site signature khác type tĩnh của `invokeExact` hoặc MH target/guard không compatible | `CallSiteDescriptor.getMethodType()`, `MethodHandle.type()`, return cast |
| `ClassCastException` | Target hoặc adapter ép receiver/value sang kiểu không phù hợp | Guard, `asType`, converter và runtime class |
| `IllegalAccessException` | Lookup không đủ quyền tìm method/field | `lookup.lookupClass()`, modes, module exports/opens |
| `BootstrapMethodError` khi chạy indy | Bootstrap fail/CallSite type sai trong lúc JVM link | BSM code, cause, `BootstrapMethods` bytecode |
| Nhiều lần relink không mong muốn | Receiver shapes biến động hoặc guard quá cụ thể | Cache strategy, site profile, type distributions |
| Kết quả cũ sau thay đổi object shape | Guard/invalidation thiếu điều kiện | `SwitchPoint`, shape version, prototype invalidation |
| Java bean public mà Dynalink không thấy | Class/package chưa public/export theo module rules hoặc operation sai namespace | JPMS exports, bean accessors, `PROPERTY` vs `ELEMENT` |
| Linker tùy biến không được gọi/luôn trả null | Chưa set prioritized, check receiver sai, chưa gỡ NamedOperation wrapper | `setPrioritizedLinker`, `NamedOperation.getBaseOperation` |
| Site trả error ngôn ngữ không nhất quán | Fallback missing-member policy thiếu thiết kế | Custom fallback linker, language semantics |

**Nguyên tắc đo lỗi:** log tối thiểu `operation`, `descriptor.getMethodType()`, receiver runtime class (khi có), linker nào xử lý, guard result và số relink; tránh log toàn bộ object/user data không cần thiết. Đối với code engine chạy dữ liệu bên ngoài, giới hạn kích thước log và ẩn secrets.

### Mẫu debug nhỏ (snippet không độc lập)

~~~java
CallSiteDescriptor desc = request.getCallSiteDescriptor();
Object receiver = request.getReceiver();

System.out.println("operation=" + desc.getOperation());
System.out.println("siteType=" + desc.getMethodType());
System.out.println("receiverType=" +
    (receiver == null ? "null" : receiver.getClass().getName()));
~~~

Đoạn này giả định biến `LinkRequest request` tồn tại bên trong `GuardingDynamicLinker.getGuardedInvocation(...)`. Không lấy `request.getReceiver()` làm bằng chứng compiler đã biết kiểu receiver tại compile time: đây là **object runtime** của một lần yêu cầu link.

## 16. Những ngộ nhận hay gặp

- “`invokedynamic` và Dynalink là cùng một thứ.” — Không. Opcode/protocol thuộc JVM; Dynalink là thư viện hỗ trợ link operations.
- “Dynalink tự parse ngôn ngữ và chạy script.” — Không. Nó không có grammar, parser hay evaluator hoàn chỉnh.
- “Chỉ JavaBeans mới dùng được Dynalink.” — Không. Custom `GuardingDynamicLinker` có thể hiểu object model của ngôn ngữ khác.
- “Dùng Java field access thông thường cũng sẽ được Dynalink cache.” — Không. Compiler phải tạo/cấu hình site dùng Dynalink.
- “`DynamicLinker.link` đã tìm target cho tất cả receiver ngay lúc setup.” — Không. Target thực tế thường được link lúc site nhận runtime arguments.
- “Property name của `NamedOperation` vẫn phải truyền qua một tham số runtime riêng.” — Không. Với GET/SET, tên đã được cố định và không còn xuất hiện trong site signature.
- “Có thể gọi `NamespaceOperation.contains` trực tiếp trên outer NamedOperation.” — Không theo contract đó; trước hết gỡ wrapper bằng `NamedOperation.getBaseOperation`.
- “`RelinkableCallSite` interface có `dynamicInvoker()`.” — Không. Method này thuộc class `CallSite`; các concrete implementations sẵn có kế thừa CallSite.
- “Guard chỉ cần kiểm tra class trong mọi object model.” — Không. Nếu shapes/prototypes thay đổi, class-only guard có thể quá yếu.
- “`ChainedCallSite` luôn nhanh hơn `SimpleRelinkableCallSite`.” — Không, phụ thuộc polymorphism tại site và guard cost.
- “`setPrioritizedLinker` làm JavaBeans fallback biến mất.” — Không mặc định; built-in BeansLinker vẫn có thể xử lý object khi custom linker trả null.
- “`requires jdk.dynalink` cho phép đọc mọi Java member trong package private.” — Không. Java visibility/JPMS vẫn áp dụng.
- “Không link được một member luôn phải trả null.” — Không, language runtime phải quyết định missing-member semantics.
- “`MethodHandle.invokeExact` tự widen/cast mọi argument.” — Không; call-site descriptor phải khớp chính xác.
- “Dynalink tự làm sandbox cho code động.” — Không. Nó không chặn CPU, I/O, reflection, network hay class loading của code mà engine cho phép thực thi.
- “Một site cho receiver type A sẽ bị liên kết vĩnh viễn với A.” — Không. Relinking/guards giúp xử lý type B, C... ở cùng site.

## 17. Bài tập tự kiểm tra

**Câu 1.** Một DSL có expression `obj.color` với receiver lúc chạy có thể là `Person` hoặc `Map`. Dynalink đóng vai trò gì?

**Đáp án:** Biểu diễn operation đọc property/element, chọn guarding linker theo receiver và relink target khi receiver không còn thỏa guard. DSL vẫn phải định nghĩa rõ liệu Map dùng `PROPERTY` hay `ELEMENT` namespace.

**Câu 2.** Vì sao site `GET PROPERTY name` với `NamedOperation` có type `(Object)Object` thay vì `(Object,String)Object`?

**Đáp án:** Tên property `name` đã được cố định trong operation metadata. Chỉ receiver là dynamic argument tại invocation; return là Object.

**Câu 3.** `DynamicLinkerFactory` mặc định có linker nào giúp Java interoperability?

**Đáp án:** `BeansLinker` trong fallback configuration, cho phép link các operation thông dụng trên JavaBeans, Java arrays/List/Map và nhiều Java public members.

**Câu 4.** Custom linker trả null trong `getGuardedInvocation` có phải báo đã liên kết thành công với target null không?

**Đáp án:** Không. Null nghĩa linker đó **không xử lý** operation và cho phép thử các linkers tiếp theo. Nếu không ai xử lý, site có thể ném `NoSuchDynamicMethodException` lúc invocation.

**Câu 5.** `SimpleRelinkableCallSite` và `ChainedCallSite` khác nhau ở điểm nào?

**Đáp án:** Simple giữ một guarded invocation; Chained giữ một chuỗi guarded invocations (mặc định tối đa 8). Chained có thể reuse target cho type đã gặp, nhưng chi phí/hiệu năng tùy workload.

**Câu 6.** Vì sao `DynalinkCustomDemo` có `simpleLinks=2` và `chainLinks=1`?

**Đáp án:** Chuỗi receiver là DynRecord→JavaBean→DynRecord. Simple thay target khi chuyển JavaBean, nên DynRecord quay lại phải relink. Chained giữ guard cho DynRecord trước đó nên không cần custom link mới ở lượt thứ ba.

**Câu 7.** `MethodHandle.invokeExact` với site `(Object)Object` gán kết quả trực tiếp dưới `String` có được không?

**Đáp án:** Nếu cast ở call site thành `String` thì return descriptor không khớp `Object`, gây `WrongMethodTypeException`. Nhận `Object` trước hoặc dùng API conversion có kiểm soát.

**Câu 8.** `requires jdk.dynalink` trong named module có tự khiến default BeansLinker đọc được public bean ở package không exported không?

**Đáp án:** Không. Readability của module API và export/visibility của bean package là hai kiểm tra khác nhau. Cần thiết kế exposure phù hợp.

**Câu 9.** Nếu object có thể đổi prototype/shape sau khi site đã link, nên bổ sung gì?

**Đáp án:** Guard kiểm tra shape/version hoặc invalidate `SwitchPoint`/target khi assumptions thay đổi; class-only guard có thể không còn đúng.

**Câu 10.** Dùng Dynalink trong interpreter không có bytecode `invokedynamic` được không?

**Đáp án:** Được. Interpreter có thể gắn một `CallSite` cho mỗi AST operation và gọi `dynamicInvoker()`. Nhưng lúc đó là sử dụng Dynalink qua Java APIs, không phải chứng minh interpreter đã sinh opcode indy.

**Câu 11.** `BeansLinker` được dùng cho object model tự định nghĩa mà không có Java field/getter tương ứng, chỉ cần class public thôi có đủ không?

**Đáp án:** Không. Phải định nghĩa linker riêng hoặc adapter mapping phù hợp, rồi đưa nó vào pipeline của `DynamicLinkerFactory`.

**Câu 12.** Dynalink có bảo đảm một site khi chạy trên các receiver khác nhau sẽ luôn không có cache misses không?

**Đáp án:** Không. Guards có thể fail, site relink, cache chain có giới hạn, và assumptions có thể bị invalidate. Đó chính là lý do cần cấu hình và đo lường chiến lược call site.

## 18. Tài liệu Java SE 17 chính thức

- Module `jdk.dynalink` — mục tiêu, example architecture, language-specific linkers, BeansLinker và interoperability: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/module-summary.html
- `DynamicLinker` — `link(RelinkableCallSite)` và relink mechanism: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinker.html
- `DynamicLinkerFactory` — prioritized/fallback linkers, class loader discovery, relink policy: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/DynamicLinkerFactory.html
- `CallSiteDescriptor`, `Operation`, `StandardOperation`, `StandardNamespace`, `NamedOperation`, `NamespaceOperation`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/package-summary.html
- `SimpleRelinkableCallSite` — monomorphic inline cache: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/support/SimpleRelinkableCallSite.html
- `ChainedCallSite` — polymorphic inline cache, mặc định tối đa 8 entries: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/support/ChainedCallSite.html
- `GuardingDynamicLinker`, `LinkRequest`, `GuardedInvocation`, `LinkerServices`: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/linker/package-summary.html
- `BeansLinker` — Java properties, methods, arrays/List/Map và public access: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.dynalink/jdk/dynalink/beans/BeansLinker.html
- `java.lang.invoke` — MethodHandles, MethodType, CallSite và invokedynamic: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/package-summary.html

**Ghi nhớ:** `invokedynamic` là cơ chế liên kết ở mức JVM; `java.lang.invoke` biểu diễn MethodHandles/CallSites; còn `jdk.dynalink` là tầng **diễn giải thao tác cấp cao, chọn guarding linker và quản lý relink/cache** để một bộ thực thi ngôn ngữ động có thể xử lý nhiều kiểu receiver và liên thông với Java objects. Muốn dùng đúng phải thiết kế **operation semantics, guard validity, access rights, cache policy và error behavior**; Dynalink không tự quyết định những điều đó thay cho ngôn ngữ của bạn.