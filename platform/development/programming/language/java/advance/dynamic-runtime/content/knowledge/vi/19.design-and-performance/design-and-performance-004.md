# 19.4 Khóa bộ nhớ đệm theo `Class` và chữ ký; tránh nhầm kiểu cùng tên từ loader khác

Trong hệ thống Java dùng Reflection, `MethodHandle`, dynamic proxy, serializer hoặc plugin runtime, việc tìm một method/constructor/field theo tên có thể tốn chi phí nếu lặp lại nhiều lần. Cache kết quả lookup thường hữu ích, nhưng **khóa cache sai có thể khiến code gọi nhầm member hoặc nhầm một kiểu từ class loader khác**.

Ví dụ hai plugin cùng cung cấp class tên `plugin.Greeter`, nhưng mỗi plugin chạy bằng **một defining `ClassLoader` riêng**. Hai class có cùng `Class.getName()`, cùng bytecode và cùng text chữ ký nhưng **không phải cùng runtime type**. Một `Method` hoặc `MethodHandle` tìm được từ class của loader A không thể được coi như method của class do loader B định nghĩa.

**Quy tắc trọng tâm:** cache resolution phải dùng **đúng runtime `Class<?>` của owner**, **chữ ký đủ chính xác**, **loại thao tác** (static, virtual, constructor, field getter...) và **ranh giới quyền truy cập/lookup policy**. Không chỉ dùng tên class, tên method hoặc một chuỗi descriptor làm khóa.

Bài học này xây mô hình cache an toàn ở Java 17+, giải thích class identity, `MethodType`, class loader, `ClassValue`, memory leaks, thread safety và quyền của `MethodHandles.Lookup`. Ba chương trình hoàn chỉnh đã được biên dịch bằng `javac --release 17` và chạy kiểm chứng.

## 1. Vì sao phải cache thao tác reflection/runtime lookup?

Một framework có thể nhận request như:

```text
operation = "format"
receiver type = com.example.Service
arguments = [42]
```

Để thực hiện, nó cần tra method thích hợp, kiểm tra quyền, lựa chọn loại invocation và chuẩn bị cách gọi. Ví dụ khi dùng Java Reflection:

```java
// Mã minh họa; Service và receiver cần được khai báo trước.
Method method = Service.class.getMethod("format", int.class);
Object value = method.invoke(receiver, 42);
```

Nếu lookup được lặp trong hàng triệu lượt gọi với **cùng class, cùng method và cùng signature**, một cache có thể giảm công việc tìm kiếm metadata, xây adapter và xử lý lựa chọn member.

Nhưng những thao tác sau **không** thể bị đồng nhất:

- `Service.format(int)` và `Service.format(String)`: cùng tên nhưng khác parameter types.
- `Service.format(long)` static và `Service.format(int)` instance: invocation kind khác nhau.
- `plugin.Greeter` được loader A định nghĩa và `plugin.Greeter` được loader B định nghĩa: cùng binary name nhưng hai `Class<?>` khác nhau.
- Method handle đã được tạo bằng một privileged `Lookup` và lời gọi của consumer chỉ có quyền public: **capability đã được cấp** không nên phát tán tự do.
- Một `MethodHandle` chưa bind receiver và một handle đã `bindTo(specificReceiver)`: cache một bound handle dưới khóa chỉ chứa class có thể làm nhầm object.
- Một `MethodHandle` gốc và adapter `asType`: chúng có thể có kiểu call-site khác nhau, nên nếu cache adapters phải có khóa khác nhau.

**Đúng khóa cache là yêu cầu correctness, không chỉ optimization.** Performance tốt nhưng gọi sai lớp hoặc rò rỉ class loaders là lỗi thiết kế.

## 2. Class identity trong JVM: không chỉ tên lớp

Theo Java Virtual Machine Specification, một non-array class/interface tại runtime được xác định bằng **cặp (binary name, defining loader)**. Vì vậy:

```text
Lớp 1:
  binary name:  plugin.Greeter
  defining loader: LoaderA

Lớp 2:
  binary name:  plugin.Greeter
  defining loader: LoaderB

Tên giống nhau, bytes có thể giống nhau,
nhưng LoaderA != LoaderB -> hai runtime classes khác nhau.
```

Có thể kiểm tra bằng:

```java
// Mã minh họa; classA/classB là Class<?> đã được nạp trước.
System.out.println(classA.getName().equals(classB.getName()));
System.out.println(classA == classB);
System.out.println(classA.getClassLoader() == classB.getClassLoader());
```

Nếu `classA` và `classB` được hai defining loaders riêng định nghĩa từ cùng class file, ba dòng thường là `true`, `false`, `false` như ví dụ đầy đủ ở mục 6.

### 2.1. Binary name giống nhau không có nghĩa kiểu tương thích

Giả sử:

```java
Class<?> a = /* plugin.Greeter từ loader A */;
Class<?> b = /* plugin.Greeter từ loader B */;
```

Một instance tạo bởi `a.getConstructor().newInstance()` không tự là instance của `b`, dù cả hai classes có cùng code và các method names giống nhau. Vì thế:

- `a.isInstance(objectB)` sẽ là `false` nếu objectB được tạo từ class B và không có quan hệ type assignability đặc biệt.
- `Method` lấy bằng `a.getMethod("hello")` không nhận object B làm target instance hợp lệ.
- `MethodHandle` virtual getter/method từ class A có receiver type tương ứng với A, không thể mặc nhiên nhận object B.
- Serialize object và deserialize bằng loader khác có thể dẫn đến type mismatch, nếu framework không giữ đúng type resolution context.

Về mặt JVM, tên chỉ là **danh xưng**, không phải toàn bộ type identity. Khi dùng làm khóa cache, `Class<?>` object biểu diễn identity đã được resolve chính xác.

### 2.2. Defining loader khác initiating loader

Trong cơ chế delegation, một custom loader có thể được yêu cầu load `java.lang.String` rồi **ủy quyền** cho parent/bootstrap loader. Hai initiating loaders khác nhau có thể trả về **cùng `Class<String>`**. Vì thế câu “mỗi lần gọi `loadClass` bằng một loader khác nhau đều tạo kiểu mới” là sai.

- **Defining loader** là loader đã thực sự định nghĩa class.
- **Initiating loader** có thể chỉ chuyển tiếp yêu cầu và nhận class do parent định nghĩa.
- `Class.getClassLoader()` phản ánh defining loader (bootstrap class có thể trả `null`).
- Không dùng object loader yêu cầu load làm đại diện chắc chắn cho class identity.

Ví dụ của bài chủ động để `plugin.Greeter` **ngoài runtime classpath**, vì nếu parent đã tìm thấy class ấy thì hai child loaders có thể đều nhận **một class parent-defined**, làm mất ý nghĩa phép thử.

### 2.3. Runtime package và module không thay thế Class identity

Hai class cùng có text `package plugin;` có thể ở hai loaders khác nhau, dẫn đến runtime package khác nhau và access rules khác nhau. JPMS còn thêm ràng buộc module/readability/exports/opens, nhưng khi cache đối tượng `Class<?>`, bạn đang giữ **runtime type đã được resolve**, bao gồm defining loader/module context của nó.

Dùng `Class.getName()` cùng một chuỗi `module.getName()` cũng **chưa đủ** để suy ra cùng class: nhiều module layers, loaders hoặc môi trường plugin có thể chứa cùng những tên danh nghĩa. Khi API đã đưa `Class<?>`, ưu tiên dùng chính object đó làm khóa hoặc dùng `ClassValue`.

## 3. “Chữ ký” phải hiểu đủ: tên + parameter types + return type + kind

Một method không được xác định đúng chỉ bằng tên `"format"`. Hãy phân biệt:

- **Member name:** `format`, `hello`, `<init>` (constructor ở mức JVM).
- **Parameter types:** `int`, `String`, `long`, thứ tự và số lượng.
- **Return type:** `void`, `int`, `String`, v.v. `MethodType` luôn chứa return type.
- **Invocation kind:** instance virtual, static, interface, special invocation, constructor, field getter/setter; tùy API.
- **Declaring/lookup owner `Class<?>`:** nơi method được tra, ảnh hưởng inheritance và access.
- **Lookup/access context:** quyền của caller và các quy tắc JPMS. Đó là một policy dimension, không chỉ một cặp tên/chữ ký.

Một khóa cache MethodHandle cho những lookup cơ bản có thể là:

```java
enum Kind { VIRTUAL, STATIC }

record Key(Class<?> owner, Kind kind,
           String name, MethodType memberType) {}
```

