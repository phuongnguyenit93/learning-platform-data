# 12.8. Bộ nhớ đệm tại điểm gọi, kiểm tra kiểu receiver và nhánh liên kết lại

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích ý nghĩa của **call site**, `CallSite.getTarget()`, `CallSite.dynamicInvoker()` và lý do cập nhật target giúp tránh thực hiện lookup đầy đủ ở mọi lời gọi động.
2. Phân biệt **monomorphic inline cache**, **polymorphic inline cache (PIC)** và trường hợp **megamorphic**; biết vì sao số guard cần được giới hạn.
3. Tạo phép **kiểm tra kiểu receiver** bằng `receiver.getClass() == expectedClass` và `MethodHandles.guardWithTest(...)`.
4. Thiết kế **nhánh fallback/relink**: cache miss → tìm `MethodHandle` cho kiểu receiver mới → chuyển về `MethodType` chung → gắn guard → cập nhật `MutableCallSite.setTarget(...)` → gọi đích vừa tìm.
5. Hiểu **target của CallSite có kiểu cố định** ngay cả khi phương thức được chọn thay đổi; phân biệt `asType`, `invokeExact` và `WrongMethodTypeException`.
6. Xử lý `null`, method không tồn tại, quyền truy cập, class loader, invalidation và concurrency; hiểu vai trò của `MutableCallSite.syncAll(...)`, `VolatileCallSite`, `SwitchPoint`.
7. Chạy ví dụ Java 17+ có cache tối đa ba lớp receiver, quan sát hit/miss và tránh nhầm cache hit với bảo đảm JIT đã tối ưu.

**Ngữ cảnh:** Trong dynamic languages chạy trên JVM, expression như `receiver.speak()` có thể nhận nhiều kiểu object khác nhau tại cùng một vị trí trong code. Một triển khai ngây thơ sẽ tìm lại method phù hợp mỗi lần gọi. **Inline cache** ghi nhớ các kiểu đã gặp và đường gọi tương ứng tại chính **điểm gọi** để tăng tốc đường nóng. `CallSite`, `MethodHandle` và `guardWithTest` cho phép mô hình hóa cách hoạt động này bằng API Java.

## 1. Call site là gì và nó giữ gì?

`java.lang.invoke.CallSite` là object lưu một **target `MethodHandle`**. Target là hành vi sẽ được gọi tại điểm gọi đó.

- `site.type()` trả **`MethodType` cố định** của điểm gọi.
- `site.getTarget()` trả target đang liên kết theo semantics của lớp `CallSite`.
- `site.dynamicInvoker()` tạo handle có hành vi gọi target hiện tại của site; nó **không đơn giản đóng băng target ban đầu** với site mutable.
- `site.setTarget(newTarget)` đổi target nếu loại site cho phép và `newTarget.type()` **bằng chính xác** `site.type()`.

Ba biến thể quan trọng:

| Loại | Có thể thay target? | Điểm cần nhớ |
| --- | --- | --- |
| `ConstantCallSite` | Không | Target được liên kết cố định; phù hợp lời gọi không cần relink. |
| `MutableCallSite` | Có | Update target có semantics như biến thường; muốn công bố thay đổi đúng cho các thread khác cần thiết kế synchronization, thường dùng `syncAll`. |
| `VolatileCallSite` | Có | Update target có volatile semantics, thích hợp khi cần thấy thay đổi giữa nhiều thread theo hợp đồng volatile. |

Ở mức JVM, một lệnh `invokedynamic` được liên kết với `CallSite`. Nhưng trong một chương trình Java thuần, ta cũng có thể **khởi tạo site trực tiếp và gọi `dynamicInvoker()`** để mô phỏng hành vi relinking. Ví dụ hoàn chỉnh ở phần 7 **không tự phát sinh bytecode invokedynamic cho lời gọi mẫu**; nó minh họa chính xác cơ chế xây dựng và cập nhật target.

### 1.1. Target type được giữ cố định

Giả sử một điểm gọi có contract:

```text
(Object receiver)String
```

Nó nhận một receiver ở compile time dưới kiểu `Object` và trả `String`. Từ đó, dù receiver thực tế là `Dog`, `Cat` hay `Bird`, target của site vẫn **phải có kiểu `(Object)String`**.

Điều này khác với đích được tìm ở runtime:
- `findVirtual(Dog.class, "speak", ()String)` cho handle có kiểu `(Dog)String`.
- `findVirtual(Cat.class, "speak", ()String)` cho handle có kiểu `(Cat)String`.

Hai handle này không thể đưa trực tiếp vào một site `(Object)String`. Cần **adapt** chúng về cùng kiểu site bằng `asType(MethodType.methodType(String.class, Object.class))`. Khi adapt một handle `(Dog)String` thành `(Object)String`, adapter sẽ yêu cầu receiver tương thích `Dog` ở runtime.

**Bất biến quan trọng:** Relink thay đổi **đường đi thực thi**, không thay đổi chữ ký của điểm gọi. `CallSite.setTarget` từ chối target sai `MethodType` bằng `WrongMethodTypeException`.

## 2. Bộ nhớ đệm tại điểm gọi (*inline cache*)

Một inline cache là một dạng ghi nhớ **ngay tại một call site cụ thể**, thường dựa trên kiểu hoặc hình dạng (*shape*) của receiver. Thay vì lặp lại full lookup:

```text
Mỗi lời gọi (chưa có cache)
    receiver -> lấy kiểu/hình dạng -> tìm method -> tạo adapter -> gọi target
```

Ta có thể dùng:

```text
Lần đầu:
    receiver -> CACHE MISS
             -> resolve target cho kiểu mới
             -> cài một type guard và target đã resolve
             -> gọi target

Lần sau cùng kiểu:
    receiver -> GUARD ĐÚNG -> gọi target đã cache (CACHE HIT)

Khi receiver thuộc kiểu khác:
    receiver -> GUARD SAI -> FALLBACK -> resolve/relink
```

