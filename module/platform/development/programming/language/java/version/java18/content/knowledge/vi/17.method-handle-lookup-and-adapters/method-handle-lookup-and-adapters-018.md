# Cache handle và adapter theo Class, chữ ký, quyền truy cập và vòng đời class loader

> **Chương:** Lookup và adapter  
> **Module:** `JAVA_VERSION_JAVA18`  
> **Mục tiêu:** Thiết kế cache `MethodHandle` và adapter theo `Class<?>`, chữ ký `MethodType`, dạng member và quyền `Lookup`; sử dụng `static final`, `ClassValue` hoặc cache theo vòng đời plugin một cách có cơ sở; tránh rò quyền private và rò class loader trên JDK hiện đại.
>
> **Phạm vi:** `MethodHandle` và `MethodHandles.Lookup` là API công khai từ trước Java 18. JEP 416 (Java 18) tái triển khai core reflection bằng method handles; điều đó không biến mọi handle thành cache toàn JVM hoặc thay đổi access checks. Bài chỉ đề cập các API vẫn dùng hiện nay, không dùng `sun.*`/`jdk.internal.*` hoặc cơ chế reflection legacy.

## 1. Vấn đề: không thể cache handle chỉ theo tên method

Framework serializer, mapper, dependency injection hoặc plugin loader có thể cần tìm method động:

~~~java
MethodHandle label = MethodHandles.publicLookup().findVirtual(
        type, "label", MethodType.methodType(String.class));
~~~

Nếu tra cứu lại cho mỗi request, có thể lặp công việc lookup và tạo adapter không cần thiết. Nhưng một map keyed bằng chuỗi `"label"` là không đủ, bởi vì:

- Hai class khác nhau có cùng tên method.
- Hai class loader có thể định nghĩa **hai Class khác nhau** với cùng binary name.
- Cùng tên method nhưng overload khác tham số hoặc return descriptor.
- `static`, instance, constructor và field accessor có cách lookup khác nhau.
- Caller cần adapter với `MethodType` khác nhau.
- Một lookup có quyền private, lookup khác chỉ có quyền public.
- Một plugin đã unload nhưng map sống lâu vẫn giữ MethodHandle/Class của plugin.

Mục tiêu không đơn thuần là tăng cache-hit rate. Cache phải **đúng target, đúng contract, đúng authority và đúng lifetime**.

Một cache sai có thể gây `WrongMethodTypeException`, `ClassCastException`, gọi nhầm method hoặc tạo lỗ hổng do chia sẻ privileged handle.

## 2. Phân biệt lookup, adaptation và invocation

~~~text
Input: Class + name + descriptor + operation + quyền
                     |
               Lookup.find...
                     |
                     v
              Target MethodHandle
                     |
                asType / bindTo /
               filters / combinators
                     |
                     v
              Adapted MethodHandle
                     |
               invokeExact / invoke
                     |
                     v
                  Kết quả
~~~

Ba công đoạn có tính chất riêng:

| Công đoạn | Vai trò | Caching có ích khi nào |
|---|---|---|
| Lookup | Tìm member và kiểm tra Java/module access | Thành viên được dùng nhiều lần |
| Adaptation | Xây handle có kiểu hoặc pipeline chuyển đổi phù hợp | Adapter có tham số/kiểu ổn định |
| Invocation | Gọi target, chuyển đối số, xử lý kết quả và exception | Vẫn phải chạy mỗi lần; cache không bỏ qua thao tác |

Một `MethodHandle` được tạo bằng `findVirtual` không giống adapter trả về bởi `asType`. Nếu cache target nhưng mỗi lần vẫn tạo `asType` mới, phần adaptation setup có thể vẫn lặp lại. Ngược lại, cache adapter mà key thiếu target identity có thể trả handle gọi sai method.

### 2.1. Caching không làm đổi ngữ nghĩa

Ví dụ target có type `(Counter,int)int`, adapter có type `(Object,Integer)Integer`:

~~~text
Object receiver -> cast Counter
Integer value  -> unbox int
invoke Counter.add(int)
int result     -> box Integer
~~~

Adapter thực hiện conversion khi gọi. Cache adapter không làm bỏ qua cast, unboxing, boxing, hay quyền truy cập đã được xác nhận lúc lookup.

## 3. MethodType và dạng member là phần thiết yếu của khóa

`java.lang.invoke.MethodType` chứa return type và các parameter types. Mỗi kiểu `Class<?>` trong descriptor có runtime identity, không chỉ tên chuỗi.

~~~java
MethodType a = MethodType.methodType(int.class, int.class);
MethodType b = MethodType.methodType(long.class, long.class);

System.out.println(a); // (int)int
System.out.println(b); // (long)long
~~~

`methodType(returnType, parameters...)` đặt return type đầu tiên trong factory, nhưng `toString()` hiển thị `(parameters)return`.

### 3.1. findVirtual đưa receiver vào resulting handle

Ví dụ:

~~~java
public final class Counter {
    public int add(int delta) { return delta; }

    public static int twice(int value) { return value * 2; }

    public Counter(int initial) {}
}
~~~

Tra cứu instance method:

~~~java
MethodHandle virtual = lookup.findVirtual(
        Counter.class,
        "add",
        MethodType.methodType(int.class, int.class));
~~~

Descriptor dùng để tìm member là `(int)int`, nhưng `virtual.type()` là `(Counter,int)int`. Receiver được thêm ở **đầu** resulting handle type.

Tra cứu static method:

~~~java
MethodHandle statik = lookup.findStatic(
        Counter.class,
        "twice",
        MethodType.methodType(int.class, int.class));
~~~

`statik.type()` là `(int)int`, không có receiver.

Tra cứu constructor:

~~~java
MethodHandle ctor = lookup.findConstructor(
        Counter.class,
        MethodType.methodType(void.class, int.class));
~~~

Descriptor truyền vào `findConstructor` có return `void`; resulting handle của constructor có type `(int)Counter`.

Field getter cũng có dạng riêng: instance getter `(Counter)int`, static getter `()int`. Vì vậy, operation kind là một phần của định danh lookup.

### 3.2. Bảng định danh