Đây là **mã khai báo minh họa** trong một Java file có import `java.lang.invoke.MethodType`. Vì đây là `record` Java 17, `equals` và `hashCode` của khóa xét tất cả components. Với component `Class<?>`, equality dựa trên runtime class identity; với `MethodType`, equality xét từng parameter/return `Class<?>`.

Nếu cache chỉ lưu một loại lookup cố định (ví dụ **chỉ public virtual method**), có thể giảm khóa bớt `Kind` bởi vì chính cache/namespace đã xác định kind. Nhưng trong một cache dùng chung cho nhiều kinds, **phải ghi rõ kind**.

### 3.1. `MethodType` là kiểu thao tác, không phải chỉ danh sách tham số

Ví dụ:

```java
MethodType m1 = MethodType.methodType(
        String.class, int.class);

MethodType m2 = MethodType.methodType(
        String.class, String.class);

MethodType m3 = MethodType.methodType(
        Object.class, int.class);
```

Tương ứng:

```text
m1: (int)String
m2: (String)String
m3: (int)Object
```

Cả `m1 != m2` lẫn `m1 != m3` về mặt `MethodType.equals`: trường hợp đầu khác parameter type, trường hợp sau khác return type. Java source bình thường không overload **chỉ bằng return type**, nhưng bytecode có thể chứa bridge/synthetic methods và các tình huống JVM descriptor quan tâm return type. Framework dùng `MethodHandle` cũng cần kiểm tra return type ngay cả khi thao tác business chỉ quan tâm tên method.

### 3.2. `findVirtual` và `findStatic` khác receiver signature

Một điều dễ gây lỗi khi thiết kế khóa:

```java
// Trong class có phương thức instance String format(int):
lookup.findVirtual(Service.class, "format",
        MethodType.methodType(String.class, int.class));

// Trong class có phương thức static String format(long):
lookup.findStatic(Service.class, "format",
        MethodType.methodType(String.class, long.class));
```

Với `findVirtual`, `MethodType` truyền vào lookup mô tả **method member** và **không chứa receiver**. Khi lookup thành công, handle thường có type **có receiver** ở vị trí đầu:

```text
member type cho findVirtual: (int)String
result handle.type():       (Service,int)String
```

Với `findStatic`, không có receiver:

```text
member type cho findStatic:  (long)String
result handle.type():        (long)String
```

**Đừng trộn** member lookup type với resolved handle invocation type khi tạo khóa: nếu API cache nhận `MethodType` của member, hãy định nghĩa rõ đó là type **trước khi lookup**. Nếu cache nhận type của call-site `MethodHandle`, cần chuẩn hóa receiver/adapter trước khi tạo khóa. Một kiểu lẫn lộn gây miss, duplicate entries hoặc `WrongMethodTypeException`.

### 3.3. Generics và erasure

Với phương thức `handle(List<String>)`, runtime parameter `Class<?>` là `java.util.List.class` do type erasure. `List<String>` và `List<Integer>` không có hai `Class<?>` runtime khác nhau và không thể overload chỉ dựa vào generic type argument trong Java source.

- **Dispatch cache ở mức JVM:** dùng erased runtime `Class<?>` và `MethodType` tương ứng.
- **Serializer/validator/DI cache có logic dựa vào generic type:** có thể cần giữ thêm `java.lang.reflect.Type`, annotated types hoặc metadata tham số hóa theo contract framework.

Không cho rằng `MethodType` giữ được toàn bộ Java generic annotations/type arguments; nó giữ **runtime Class types** của arguments và return.

## 4. Những khóa cache dễ sai

| Khóa cache | Vì sao nguy hiểm | Cách thay |
| --- | --- | --- |
| `"plugin.Greeter#hello"` | Bỏ qua defining loader; hai runtime classes cùng tên bị nhập một | Owner `Class<?>` hoặc `ClassValue` |
| `methodName` | Bỏ qua owner và overloads | Kèm owner, full signature, kind |
| `className + methodName + arity` | Hai overload có cùng số argument, khác parameter types | Kèm từng parameter type |
| `className + textDescriptor` | ClassLoader identity bị mất nếu descriptor chứa same-name reference types | Giữ `Class<?>`/`MethodType` đã resolve |
| `owner.getClassLoader() + name` | Một loader định nghĩa nhiều classes; không đủ thông tin về owner, null bootstrap loader | Dùng owner `Class<?>` |
| `Class<?> + name` | Overloads và kind có thể khác | Kèm full member `MethodType` và kind |
| `MethodType` một mình | Không chỉ rõ owner/name/kind | Kèm member identity |
| `MethodHandle.type()` một mình | Nhiều phương thức khác nhau có cùng invocation type | Kèm owner/name/kind |
| `String.valueOf(MethodType)` | Hiển thị kiểu theo tên, không bảo toàn loader identity | Dùng trực tiếp `MethodType` object |
| `ClassValue` nhưng không phân biệt lookup policy | Cache handle có private capability, rồi cho caller không đủ quyền nhận | Tách quyền/trust boundary, giới hạn sharing |
| `owner, signature` cho handle đã `bindTo(receiver)` | Bỏ qua receiver identity; dễ dùng nhầm object | Cache unbound handle hoặc khóa theo bound receiver với lifecycle phù hợp |
| Key adapter chỉ theo underlying method | `asType` target có thể đổi type và conversion semantics | Kèm requested call-site type/adaptation policy |

**Đừng dùng String làm khóa chỉ vì `HashMap<String,...>` dễ serialize.** Một cache runtime có khả năng giữ chính các `Class<?>`/`MethodType` objects thì nên dùng type identity đã được JVM giải quyết. Chuỗi có thể là **log/debug description**, không đủ làm identity.

## 5. Chứng minh: hai `MethodType` có descriptor text giống nhưng không bằng nhau

`MethodType` lưu reference types dưới dạng `Class<?>`. Nếu hai classes có cùng binary name nhưng khác defining loaders:

```java
// Minh họa: a và b là hai Class<?> khác nhau cùng getName().
MethodType first = MethodType.methodType(void.class, a);
MethodType second = MethodType.methodType(void.class, b);
```

Kết quả quan trọng:

```text
first.toMethodDescriptorString()
  == second.toMethodDescriptorString()     // true

first.equals(second)                       // false
```

Cả hai text descriptor đều có thể là `(Lplugin/Greeter;)V` vì descriptor ghi **binary name**, không ghi defining loader object. Nhưng `MethodType.equals` so **Class<?> parameter types**, nên phân biệt `a` và `b`.

**Hệ quả:** việc chuyển `MethodType` thành descriptor String rồi dùng làm khóa có thể **đánh mất identity**. Ngược lại, khi đọc descriptor String bằng `MethodType.fromMethodDescriptorString(descriptor, loader)`, phải cung cấp **loader phù hợp** để resolve các reference types. Cùng descriptor với loaders khác nhau có thể tạo `MethodType` khác nhau.

Đây là vấn đề rất thật ở plugin systems, hot-reload class loaders, application servers và test harness nạp nhiều phiên bản của cùng FQCN.

## 6. Ví dụ hoàn chỉnh 1 — lỗi cache theo tên và cách sửa bằng `ClassValue`

Chương trình này tự định nghĩa **hai bản `plugin.Greeter` từ cùng bytecode** bằng hai class loaders. Nó cố ý tạo một cache sai `Map<String, Method>` để quan sát lỗi khi dùng Method của loader A với instance thuộc loader B. Sau đó dùng `ClassValue<ConcurrentMap<Signature,MethodHandle>>` để cache riêng theo **từng `Class<?>` runtime**.

### 6.1. Cấu trúc file

```text
src/
  plugin/
    Greeter.java
  LoaderCacheDemo.java

build/
  plugin/Greeter.class       # bytes của plugin, KHÔNG đưa vào runtime classpath

runtime/
  LoaderCacheDemo.class
  LoaderCacheDemo$BytesLoader.class
  LoaderCacheDemo$Signature.class
  LoaderCacheDemo$1.class    # anonymous ClassValue
  ...                      # các nested/record classes nếu compiler tạo
```

Đường dẫn file `runtime` ở trên chỉ mang tính minh họa. Không cần tự sao chép từng `$...class` nếu dùng `javac -d runtime` để compiler tạo đầy đủ.

### 6.2. File `src/plugin/Greeter.java`

```java
package plugin;

public class Greeter {
    public String hello() {
        return "greeting";
    }
}
```