Điểm mấu chốt: **nhiều call sites** trong cùng một method có thể quan sát phân phối receiver khác nhau. Ví dụ call site bên trong một vòng lặp xử lý `Dog` 99% thời gian có thể cache riêng `Dog`, không cần chịu ảnh hưởng của call site ở đoạn code khác chủ yếu gọi `Cat`.

So sánh với cache toàn cục:
- **Per-site inline cache:** tối ưu theo hành vi tại điểm gọi; có thể giúp JIT thấy nhiều đường thường xuyên đi qua guard ổn định.
- **Global lookup cache:** dùng chung dữ liệu giải quyết method cho nhiều call sites; có thể giảm chi phí resolve nhưng không tự thay thế các guard/nhánh dispatch của từng site.
- Hai tầng có thể **kết hợp**. Per-site PIC có thể trỏ tới handle đã được cache theo class trong một bảng chung.

### 2.1. Monomorphic, polymorphic, megamorphic

| Hình thái | Receiver thấy tại site | Cấu trúc tiêu biểu |
| --- | --- | --- |
| **Monomorphic** | Một class chủ đạo | Một guard `receiver.class == Dog`, một fast target, một miss fallback |
| **Polymorphic (PIC)** | Số ít class thường gặp | Chuỗi nhỏ `guard(Dog) → guard(Cat) → guard(Bird) → fallback` |
| **Megamorphic** | Rất nhiều class/hình dạng | Thường cần đường dispatch chung, bảng cache hoặc lookup tối ưu khác thay vì tăng chuỗi guard mãi |

Không có ngưỡng cố định áp dụng cho mọi runtime. Ví dụ ở phần 7 chọn **tối đa ba guard** để dễ quan sát; đó là quyết định của demo, không phải ngưỡng do JVM/JDK quy định.

Tạo guard cho mọi class từng gặp có thể gây:
- chuỗi kiểm tra ngày càng dài;
- tăng số lượng `MethodHandle` và metadata;
- khó tối ưu JIT và tốn bộ nhớ;
- giữ reference tới `Class`/class loader lâu hơn cần thiết.

Vì thế PIC thường được **giới hạn**, và khi bão hòa có thể dùng generic fallback hoặc một global megamorphic cache.

## 3. Guard: kiểm tra kiểu receiver trước khi vào fast path

### 3.1. Predicate kiểm tra exact class

Một predicate tối giản:

```java
static boolean isExactClass(Class<?> expected, Object receiver) {
    return receiver != null && receiver.getClass() == expected;
}
```

Đây là method minh họa trong một class Java. Nó trả `true` chỉ khi receiver khác `null` và class runtime **chính xác** là `expected`.

Tại sao dùng `==` giữa hai `Class<?>`?
- `Class` biểu diễn **class identity** thật của JVM, bao gồm ngữ cảnh class loader. So tên chuỗi bằng `getName().equals(...)` có thể nhầm hai class được định nghĩa bởi hai loader khác nhau.
- Nếu muốn cache kết quả của method lookup dành riêng cho một class, exact-class guard đảm bảo adapter đã resolve sẽ nhận đúng receiver đã kiểm tra.
- Predicate không gây `NullPointerException` cho `null`; null sẽ đi fallback để xử lý theo policy rõ ràng.

### 3.2. Exact class khác `instanceof`

Với `receiver instanceof Dog`, một subclass của `Dog` cũng qua guard. Cách này **có thể hợp lệ** nếu target đã resolve thực sự tương thích và hợp đồng dispatch cho phép sử dụng cùng adapter, chẳng hạn một virtual method inherited/overridden theo đúng quy tắc Java.

Tuy nhiên trong runtime động, subclass có thể có cách resolve method khác do overload, extension, monkey patching, property lookup hoặc descriptor riêng. Exact-class guard là lựa chọn **an toàn và dễ chứng minh** cho demo: một target được cache cho một kiểu đúng.

**Cảnh báo:** Kiểm tra kiểu receiver **không thay thế** các điều kiện khác của protocol. Nếu dispatch còn phụ thuộc version của plugin, cấu hình runtime, quyền truy cập hoặc schema, chỉ guard trên class có thể dẫn tới cache **stale**. Khi đó phải bổ sung guard phiên bản/invalidation.

### 3.3. MethodHandles.guardWithTest

API:

```java
MethodHandle branch = MethodHandles.guardWithTest(
        test, fastTarget, fallback);
```

Đoạn này chỉ minh họa cấu trúc gọi; ba biến phải là `MethodHandle` với kiểu tương thích.

Khi gọi `branch`:
1. Chạy `test(receiver)`.
2. Nếu `true`, chạy `fastTarget(receiver)`.
3. Nếu `false`, chạy `fallback(receiver)`.

Để tương thích:
- `test` ở demo có kiểu `(Object)boolean`.
- `fastTarget` có kiểu `(Object)String`.
- `fallback` có kiểu `(Object)String`.

Guard có thể dùng ít tham số hơn target/fallback theo API, nhưng **phải** trả `boolean`. Nếu target/fallback có `MethodType` không trùng, hoặc test không phù hợp, `guardWithTest` ném `IllegalArgumentException` ngay khi tạo adapter.

### 3.4. Cố định class cần so sánh bằng insertArguments

Ở trạng thái gốc, `isExactClass(Class<?> expected,Object receiver)` nhận **hai tham số**, cho handle có kiểu `(Class,Object)boolean`. Ta có thể buộc `expected` thành class đã resolve:

```java
MethodHandle test = MethodHandles.insertArguments(
        IS_EXACT_CLASS, 0, actualClass);
// Kiểu test còn lại: (Object)boolean.
```

Đây là đoạn minh họa khi đã có biến `IS_EXACT_CLASS` và `actualClass`. `insertArguments` **ràng buộc sẵn** tham số đầu ở vị trí `0`, làm handle mới chỉ cần nhận receiver. Nó không sửa handle gốc và không tạo lookup mới ở mỗi lần test.

Kết hợp:
- guard class exact;
- target đã adapt tới `(Object)String`;
- fallback vẫn `(Object)String`.