| Operation | Lookup API | Giá trị cần nằm trong key |
|---|---|---|
| Instance method | `findVirtual` | Owner, name, declared method type |
| Static method | `findStatic` | Owner, name, declared method type |
| Constructor | `findConstructor` | Owner, constructor descriptor |
| Instance field getter | `findGetter` | Owner, field name, field type |
| Static field getter | `findStaticGetter` | Owner, field name, field type |
| Field setter | `findSetter`/`findStaticSetter` | Owner, field name, field type, kind |
| Special invocation | `findSpecial` | Owner, name, descriptor, special caller/authority |

Không gom các operation khác nhau vào một key chỉ vì resulting handle có type giống nhau.

## 4. Các chiều của cache key

Một key logic thường phải xét:

| Chiều | Ví dụ | Lý do |
|---|---|---|
| Owner `Class<?>` | `Customer.class` | Định danh type và defining loader |
| Member name | `"score"`, `"read"` | Xác định member |
| Operation kind | `VIRTUAL`, `STATIC`, `GETTER` | Tránh lookup nhầm dạng thành viên |
| Declared descriptor | `MethodType` hoặc field type | Overload, return, parameter types |
| Adapter descriptor | `(Object)Object` | Caller yêu cầu type khác |
| Adapter pipeline | `asType`, bound receiver, filter | Cùng signature vẫn có thể khác semantics |
| Lookup authority | Public/private, caller/module/special caller | Không rò privileged capability |
| Owner generation | Plugin/schema version khi cần | Invalidation đúng khi cấu hình thay đổi |

Không nhất thiết tất cả đều có trong một Java record. Ví dụ khi `ClassValue` đã phân vùng theo owner, key trong map per-class có thể bỏ field owner. Khi cache chỉ tạo handle bằng `publicLookup()`, authority là hằng theo phạm vi cache.

**Nguyên tắc:** Chỉ bỏ một chiều của key khi chiều đó **thật sự bất biến** trong toàn scope cache.

### 4.1. Key cho public methods có owner ngầm

~~~java
enum Kind { VIRTUAL, STATIC }

record Key(
        String name,
        MethodType declaredType,
        MethodType exposedType,
        Kind kind) {}
~~~

Owner được cung cấp qua `ClassValue.get(owner)`. Mọi entry đều dùng `MethodHandles.publicLookup()`.

Key này đủ cho ví dụ public `findStatic` và `findVirtual`, nhưng **không** hỗ trợ private lookup, constructor, findSpecial hay dynamic filters. Khi mở rộng chức năng cần mở rộng key hoặc tách registry tương ứng.

## 5. Class identity không đồng nghĩa binary name

Trong JVM, class được nhận diện bằng **binary name và defining class loader**. Hai class loader có thể định nghĩa hai type tên `plugin.Handler`:

~~~text
Plugin loader A                      Plugin loader B
      |                                    |
      v                                    v
Class A: plugin.Handler             Class B: plugin.Handler
      |                                    |
      v                                    v
Handle nhận receiver Class A         Handle nhận receiver Class B
~~~

Vì vậy:

~~~java
classA != classB
classA.getName().equals(classB.getName()) // true
~~~

là tình huống có thể xảy ra khi hai loader định nghĩa cùng binary name.

Cache này không đủ:

~~~java
String key = type.getName() + "#" + methodName;
~~~

Nếu lấy nhầm handle của Class A để gọi object Class B, có thể xảy ra lỗi kiểu hoặc adapter mismatch. Đừng tự ghép tên loader + tên class để thay object `Class`: tên loader không phải định danh duy nhất đáng tin.

### 5.1. MethodType cũng mang type identity

Một descriptor `(plugin.Model)String` có thể chứa `Class<?>` của loader A hoặc B. Dù chuỗi in giống nhau, hai descriptor không tương đương về runtime type identity.

Dùng trực tiếp `MethodType` với các `Class<?>` thật trong key. Nếu dùng serialize key qua text, phải giải quyết riêng quá trình tải type trong đúng loader và trust context.

## 6. Quyền Lookup là ranh giới an toàn của cache

`MethodHandles.Lookup` là object mang lookup class, modes và quyền truy cập theo Java language access và JPMS. Nó không chỉ là factory vô trạng thái.

| Lookup | Phạm vi sử dụng |
|---|---|
| `MethodHandles.publicLookup()` | Member public mà public lookup được phép truy cập |
| `MethodHandles.lookup()` | Quyền của class đang gọi `lookup()` |
| `MethodHandles.privateLookupIn(target, caller)` | Truy cập private target khi đủ điều kiện lookup/JPMS |
| `lookup.in(type)` | Di chuyển/giới hạn lookup theo API; không tự sinh thêm quyền |

`findVirtual`/`findStatic` có thể ném `NoSuchMethodException` hoặc `IllegalAccessException`. Hai lỗi này có nghĩa khác nhau: không tìm thấy đúng descriptor và không có quyền sử dụng member.

### 6.1. JPMS exports và opens

Với named modules:

- `exports p` cho phép truy cập public APIs trong package theo module access rules.
- `opens p to framework.module` cho phép deep reflection/private lookup có chủ đích theo các điều kiện bổ sung.
- `privateLookupIn` không mặc nhiên thành công cho mọi class: caller cần đủ lookup modes, module readability và openness.

Ví dụ:

~~~java
module customer.model {
    exports com.example.customer.api;
    opens com.example.customer.internal to mapper.framework;
}
~~~

Module `mapper.framework` có thể được cấp quyền tra cứu sâu tới package internal nếu đủ điều kiện. Module khác không tự nhận quyền đó.

### 6.2. MethodHandle là capability sau khi lookup thành công

Một handle đã được tạo hợp lệ có thể được truyền tới code khác và tiếp tục cho phép gọi target tương ứng; quyền truy cập không đơn giản bị kiểm tra lại theo từng consumer giống một lượt `Lookup.findVirtual` mới.

Đây là lý do cache có thể làm **rò quyền**:

1. Component A có private lookup và lấy handle tới method nhạy cảm.
2. A lưu handle trong một global registry keyed chỉ theo `Class` và tên method.
3. Component B chỉ có public authority nhưng lấy cùng entry.
4. B nhận capability gọi target private qua handle đã được A tạo.

`asType` không hạ quyền của handle. Dù adapter expose signature `(Object)Object`, nó vẫn gọi cùng target.