### 6.3. File `src/LoaderCacheDemo.java`

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public class LoaderCacheDemo {
    static final class BytesLoader extends ClassLoader {
        private final byte[] bytes;

        BytesLoader(byte[] bytes) {
            super(LoaderCacheDemo.class.getClassLoader());
            this.bytes = bytes.clone();
        }

        @Override
        protected Class<?> findClass(String name) throws ClassNotFoundException {
            if (!name.equals("plugin.Greeter")) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, bytes, 0, bytes.length);
        }
    }

    record Signature(String name, MethodType type) {}

    private static final ClassValue<ConcurrentMap<Signature, MethodHandle>> CACHE =
            new ClassValue<>() {
                @Override
                protected ConcurrentMap<Signature, MethodHandle>
                        computeValue(Class<?> type) {
                    return new ConcurrentHashMap<>();
                }
            };

    private static MethodHandle findPublicVirtual(
            Class<?> owner, String name, MethodType type) {
        Signature signature = new Signature(name, type);
        return CACHE.get(owner).computeIfAbsent(signature, key -> {
            try {
                return MethodHandles.publicLookup()
                        .findVirtual(owner, key.name(), key.type());
            } catch (ReflectiveOperationException error) {
                throw new IllegalStateException("Unable to resolve " + key, error);
            }
        });
    }

    public static void main(String[] args) throws Throwable {
        byte[] classBytes = Files.readAllBytes(Path.of(args[0]));
        Class<?> a = Class.forName(
                "plugin.Greeter", true, new BytesLoader(classBytes));
        Class<?> b = Class.forName(
                "plugin.Greeter", true, new BytesLoader(classBytes));

        System.out.println("same binary name: " + a.getName().equals(b.getName()));
        System.out.println("same Class object: " + (a == b));
        System.out.println("same defining loader: "
                + (a.getClassLoader() == b.getClassLoader()));

        MethodType ta = MethodType.methodType(void.class, a);
        MethodType tb = MethodType.methodType(void.class, b);
        System.out.println("same textual descriptor: "
                + ta.toMethodDescriptorString().equals(tb.toMethodDescriptorString()));
        System.out.println("same MethodType: " + ta.equals(tb));

        Object instanceA = a.getConstructor().newInstance();
        Object instanceB = b.getConstructor().newInstance();
        Map<String, Method> wrongCache = new HashMap<>();
        String keyA = a.getName() + "#hello";
        String keyB = b.getName() + "#hello";
        wrongCache.put(keyA, a.getMethod("hello"));

        try {
            wrongCache.get(keyB).invoke(instanceB);
        } catch (IllegalArgumentException error) {
            System.out.println("wrong name-only cache: IllegalArgumentException");
        }

        MethodType returnString = MethodType.methodType(String.class);
        MethodHandle ha = findPublicVirtual(a, "hello", returnString);
        MethodHandle hb = findPublicVirtual(b, "hello", returnString);

        System.out.println("loader A: " + (String) ha.invokeWithArguments(instanceA));
        System.out.println("loader B: " + (String) hb.invokeWithArguments(instanceB));
        System.out.println("cached A again: " + (ha == findPublicVirtual(
                a, "hello", returnString)));
        System.out.println("cache entries per class: "
                + CACHE.get(a).size() + " / " + CACHE.get(b).size());
    }
}
```

### 6.4. Cách biên dịch/chạy trên Java 17+ (Bash)

Chạy tại thư mục chứa `src`:

```bash
mkdir -p build runtime

javac --release 17 -d build src/plugin/Greeter.java
javac --release 17 -d runtime src/LoaderCacheDemo.java

java -cp runtime LoaderCacheDemo build/plugin/Greeter.class
```

Điểm mấu chốt là **`build` không nằm trong runtime classpath**. `plugin.Greeter` chỉ tồn tại ở bytes được `LoaderCacheDemo` đọc, và parent loader không tìm thấy nó. Khi các `BytesLoader` riêng nhận yêu cầu `plugin.Greeter`, mỗi loader sẽ định nghĩa một bản riêng.

Nếu dùng PowerShell, thay `mkdir -p build runtime` bằng `New-Item -ItemType Directory -Force build,runtime`. Những lệnh `javac` và `java` có thể viết như trên.

### 6.5. Stdout đã xác minh bằng chạy thật

```text
same binary name: true
same Class object: false
same defining loader: false
same textual descriptor: true
same MethodType: false
wrong name-only cache: IllegalArgumentException
loader A: greeting
loader B: greeting
cached A again: true
cache entries per class: 1 / 1
```

### 6.6. Phân tích đúng cơ chế

1. Hai `new BytesLoader(classBytes)` tạo hai defining loaders khác nhau. `Class.forName(...,loader)` gọi đường nạp lớp phù hợp; bởi `Greeter` không có trên parent runtime classpath, mỗi loader định nghĩa một class riêng.
2. `a.getName().equals(b.getName())` trả `true` vì binary name giống nhau.
3. `a == b` và so sánh defining loaders đều `false`. Hai `Class<?>` là hai runtime types khác nhau.
4. `MethodType.methodType(void.class,a)` và tương tự với `b` có cùng descriptor text nhưng `equals` trả `false`: type identity chứa actual resolved classes.
5. Cache sai `Map<String,Method>` lưu Method thuộc owner `a`, nhưng vì `keyA.equals(keyB)`, code lấy chính Method đó rồi gọi trên `instanceB`. Reflection từ chối bằng `IllegalArgumentException`.
6. Cache đúng dùng `ClassValue`: `CACHE.get(a)` và `CACHE.get(b)` là hai maps gắn với hai `Class<?>` khác nhau. `findVirtual` tạo MethodHandles tương ứng với từng owner.
7. `ha.invokeWithArguments(instanceA)` và `hb.invokeWithArguments(instanceB)` đều thành công, trả `greeting`. `invokeWithArguments` được dùng vì type của receiver chỉ biết **động qua `Class<?>`** ở source host; nếu muốn dùng `invokeExact`, caller cần chữ ký tĩnh phù hợp hoặc adapter đã chuẩn hóa.
8. `ha == findPublicVirtual(a,...)` là `true` vì cache hit trong cùng owner và cùng signature.
9. Hai maps đều có một entry; điều đó **không** có nghĩa `a` và `b` đã bị hợp nhất vào một cache entry.

**Giới hạn minh họa:** cache chỉ dùng **`findVirtual` cho public method** và `MethodHandles.publicLookup()`. Vì invocation kind đã cố định bởi riêng hàm `findPublicVirtual`, record `Signature(name,type)` là đủ cho cache cụ thể này. Khi cache nhiều kinds hoặc quyền khác nhau, phải mở rộng khóa hoặc tách namespace.

## 7. Khi cache dùng `Method`, `Constructor`, `Field` và `MethodHandle`

Các loại metadata/handle khác nhau có điểm chung: chúng liên hệ với **declaring class**, method/field name và type.

### 7.1. Reflection `Method`

`Class.getMethod(name,parameterTypes...)` trả public method phù hợp, bao gồm inherited public methods theo contract. `getDeclaredMethod` tra method khai báo trực tiếp trong class. Khóa cache nên phân biệt **lookup policy** (public/inherited hay declared/private) nếu một cache dùng cả hai.

Ví dụ:

```java
record ReflectionMethodKey(
        Class<?> owner,
        String name,
        java.util.List<Class<?>> parameterTypes,
        boolean declaredOnly) {}