Khi receiver class trùng, fast path **không chạy lại nhánh relink**.

## 4. Nhánh liên kết lại (*relink fallback*) hoạt động thế nào?

Fallback được gọi khi chưa có guard tương ứng, hoặc khi đường cache không còn hợp lệ.

Một sơ đồ PIC đơn giản:

```text
site.target = guard(Bird, invokeBird,
                guard(Cat, invokeCat,
                  guard(Dog, invokeDog,
                    relinkFallback)))

Call(receiver):
    if class(receiver) == Bird -> invokeBird
    else if class(receiver) == Cat -> invokeCat
    else if class(receiver) == Dog -> invokeDog
    else -> relinkFallback(receiver)
```

**Đường đi khi miss:**

1. Nhận receiver.
2. Kiểm tra `null` và những tiền điều kiện của call site.
3. Lấy `receiver.getClass()`; nếu dispatch phức tạp, có thể cần cả runtime shape/version.
4. Resolve target: ví dụ `Lookup.findVirtual(actualClass,"speak", MethodType.methodType(String.class))`.
5. Chuyển handle vừa tìm về `site.type()` bằng `asType(...)`.
6. Dựng predicate exact-class, rồi tạo adapter mới:
   `guardWithTest(test, newDirectHandle, oldTarget)`.
7. Nếu cache chưa bão hòa và chính sách cho phép, thay `site.setTarget(newChain)`.
8. Công bố update giữa các thread theo semantics của loại call site, ví dụ `MutableCallSite.syncAll(...)`.
9. **Gọi target vừa tìm** cho chính lần miss này, rồi trả kết quả bình thường.

Tại sao bước 9 gọi target trực tiếp thay vì gọi lại `dynamicInvoker`? Vì target đã resolve cho receiver hiện tại. Nếu gọi lại qua toàn chuỗi mà không cẩn thận, có thể tạo relink lặp, double invocation hoặc recursion không cần thiết. Code demo dùng `direct.invokeExact(receiver)` ngay sau khi liên kết.

### 4.1. Không được đổi kiểu của CallSite khi relink

Ví dụ site `(Object)String`:
- Tìm method Dog `(Dog)String`.
- Adapt thành `(Object)String`.
- Guard đã buộc class có kiểu `(Object)boolean`.
- `guardWithTest` tạo `(Object)String`.
- `setTarget` chấp nhận.

Nếu quên `asType` và đưa trực tiếp `(Dog)String` vào `setTarget`, cập nhật bị từ chối bằng `WrongMethodTypeException`. `CallSite` giữ kiểu cố định ngay cả khi target thay đổi nhiều lần.

### 4.2. Vì sao cần giữ fallback ở cuối?

Nếu chỉ lắp một target cho `Dog` và không có fallback, lúc gặp `Cat` có thể:
- ném `ClassCastException` từ adapter;
- hoặc gọi sai logic;
- hoặc không còn chỗ resolve method mới.

Nhánh `guardWithTest` phải dẫn về một **fallback đúng hợp đồng**, thay vì giả định receiver không bao giờ đổi kiểu. Ngay cả sau khi PIC đạt giới hạn, fallback phải xử lý những class chưa cache nếu mục tiêu ứng dụng yêu cầu hỗ trợ chúng.

### 4.3. Tránh cache sai class khi miss đồng thời

Trong hệ thống nhiều luồng, hai thread có thể cùng miss với các class khác nhau. Nếu mỗi thread làm `getTarget → guardWithTest → setTarget` không có coordination, update của thread này có thể ghi đè nhánh vừa thêm của thread kia (*lost relink*).

Mẫu demo đặt phần **kiểm tra cache và cập nhật target** trong `synchronized(site)`. Điều này tuần tự hóa các writer đang relink cùng một site. Ngoài ra phải dùng cơ chế visibility phù hợp cho reader, vì lock của writer **không tự đảm bảo** những thread chỉ gọi target mà không lấy lock ấy sẽ nhìn thấy thay đổi trong `MutableCallSite`.

## 5. Bộ nhớ đệm theo điểm gọi: chi phí hit và miss

### 5.1. Cache hit

Với receiver `Dog` đã cache:
- Kiểm tra một hoặc vài guard.
- Nhảy tới adapter handle đã resolve.
- Không gọi `Lookup.findVirtual` và không thay target.

Cache hit thường rẻ hơn một full resolution. Nếu call site ổn định, JVM/JIT **có thể** tối ưu hóa đường thường xuyên chạy, nhưng không có bảo đảm mọi call site đều được inline bởi JIT.

### 5.2. Cache miss

Miss có thể phải:
- kiểm tra nhiều guard;
- lấy class/shape;
- kiểm tra quyền/method;
- tạo/adapt handle;
- cấp phát node guard mới;
- cập nhật/công bố callsite target;
- cuối cùng mới gọi phương thức đích.

Vì thế **miss đắt hơn hit**. Đặt `syncAll` ở mỗi lời gọi hoặc relink không cần thiết sẽ phá mục tiêu tối ưu. Chỉ nên relink khi thực sự có target mới cần cache và chính sách cho phép.

### 5.3. Polymorphic Inline Cache (PIC) có giới hạn

Demo dùng giới hạn 3 class:
- `Dog`, `Cat`, `Bird`: được cache.
- `Fox`: vẫn dispatch đúng qua fallback, nhưng **không thêm guard thứ tư**.
- `Fox` được gọi lần nữa: lại fallback, vì ta chủ động không cache.

Điều này mô phỏng **đường chung** sau khi PIC bão hòa, không phải thuật toán megamorphic tối ưu cuối cùng. Trong production có thể dùng bảng tra đã cache theo `Class`, `ClassValue` hoặc một dispatch cấu trúc khác để tránh lookup đắt khi các kiểu hiếm xuất hiện lặp lại.

### 5.4. Không hiểu số miss là số receiver khác nhau