**Quy tắc thiết kế:** Public cache chỉ tạo những public handles được phép chia sẻ. Private cache nằm trong trusted component, không trả privileged handles cho untrusted caller.

### 6.3. lookupModes không phải token quyền đầy đủ

Không dùng riêng `lookup.lookupModes()` làm authority key. Hai `Lookup` có cùng modes vẫn có thể khác lookup class, module, protected receiver restrictions và special-caller context.

Nếu nhiều trust domains cần dùng cache, ưu tiên **tách cache theo owner/trust domain** và kiểm soát API trao capability. Không nhận một `Lookup` arbitrary từ request rồi cache kết quả thành tài nguyên dùng chung.

## 7. Member cố định: static final là lựa chọn đơn giản

Khi target được biết tại thời điểm viết code:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public final class FixedHandle {
    public static int twice(int value) {
        return value * 2;
    }

    private static final MethodHandle TWICE = findTwice();

    private static MethodHandle findTwice() {
        try {
            return MethodHandles.lookup().findStatic(
                    FixedHandle.class,
                    "twice",
                    MethodType.methodType(int.class, int.class));
        } catch (NoSuchMethodException | IllegalAccessException failure) {
            throw new ExceptionInInitializerError(failure);
        }
    }

    public static void main(String[] args) throws Throwable {
        int result = (int) TWICE.invokeExact(21);
        System.out.println(result);
    }
}
~~~

Kết quả:

~~~text
42
~~~

Lợi ích: lookup một lần, target ổn định, có thể giúp JIT chuyên biệt hóa call site. Nhưng `static final MethodHandle` không phải Java compile-time constant; JIT optimization phụ thuộc runtime và workload.

Nếu lookup sai, class có thể thất bại lúc khởi tạo vì `ExceptionInInitializerError`. Đây là fail-fast rõ ràng nhưng có trade-off về startup. Không thay lỗi này bằng `null` để chương trình trễ lỗi sang `NullPointerException` không có ngữ cảnh.

Nếu có thể gọi trực tiếp `twice(21)` mà không cần reflection/dynamic dispatch, lời gọi Java thông thường thường dễ bảo trì hơn.

## 8. ClassValue cho member phụ thuộc runtime Class

`ClassValue<T>` là cơ chế Java tiêu chuẩn gắn một giá trị tính toán với từng `Class<?>`. Với mapper xử lý class bất kỳ:

~~~text
Class A -> ClassValue.get(A) -> handle A
Class B -> ClassValue.get(B) -> handle B
Class C -> ClassValue.get(C) -> handle C
~~~

`ClassValue` không buộc framework giữ một strong-key global map `Map<Class<?>, ...>` để tìm dữ liệu.

### 8.1. Ví dụ ClassValueHandleDemo.java

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Objects;

public final class ClassValueHandleDemo {
    public static final class Product {
        public String label() {
            return "Sản phẩm Java";
        }
    }

    // Chỉ dùng publicLookup: cache không cấp quyền private.
    private static final ClassValue<MethodHandle> LABELS =
            new ClassValue<>() {
                @Override
                protected MethodHandle computeValue(Class<?> type) {
                    try {
                        MethodHandle exact =
                                MethodHandles.publicLookup().findVirtual(
                                        type,
                                        "label",
                                        MethodType.methodType(String.class));

                        // Từ (Product)String thành (Object)String.
                        return exact.asType(
                                MethodType.methodType(
                                        String.class, Object.class));
                    } catch (NoSuchMethodException
                             | IllegalAccessException failure) {
                        throw new IllegalArgumentException(
                                "No accessible public label() on "
                                        + type.getName(), failure);
                    }
                }
            };

    public static String label(Object target) throws Throwable {
        Objects.requireNonNull(target, "target");
        MethodHandle handle = LABELS.get(target.getClass());
        return (String) handle.invokeExact(target);
    }