```

Đây là khai báo minh họa. Nếu dùng `List<Class<?>>`, phải tạo **immutable copy** khi tạo key (chẳng hạn `List.copyOf(...)`) để khóa không bị thay đổi sau khi đưa vào `Map`. Không dùng raw mutable arrays rồi dựa vào `Object.equals` của array; arrays mặc định so identity chứ không so phần tử.

**Return type:** `getMethod/getDeclaredMethod` chỉ nhận name và parameter types, không nhận return type để lựa chọn từ caller. Nếu một framework cần phân biệt bridge/synthetic hoặc bytecode-level descriptors có return types khác nhau, việc chọn method/kiểm tra return type phải được thiết kế thêm. Caching ở mức `MethodHandle.findVirtual/findStatic` thường tiện vì `MethodType` biểu diễn cả return.

### 7.2. Constructors

Với `Constructor<?>`, khóa thực tế thường là owner `Class<?>` + ordered constructor parameter types + accessibility policy. Với `MethodHandles.Lookup.findConstructor(owner, type)`, `MethodType` đầu vào có return type `void` (để biểu diễn signature constructor) dù resolved handle khi gọi trả object của class mới. Không dùng method-handle type sau resolve một cách máy móc làm key cho `findConstructor` mà không chuẩn hóa.

### 7.3. Fields và VarHandles

Một field lookup phải xét owner, name, **field type**, static/instance kind và access policy. Nếu dùng `Lookup.findVarHandle` hoặc `findStaticVarHandle`, field type phải khớp đúng. Không nên dùng key chỉ là `"count"`, vì field cùng tên có thể xuất hiện ở nhiều lớp và có kiểu khác nhau.

`VarHandle` chứa variable type và coordinate types, đồng thời cho phép nhiều access modes. Nếu cache `VarHandle.toMethodHandle(mode)`, còn phải xét **mode** vì `GET`, `SET`, `COMPARE_AND_SET` có các chữ ký/semantics khác nhau.

### 7.4. MethodHandle adapters

`MethodHandle.asType`, `bindTo`, `insertArguments`, `filterArguments` và các combinators có thể tạo handles **khác nhau** trên cùng underlying method.

- Adapter `asType` phụ thuộc vào **requested `MethodType`** và conversion policy.
- `bindTo(receiver)` gắn một **receiver instance cụ thể**; nếu lưu global under key `Class<?>+name`, có thể gọi sai object.
- `insertArguments` khóa một hoặc nhiều values cụ thể; cache phải xét các bound values/identity hoặc giữ adapter chỉ trong vòng đời chủ sở hữu.
- Một `MethodHandle` có thể đại diện cho nhiều bước xử lý chứ không chỉ một declared method; key cần đại diện được cấu trúc thực tế muốn tái sử dụng.

Nguyên tắc: **cache unbound resolution riêng, tạo per-object/per-request adapters khi cần**, trừ khi bạn có chính sách caching bound handles với lifetime được kiểm soát.

## 8. Ví dụ hoàn chỉnh 2 — cache theo owner, invocation kind và `MethodType`

Chương trình này không dùng custom loaders; nó chứng minh một lớp `Service` có **ba phương thức cùng tên** nhưng khác signature/kind. Cache dùng:

```java
record Key(Class<?> owner, Kind kind,
           String name, MethodType memberType) {}
```

Cần cả bốn components khi cache phải hỗ trợ nhiều loại `Lookup`.

### 8.1. File `SignatureCacheDemo.java`

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public class SignatureCacheDemo {
    public static final class Service {
        public String format(int n) { return "number:" + n; }
        public String format(String text) { return "text:" + text; }
        public static String format(long n) { return "static:" + n; }
    }

    enum Kind { VIRTUAL, STATIC }

    record Key(Class<?> owner, Kind kind, String name, MethodType memberType) {}

    private static final ConcurrentMap<Key, MethodHandle> CACHE =
            new ConcurrentHashMap<>();

    private static MethodHandle resolve(Key key) {
        return CACHE.computeIfAbsent(key, k -> {
            try {
                MethodHandles.Lookup lookup = MethodHandles.publicLookup();
                return switch (k.kind()) {
                    case VIRTUAL -> lookup.findVirtual(
                            k.owner(), k.name(), k.memberType());
                    case STATIC -> lookup.findStatic(
                            k.owner(), k.name(), k.memberType());
                };
            } catch (ReflectiveOperationException error) {
                throw new IllegalStateException("Cannot resolve " + k, error);
            }
        });
    }

    public static void main(String[] args) throws Throwable {
        Service receiver = new Service();
        Key intKey = new Key(Service.class, Kind.VIRTUAL, "format",
                MethodType.methodType(String.class, int.class));
        Key stringKey = new Key(Service.class, Kind.VIRTUAL, "format",
                MethodType.methodType(String.class, String.class));
        Key longKey = new Key(Service.class, Kind.STATIC, "format",
                MethodType.methodType(String.class, long.class));

        MethodHandle intCall = resolve(intKey);
        MethodHandle stringCall = resolve(stringKey);
        MethodHandle longCall = resolve(longKey);

        System.out.println("virtual int: " + (String) intCall.invokeExact(receiver, 7));
        System.out.println("virtual String: "
                + (String) stringCall.invokeExact(receiver, "Lan"));
        System.out.println("static long: " + (String) longCall.invokeExact(9L));
        System.out.println("entries: " + CACHE.size());
        System.out.println("cache hit: " + (intCall == resolve(intKey)));
        System.out.println("int handle type: " + intCall.type());
        System.out.println("long handle type: " + longCall.type());

        try {
            Object wrong = intCall.invokeExact(receiver, 7);
            System.out.println(wrong);
        } catch (WrongMethodTypeException error) {
            System.out.println("wrong return: WrongMethodTypeException");
        }
    }
}
```

Chạy:

```bash
javac --release 17 SignatureCacheDemo.java
java SignatureCacheDemo
```

**Stdout đã kiểm chứng:**

```text
virtual int: number:7
virtual String: text:Lan
static long: static:9
entries: 3
cache hit: true
int handle type: (Service,int)String
long handle type: (long)String
wrong return: WrongMethodTypeException
```

### 8.2. Vì sao có ba entries?

Mỗi `Key` khác về `Kind` hoặc `MethodType`:

- `format(int)`: `VIRTUAL`, member type `(int)String`.
- `format(String)`: `VIRTUAL`, member type `(String)String`.
- `format(long)`: `STATIC`, member type `(long)String`.

Resolved handle của virtual method nhận thêm receiver ở đầu, nên `intCall.type()` là `(Service,int)String`. Static handle không có receiver, nên `longCall.type()` là `(long)String`.

`CACHE.computeIfAbsent` tái sử dụng handle cho một key đã có; đó là lý do `cache hit: true`. Trong ví dụ chạy một thread, entries bằng ba.

### 8.3. Cache đúng nhưng call site vẫn có thể sai

Ở cuối demo:

```java
Object wrong = intCall.invokeExact(receiver, 7);
```

Caller yêu cầu return type `Object`, nhưng `intCall.type()` trả `String`. `invokeExact` yêu cầu **khớp cả argument types và return type**: result object ở runtime sẽ là String không làm static return type tự khớp. Vì vậy ném `WrongMethodTypeException`.

Cache không thể sửa một caller có chữ ký sai. Nếu caller cần return `Object` và chuyển đổi hợp lệ, có thể chủ động tạo adapter `asType` với method type mong muốn, hoặc dùng `invoke`/`invokeWithArguments` phù hợp. Nhưng phải xem conversion semantics chứ không dùng adaptation để che lỗi API contract.

## 9. Cache correctness khác quyền truy cập của `Lookup`

Một `MethodHandle` được tạo bằng `MethodHandles.Lookup` mang theo khả năng gọi thành viên mà lookup lúc tạo được phép truy cập. Có thể một caller không đủ quyền **tự resolve** một private method, nhưng nếu được trao một handle đã được tạo hợp lệ từ nơi có quyền, caller có thể **invoke handle đó** như capability được chuyển giao.

Vì thế:

- Cache key `(owner,kind,name,MethodType)` là nền tảng cho **type correctness**.
- Nhưng nếu hệ thống đa tenant, đa plugin hoặc có quyền caller khác nhau, **access policy/trust boundary** là một dimension riêng.
- Không lưu privileged private handle vào một **global cache công khai** rồi trả cho consumer chỉ nên có quyền public, dù type key hoàn toàn đúng.
- Có thể tách cache `publicLookup` khỏi cache privileged của module/trusted component, hoặc giới hạn API lấy handle theo quyền đã được chứng thực trước.
- `MethodHandles.Lookup` được trao có thể bị giới hạn mode khi chuyển scope/module; không mặc định dùng bất kỳ Lookup nào cũng resolve được cùng member.

### 9.1. `lookupClass()` và `lookupModes()` có giá trị chẩn đoán

Khi gặp `IllegalAccessException`:

```java
// Mã minh họa: lookup và owner đã được truyền vào.
System.out.println(lookup.lookupClass());
System.out.println(lookup.lookupModes());
System.out.println(owner.getModule());
```

Để lấy private handle ở module khác, có thể cần `privateLookupIn`, nhưng điều đó chỉ thành công khi caller có quyền và target module mở package thích hợp. Không dùng cache để bypass JPMS: cache chỉ nên giữ capability trong trust boundary được thiết kế rõ.

### 9.2. Ví dụ hoàn chỉnh 3 — `publicLookup` và private lookup

Tạo file **`AccessScopeDemo.java`**:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;