Một receiver class chưa cache có thể tạo **nhiều lần miss**, nhất là khi vượt giới hạn PIC. Ngược lại nhiều object khác nhau cùng class có thể đều hit một guard. Vì thế thống kê misses phải diễn giải theo **điểm gọi**, **class distribution** và **chính sách cache**.

## 6. API tối thiểu và các quy tắc kiểu bắt buộc

| API | Mục đích | Quy tắc cần tuân thủ |
| --- | --- | --- |
| `new MutableCallSite(MethodType)` | Tạo site có chữ ký xác định | Target ban đầu chỉ là placeholder; phải cài target sử dụng được trước khi gọi |
| `site.dynamicInvoker()` | Lời gọi đi theo target hiện tại | Kiểu của invoker bằng `site.type()` |
| `site.getTarget()` | Lấy chain đang dùng | Với MutableCallSite, các thread khác có thể cần sync để thấy target mới |
| `site.setTarget(handle)` | Cập nhật đường thực thi | `handle.type().equals(site.type())` là bắt buộc |
| `MutableCallSite.syncAll(sites)` | Đồng bộ các target updates | Chi phí có thể lớn; không gọi trong hot path mỗi invocation |
| `Lookup.findVirtual(...)` | Resolve method đích cho class runtime | Cần đúng tên, signature và quyền truy cập |
| `handle.asType(site.type())` | Adapt kiểu đối số/kết quả | Chỉ hỗ trợ những conversion hợp lệ; có thể kiểm tra/cast runtime |
| `MethodHandles.insertArguments(...)` | Cố định expected receiver class cho test | Kết quả có ít tham số hơn, đúng vị trí đã bound |
| `MethodHandles.guardWithTest(...)` | Ghép fast path và fallback | Predicate trả boolean; target/fallback cùng method type |

Không được nhầm:
- **`MethodType`** là signature, không tự thực thi method.
- **`MethodHandle`** là đối tượng có thể thực thi một đường gọi.
- **`CallSite`** giữ một target handle có thể thay đổi.
- **Inline cache** là **chiến lược** xây cấu trúc guard/target/fallback quanh call site, không phải một subtype Java tên `InlineCache` có sẵn.

## 7. Ví dụ hoàn chỉnh Java 17+: PIC với guard receiver và relink fallback

File **`InlineCacheDemo.java`** dưới đây có bốn class receiver khác nhau, mỗi class khai báo `public String speak()`. `Cache` là một `MutableCallSite` kiểu `(Object)String`. Một fallback cho phép resolve bằng `findVirtual`, dựng guard theo **exact runtime class**, và cập nhật target nếu chưa đủ ba class đã cache.

**Mã nguồn chạy độc lập:**

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.MutableCallSite;
import java.util.LinkedHashSet;
import java.util.Objects;
import java.util.Set;

public class InlineCacheDemo {
    private static final MethodHandles.Lookup LOOKUP = MethodHandles.lookup();
    private static final MethodType SITE_TYPE =
            MethodType.methodType(String.class, Object.class);
    private static final int MAX_GUARDS = 3;
    private static final MethodHandle RELINK;
    private static final MethodHandle IS_EXACT_CLASS;