    public static void main(String[] args) throws Throwable {
        Product product = new Product();

        System.out.println(label(product));
        System.out.println(label(product));

        MethodHandle a = LABELS.get(Product.class);
        MethodHandle b = LABELS.get(Product.class);
        System.out.println("sameCachedHandle=" + (a == b));
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac -encoding UTF-8 --release 18 -d out ClassValueHandleDemo.java
java -cp out ClassValueHandleDemo
~~~

Kết quả dự kiến:

~~~text
Sản phẩm Java
Sản phẩm Java
sameCachedHandle=true
~~~

Code có ràng buộc: class và method `label()` phải public, được public lookup nhìn thấy, không có argument và trả `String`. Với named module không exports, `publicLookup` có thể không truy cập được dù member khai báo `public`.

### 8.2. computeValue không phải "exactly once"

Theo contract `ClassValue`, hai thread cạnh tranh có thể thực thi `computeValue` nhiều lần cho cùng type, dù cuối cùng cache lưu một giá trị tương ứng.

Vì vậy:

- Không đặt side effect không thể lặp trong `computeValue`.
- Không đếm số lần compute như số cache miss tuyệt đối.
- Tránh mở socket, đăng ký listener hoặc cấp resource chưa có cleanup.
- Nếu `computeValue` ném exception, `get` thất bại; lần `get` sau có thể tính lại.
- `ClassValue.remove(type)` cho phép invalidation có chủ đích, nhưng không tự kết thúc các invocation đang chạy.

`ClassValue` tự phân vùng theo `Class`, **không tự phân vùng theo caller quyền public/private**.

## 9. Cache nhiều handle và adapter cho một Class

Một class có thể có nhiều member. Có thể đặt `ConcurrentHashMap<Key, MethodHandle>` bên trong `ClassValue`:

~~~text
Class owner
  |
  v
ClassValue.get(owner)
  |
  +-- Key(name, declaredType, exposedType, kind)
  |        -> MethodHandle
  |
  +-- Key(...) -> MethodHandle
~~~

Ví dụ dưới đây chỉ hỗ trợ public virtual/static methods. Key có member name, declared method type, adapter type và kind. Owner và authority đã được cố định tại scope của cache.

### 9.1. MethodHandleCacheDemo.java

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.concurrent.ConcurrentHashMap;

public final class MethodHandleCacheDemo {

    public static final class Fixture {
        public int triple(int number) {
            return number * 3;
        }

        public static String surround(String text) {
            return "[" + text + "]";
        }
    }

    private enum Kind {
        VIRTUAL, STATIC
    }

    private record Key(
            String name,
            MethodType declaredType,
            MethodType exposedType,
            Kind kind) {}

    private static final ClassValue<ConcurrentHashMap<Key, MethodHandle>>
            PUBLIC_CACHE = new ClassValue<>() {
                @Override
                protected ConcurrentHashMap<Key, MethodHandle> computeValue(
                        Class<?> type) {
                    return new ConcurrentHashMap<>();
                }
            };

    private static MethodHandle cachedPublic(Class<?> owner, Key key) {
        return PUBLIC_CACHE.get(owner).computeIfAbsent(key, k -> {
            try {
                MethodHandles.Lookup lookup =
                        MethodHandles.publicLookup();

                MethodHandle target = switch (k.kind()) {
                    case STATIC -> lookup.findStatic(
                            owner, k.name(), k.declaredType());
                    case VIRTUAL -> lookup.findVirtual(
                            owner, k.name(), k.declaredType());
                };

                return target.asType(k.exposedType());

            } catch (NoSuchMethodException
                     | IllegalAccessException failure) {
                throw new IllegalArgumentException(
                        "Cannot resolve public " + k.kind()
                                + " method " + owner.getName()
                                + "." + k.name(), failure);
            }
        });
    }

    public static void main(String[] args) throws Throwable {
        Key virtualKey = new Key(
                "triple",
                MethodType.methodType(int.class, int.class),
                MethodType.methodType(
                        Integer.class, Object.class, Integer.class),
                Kind.VIRTUAL);

        MethodHandle virtual =
                cachedPublic(Fixture.class, virtualKey);

        // Target: (Fixture,int)int
        // Adapter: (Object,Integer)Integer
        Object receiver = new Fixture();
        Integer argument = Integer.valueOf(7);
        Integer result = (Integer)
                virtual.invokeExact(receiver, argument);

        System.out.println("virtual=" + result);
        System.out.println("cached="
                + (virtual == cachedPublic(Fixture.class, virtualKey)));

        Key staticKey = new Key(
                "surround",
                MethodType.methodType(String.class, String.class),
                MethodType.methodType(Object.class, Object.class),
                Kind.STATIC);

        MethodHandle staticHandle =
                cachedPublic(Fixture.class, staticKey);

        // Adapter: (Object)Object
        Object input = "vi";
        Object wrapped = (Object) staticHandle.invokeExact(input);
        System.out.println("static=" + wrapped);
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac -encoding UTF-8 --release 18 -d out MethodHandleCacheDemo.java
java -cp out MethodHandleCacheDemo
~~~

Kết quả dự kiến:

~~~text
virtual=21
cached=true
static=[vi]
~~~

**Vì sao kết quả hợp lý?**

- `findVirtual` tìm `triple(int)`, resulting type `(Fixture,int)int`.
- `asType` tạo `(Object,Integer)Integer`: cast receiver, unbox argument, box return.
- `findStatic` tìm `surround(String)`, rồi tạo `(Object)Object`.
- Cùng owner/key dùng chung entry đã cache; đối chiếu identity cho thấy nhận lại cùng object.
- Nếu `exposedType` khác, key khác và adapter phải được tạo theo contract mới.

### 9.2. ConcurrentHashMap có giới hạn gì?

`computeIfAbsent` xử lý entry một cách atomic cho key trong map. Mapping function phải ngắn, không recursive update vào chính map, không chạy side effect nặng.

Nếu lookup ném exception, entry không chứa một valid MethodHandle. Một request sau có thể thử lookup lại. Không mặc định cache failure; đặc biệt `NoSuchMethodException` và `IllegalAccessException` cần được phân biệt.

Ví dụ sử dụng `record` và switch expression, đều là cú pháp đã final trước Java 18 nên dùng được trên JDK hiện đại.

## 10. Adapter type phải là một chiều của khóa

Một target có thể có nhiều adapter:

~~~text
target: (Counter,int)int
             |
      +------+---------------------+
      |                            |
      v                            v
(Object,Integer)Integer       (Counter,int)Object
      |                            |
caller generic                 caller typed
~~~

`MethodHandle.asType` thích nghi parameter từ adapter type sang target type, và return từ target type sang adapter type. Với fixed-arity handle, số tham số phải khớp.

Kết quả adapter có thể được tạo một lần cho mỗi desired `MethodType`, rồi tái dùng `invokeExact` đúng descriptor.

### 10.1. Nếu chỉ có một target nhưng nhiều adapters

Có thể thiết kế hai tầng:

~~~text
Class -> Map<MemberKey, target MethodHandle>
                        |
                        v
              Map<MethodType, adapted MethodHandle>
~~~

Tách hai tầng giúp tái sử dụng target lookup, nhưng làm tăng độ phức tạp bộ nhớ/concurrency. Nếu số adapter ít, một map key gồm member + desired type như ví dụ phần 9 thường dễ hiểu hơn.

### 10.2. Cùng MethodType không có nghĩa cùng adapter semantics

Nếu dùng thêm `bindTo`, `insertArguments`, `filterArguments`, `filterReturnValue`, `permuteArguments`, `asCollector` hoặc `asSpreader`, hai adapter có thể có **cùng type** nhưng gọi operation khác hoặc giữ bound values khác.

Vì vậy, key lúc đó phải chứa đủ **adapter pipeline identity** hoặc cache nằm trong context cố định pipeline. Không thể dùng chỉ `MethodType` để khẳng định hai adapter tương đương.

### 10.3. Lỗi adaptation khác lỗi invocation

`asType` có thể ném `WrongMethodTypeException` khi conversion hoặc arity không phù hợp. Một adapter được tạo hợp lệ vẫn có thể ném `ClassCastException` hoặc `NullPointerException` lúc invoke vì reference runtime sai kiểu hoặc unbox null.

Không cache một adapter lỗi như thể nó là handle dùng được, và không đổi exception conversion thành `NoSuchMethodException` nếu member lookup đã thành công.

**Kết luận phần nền:** Khóa cache phải biểu diễn target thực, adapter type và policy; cache chỉ có ý nghĩa khi quyền và vòng đời đã được xác định rõ.


## 11. Không trộn public cache với privileged cache

Một mô hình dễ kiểm soát:

~~~text
PUBLIC CACHE
  - lookup source luôn là publicLookup()
  - lookup policy cố định, dễ kiểm toán
  - không chứa privileged handles
  - API trả handle chỉ trong phạm vi capability public

PRIVATE CACHE
  - sở hữu bởi trusted component/module
  - Lookup được cấp quyền theo ngữ cảnh riêng
  - không xuất private handle vào registry public
  - có cleanup theo vòng đời owner
~~~

`privateLookupIn` có thể được sử dụng khi module target mở package phù hợp và lookup của caller đủ quyền:

~~~java
MethodHandles.Lookup privateLookup =
        MethodHandles.privateLookupIn(
                targetClass,
                MethodHandles.lookup());
~~~

Đoạn trên là trích đoạn, không có bảo đảm thành công với mọi `targetClass`. Khi điều kiện JPMS không đáp ứng, API ném `IllegalAccessException`.

### 11.1. Vì sao không cache theo lookupModes?

`lookup.lookupModes()` chỉ là bitmask modes. Hai lookup cùng mode bits vẫn có thể khác lookup class, module, protected receiver restrictions hoặc special-caller context. Key như sau không đủ:

~~~java
String key = type.getName() + "|" + lookup.lookupModes();
~~~

Nó vừa không phân biệt Class ở loader khác nhau vừa không định danh đầy đủ authority.

Thay vào đó, cố định authority tại **scope cache**: public cache chỉ sử dụng `publicLookup()`; privileged cache ở một trusted component riêng. Không nhận một `Lookup` bất kỳ từ request rồi chia sẻ kết quả cho mọi caller.

### 11.2. findSpecial và protected receiver

`findSpecial` mang ngữ nghĩa special invocation, phụ thuộc special caller. Với protected instance access ở package khác, receiver cũng có thể bị giới hạn theo caller.

Do đó, một cache generic chỉ keyed bằng `(Class, name, MethodType)` có thể trộn các handle khác semantics. Nếu ứng dụng thực sự cần `findSpecial`, cần cache per-caller/special-caller hoặc có authority domain rõ ràng và test riêng.

## 12. Cache poisoning và quyền nghiệp vụ

Hãy phân biệt **Java access control** với **business authorization**.

Ví dụ:

1. Trusted framework lookup private method của `Customer` thành công.
2. `MethodHandle` được cache trong privileged registry.
3. User A có quyền gọi operation nên framework thực hiện.
4. User B không còn quyền nhưng code xem cache hit rồi gọi luôn handle.

Ở bước 4, lỗi thuộc application authorization. JVM không tự hỏi user B có quyền nghiệp vụ hay không.

Các quy tắc:

- Không dùng cache hit để chứng minh request có quyền.
- Authorize tại boundary của từng operation khi chính sách yêu cầu.
- Không công khai direct privileged handle cho untrusted caller.
- Tách cache metadata khỏi cache quyết định theo user/tenant.
- Thay đổi policy phải khiến quyền nghiệp vụ được đánh giá lại, không phụ thuộc cache lâu đời.

### 12.1. asType không hạ quyền

~~~java
MethodHandle generic =
        privateHandle.asType(
                MethodType.methodType(Object.class, Object.class));
~~~

Nếu kiểu thích nghi hợp lệ, adapter vẫn gọi target đã được lookup cho phép. Chữ ký `(Object)Object` không biến private method thành public cũng không xóa capability của handle.

Muốn giới hạn hành vi, phải thiết kế API, kiểm soát việc cấp handle và authorize request; không dùng type adapter như một security boundary.

## 13. Cache và vòng đời class loader

Một registry toàn cục:

~~~java
static final Map<Class<?>, MethodHandle> GLOBAL =
        new ConcurrentHashMap<>();
~~~

có thể là strong-reference root trong framework sống lâu.

~~~text
Framework Class (loader sống lâu)
       |
       v
  static global registry
       |
       +---- key: PluginClass
       |              |
       |              v
       |        PluginClassLoader
       |
       +---- value: MethodHandle -> PluginClass
~~~

Khi plugin bị gỡ, registry vẫn giữ class và handle, class loader có thể chưa được thu gom. Đây là một vấn đề lifecycle và bộ nhớ, không đơn thuần là cache miss/hit.

### 13.1. ClassValue giúp nhưng không thay plugin manager

`ClassValue` lưu metadata gắn với `Class` và tránh nhu cầu map strong-key toàn cục cho dữ liệu thực sự per-class. Nhưng nó không:

- Dừng threads, executors, callbacks hoặc network connections.
- Hủy đăng ký listener do plugin tạo.
- Xác định đúng policy quyền của mỗi request.
- Buộc GC/class unloading xảy ra vào một thời điểm cố định.
- Tự xóa reference từ các registry khác đang giữ plugin.

Với plugin có thể unload, luôn cần lifecycle manager ở application layer.

### 13.2. ClassValue cũng có thể chứa reference từ loader khác

Nếu ClassValue gắn với class của framework tồn tại lâu nhưng value giữ MethodHandle của plugin:

~~~text
Long-lived FrameworkClass
       |
       v
ClassValue value -> PluginMethodHandle
                       |
                       v
                 PluginClassLoader
~~~

thì value vẫn có thể giữ plugin loader sống. Cần chọn **Class owner** và **scope value** đúng với vòng đời dữ liệu; ClassValue không phải giải pháp tự động cho mọi cross-loader reference.

## 14. Tại sao WeakHashMap<Class, MethodHandle> chưa đủ?

`WeakHashMap` có weak keys nhưng giữ values theo strong references. Nếu value `MethodHandle` giữ class là key, có thể hình thành:

~~~text
Long-lived WeakHashMap
       |
       v
strong value MethodHandle
       |
       v
Class (đồng thời là weak key)
~~~

Class vẫn reachable qua value nên key không được GC như mong đợi. Đổi `ConcurrentHashMap` sang `WeakHashMap` một cách máy móc có thể tạo cảm giác an toàn giả.

`ClassValue` thường phù hợp hơn với per-class metadata. Với registry nhiều loại class và plugin, cần xem reference graph, explicit eviction, strong/weak value strategy và chính sách lifecycle.

### 14.1. Không biến tất cả thành weak reference

Nếu giữ handle bằng weak value nhưng code không giữ reference đủ lâu, handle có thể bị GC rồi phải lookup/adapter lặp lại. Một số cache cần strong reference **trong phạm vi owner còn sống** và cleanup khi owner kết thúc.

Mục tiêu không phải “mọi thứ đều weak”, mà là **strong reference có vòng đời được thiết kế**.

## 15. MethodType và bound values cũng có thể giữ loader

Không chỉ `Class<?>` trong key mới đáng chú ý:

| Thành phần | Có thể giữ reference tới |
|---|---|
| `MethodType` | `Class<?>` của return/parameters |
| Target `MethodHandle` | Declaring class và metadata |
| `bindTo(receiver)` | Receiver object và class loader |
| `insertArguments` | Các bound values |
| `filterArguments`/`filterReturnValue` | Converter handles và class tương ứng |
| Lambda/closure của registry | Captured context, object và loader |
| Exception được cache | Cause/stack/context tùy trường hợp |

Ví dụ:

~~~java
MethodHandle bound = virtualHandle.bindTo(pluginService);
~~~

Nếu `bound` nằm trong global registry, nó có thể giữ cả `pluginService` sống dù plugin không còn nhận request.

### 15.1. Bảng chọn owner cho từng cache

| Tình huống | Owner/cache phù hợp | Cách dọn dẹp |
|---|---|---|
| Một method cố định của ứng dụng | `static final MethodHandle` | Theo vòng đời class |
| Metadata thuần theo runtime class | `ClassValue` | Theo class lifecycle/`remove` khi có lý do |
| Nhiều member của một class | `ClassValue<Map<Key,Handle>>` | Giới hạn entries phù hợp |
| Schema có generation | Per-schema registry | Bỏ registry khi schema đổi |
| Plugin hot reload | Per-plugin context | Explicit stop/unregister/release |
| Adapter bound theo request | Request scope | Kết thúc request |
| Public shared registry lâu dài | Map có eviction/policy | Invalidation và memory budget |

Không đặt adapter chứa receiver user hoặc tenant vào global static cache chỉ vì callable signature giống nhau.

## 16. Khi nào invalidate cache?

Cache cần làm mới khi:

- Plugin cũ unload và plugin mới dùng class loader khác.
- Schema hoặc config chọn method/converter khác.
- Adapter pipeline đổi, dù `MethodType` không đổi.
- Quyền ứng dụng hoặc mapping trust domain thay đổi.
- Runtime-generated class mới thay thế class cũ.
- Test cần tách một cấu hình JDK/module khỏi cấu hình khác.

Với loader mới, object `Class` cũng mới; cache keyed theo Class identity tự phân biệt. Với cache keyed theo string name, entry cũ có thể bị dùng nhầm.

Trong cùng một Class, nếu cấu hình đổi, cần:

1. Đưa version/generation vào key.
2. Hoặc thay registry instance.
3. Hoặc explicit remove/evict entries cũ với quy tắc concurrency rõ ràng.

`ClassValue.remove(type)` bỏ value hiện có trong ClassValue cho type đó; không xóa các external maps khác hoặc chấm dứt lời gọi đã nhận handle cũ.

### 16.1. Class redefinition là tình huống riêng

JVM instrumentation có hỗ trợ class redefinition/retransformation trong những giới hạn nhất định. Không kết luận rằng mọi cached handle chắc chắn giữ implementation cũ hoặc tự cập nhật hoàn hảo với mọi thay đổi. Nếu hệ thống dựa vào instrumentation, kiểm tra spec/JDK implementation và test riêng trên runtime thực tế.

## 17. Thread safety và tránh recursive cache computation

MethodHandle/MethodType có tính immutable theo contract, tiện chia sẻ giữa các thread khi đã được xây đúng. Nhưng cấu trúc cache vẫn cần thread-safe.

Các lỗi cần tránh:

- Dùng mutable `HashMap` đồng thời mà không bảo vệ.
- `computeIfAbsent` gọi lại cùng map/key từ callback.
- `ClassValue.computeValue` có side effect dù có thể được gọi nhiều lần.
- Static initializer gọi vòng sang class khác rồi quay lại.
- Lưu object gắn với một request trong cached singleton.
- Thay cache khi request đang giữ một handle cũ mà không có lifecycle policy.

### 17.1. Giới hạn critical section

Khi đã lấy MethodHandle, nên invoke ngoài lock quản lý cache:

~~~text
lookup cache -> lấy MethodHandle -> thả lock
                                 |
                                 v
                           invoke target
~~~

Target có thể block vì I/O hoặc lock; giữ cache lock xuyên invocation gây nghẽn framework.

`ConcurrentHashMap.computeIfAbsent` có semantics atomic cho entry; callback nên ngắn, không recursive update vào map và không thực hiện external side effect nặng.

### 17.2. Kiểm thử nhiều thread

Cho nhiều task đồng thời lấy cùng owner/key. Xác minh không map corruption, không deadlock, các handle có cùng semantics và không lẫn authority.

Không assert ClassValue `computeValue` đúng một lần. Khi đo, phân biệt số lần factory chạy và số entry đang lưu. Concurrency test cũng **không** tự chứng minh loader có thể unload.

## 18. Có nên cache lookup thất bại?

Các lỗi thường gặp:

- `NoSuchMethodException`: lookup không tìm thấy method/descriptor.
- `NoSuchFieldException`: không thấy field tương ứng.
- `IllegalAccessException`: lookup không được phép.
- `WrongMethodTypeException`: không thể tạo adapter.
- `ClassCastException`/`NullPointerException`: adapter hợp lệ nhưng input runtime không hợp lệ.

Không gom tất cả thành một kết quả `"not found"`.

Nếu lookup dưới `publicLookup()` bị `IllegalAccessException`, điều đó không chứng minh private lookup cũng phải thất bại. Negative cache phải gắn với **quyền và vòng đời** của lookup context.

Nếu framework không có nhiều negative misses, đơn giản nhất là **không cache failure**. Trong ví dụ `computeIfAbsent`, callback ném exception và map không lưu handle; request sau có thể thử lại.

Nếu nhu cầu cache failure được chứng minh bằng số liệu, cần:

- Tách missing và inaccessible.
- Version/TTL/eviction có giới hạn.
- Không tiết lộ private member qua error message.
- Không giữ exception object và classloader context quá lâu.
- Không tái sử dụng denial của domain này cho domain khác.

## 19. Hiệu năng: đo setup và invocation riêng

JEP 416 mô tả cơ hội JIT tối ưu với reflective objects ổn định. Nhưng nó không bảo đảm mọi ClassValue cache nhanh hơn mọi instance field, map hoặc direct call.

| Thành phần | Câu hỏi cần đo |
|---|---|
| Member lookup | Mỗi request có còn `findVirtual`/`findStatic` không? |
| Adapter setup | Có gọi `asType` lặp không? |
| Cache access | `ClassValue.get`/`Map.get` có đáng kể không? |
| Invocation | `invokeExact` ổn định hay đa hình? |
| Boxing/cast | Adapter phải làm những conversion gì? |
| Business target | Method làm I/O hoặc computation nặng không? |
| Memory | Cache có tăng entries theo schema/plugin không? |
| Unloading | Loader cũ có được thu gom khi plugin dừng không? |

### 19.1. Ví dụ toán học

Giả sử request tốn 20 ms và lookup/adaptation chiếm 0,2 ms. Nếu cache loại bỏ hoàn toàn phần này, tổng còn 19,8 ms: chỉ giảm **1%** trong ví dụ giả định.

Đây không phải benchmark trên một JDK cụ thể. Với mapper thao tác hàng triệu property, tỷ trọng lookup có thể cao hơn nhiều; với ứng dụng chờ network, cải thiện có thể khó quan sát.

### 19.2. Benchmark trên runtime thực tế

Sử dụng JMH với warmup/forks/iterations; so sánh direct call, lookup-per-call, cached target, cached adapter và cache-map access. Đo cả cold-start, throughput, allocation, GC và memory/classloader retention.

Ghi JDK vendor/version, VM flags, CPU, OS, framework version và workload. Không dùng vài vòng `System.nanoTime()` để suy tỷ lệ tăng tốc toàn ứng dụng.

## 20. Quy trình plugin hot reload có kiểm soát

Một plugin system có thể quản lý mỗi thế hệ:

~~~text
Framework
   |
   +-- PluginContext generation=1
   |     +-- Loader1
   |     +-- Registry1
   |     +-- Handles / adapters1
   |
   +-- PluginContext generation=2
         +-- Loader2
         +-- Registry2
         +-- Handles / adapters2
~~~

Khi thay plugin:

1. Dừng nhận request mới từ context cũ.
2. Kết thúc/hủy invocation đang chạy theo chính sách.
3. Đóng executor, listener, scheduled task và network resource.
4. Bỏ registry/context khỏi cấu trúc sống lâu của framework.
5. Thả references tới Class, MethodType, MethodHandle và bound receiver.
6. Cho GC cơ hội thu gom loader cũ.
7. Dùng heap profiler/reference graph nếu memory tăng qua nhiều lần reload.

Không assert GC phải xảy ra trong một số mili giây cố định; class unloading không có deadline tất định ở application API thông thường.

## 21. Kế hoạch kiểm thử correctness và bảo mật

### 21.1. Kiểm tra lookup và adaptation

Tạo class fixture có `static String title(String)`, `int add(int)`, overload `int add(int,int)`, constructor nhận int và field `int score`.

Kiểm tra:

1. `findVirtual` descriptor đầu vào không có receiver, resulting handle có receiver.
2. `findStatic` không có receiver.
3. `findConstructor` nhận descriptor return `void`, resulting handle trả object.
4. Cache không trộn overload, getter/setter, static/virtual.
5. Hai exposed `MethodType` khác nhau không trộn entry.
6. `invokeExact` đòi call-site type chính xác.
7. `asType` không hợp lệ báo `WrongMethodTypeException`.
8. Cast/unbox sai runtime báo lỗi tương ứng.

### 21.2. Kiểm tra JPMS và authority

Tạo hai named modules; một module có public exported package và một package internal chỉ mở cho trusted framework.

Kiểm tra public cache không trả private handle, private lookup chỉ thành công khi đủ quyền, và untrusted caller không lấy được capability từ cache khác.

Thay permission nghiệp vụ giữa hai request để xác minh framework vẫn authorize dù handle cached.

### 21.3. Kiểm tra hai defining loaders

Dùng hai class loaders **thật sự định nghĩa riêng** cùng một binary name, không phải hai initiating loaders cùng delegate về một definition.

So sánh Class identity, handle types, kết quả cache và kiểm tra cleanup. Không assert GC xảy ra đúng thời điểm.

### 21.4. Kiểm tra thread safety

Cho nhiều thread truy cập cùng entry, kiểm tra không deadlock/recursive map update và không lẫn dữ liệu theo user. Việc map đúng dưới race không đủ chứng minh classloader không leak.

## 22. Bảng chẩn đoán nhanh

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `WrongMethodTypeException` | Adapter/call-site type không khớp | In `handle.type()` và expected descriptor |
| `ClassCastException` giữa class cùng tên | Class identity khác loader | So sánh `Class<?>` và defining loader |
| `NoSuchMethodException` | Sai overload, declared descriptor hoặc kind | Xem `MethodType` được truyền cho lookup |
| `IllegalAccessException` | Lookup/module không cấp quyền | Xem lookup class, `exports`/`opens` |
| Handle private lộ qua public API | Registry trộn trust domain | Tách public/private cache |
| Gọi nhầm version plugin | Key tên chuỗi hoặc thiếu generation | Dùng Class identity và invalidation |
| Class loader không unload | Global refs, bound receiver hoặc callback | Heap/reference graph |
| Memory tăng sau mỗi reload | Cache không có owner/eviction | Registry per-plugin context |
| Lookup lỗi liên tục | `computeIfAbsent` ném, không lưu entry | Ghi nguyên nhân, cân nhắc failure policy |
| Deadlock khởi tạo | Recursive lookup hoặc class-init cycle | Giảm side effects trong callback |
| Adapter đúng type nhưng sai kết quả | Key thiếu filter/bound identity | Bổ sung pipeline context |
| Cache hit cao nhưng latency ít đổi | Lookup chiếm ít tổng thời gian | Benchmark/profiler end-to-end |

## 23. Hiểu nhầm thường gặp

| Nhầm lẫn | Quy tắc đúng |
|---|---|
| Class name đủ làm key | Class identity phụ thuộc defining loader |
| Method name là toàn bộ key | Cần descriptor, operation kind và adapter |
| `findVirtual` input descriptor chứa receiver | Receiver nằm trong resulting handle |
| `findConstructor` resulting handle trả void | Descriptor đầu vào void, handle trả instance |
| ClassValue tự phân biệt quyền caller | Value gắn theo Class, authority cần scope riêng |
| Cache private handle tự check quyền ở mỗi invoke | Handle là capability được lookup trước đó |
| lookupModes đủ để định danh mọi quyền | Lookup class/module/special caller cũng quan trọng |
| `static final Map` làm entries bất biến | Chỉ field reference là final |
| `WeakHashMap<Class,MethodHandle>` luôn unload | Strong value có thể giữ Class key sống |
| ClassValue.computeValue luôn exactly once | Concurrency có thể tính nhiều lần |
| Adapter key chỉ cần MethodType | Target và bound/filter semantics cũng quan trọng |
| Business authorization không cần sau cache hit | User/request vẫn cần authorize |
| Plugin unload chỉ là xóa một cache | Threads, callbacks và registry khác vẫn giữ refs |
| JEP 416 cho tỷ lệ tăng tốc cố định | Phải đo trên runtime và workload thực |
| asType có thể bỏ qua quyền JPMS | Adapter không cấp quyền lookup mới |

## 24. Bài tập thực hành

### Bài 1 — Khóa cache đầy đủ

Hai class cùng binary name nhưng loader khác, hai overload `read(int)` và `read(String)`, hai adapter types.

**Tiêu chí:** Key không trộn Class identity, overload, kind, exposed type và authority.

### Bài 2 — Chạy ClassValueHandleDemo

Sử dụng code phần 8, compile và thử với hai target classes khác nhau.

**Tiêu chí:** Mỗi Class có entry riêng, adapter `(Object)String` tương thích `invokeExact`.

### Bài 3 — Mở rộng MethodHandleCacheDemo

Thêm static overload hoặc đổi `exposedType` của một key.

**Tiêu chí:** Cache không trả lại adapter cũ với descriptor sai.

### Bài 4 — Public và privileged cache

Tạo module chỉ mở internal package cho một trusted module, thử public lookup và private lookup.

**Tiêu chí:** Không rò private handle vào shared public registry.

### Bài 5 — Classloader retention

Đề xuất reference graph của plugin system và quy trình cleanup theo vòng đời.

**Tiêu chí:** Bao phủ Class, MethodType, MethodHandle, bound values, listeners và threads.

### Bài 6 — Chọn cache phù hợp

Đối chiếu ba trường hợp: member cố định, mapper xử lý class động, plugin hot reload.

**Tiêu chí:** Chọn `static final`, `ClassValue` và per-plugin registry có lý do, không một mẫu cho mọi trường hợp.

### Bài 7 — Benchmark

Dùng JMH so sánh lookup per call, cached target, cached adapter và direct call trên cùng target, cùng workload.

**Tiêu chí:** Báo cáo JDK, warmup, forks, allocation; không suy từ một ns/op ra hiệu năng toàn hệ thống.

## 25. Checklist đưa vào ứng dụng

- [ ] Dùng `Class<?>` identity, không chỉ string class name.
- [ ] Key bao gồm member name, declared descriptor và operation kind.
- [ ] Key có desired adapter `MethodType` khi cần.
- [ ] Bound/filter adapters có pipeline identity hoặc cache scope phù hợp.
- [ ] Public và private caches có ranh giới authority rõ.
- [ ] Không dùng `lookupModes()` đơn độc làm authority key.
- [ ] Không trả privileged handles cho untrusted caller.
- [ ] Vẫn thực hiện business authorization cho request.
- [ ] `static final` dùng cho target cố định phù hợp.
- [ ] `ClassValue` dùng cho metadata thật sự per-class.
- [ ] Không dựa vào WeakHashMap mà bỏ qua strong value references.
- [ ] Kiểm tra cross-loader references trong MethodType/adapter.
- [ ] Có invalidation khi plugin, schema hoặc policy đổi.
- [ ] Cleanup registries, listeners, executors và bound objects.
- [ ] Mapping function thread-safe, không recursive hoặc block lâu.
- [ ] Không giả định ClassValue.computeValue exactly once.
- [ ] Phân biệt missing member và access-denied.
- [ ] Negative cache có scope và expiry nếu cần.
- [ ] Test overload, static/virtual, constructor, adapter types.
- [ ] Test quyền JPMS và hai defining class loaders.
- [ ] Đo lookup, adaptation, invocation và memory riêng khi tối ưu.
- [ ] Không sử dụng reflection internals hoặc kỹ thuật legacy.

## 26. Tài liệu chính thức

1. [MethodHandles.Lookup — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): các loại lookup, caller authority, `findVirtual`, `findStatic`, `findConstructor`, `findSpecial`.
2. [MethodHandles — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandles.html): `publicLookup()`, `privateLookupIn()`, adapter combinators.
3. [MethodHandle — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodHandle.html): `asType`, `type()`, `invokeExact` và bound handles.
4. [MethodType — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/invoke/MethodType.html): method descriptors và type identity.
5. [ClassValue — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/ClassValue.html): per-Class values, concurrent computation và `remove`.
6. [Class — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Class.html): `getClassLoader()` và runtime Class.
7. [ConcurrentHashMap — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): `computeIfAbsent`.
8. [WeakHashMap — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/WeakHashMap.html): weak keys, strong value reference caution.
9. [JEP 416 — Reimplement Core Reflection with Method Handles](https://openjdk.org/jeps/416): bối cảnh Java 18, không thay quyền MethodHandle.
10. [Java Virtual Machine Specification `5](https://docs.oracle.com/javase/specs/jvms/se27/html/jvms-5.html): class loading và initialization.
11. [JMH — Java Microbenchmark Harness](https://github.com/openjdk/jmh): benchmark có warmup/forks và thống kê.

**Kết quả cần đạt:** Bạn thiết kế được cache MethodHandle/adapter theo Class identity, chữ ký, dạng lookup và quyền; chọn đúng `static final`, `ClassValue` hoặc registry per-plugin theo lifecycle; nhận biết reference giữ class loader sống và không đánh đổi quyền hoặc tính đúng đắn chỉ để tăng cache hit. Những nguyên tắc này vẫn còn áp dụng trên JDK hiện đại.