public class AccessScopeDemo {
    public static final class Vault {
        private String secret() { return "s3"; }
        public String open() { return "public"; }
    }

    public static void main(String[] args) throws Throwable {
        Vault vault = new Vault();
        MethodType type = MethodType.methodType(String.class);
        MethodHandles.Lookup trusted = MethodHandles.lookup();
        MethodHandles.Lookup publicOnly = MethodHandles.publicLookup();

        MethodHandle open = publicOnly.findVirtual(Vault.class, "open", type);
        System.out.println("public method: " + (String) open.invokeExact(vault));

        try {
            publicOnly.findVirtual(Vault.class, "secret", type);
        } catch (IllegalAccessException error) {
            System.out.println("public lookup private: IllegalAccessException");
        }

        MethodHandle secret = trusted.findVirtual(Vault.class, "secret", type);
        System.out.println("trusted private: " + (String) secret.invokeExact(vault));
        System.out.println("same method type: " + secret.type().equals(open.type()));
    }
}
```

Biên dịch/chạy:

```bash
javac --release 17 AccessScopeDemo.java
java AccessScopeDemo
```

**Stdout đã kiểm chứng:**

```text
public method: public
public lookup private: IllegalAccessException
trusted private: s3
same method type: true
```

Ở đây `Vault` là nested class trong cùng **nest** với `AccessScopeDemo`. Vì vậy `MethodHandles.lookup()` từ `AccessScopeDemo` có thể lookup private member của `Vault`. Trong khi đó `publicLookup()` chỉ tìm public method và bị từ chối với `secret`.

Dòng cuối cho thấy **hai handles có cùng `MethodType` nhưng khác member và access level**. Chỉ khóa theo handle `type()` hoàn toàn sai. Quan trọng hơn, nếu một hệ thống cache privileged handle `secret` mà consumer không đáng tin có thể lấy từ cache, security boundary đã bị phá bởi **việc phát tán capability**, không phải `publicLookup` tự nhiên bỗng được thêm quyền.

## 10. `ClassValue`: cache gắn trực tiếp vào từng `Class<?>`

`java.lang.ClassValue<T>` được thiết kế để **liên kết một giá trị tính toán lười với một runtime class**. Nó rất phù hợp cho metadata caches cần phân biệt classes theo defining loader.

Mẫu nền tảng:

```java
private static final ClassValue<ConcurrentMap<Signature, MethodHandle>>
        CACHE = new ClassValue<>() {
    @Override
    protected ConcurrentMap<Signature, MethodHandle>
            computeValue(Class<?> owner) {
        return new ConcurrentHashMap<>();
    }
};
```

Trong ví dụ đầy đủ, `Signature` chứa name và `MethodType`, và cache chỉ phục vụ public virtual lookup. `CACHE.get(owner)` trả map riêng gắn với **chính `Class<?>` owner** đó. Hai classes có cùng tên nhưng là hai objects khác nhau sẽ không bị dùng chung giá trị ClassValue.

### 10.1. Ưu điểm của `ClassValue`

- **Runtime class identity** là namespace tự nhiên, không phải chuỗi tên.
- Hữu ích với plugin class loaders, schema metadata, Reflection descriptors và method-handle dispatch table.
- Tính toán lười qua `computeValue` khi `get(Class<?>)` được gọi lần đầu.
- Không cần giữ một global `ConcurrentHashMap<Class<?>,...>` với strong key tới **mọi plugin class**.
- Có `remove(Class<?>)` khi bạn muốn loại bỏ association hiện tại và tính lại trong lần `get` sau.
- JVM hỗ trợ cấu trúc ClassValue dành cho per-class values; dùng trực tiếp đúng với trường hợp của bài.

### 10.2. Không cam kết `computeValue` chạy đúng một lần dưới mọi cạnh tranh

Tài liệu `ClassValue.get` nói quá trình **cài đặt giá trị đã tính lên class là atomic**, nhưng nếu nhiều threads đồng thời thấy chưa có giá trị, **có thể có nhiều lần `computeValue` được gọi** rồi JVM chọn một kết quả để dùng. Vì vậy:

- Không đặt side effect không idempotent, tạo resource khó giải phóng hoặc ghi DB vào `computeValue` mà giả định chạy đúng một lần.
- `computeValue` tốt nhất chỉ tạo một cấu trúc cache độc lập, ví dụ `new ConcurrentHashMap<>()`, hoặc tính metadata có thể làm lại an toàn.
- Nếu có `remove` cạnh tranh với `get`, semantics của việc tính lại phức tạp hơn; phải thiết kế lifecycle phù hợp.
- Trong code của bài, `computeValue` chỉ tạo một empty map, nên các tính toán dư do race (nếu có) không làm sai business state.

Một số người nhầm `ClassValue` là một `ConcurrentHashMap` mà `computeValue` chắc chắn chỉ được gọi đúng một lần. Đó **không phải bảo đảm** nên dựa vào.

### 10.3. `remove` không phải hệ thống unload class

`CACHE.remove(owner)` loại association của một ClassValue với một class, giúp lần `get` sau có thể tính lại value. Nó **không** làm unload class, không hủy các `MethodHandle` đã được code khác giữ và không invalid mọi adapter/call site trong JVM.

Nếu framework cần invalidation khi plugin reload, phải quyết định:

1. Class cũ còn sống trong loader cũ không?
2. Các requests đang dùng handle cũ có được phép hoàn tất không?
3. Có registry/weak references/pool nào vẫn giữ class cũ không?
4. Có cần invalidation của `CallSite`, `SwitchPoint` hoặc một generation pointer ngoài ClassValue không?

Không tự coi `ClassValue.remove` là transaction hủy tất cả runtime state.

## 11. Memory leak: global cache có thể giữ class loader sống mãi

Một plugin container thường phải unload phiên bản cũ. Nhưng **một global strong-reference cache** có thể khiến việc unload không xảy ra.

Ví dụ dễ gặp:

```java
// Mã minh họa nguy cơ lifecycle:
static final Map<Class<?>, MethodHandle> GLOBAL = new HashMap<>();

GLOBAL.put(pluginClass, pluginMethodHandle);
```

Trong khi JVM còn sống và `GLOBAL` tồn tại, entry có thể giữ `Class<?>`/`MethodHandle`/loader liên quan reachable. Dù plugin đã “stop”, loader vẫn có thể không được garbage collected/unloaded. Sau nhiều lần reload, heap chứa nhiều lớp cũ.

### 11.1. Tại sao `WeakHashMap<Class<?>,MethodHandle>` không phải sửa chữa tự động?

`WeakHashMap` giữ **keys** weakly, nhưng **values** vẫn là strong references. Một `MethodHandle` thường giữ reference đến declaring class hoặc types trong signature. Sơ đồ retention có thể là:

```text
static cache
    |
    v
WeakHashMap entry
    |
    +-- weak key ------> Class<?> (plugin)
    |
    +-- strong value --> MethodHandle
                             |
                             v
                        Class<?> (plugin)
                             |
                             v
                       defining loader