    static {
        try {
            RELINK = LOOKUP.findStatic(
                    InlineCacheDemo.class, "relink",
                    MethodType.methodType(String.class, Cache.class, Object.class));
            IS_EXACT_CLASS = LOOKUP.findStatic(
                    InlineCacheDemo.class, "isExactClass",
                    MethodType.methodType(boolean.class, Class.class, Object.class));
        } catch (ReflectiveOperationException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    public static final class Dog {
        public String speak() { return "woof"; }
    }
    public static final class Cat {
        public String speak() { return "meow"; }
    }
    public static final class Bird {
        public String speak() { return "chirp"; }
    }
    public static final class Fox {
        public String speak() { return "yip"; }
    }

    static final class Cache extends MutableCallSite {
        final MethodHandle invoker;
        final Set<Class<?>> cachedTypes = new LinkedHashSet<>();
        int misses;

        Cache() {
            super(SITE_TYPE);
            MethodHandle fallback = MethodHandles.insertArguments(RELINK, 0, this);
            setTarget(fallback);
            invoker = dynamicInvoker();
        }
    }

    private static boolean isExactClass(Class<?> expected, Object receiver) {
        return receiver != null && receiver.getClass() == expected;
    }

    private static String relink(Cache site, Object receiver) throws Throwable {
        Objects.requireNonNull(receiver, "receiver");
        Class<?> actual = receiver.getClass();

        MethodHandle direct = LOOKUP.findVirtual(
                actual, "speak", MethodType.methodType(String.class))
                .asType(SITE_TYPE);

        synchronized (site) {
            site.misses++;
            if (site.cachedTypes.size() < MAX_GUARDS
                    && !site.cachedTypes.contains(actual)) {
                MethodHandle test =
                        MethodHandles.insertArguments(IS_EXACT_CLASS, 0, actual);
                MethodHandle next = MethodHandles.guardWithTest(
                        test, direct, site.getTarget());
                site.setTarget(next);
                site.cachedTypes.add(actual);
                MutableCallSite.syncAll(new MutableCallSite[]{site});
            }
        }
        return (String) direct.invokeExact(receiver);
    }

    private static void call(Cache site, String label, Object receiver)
            throws Throwable {
        String result = (String) site.invoker.invokeExact(receiver);
        System.out.println(label + "=" + result
                + ";misses=" + site.misses
                + ";cached=" + site.cachedTypes.size());
    }

    public static void main(String[] args) throws Throwable {
        Cache site = new Cache();
        System.out.println("siteType=" + site.type());
        call(site, "dog1", new Dog());
        call(site, "dog2", new Dog());
        call(site, "cat1", new Cat());
        call(site, "dog3", new Dog());
        call(site, "bird1", new Bird());
        call(site, "fox1", new Fox());
        call(site, "fox2", new Fox());
        call(site, "cat2", new Cat());

        try {
            String ignored = (String) site.invoker.invokeExact((Object) null);
        } catch (NullPointerException e) {
            System.out.println("nullReceiver=" + e.getClass().getSimpleName());
        }
        try {
            String ignored = (String) site.invoker.invokeExact((Object) new Object());
        } catch (NoSuchMethodException e) {
            System.out.println("unsupported=" + e.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 InlineCacheDemo.java
java InlineCacheDemo
```

**Stdout đã kiểm chứng bằng bản Java tương thích Java 17:**

```text
siteType=(Object)String
dog1=woof;misses=1;cached=1
dog2=woof;misses=1;cached=1
cat1=meow;misses=2;cached=2
dog3=woof;misses=2;cached=2
bird1=chirp;misses=3;cached=3
fox1=yip;misses=4;cached=3
fox2=yip;misses=5;cached=3
cat2=meow;misses=5;cached=3
nullReceiver=NullPointerException
unsupported=NoSuchMethodException
```

### 7.1. Khởi tạo bằng fallback

`new MutableCallSite(SITE_TYPE)` cố định signature `(Object)String`. Constructor của `Cache` xây fallback bằng `insertArguments(RELINK,0,this)`, biến `relink(Cache,Object)String` thành handle `(Object)String` rồi `setTarget(fallback)`. Chưa có class nào được cache, nên lời gọi đầu phải đi fallback.

`invoker = dynamicInvoker()` được tạo **một lần** và vẫn dùng được sau mọi lần thay target. Đây là đặc tính then chốt: caller **không cần lấy MethodHandle mới** mỗi khi lớp receiver thay đổi.

### 7.2. `Dog` lần đầu: miss và học target

Dòng `dog1=woof;misses=1;cached=1`:

1. `invoker` đi tới fallback.
2. `relink` nhận `Dog`, tìm `Dog.speak()` bằng `findVirtual`.
3. `asType(SITE_TYPE)` chuyển `(Dog)String` thành `(Object)String`.
4. `insertArguments` cố định `Dog.class` cho predicate, tạo `(Object)boolean`.
5. `guardWithTest(test, direct, oldTarget)` tạo target mới gồm fast path Dog và fallback cũ.
6. `setTarget` cài chain, `syncAll` công bố thay đổi.
7. Fallback gọi `direct.invokeExact(receiver)` cho **chính lời gọi đầu tiên**, nhận `"woof"`.

### 7.3. `Dog` lần thứ hai: cache hit

Dòng `dog2=woof;misses=1;cached=1` chứng minh lần gọi thứ hai với **một object Dog khác** có cùng runtime class được guard nhận diện, không vào `relink`. Số misses không tăng.

Đó là **cache theo class**, không phải cache theo object instance. Hai object `new Dog()` khác nhau đều thỏa `receiver.getClass() == Dog.class`.

### 7.4. `Cat` và `Bird`: mở rộng PIC

Lần đầu gặp Cat, guard Dog trả false, fallback resolve target Cat rồi cài:

```text
guard(Cat, catHandle, guard(Dog, dogHandle, fallback))
```

Lần đầu gặp Bird, cấu trúc thành:

```text
guard(Bird, birdHandle,
    guard(Cat, catHandle,
        guard(Dog, dogHandle,
            fallback)))
```

Các call Dog/Cat tiếp theo vẫn hit guard tương ứng. Vì guard mới thêm ở **đầu chain**, kiểu mới nhất được kiểm tra trước; thứ tự này không phải thuật toán luôn tối ưu mọi workload. Với distribution ổn định, có thể sắp theo tần suất hoặc đổi chính sách PIC sau đo đạc.

### 7.5. `Fox` sau khi cache có ba class

Dòng `fox1=yip;misses=4;cached=3` cho biết `Fox` được xử lý đúng bằng đường miss, nhưng **không thêm guard mới** vì đạt `MAX_GUARDS=3`. Gọi Fox lần nữa làm misses tăng lên `5`.

Hai lần Fox trả `yip` hợp lệ. Không nên đánh đồng “không cache” với “không hỗ trợ phương thức”. Fallback vẫn có thể gọi bất kỳ class nào có method `speak()String` mà `Lookup` truy cập được.

### 7.6. Null và method không tồn tại

- `nullReceiver=NullPointerException`: predicate exact-class trả false cho null; fallback chủ động dùng `Objects.requireNonNull` trước lookup.
- `unsupported=NoSuchMethodException`: `new Object()` không có method `speak()String`, nên `Lookup.findVirtual` thất bại. Đây là **lỗi resolution**, không phải cache miss thông thường đã dispatch thành công.

Trong demo, `misses` chỉ tăng **sau khi** `findVirtual` thành công, nên null và unsupported không làm tăng số đếm. Đây là cách định nghĩa metric của **ví dụ**, không phải quy ước toàn JVM.

### 7.7. Tính đúng khi nhiều thread dùng cùng site

Phần cài guard diễn ra trong `synchronized(site)`, giảm rủi ro hai writer ghi đè chain của nhau. `syncAll` công bố target mới tới các thread khác theo semantics `MutableCallSite`.

**Giới hạn cố ý của chương trình:** Các lần `call(...)` trong `main` được chạy **tuần tự** để stdout xác định. Hai trường `misses` và `cachedTypes` được đọc để hiển thị mà không lấy lock vì demo không có reader ghi song song trong lúc in. Với code production nhiều luồng, cần đồng bộ hoặc dùng primitive thread-safe cho **các metrics và trạng thái cache**, không chỉ cho việc thay target.

### 7.8. Vì sao ví dụ không phải benchmark?

Số misses và cached classes là **chứng cứ đường dispatch**, không phải số đo performance hoặc bằng chứng JIT đã inline các method. `System.out.println`, allocation, first-time class loading và setup handles ảnh hưởng đáng kể nếu đo thời gian trực tiếp trong demo. Benchmark nghiêm túc nên có warm-up, phân phối receiver rõ ràng và công cụ như JMH.

## 8. Thread safety và visibility của MutableCallSite

`MutableCallSite.setTarget(...)` có semantics của một **biến thông thường**. Chỉ gọi `setTarget` từ một thread **không buộc** các thread khác đang thực thi target phải ngay lập tức thấy update; JIT/runtime được phép giữ target cũ trong những điều kiện mà memory model cho phép.

`MutableCallSite.syncAll(MutableCallSite[] sites)` cung cấp cơ chế đồng bộ đặc biệt để những lần đọc về sau chấp nhận target mới nhất tương đối với lần sync. Nó **không quay ngược** những lời gọi đã bắt đầu chạy theo target cũ.

### 8.1. Các bước publish đúng

Trong code demo, lần relink thực hiện:
1. Đi vào `synchronized(site)` (phối hợp các writer).
2. Lấy `site.getTarget()` hiện tại **bên trong vùng khóa**.
3. Lắp guard mới lên chain đã có.
4. `site.setTarget(newChain)`.
5. Ghi metadata về class đã cache.
6. `MutableCallSite.syncAll(new MutableCallSite[]{site})`.
7. Ra khỏi vùng khóa.

Điều này giúp tránh lost relink và đảm bảo publication khi các reader tiếp tục gọi qua `dynamicInvoker()`. Một reader có thể đã bắt đầu bằng chain cũ trước khi sync; vì chain đó vẫn có fallback đúng, nó không mất tính đúng đắn.

**Lưu ý:** `syncAll` có thể tốn chi phí đáng kể, và có thể phối hợp/đợi các thread đang có target cũ. Không gọi nó sau **mọi cache hit**. Với batch nhiều sites cùng đổi, có thể gom để sync một lần khi phù hợp.

### 8.2. Khi nào chọn VolatileCallSite?

Nếu yêu cầu **mọi thread** thấy cập nhật target theo volatile visibility mà không quản lý `syncAll` riêng, `VolatileCallSite` có semantics phù hợp. Đổi lại, mỗi truy cập target mang chi phí/giới hạn tối ưu của volatile semantics. Không có đáp án luôn nhanh hơn: cân nhắc tần suất relink, số thread, độ ổn định của site và hiệu năng sau warm-up.

`ConstantCallSite` không hỗ trợ relink bằng `setTarget`; nó hợp lý nếu bootstrap đã xác định đích và đích không đổi. Không chọn `ConstantCallSite` rồi kỳ vọng dựng PIC bằng cập nhật target trực tiếp.

### 8.3. Không dùng target update để sửa một transaction

Target của CallSite quyết định **đường thực thi**, không tự bảo đảm tính nhất quán của dữ liệu ứng dụng khi plugin/config thay đổi. Nếu target tham chiếu state mutable, bản thân state đó vẫn cần synchronization theo Java Memory Model. Một relink không tương đương transaction hay distributed configuration barrier.

## 9. Hợp lệ hóa cache và nhánh liên kết lại

Một cache theo class đúng khi kết quả method resolution **chỉ phụ thuộc vào runtime class và những yếu tố ổn định**. Nếu hệ thống còn hỗ trợ:
- hot reload plugin;
- thay đổi quyền truy cập/chính sách;
- schema hoặc protocol version;
- method table/runtime shape của ngôn ngữ động;
- feature flag thay target implementation;

thì cache có thể bị **stale** dù receiver class không đổi. Một class guard đơn lẻ không thể phát hiện mọi thay đổi đó.

### 9.1. Invalidation bằng SwitchPoint

`java.lang.invoke.SwitchPoint` hỗ trợ một công tắc **hợp lệ → không hợp lệ** chỉ đi một chiều. Nó có thể bọc fast target và fallback:

```java
SwitchPoint version = new SwitchPoint();
MethodHandle guarded = version.guardWithTest(fastTarget, fallback);
// Khi version này không còn dùng được:
SwitchPoint.invalidateAll(new SwitchPoint[]{version});
```

Đây là đoạn minh họa, cần import `java.lang.invoke.SwitchPoint` và có `fastTarget/fallback` **cùng MethodType**. Sau invalidation, lời gọi tới guard đó chuyển qua fallback. Không thể “bật lại” cùng một `SwitchPoint`; muốn cache thế hệ mới, tạo switch point/guard mới.

**Quan trọng:** Cơ chế invalidate phải được ứng dụng gọi khi policy/metadata thay đổi. `SwitchPoint` **không tự quan sát** file cấu hình hay thay đổi plugin để phát hiện stale cache.

### 9.2. Cache miss khác cache invalidation

- **Miss:** Chưa có guard phù hợp cho receiver mới, hoặc PIC đã bão hòa nên receiver đi nhánh chung.
- **Invalidation:** Guard/target đã được cache nhưng bị coi là không còn hợp lệ do version/policy/shape đổi.
- **Relink:** Hành động tìm và cài đường gọi mới; có thể xuất phát từ miss **hoặc** invalidation.

Sử dụng một fallback cho cả hai loại tình huống vẫn được, nhưng cần phân biệt metric/policy để tránh relink vô hạn khi configuration không hợp lệ.

### 9.3. ClassLoader và reference giữ sống lâu

Một guard chứa đối tượng `Class<?>` và handle tham chiếu tới method/class. Nếu cache sống lâu hơn plugin/class loader, nó có thể ngăn class loader được thu gom. Trong hệ thống plugin động:
- dùng scope cache gắn với vòng đời plugin/tenant;
- xóa hoặc thay target khi unload;
- hạn chế PIC chain;
- cân nhắc weak references/`ClassValue` khi thiết kế cache toàn cục, nhưng phải hiểu semantics và vòng đời thực sự;
- không dùng tên class dạng `String` làm định danh duy nhất nếu nhiều loader có thể định nghĩa cùng tên.

Giới hạn ba guard trong demo vừa giúp học, vừa minh họa cách hạn chế việc tích lũy class references trên một site.

## 10. Xử lý lỗi trong lookup, adapter và target

Đường fallback ở ví dụ thực hiện:

```java
MethodHandle direct = LOOKUP.findVirtual(
        actual, "speak", MethodType.methodType(String.class))
        .asType(SITE_TYPE);
```

Đây là đoạn trích từ chương trình đầy đủ. Những loại lỗi cần phân biệt:

| Giai đoạn | Ví dụ | Kết quả hoặc cách xử lý |
| --- | --- | --- |
| Receiver null | Caller truyền `null` | Demo chủ động ném `NullPointerException("receiver")`; có thể đổi thành policy riêng |
| Lookup: method không tồn tại | Class không có `speak()String` phù hợp | `NoSuchMethodException` |
| Lookup: quyền truy cập | Method/class không thể truy cập bằng `Lookup` hiện có | `IllegalAccessException` |
| Adapter: không tương thích | `asType` không thể chuyển kiểu như yêu cầu | Có thể `WrongMethodTypeException` khi tạo adapter hoặc lỗi conversion khi invoke |
| Update site: target sai type | `setTarget` nhận `MethodHandle` khác `site.type()` | `WrongMethodTypeException` |
| Guard: bộ handle sai type | `guardWithTest` nhận test/target/fallback không phù hợp | `IllegalArgumentException` |
| Thực thi target | `speak()` ném exception | Throwable từ đích có thể truyền trực tiếp qua MethodHandle; không tự bọc bằng `InvocationTargetException` |
| Cache quá lớn | Tích lũy nhiều guards, handles, classes | Tăng chi phí/bộ nhớ; cần cap, fallback và eviction/invalidation policy |

Không nên bắt mọi exception trong fallback rồi **cache một lỗi chung** hoặc trả chuỗi mặc định, trừ khi đó là contract ứng dụng. Ví dụ một method không tồn tại có thể cần diagnostic rõ:
- class runtime được quan sát;
- tên và method type đã yêu cầu;
- class loader hoặc module;
- policy của site và hành động fallback.

### 10.1. Vấn đề bảo mật của dynamic method lookup

`MethodHandles.lookup()` mang quyền truy cập của class tại nơi tạo lookup. Nó **không** cho phép bypass mọi `private` members/module boundaries. Đừng nhận arbitrary class name/method name từ dữ liệu ngoài rồi cho phép gọi bất kỳ method nào: validate whitelist/schema/permissions, dùng lookup giới hạn và kiểm soát exception.

Trong chương trình demo, các class `Dog/Cat/Bird/Fox` nằm trong cùng class bao ngoài (nest) và các method `public`, nên lookup hợp lệ. Với plugin thực, JPMS `exports`/`opens`, access context và package visibility có thể ảnh hưởng kết quả.

### 10.2. Không nén lỗi của target thành “cache miss”

Khi một guard hit và method đích ném `IllegalStateException`, đó là **lỗi target**, không phải lời gọi cần relink theo mặc định. Nếu catch Throwable trên toàn hot path và re-resolve với mọi exception, bạn có thể thực thi lại side effect nguy hiểm hoặc che bug nghiệp vụ.

Chỉ đi nhánh relink khi **điều kiện guard/invalidation thất bại**. Exception từ target phải tuân theo hợp đồng phương thức và cơ chế xử lý lỗi của ứng dụng.

## 11. Một điểm gọi không nhất thiết luôn cache cùng bộ kiểu

Một site có thể trải qua các pha:

```text
Initial (cold)
    target = relinkFallback

Monomorphic
    target = guard(Dog, dogHandle, relinkFallback)

Polymorphic
    target = guard(Cat, catHandle,
                guard(Dog, dogHandle, relinkFallback))

Saturated PIC
    target = guard(Bird, birdHandle,
                guard(Cat, catHandle,
                    guard(Dog, dogHandle, relinkFallback)))

Receiver mới sau bão hòa
    -> fallback (resolve/generic dispatch, không thêm guard mới)
```

Một runtime tối ưu hóa phức tạp hơn có thể thay chain bằng:
- bảng lookup theo class;
- dạng dispatch theo receiver shape;
- một target generic tối ưu cho megamorphic site;
- code cache được dựng lại theo profile hoặc theo tier của JIT.

Đây là **những lựa chọn thiết kế**, không phải các trạng thái mặc định mà `MutableCallSite` tự động chuyển đổi. JDK chỉ cung cấp primitives; ứng dụng/runtime phải thực hiện logic để chuyển giữa các chiến lược.

## 12. Những ngộ nhận thường gặp

1. **“`CallSite` tự cache mọi receiver class.”** Sai. `CallSite` chỉ giữ một target handle. Cache/guard/relink là logic do runtime ứng dụng xây.
2. **“`dynamicInvoker()` gọi mãi target ban đầu.”** Sai với mutable call site; nó theo target hiện tại của site, theo semantics visibility tương ứng.
3. **“Muốn tối ưu cho Dog thì đổi site type từ Object sang Dog.”** Không hợp lệ. `CallSite.type()` cố định; phải adapt target riêng bằng `asType`.
4. **“Kiểm tra tên class bằng chuỗi là tương đương kiểm tra Class identity.”** Sai khi có nhiều class loaders.
5. **“Một guard có thể nhận null rồi gọi method bình thường.”** Không nếu đích cần receiver instance; phải chọn policy null rõ.
6. **“Guard dùng `instanceof` luôn an toàn.”** Không nếu dispatch phụ thuộc exact runtime class, shape hoặc version.
7. **“Relink phải gọi lại `dynamicInvoker` cho chính lần miss.”** Không bắt buộc và dễ gây recursion/đếm kép; có thể gọi direct handle đã resolve.
8. **“`MutableCallSite.setTarget` đảm bảo mọi thread nhìn thấy ngay.”** Sai. Cần đồng bộ phù hợp, ví dụ `syncAll`; `VolatileCallSite` có semantics khác.
9. **“`syncAll` làm các invocation đã chạy target cũ quay lại chạy target mới.”** Sai; các lời gọi đã bắt đầu có thể hoàn tất theo target cũ.
10. **“Cứ thêm guard cho tất cả class thì luôn nhanh nhất.”** Không. PIC quá dài tốn lookup trên miss, tăng footprint và có thể ảnh hưởng JIT.
11. **“Số miss bằng số class khác nhau.”** Không; class không được cache có thể miss nhiều lần.
12. **“Cache hit nghĩa là JIT chắc chắn đã inline target.”** Không. Hit chỉ mô tả đường đi qua guard/handle; tối ưu JIT cần profiling và không được cam kết.
13. **“Một lần lookup thất bại là receiver không có method ở mọi context.”** Không. Quyền của `Lookup`, module access, method signature và loader ảnh hưởng resolution.
14. **“Relink có thể sửa luôn trạng thái nghiệp vụ khi exception target xảy ra.”** Không. Relink là thay đường dispatch, không phải retry side effect tùy tiện.
15. **“Giữ Class/MethodHandle trong cache không ảnh hưởng unload plugin.”** Có thể ảnh hưởng vòng đời class loader và memory.
16. **“`SwitchPoint` tự invalidates khi plugin đổi.”** Không. Ứng dụng phải phát tín hiệu invalidation theo chính sách của mình.

## 13. Tự kiểm tra

### Bài 1 — Vẽ PIC

Một site có target `guard(Cat, catHandle, guard(Dog, dogHandle, miss))`. Khi gọi với một `Dog` mới, nhánh nào chạy?

**Đáp án:** Guard Cat trả false, guard Dog trả true, nên gọi `dogHandle`. Không gọi `miss` và không thêm cache entry.

### Bài 2 — Receiver class và MethodType

Site có kiểu `(Object)String`, nhưng `findVirtual(Dog.class,"speak",()String)` tạo `(Dog)String`. Có thể `site.setTarget(dogHandle)` trực tiếp không?

**Đáp án:** Không. `setTarget` yêu cầu method type **bằng** site type. Cần `dogHandle.asType(MethodType.methodType(String.class,Object.class))`, rồi gắn guard `Dog.class` để bảo đảm receiver đúng.

### Bài 3 — Miss ở cache đã đầy

PIC giới hạn ba class, đã cache Dog/Cat/Bird. Có hai lời gọi Fox liên tiếp. Nếu fallback không bổ sung Fox vào cache, sẽ có bao nhiêu miss mới?

**Đáp án:** Hai miss. Mỗi lần Fox đi qua hết ba guard và vào fallback; vẫn có thể trả kết quả đúng.

### Bài 4 — Đồng bộ các writer

Hai thread đồng thời lấy oldTarget, một cài guard Dog, một cài guard Cat. Cả hai `setTarget` không lock. Rủi ro nào?

**Đáp án:** Lost relink: target cuối có thể thiếu guard do thread kia vừa thêm. Phải cập nhật chain theo policy phối hợp writer (ví dụ `synchronized(site)`) và bảo đảm target visibility cho reader bằng cơ chế thích hợp.

### Bài 5 — Invalidation

Receiver vẫn là Dog nhưng plugin được cấu hình để Dog.speak có hành vi mới. Guard `getClass()==Dog.class` còn trả true. PIC có tự biết target stale không?

**Đáp án:** Không. Nếu hành vi dispatch phụ thuộc version/config ngoài class identity, cần guard bổ sung hoặc invalidation, chẳng hạn bằng `SwitchPoint.invalidateAll(...)` và relink tới target thế hệ mới.

### Bài 6 — Gọi exact đúng kiểu

`MethodHandle invoker` có kiểu `(Object)String`. Sự khác nhau giữa:

```java
String good = (String) invoker.invokeExact((Object) new Dog());
String bad = (String) invoker.invokeExact(new Dog());
```

Đây là hai dòng minh họa trong method có biến `invoker` và class `Dog`. Nếu kiểu tĩnh biểu thức thứ hai là `Dog`, nó không khớp parameter `Object` mà `invokeExact` đòi hỏi; có thể ném `WrongMethodTypeException`. Dòng đầu cast receiver thành `Object` để tạo call-site descriptor đúng, trong khi guard runtime vẫn nhìn thấy class thực `Dog`.

### Bài 7 — Tiêu chí hiệu năng

Khi PIC có ba guard, liên tục gọi 100 class khác nhau mỗi class một lần. Vì sao có thể chậm hơn generic dispatch phù hợp?

**Đáp án:** Hầu hết lời gọi đều qua ba guard rồi miss, phải resolve và có thể tạo adapter mới mà không cache; chi phí per-miss cao. Cần đo workload thực, tối ưu fallback cho megamorphic hoặc chọn cache toàn cục phù hợp.

## Tài liệu chính thức

- [Java SE 17 — CallSite](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/CallSite.html): contract `type`, `target` và `dynamicInvoker`.
- [Java SE 17 — MutableCallSite](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MutableCallSite.html): `setTarget`, `syncAll` và visibility giữa các thread.
- [Java SE 17 — VolatileCallSite](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/VolatileCallSite.html): target theo volatile semantics.
- [Java SE 17 — MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): `guardWithTest`, `insertArguments`, `Lookup.findVirtual`.
- [Java SE 17 — MethodHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `asType`, `invokeExact`.
- [Java SE 17 — SwitchPoint](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/SwitchPoint.html): invalidate guarded targets khi thông tin cache hết hiệu lực.

## Kết luận

Bộ nhớ đệm tại điểm gọi giúp **chuyển lookup động lặp lại thành đường nhanh có guard**. Với receiver class từng gặp, `guardWithTest` chọn target đã resolve; khi gặp class khác, nhánh **fallback/relink** kiểm tra kiểu, tìm handle mới, adapt về `CallSite.type()` và cập nhật chain. `MutableCallSite` không tự cung cấp một PIC: ứng dụng phải xây guard, giới hạn số nhánh, đồng bộ update giữa các thread và quản lý invalidation. Một thiết kế đúng phải bảo toàn hợp đồng kiểu, không bỏ qua null/lookup failure, không vô tình cache target stale và không đánh đồng cache hit với bảo đảm tối ưu JIT.