```

Nếu value giữ mạnh Class của key theo đường tham chiếu khác, weak key **không mất reachability**, entry không được dọn như bạn mong. Điều này được cảnh báo phổ biến với weak-key maps chứa values có quan hệ ngược tới keys.

**Không khẳng định mọi `WeakHashMap` đều leak**; vấn đề là **reference graph của values**. Khi values giữ declaring classes, một weak-key map đơn giản có thể chưa đủ. `ClassValue` thường thích hợp hơn cho **per-class cached metadata**, nhưng vẫn phải xem toàn bộ hệ thống.

### 11.2. `ClassValue` có giải quyết mọi memory leak không?

Không. Nếu app còn một global list chứa `Class<?>`, một active thread với context class loader của plugin, một listener không unregister, executor task, timer hoặc static registry giữ object plugin, class vẫn có thể sống.

`ClassValue` giải quyết **một kiểu liên kết cache per-class** tốt hơn việc tự giữ global strong keys; nó không thay thế quản lý lifecycle của plugin, threads, class loaders và references ngoài cache.

### 11.3. Các giá trị bên trong cache cũng có thể giữ cross-loader references

Một per-class cache có thể chứa `MethodType` nhắc đến parameter types từ **loader khác**, hoặc adapters/bound instances đi xuyên các modules/plugins. Nếu bạn tạo reference graph dài sống ngoài ý muốn, một loader cũ có thể bị giữ lại gián tiếp. Thiết kế boundaries rõ: một cache gắn với owner class chỉ nên giữ các entries thực sự thuộc lifecycle đó, và phải giải phóng external registries khi thế hệ plugin không còn cần.

## 12. Cache đồng thời: `ConcurrentHashMap` và `computeIfAbsent`

Nếu nhiều threads cùng resolve một method, dùng một `HashMap` không đồng bộ có thể dẫn tới race và cấu trúc map hỏng/ghi đè. Một `ConcurrentHashMap<Key,MethodHandle>` cho phép atomic cache population theo key:

```java
return cache.computeIfAbsent(key, k -> {
    try {
        return lookup.findVirtual(
                k.owner(), k.name(), k.memberType());
    } catch (ReflectiveOperationException e) {
        throw new IllegalStateException("Lookup failed", e);
    }
});
```

Đây là **mã minh họa** cho key record chứa owner/name/memberType và một cache chỉ virtual. `computeIfAbsent` chấp nhận function không được khai báo ném checked exception; nếu `findVirtual` ném `NoSuchMethodException` hoặc `IllegalAccessException`, ví dụ bọc lại bằng unchecked `IllegalStateException` và giữ cause.

### 12.1. Không tự động cache lookup failures

Nếu mapping function ném exception, `ConcurrentHashMap.computeIfAbsent` không ghi entry thành công cho key đó. Lần lookup sau có thể cố gắng resolve lại. Đây thường là lựa chọn an toàn khi framework có giai đoạn loading hoặc access policy khác nhau.

Nếu muốn cache negative results để giảm chi phí, phải cân nhắc:

- **Lỗi có vĩnh viễn không?** Plugin đang load, module layer vừa đổi, permissions hay target version có thể thay đổi.
- Cache negative result theo đúng **class generation và access policy**.
- Có timeout/invalidating mechanism đúng lúc.
- Không biến một lỗi `IllegalAccessException` từ consumer không quyền thành “mọi consumer đều không quyền” nếu cache dùng chung mà lookup contexts khác nhau.

Đừng dùng `null` để biểu diễn cả “không có method” lẫn “map chưa cache” khi semantics cần phân biệt. `ConcurrentHashMap` không cho null values; có thể dùng sealed result/Optional (với lifecycle đúng) cho caching failure có chủ ý.

### 12.2. Mapping function nên ngắn và tránh sửa lại cùng map

Với `ConcurrentHashMap.computeIfAbsent`, mapping function không nên thực hiện recursive updates vào chính map hoặc gọi mạng chậm kéo dài mà không tính đến contention. Chương trình trong ví dụ chỉ lookup public member và trả một MethodHandle, dễ kiểm tra.

Ngoài correctness, một lookup có thể gồm class resolution/access checks và đi theo inheritance graph. Benchmark phải đo cả thời gian **cache miss**, **cache hit** và **chi phí invoke**, thay vì chỉ xem một số trung bình khi hot.

### 12.3. ClassValue và ConcurrentHashMap giải quyết hai tầng khác nhau

Thiết kế phổ biến:

```text
ClassValue
    |
    +-- Class<?> A --> ConcurrentMap<Signature, MethodHandle>
    |
    +-- Class<?> B --> ConcurrentMap<Signature, MethodHandle>
```

- `ClassValue` phân tách theo runtime `Class<?>` và lifecycle gắn với class.
- `ConcurrentMap` xử lý concurrent lookup/caching của **nhiều signatures bên trong cùng class**.
- `Signature` xét member name, parameters, return type và kind nếu namespace không cố định.
- Quyền truy cập thường được giới hạn bằng API tạo cache hoặc một trust-boundary riêng, không chỉ bằng sự tồn tại của map.

## 13. Phân biệt lookup theo class runtime và method selection theo receiver

Một cache dùng class để resolve phương thức phải trả lời rõ: **owner class là kiểu tĩnh bạn muốn lookup hay kiểu runtime của receiver?**

Ví dụ:

```java
class Parent {
    String name() { return "parent"; }
}
class Child extends Parent {
    @Override String name() { return "child"; }
}
```

Đoạn trên là minh họa, không phải chương trình độc lập. Nếu bạn lấy virtual MethodHandle tới `Parent.name()`, một receiver `Child` vẫn có thể dispatch đến override `Child.name()` theo semantics virtual invocation. Vì vậy không bắt buộc **mọi virtual call** đều cần cache riêng cho mỗi subclass để được polymorphism đúng.

Ngược lại, một dynamic language runtime có thể lựa chọn **một method theo receiver.getClass()** rồi tạo adapter/guard chuyên biệt cho class đó. Khi ấy cache key hoặc inline-cache guard phải chứa runtime class identity và invalidation strategy.

**Đừng nhầm:**

- **Method resolution owner**: class/interface được truyền vào `findVirtual` hoặc `getMethod`.
- **Actual receiver class**: class của object ở lần gọi.
- **Method selection/dispatch**: quy tắc JVM cho virtual/interface invocation; có thể đến override khác.
- **Cache strategy**: tùy nghiệp vụ, có thể theo resolution owner hoặc theo actual receiver class nhưng phải chỉ rõ.

Đối với `ClassValue` minh họa ở mục 6, owner được truyền trực tiếp trong `findPublicVirtual(owner,...)`, nên cache per owner khớp với cách tìm member. Trong framework lớn, nếu resolution nhận cả owner và receiver type, hãy tách hai vai trò trong key hoặc theo stage riêng.

### 13.1. Interface, default methods và proxy classes

Một interface method có thể được implement bởi nhiều class loaders hoặc nhiều proxy classes. Đừng dùng interface **name String** làm key cho implementation method handle đã specialize theo concrete proxy class.

Với `Proxy.newProxyInstance(loader, interfaces, handler)`, proxy class được tạo trong một class loader phù hợp. Hai proxy classes cùng implement interface có thể có class identity khác nhau. Nếu cache theo exact proxy class, hãy dùng `proxy.getClass()`/`ClassValue`; nếu cache theo interface method descriptor, phải hiểu target call vẫn có thể dispatch qua proxy invocation handler.

Tương tự, default methods, bridge methods và inherited methods có các quy tắc resolution riêng. Đừng coi `Class.getDeclaredMethods()` và `Class.getMethods()` là hai cách tạo cùng một tập entries.

## 14. Class loaders, class unloading và hot reload

Khi plugin A được thay bằng plugin B nhưng giữ cùng tên class:

```text
generation 1
  loader L1
  plugin.Service@L1
  MethodHandle H1 (declaring type của L1)
  cached resolution V1

plugin reload

generation 2
  loader L2
  plugin.Service@L2
  MethodHandle H2 (declaring type của L2)
  cached resolution V2
```

Không reuse `H1` để gọi instance của `plugin.Service@L2` chỉ vì `toString()` hoặc method descriptors giống nhau. Dù source code và bytecode y hệt, receiver types khác nhau theo JVM identity.

Một lifecycle hợp lý:

1. Định nghĩa plugin generation/loader rõ ràng.
2. Mỗi generation có class objects và resolution cache tương ứng.
3. Khi reload, xây generation mới và publish atomically theo API của framework.
4. Các request đang dùng generation cũ có thể hoàn tất hoặc được điều phối theo synchronization/cancellation policy.
5. Không giữ class loaders cũ bằng thread-local, executor, static map, listener, bound handles hoặc registries ngoài ý muốn.
6. Nếu có call sites đã tối ưu theo generation cũ, dùng relinking/invalidating logic của runtime (ví dụ `SwitchPoint`/`MutableCallSite` khi hợp lý) thay vì mong một class cache tự cập nhật.

Một `ClassValue` bám owner class mới sẽ tự tách entries theo class mới. Nhưng `ClassValue` **không** tự thay mọi `MethodHandle` mà callers đang giữ từ generation cũ, không thay mục tiêu `CallSite` và không quản lý resource cleanup.

## 15. Gợi ý chọn kiến trúc cache theo nhu cầu

| Nhu cầu | Cấu trúc thường hợp lý | Lưu ý |
| --- | --- | --- |
| Một ứng dụng nhỏ, classes cố định, dùng public reflection | `ConcurrentHashMap<Key,Method>` với `Class<?>` owner | Dễ hiểu; ít nguy cơ loader unload nếu owner sống suốt process |
| Framework per-class metadata với nhiều loaders | `ClassValue<Metadata>` | Gắn cache với runtime class, tránh string key |
| Framework per-class nhiều method signatures | `ClassValue<ConcurrentMap<Signature,MethodHandle>>` | Phân tầng owner và member signature |
| Resolution gồm virtual/static/constructor/field | Key có `Kind` và type đúng contract | Không trộn receiver handle type và member lookup type |
| Cache privileged lookup theo module/plugin | Namespace riêng theo trust/access policy | Không phát tán private MethodHandle |
| Dynamic dispatch theo receiver class | Cache by `receiver.getClass()`, guard/inline-cache phù hợp | Cần xử lý polymorphism, invalidation, receiver type |
| Hot reload plugins | ClassValue/per-generation cache + lifecycle coordination | Không giữ old loader qua global state |
| Cache adaptations/bound handles | Key gồm adapter signature và bound values nếu thực sự cần | Rủi ro memory retention; thường cache base unbound handle tốt hơn |

### 15.1. Có nên cache bằng `Method` hay `MethodHandle`?

Tùy thao tác thực tế:

- `Method` hữu ích khi cần metadata Reflection, annotations, modifiers hoặc invocation qua `Method.invoke`.
- `MethodHandle` phù hợp khi cần typed, composable invocation và có các call sites ổn định mà JVM có thể tối ưu.
- Cả hai vẫn phải resolve member một lần với đúng quyền. Không mặc định `MethodHandle` lúc nào cũng nhanh hơn `Method.invoke`; hiệu năng phụ thuộc JIT, call-site shape, warm-up, virtual dispatch, adapter chain và workload.
- Nếu chỉ cần gọi method trực tiếp đã biết ở compile time, **Java call bình thường** thường đơn giản và dễ tối ưu hơn cả hai. Không tạo dynamic runtime infrastructure khi không cần.

### 15.2. Cache theo signature không đồng nghĩa “cache một kết quả invocation”

Cache một `MethodHandle` là cache **cách gọi**; mỗi invocation vẫn nhận arguments thực tế và chạy target theo semantics. Cache result của `service.calculate(input)` là bài toán **memoization** khác, đòi key gồm input/state/version, TTL/invalidation và side-effect policy.

Đừng đưa kết quả của một method gọi trên receiver A vào cache method lookup rồi trả cho receiver B. Method handle lookup cache và business result cache cần tách biệt.

## 16. Debug lỗi cache nhầm Class/Signature

Nếu ứng dụng báo lỗi không thể giải thích dù tên class/method log vẫn đúng, hãy log theo những trường sau (không đưa secrets vào logs):

```java
// Mã minh họa; owner, memberType, kind và resolvedHandle đã có.
System.out.println("owner binary name: " + owner.getName());
System.out.println("owner defining loader: " + owner.getClassLoader());
System.out.println("owner module: " + owner.getModule());
System.out.println("owner identity: " + System.identityHashCode(owner));
System.out.println("member type: " + memberType);
System.out.println("operation kind: " + kind);
System.out.println("handle type: " + resolvedHandle.type());
```

`System.identityHashCode` chỉ có ích **cho diagnostics trong một tiến trình**, không phải unique ID vĩnh viễn hoặc khóa cache an toàn; hash collisions có thể xảy ra. Nếu bạn cần log loader identity, bao gồm loại loader và một ID generation do framework cấp, thay vì khẳng định `loader.toString()` luôn unique.

### 16.1. Triệu chứng và nguyên nhân

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| `IllegalArgumentException: object is not an instance of declaring class` khi `Method.invoke` | Dùng Method từ loader A trên instance thuộc class cùng tên nhưng loader B | So sánh actual declaring `Class<?>` và receiver `getClass()`; sửa key |
| `ClassCastException` dù tên class trong message trông giống nhau | Hai loader versions cùng FQCN; cast qua type identity khác | Log defining loaders/module; không cache theo tên |
| `WrongMethodTypeException` tại `invokeExact` | Call-site static parameters/return type không bằng handle `type()` | Kiểm tra cả return cast và receiver type |
| `NoSuchMethodException` | Lookup sai overload/generic erasure, owner hoặc member visibility | Kiểm tra `Class<?>` parameter types và declared/public lookup policy |
| `IllegalAccessException` khi `Lookup.findVirtual` | Lookup thiếu quyền/JPMS hạn chế package | Sửa Lookup/module openness hoặc public API |
| Cache hit nhưng gọi nhầm overload | Key thiếu parameter types hoặc kind | Dùng full signature |
| Cache miss dù tên method giống | Loader khác, receiver owner khác, signature/adaptation khác | Xem identity thật; đó có thể là miss đúng |
| Heap tăng sau plugin reload | Global Map/Class/Method/MethodHandle/listeners giữ loader cũ | Xem GC roots, caches, thread context class loaders; quản lý lifecycle |
| `WeakHashMap` không giải phóng entry | Value vẫn giữ owner Class/loader | Xem reference graph; cân nhắc ClassValue và cleanup |
| Multiple concurrent lookups | Cache không thread-safe hoặc mapping function bị gọi lại | ConcurrentMap + ClassValue đúng semantics; idempotent computeValue |
| Public caller nhận private handle | Privileged cache capability bị lộ qua API | Tách trust boundaries và policy checks |
| String descriptor giống nhưng MethodType khác | Same-name classes từ loaders khác | Dùng resolved MethodType / Class objects |

### 16.2. Debug theo bước

1. **Xác định lớp đích thật**: in owner `Class<?>`, binary name, defining loader và module.
2. **Xác định chữ ký thật**: parameter types và return type của member, không chỉ tên/arity.
3. **Xác định kind**: static hay virtual, constructor, field getter/setter, special invocation.
4. **Xác định lookup context**: `Lookup.lookupClass()`, modes, public/declared/private policy, JPMS.
5. **Xác định cache entry**: được tạo bằng owner/loader/generation nào, có bind receiver/adapt type không.
6. **Xác định caller**: `invokeExact` có expected return type/argument types nào, receiver thuộc loader nào.
7. **Xác định lifecycle**: liệu global cache đang giữ old generation, hoặc negative cache cũ có chặn lookup mới.
8. **Kiểm thử lại bằng cache miss** trong môi trường an toàn: nếu miss path đúng mà hit path sai, bug nằm trong khóa, lifecycle hoặc quyền publish entry.

## 17. Unit tests nên có với loader-aware cache

Một bộ test thực tế cần nhiều hơn “lookup method thành công”:

- **Cùng class, cùng signature:** cache hit và trả đúng handle/metadata theo policy.
- **Cùng class, khác overload:** entries riêng cho `(int)String` và `(String)String`.
- **Cùng class, khác kind:** static/virtual không bị nhập chung.
- **Cùng binary name, khác defining loader:** hai `Class<?>` khác và cache có entries riêng.
- **Cùng descriptor String, khác MethodType object equality:** phân biệt resolved reference types.
- **Method.invoke sai declaring class:** lỗi `IllegalArgumentException` được dự đoán đúng.
- **MethodHandle.invokeExact sai caller type:** lỗi `WrongMethodTypeException` đúng tầng.
- **Private vs public Lookup:** public lookup không tự lấy private method; không phát tán privileged handle.
- **Concurrent cache fill:** không corrupt map, idempotent per-class cache initialization.
- **Plugin reload:** không reuse handles từ old loader; loader cũ có thể được thu hồi nếu không còn references.
- **Negative lookup:** xử lý exception/cause và không lưu lỗi quá phạm vi policy.
- **Adapters/bound receiver:** handle bound cho instance A không được dùng như unbound generic method trên instance B.
- **Generic erasure:** không dùng `List<String>` và `List<Integer>` như hai Java runtime classes khác nhau.

Đối với test unloadability/GC, **không** khẳng định rằng gọi `System.gc()` một lần rồi `WeakReference.get()==null` là assertion ổn định ở mọi JVM. GC scheduling không được bảo đảm theo yêu cầu của code. Dùng heap diagnostics, kiểm soát GC roots và bài test lifecycle phù hợp.

## 18. Câu hỏi tự kiểm tra (có đáp án)

**Câu 1.** Hai class đều có `getName()=="plugin.Greeter"`. Có chắc cùng kiểu không?

**Đáp án:** Không. Class identity phụ thuộc cả binary name và defining loader; hai loaders riêng có thể định nghĩa hai types độc lập.

**Câu 2.** Tại sao key `className + methodName` nguy hiểm trong plugin runtime?

**Đáp án:** Bỏ qua class loader và method signature. Có thể lấy Method/MethodHandle của class loader A rồi dùng trên instance thuộc loader B.

**Câu 3.** Hai `MethodType` có cùng `toMethodDescriptorString()` luôn `equals` nhau không?

**Đáp án:** Không. Text descriptor chứa binary names; hai reference types cùng tên nhưng khác defining loaders có thể tạo hai `MethodType` khác nhau.

**Câu 4.** Tại sao nên dùng `Class<?>` làm khóa thay vì `Class.getName()`?

**Đáp án:** `Class<?>` là runtime type đã được resolve với defining loader/module context, phân biệt đúng hai lớp cùng tên do loaders khác nhau định nghĩa.

**Câu 5.** Cache MethodHandle toàn cục hỗ trợ virtual và static có thể chỉ key `owner,name,parameterTypes` không?

**Đáp án:** Không đủ tổng quát. Nên có invocation kind và return type (thông qua `MethodType`) hoặc tách namespace cố định từng kind.

**Câu 6.** `findVirtual(Service.class,"run",type)` yêu cầu type có receiver Service ngay trong tham số không?

**Đáp án:** Không. `MethodType` truyền cho `findVirtual` mô tả member **không có receiver**; resolved handle type sẽ chứa receiver ở đầu.

**Câu 7.** Một `MethodHandle` tới private method lấy bằng privileged lookup được đưa cho public-only consumer. Consumer có thể gọi không?

**Đáp án:** Handle là capability đã được tạo hợp lệ, nên nếu nhận được handle, consumer có thể invoke theo type/target. Đây là rủi ro **phát tán quyền**, cần quản lý trust boundary.

**Câu 8.** `ClassValue.computeValue` có chắc chạy chính xác một lần khi nhiều threads cùng `get`?

**Đáp án:** Không. Có thể có nhiều tính toán cạnh tranh rồi một kết quả được cài đặt atomic. Không đặt side effects không idempotent trong computeValue.

**Câu 9.** `WeakHashMap<Class<?>,MethodHandle>` có chắc cho phép unload class khi không còn plugin references khác không?

**Đáp án:** Không chắc: value có thể giữ strong reference ngược tới declaring Class/loader, khiến weak key không mất reachability.

**Câu 10.** `ClassValue.remove(owner)` có tự làm JVM unload owner class không?

**Đáp án:** Không. Nó chỉ loại association trong ClassValue; unloading còn phụ thuộc toàn bộ GC roots/lifecycle.

**Câu 11.** Chỉ dùng `MethodHandle.type()` làm key có đủ phân biệt hai methods cùng signature khác tên không?

**Đáp án:** Không. Hai methods khác nhau có thể có cùng type; cần owner/name/kind/member identity.

**Câu 12.** `Service.format(int)` và `Service.format(String)` có phải cùng key nếu cùng tên?

**Đáp án:** Không, vì parameter types khác; `MethodType` phải được xét.

**Câu 13.** Cache virtual method handle `bindTo(receiverA)` dưới key `Service.class,"format"` rồi gọi thay receiverB an toàn không?

**Đáp án:** Không. Bound handle đã gắn instance A và có invocation signature khác. Cache unbound handle hoặc thiết kế key/lifetime có receiver identity đúng.

**Câu 14.** `ConcurrentHashMap.computeIfAbsent` mapping function ném exception thì có entry giá trị hợp lệ được ghi không?

**Đáp án:** Không. Nếu computation thất bại bằng exception, entry thành công không được thêm; muốn negative cache phải tự thiết kế kiểu kết quả và invalidation.

**Câu 15.** Vì sao generic `List<String>` và `List<Integer>` không tạo hai `Class<?>` khác nhau?

**Đáp án:** Java generics dùng type erasure; runtime `List.class` là cùng class. Nếu framework cần phân biệt generic contracts, phải xét thêm `Type` metadata ở tầng business.

**Câu 16.** Khi plugin reload nhưng vẫn dùng cùng FQCN, nên reuse MethodHandle cũ chứ?

**Đáp án:** Không nếu class mới do defining loader khác tạo. Phải resolve/cache theo class generation mới; method handles cũ thuộc types cũ.

**Câu 17.** Một ClassLoader A và B cùng gọi `loadClass("java.lang.String")` và đều nhận cùng `String.class`. Có mâu thuẫn với type identity không?

**Đáp án:** Không. Các initiating loaders có thể delegate tới cùng bootstrap defining loader. Cặp binary name + **defining loader** của class trả về vẫn duy nhất.

**Câu 18.** Vì sao không nên dùng `System.identityHashCode(Class)` làm cache key thay thế `Class<?>`?

**Đáp án:** Identity hash có thể collision và không giữ/diễn đạt Class object identity đủ để equality. Dùng chính Class object làm khóa, identityHashCode chỉ phục vụ diagnostics.

## 19. Bài tập áp dụng

### A. Thêm một overload

Trong `SignatureCacheDemo.Service`, thêm:

```java
public String format(double n) { return "double:" + n; }
```

Tạo `Key` mới với `Kind.VIRTUAL` và `MethodType.methodType(String.class,double.class)`, resolve rồi gọi. Kiểm tra `CACHE.size()` tăng từ ba thành bốn, và các entries cũ không đổi.

### B. Tạo class cùng tên ở loader thứ ba

Trong `LoaderCacheDemo`, tạo một `new BytesLoader(classBytes)` nữa, load `plugin.Greeter` và gọi `findPublicVirtual` với owner mới. Dự đoán `Class<?>` thứ ba khác A và B, có ClassValue map riêng, nhưng source method vẫn có thể trả cùng `"greeting"`. **Cùng output không có nghĩa cùng runtime type.**

### C. Kiểm thử key chỉ bằng descriptor String

Tạo hai `MethodType.methodType(void.class,a)`/`methodType(void.class,b)` như demo, rồi đưa `toMethodDescriptorString()` của chúng vào `Map<String,Object>`. Quan sát text key collision, sau đó thay bằng `Map<MethodType,Object>` để phân biệt đúng types.

### D. Chặn privileged handle leakage

Chia cache thành hai API: một public resolver chỉ dùng `MethodHandles.publicLookup()`, và một trusted resolver có quyền private trong module. Không cho client bên ngoài gọi API lấy handle private. Viết unit test chứng minh caller public bị từ chối với `Vault.secret`, trong khi component trusted vẫn resolve được.

### E. Xem memory retention sau reload

Thiết kế plugin load/unload test với `ClassValue` và một global strong map để so sánh reference graph. Dùng heap dump/GC root analysis để tìm references giữ loader cũ. Không viết assertion ngây thơ “`System.gc()` phải unload ngay”, vì GC là không xác định.

## 20. Tài liệu chính thức

- **Java SE 17 — `ClassValue`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassValue.html — cache lazily computed per `Class<?>`, `get`/`remove`, concurrent computation semantics.
- **Java SE 17 — `ClassLoader`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html — defining/initiating loader, delegation và class-loading lifecycle.
- **Java SE 17 — `Class`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html — runtime class identity, `getName`, `getClassLoader`, `getModule` và reflection.
- **Java SE 17 — `MethodType`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html — signature với từng `Class<?>` parameter/return và descriptor conversion.
- **Java SE 17 — `MethodHandle`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html — `type`, `invokeExact`, `invoke`, `asType`, `bindTo`.
- **Java SE 17 — `MethodHandles.Lookup`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html — `findVirtual`, `findStatic`, `findConstructor`, quyền lookup.
- **Java SE 17 — `MethodHandles`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html — `lookup`, `publicLookup`, `privateLookupIn`.
- **Java SE 17 — `Method`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html — declaring class, invocation và reflection semantics.
- **Java SE 17 — `ConcurrentHashMap`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html — `computeIfAbsent` và concurrent map semantics.
- **Java SE 17 — `WeakHashMap`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/WeakHashMap.html — weak keys và cảnh báo về values giữ keys.
- **JVMS 17 `5.3 — Creation and Loading:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3 — type identity là binary name + defining loader.
- **JVMS 17 `5.4.3 — Resolution:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4.3 — symbolic references, member resolution.
- **JLS 17 `4.6 — Type Erasure:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.6 — generic erasure và runtime types.

**Kết luận:** Muốn cache reflection/MethodHandle an toàn, phải giữ **owner `Class<?>` của runtime thật**, không chỉ tên lớp; **đầy đủ member signature và invocation kind**, không chỉ method name; và **ranh giới quyền của Lookup cùng lifecycle class loader**. `ClassValue` giúp tổ chức cache theo class identity, nhưng không tự sửa privileged handle leakage, bound receiver mistakes hoặc class-loader retention ở các registries khác. Cache đúng là cache trả về **chính thao tác được resolve cho đúng class generation và đúng hợp đồng type/access**.