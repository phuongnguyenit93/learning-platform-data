# unreflect() và unreflectConstructor(): chuyển metadata reflection thành handle có quyền phù hợp

## 1. Mục tiêu: từ metadata sang lời gọi có kiểu

Trong Java, API reflection cho phép khám phá thành viên của một lớp:

- `java.lang.reflect.Method` mô tả một phương thức.
- `java.lang.reflect.Constructor` mô tả một constructor.
- `java.lang.invoke.MethodHandle` biểu diễn một khả năng gọi có kiểu được xác định bằng `MethodType`.

Hai phương thức của `MethodHandles.Lookup` kết nối các API đó:

```java
MethodHandle methodHandle = lookup.unreflect(method);
MethodHandle constructorHandle = lookup.unreflectConstructor(constructor);
```

Đây là chủ đề **Lookup và adapter** của module `JAVA_VERSION_JAVA18`: học cách kiểm chứng hợp đồng Reflection và MethodHandle bằng API vẫn được hỗ trợ trên JDK hiện đại. Java 18 đưa Core Reflection sang cách triển khai dựa trên method handles (JEP 416), nhưng hợp đồng về **quyền của caller**, **kiểu handle**, và **ngoại lệ khi gọi** là điều ứng dụng cần hiểu độc lập với chi tiết triển khai JVM.

Hãy phân biệt ba câu hỏi:

1. **Tìm được metadata chưa?** `Class.getDeclaredMethod(...)` có thể trả về `Method` cho một phương thức `private`.
2. **Được phép tạo handle chưa?** `Lookup.unreflect(...)` xét quyền truy cập dựa trên lookup và trạng thái bỏ qua kiểm tra truy cập của đối tượng `Method`.
3. **Có gọi đúng kiểu và đúng đối tượng không?** `invokeExact(...)` yêu cầu chữ ký tại điểm gọi trùng với `handle.type()`.

**Điểm quan trọng:** `unreflect(...)` không tự cấp đặc quyền cho metadata. Nếu chưa có quyền truy cập, việc chuyển metadata thành handle có thể thất bại ngay ở bước tạo handle bằng `IllegalAccessException`.

## 2. Hai API và kiểu handle được tạo

| API | Đầu vào | Kiểu handle đầu ra | Ví dụ |
|---|---|---|---|
| `lookup.unreflect(method)` | Một `Method` đã tìm thấy | Phương thức static: giữ nguyên danh sách tham số; phương thức instance: thêm receiver đầu tiên | `Greeter.hello(int):String` → `(Greeter,int)String` |
| `lookup.unreflectConstructor(constructor)` | Một `Constructor<?>` đã tìm thấy | Giữ danh sách tham số constructor, trả về đối tượng lớp khai báo | `new Greeter(String)` → `(String)Greeter` |

Với phương thức `static`:

```java
// Ví dụ Method mô tả: public static long twice(long n)
MethodHandle mh = lookup.unreflect(method);
System.out.println(mh.type()); // (long)long
```

Không có receiver, vì đây là phương thức static.

Với phương thức instance:

```java
// Ví dụ Method mô tả: public String hello(int count)
MethodHandle mh = lookup.unreflect(method);
System.out.println(mh.type()); // (Greeter,int)String
```

Handle có tham số đầu là `Greeter`, đóng vai trò receiver. Trong khi đó, Reflection API nhận receiver thành đối số riêng của `Method.invoke(receiver, args...)`.

Với constructor:

```java
// Ví dụ Constructor mô tả: public Greeter(String greeting)
MethodHandle ctor = lookup.unreflectConstructor(constructor);
System.out.println(ctor.type()); // (String)Greeter
```

Handle constructor **không nhận receiver có sẵn**; nó cấp phát và khởi tạo một đối tượng mới mỗi lần được gọi. Trong `Constructor`, constructor không có kiểu trả về như phương thức thông thường; `MethodHandle` trả về lại **có** return type là lớp được tạo.

### Khác biệt với `findVirtual()` và `findConstructor()`

Có hai con đường tạo handle:

```text
Con đường A: có Method / Constructor trước
Class.getMethod(...) / Class.getConstructor(...)
                   |
                   v
       Lookup.unreflect(...)
       Lookup.unreflectConstructor(...)
                   |
                   v
             MethodHandle

Con đường B: biết lớp, tên và MethodType ngay từ đầu
Lookup.findVirtual(refc, name, methodType)
Lookup.findConstructor(refc, methodType)
                   |
                   v
             MethodHandle
```

- `unreflect(Method)` nhận một đối tượng `Method` đã chọn; không cần lặp lại tên phương thức hay danh sách kiểu tham số trong một `MethodType` mới.
- `unreflectConstructor(Constructor<?>)` nhận `Constructor` đã chọn; không cần yêu cầu `MethodType` trả về `void` như `findConstructor(...)`.
- `findConstructor(...)` **yêu cầu** return type của `MethodType` đầu vào là `void`; handle trả về vẫn có return type là lớp cần tạo. Với `unreflectConstructor(...)`, `Constructor<?>` cung cấp trực tiếp chữ ký đã tìm.

Khi một framework đã quét annotation và có sẵn các đối tượng reflection, `unreflect` và `unreflectConstructor` là cách tự nhiên để chuyển sang mô hình lời gọi có kiểu. Nếu chưa có metadata và biết chắc tên/chữ ký, các phương thức `find...` có thể giảm một bước chuẩn bị ở cấp ứng dụng; cần đo thực tế nếu hiệu năng là lý do lựa chọn.

## 3. Ví dụ chạy được: phương thức và constructor public

Lưu mã sau trong tệp `UnreflectDemo.java`. Đoạn mã dùng JDK hiện đại, không cần dependency ngoài:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;

public final class UnreflectDemo {
    public static final class Greeter {
        private final String greeting;

        public Greeter(String greeting) {
            this.greeting = greeting;
        }

        public String hello(int repeat) {
            return greeting.repeat(repeat);
        }

        public static int twice(int value) {
            return value * 2;
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        // Bước 1: tìm metadata của các thành viên public.
        Constructor<Greeter> reflectionCtor =
                Greeter.class.getConstructor(String.class);
        Method reflectionHello =
                Greeter.class.getMethod("hello", int.class);
        Method reflectionTwice =
                Greeter.class.getMethod("twice", int.class);

        // Bước 2: dùng Lookup có quyền để tạo handle.
        MethodHandle ctor = lookup.unreflectConstructor(reflectionCtor);
        MethodHandle hello = lookup.unreflect(reflectionHello);
        MethodHandle twice = lookup.unreflect(reflectionTwice);

        System.out.println(ctor.type());   // (String)Greeter
        System.out.println(hello.type());  // (Greeter,int)String
        System.out.println(twice.type());  // (int)int

        // Bước 3: gọi theo chữ ký chính xác của handle.
        Greeter greeter = (Greeter) ctor.invokeExact("Hi ");
        String message = (String) hello.invokeExact(greeter, 2);
        int doubled = (int) twice.invokeExact(21);

        System.out.println(message);
        System.out.println(doubled);

        // Bước 4: một adapter có kiểu tổng quát hơn.
        MethodType genericType = MethodType.methodType(
                Object.class, Object.class, Object.class);

        MethodHandle genericHello = hello.asType(genericType);
        Object genericResult = (Object) genericHello.invokeExact(
                (Object) greeter, (Object) Integer.valueOf(2));

        System.out.println(genericHello.type());
        System.out.println(genericResult);
    }
}
```

Kết quả dự kiến:

```text
(String)Greeter
(Greeter,int)String
(int)int
Hi Hi 
42
(Object,Object)Object
Hi Hi 
```

Phần `asType(...)` minh họa một **adapter**, không thay đổi phương thức đích. Vì handle gốc nhận `(Greeter,int)` và trả `String`, adapter `(Object,Object)Object` phải kiểm tra/cast receiver sang `Greeter`, chuyển `Integer` sang `int`, rồi trả `String` dưới kiểu tham chiếu `Object`. Một adapter có thể phát sinh chi phí chuyển đổi kiểu; nên tạo và cache nếu được dùng nhiều lần.

Các dòng `(Greeter) ctor.invokeExact(...)`, `(String) hello.invokeExact(...)` và `(int) twice.invokeExact(...)` cũng quan trọng: `invokeExact` kiểm tra **kiểu trả về tại điểm gọi**, không chỉ đối số truyền vào.

## 4. Metadata tồn tại chưa chắc có quyền tạo handle

Cách hiểu sai phổ biến là: “`getDeclaredMethod(...)` lấy được `Method` của `private`, vậy `unreflect(...)` chắc chắn tạo được handle.” Trên thực tế, **khám phá** và **truy cập** là hai bước riêng.

```text
getDeclaredMethod / getDeclaredConstructor
             │
             ▼
        Có metadata
             │
             ▼
        unreflect / unreflectConstructor
             │
      ┌──────┴─────────┐
      │                │
      ▼                ▼
 Quyền hợp lệ       Chưa đủ quyền
      │                │
      ▼                ▼
  MethodHandle     IllegalAccessException
```

### `Lookup` có thể làm gì?

`MethodHandles.lookup()` tạo `Lookup` gắn với **lớp gọi**, mang các khả năng truy cập tương ứng. Nó không tự động có quyền đối với mọi thành viên `private` của mọi lớp.

`MethodHandles.publicLookup()` có phạm vi hạn chế hơn, thích hợp với các kiểu và thành viên public được phép truy cập trong điều kiện module thích hợp.

Có thể dùng `MethodHandles.privateLookupIn(targetClass, callerLookup)` để xin một lookup có quyền truy cập sâu cho một lớp đích, **nếu** caller lookup có đủ khả năng và các điều kiện truy cập/module cho phép. Với named module khác nhau, package đích thường phải `opens` cho module của caller. Đây là cơ chế kiểm soát có chủ đích, không phải cách tự động vượt qua JPMS.

### Cờ bỏ qua kiểm tra truy cập của metadata

`Method` và `Constructor` kế thừa `AccessibleObject`. Trạng thái **access override** có thể được yêu cầu bằng `trySetAccessible()` hoặc `setAccessible(true)`. Với `unreflect(...)` và `unreflectConstructor(...)`, khi access override đã được bật hợp lệ trên chính metadata đó, việc kiểm tra quyền truy cập của member qua `Lookup` có thể được bỏ qua theo hợp đồng API.

Tuy nhiên:

- `trySetAccessible()` **có thể trả `false`**; việc bật cờ phải thỏa ranh giới package/module.
- `setAccessible(true)` **có thể ném `InaccessibleObjectException`** nếu không được phép bật truy cập sâu.
- Lấy được metadata **không** ngầm bật cờ này.
- Bật access override thành công không có nghĩa bỏ qua các yêu cầu đúng kiểu khi gọi handle, hoặc bỏ qua ngoại lệ từ mã đích.

Do đó, hai con đường hợp lệ thường là **Lookup có quyền phù hợp ngay từ đầu** hoặc **metadata đã được phép bật access override**. Không nên thiết kế ứng dụng dựa vào việc mọi private member luôn có thể được mở bằng reflection.

## 5. Ví dụ phân biệt quyền: hai lớp top-level độc lập

Để thử trường hợp `private` một cách rõ ràng, dùng hai lớp **top-level** trong cùng tệp `AccessToHandleDemo.java`. Không đặt `SecretBox` là lớp lồng của `AccessToHandleDemo`, vì các **nestmate** trong Java hiện đại có thể truy cập private member của nhau theo quy tắc riêng.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;

public final class AccessToHandleDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        // Tra cứu metadata thành công, dù thành viên là private.
        Method secret = SecretBox.class.getDeclaredMethod("message");
        Constructor<SecretBox> hiddenCtor =
                SecretBox.class.getDeclaredConstructor(String.class);

        try {
            lookup.unreflect(secret);
            throw new AssertionError("Expected IllegalAccessException");
        } catch (IllegalAccessException expected) {
            System.out.println("Method: access denied");
        }

        try {
            lookup.unreflectConstructor(hiddenCtor);
            throw new AssertionError("Expected IllegalAccessException");
        } catch (IllegalAccessException expected) {
            System.out.println("Constructor: access denied");
        }

        // Trong ví dụ classpath / unnamed module này,
        // cùng module cho phép thử bật quyền truy cập sâu.
        boolean methodOpened = secret.trySetAccessible();
        boolean ctorOpened = hiddenCtor.trySetAccessible();

        System.out.println(methodOpened);
        System.out.println(ctorOpened);

        if (methodOpened && ctorOpened) {
            MethodHandle create = lookup.unreflectConstructor(hiddenCtor);
            MethodHandle reveal = lookup.unreflect(secret);

            System.out.println(create.type());  // (String)SecretBox
            System.out.println(reveal.type());  // (SecretBox)String

            SecretBox box = (SecretBox) create.invokeExact("safe");
            String message = (String) reveal.invokeExact(box);

            System.out.println(message);
        }
    }
}

// Lớp top-level khác, không phải nestmate của AccessToHandleDemo.
class SecretBox {
    private final String value;

    private SecretBox(String value) {
        this.value = value;
    }

    private String message() {
        return "value=" + value;
    }
}
```

Kết quả dự kiến trong môi trường classpath thông thường:

```text
Method: access denied
Constructor: access denied
true
true
(String)SecretBox
(SecretBox)String
value=safe
```

Ở bước đầu, `Method` và `Constructor` đã có metadata, nhưng `Lookup` thuộc lớp top-level `AccessToHandleDemo` chưa có quyền truy cập private của `SecretBox`, nên việc chuyển thành handle bị từ chối.

Sau khi gọi `trySetAccessible()` thành công trong môi trường ví dụ, `Lookup.unreflect(...)` và `Lookup.unreflectConstructor(...)` có thể tạo handle. Đó là **kết quả của quyền truy cập được cấp hợp lệ**, không phải hành vi vượt qua bảo vệ của Java.

**Không đem nguyên giả định này sang named modules.** Nếu lớp đích thuộc một named module khác mà package không được mở cho caller, `trySetAccessible()` có thể trả `false` và việc tạo handle vẫn phải được xử lý như một trường hợp không đủ quyền.

### Dùng `privateLookupIn(...)` khi thiết kế quyền chủ đích

Để làm việc với private member bằng MethodHandle API ngay từ đầu, có thể tạo lookup phù hợp:

```java
MethodHandles.Lookup caller = MethodHandles.lookup();
MethodHandles.Lookup privateLookup =
        MethodHandles.privateLookupIn(SecretBox.class, caller);

MethodHandle create = privateLookup.findConstructor(
        SecretBox.class,
        java.lang.invoke.MethodType.methodType(void.class, String.class));
```

Đoạn minh họa giả định caller có đủ quyền tạo `privateLookup` (như trường hợp hai lớp trong cùng unnamed module của ví dụ). Khi tra `findConstructor`, request dùng return type `void`, trong khi handle trả về có kiểu `(String)SecretBox`.

Nếu đã có `Constructor<SecretBox>`, cũng có thể gọi:

```java
MethodHandle create = privateLookup.unreflectConstructor(hiddenCtor);
```

Với named module khác nhau, cần kiểm chứng điều kiện `opens` và khả năng của lookup; `privateLookupIn(...)` có thể ném `IllegalAccessException`. Trong sản phẩm, nếu không cần truy cập sâu, public factory hoặc constructor public thường có hợp đồng rõ ràng hơn.

## 6. `exports` và `opens` của named module

Ranh giới Java Platform Module System (JPMS) ảnh hưởng cả Reflection và MethodHandle. Với một member `public` trong kiểu `public`:

- `exports some.package` cho phép module được đọc truy cập public API của package theo quy tắc Java.
- `opens some.package` cho phép **deep reflection** vào package theo quy tắc truy cập sâu, nhưng không tương đương việc public API được export để import khi biên dịch.

Giả sử module `example.model` chứa lớp public `example.model.api.Account` có phương thức `public String id()` và constructor `private Account(String)`. Module `example.bridge` là caller.

| Khai báo package trong `example.model` | `unreflect` phương thức public bằng lookup hợp lệ ở module khác | Private constructor từ module khác |
|---|---|---|
| `exports example.model.api;` | Có thể tạo handle nếu đủ điều kiện truy cập public | `getDeclaredConstructor` có thể lấy metadata; deep access không mặc định được phép |
| `opens example.model.api to example.bridge;` | Phụ thuộc quyền và cách caller tiếp cận kiểu; `opens` không phải `exports` để import | Có thể thử `trySetAccessible` / `privateLookupIn` nếu đủ điều kiện |
| Cả `exports` lẫn `opens` cho caller | Public API truy cập được | Có thể sử dụng deep reflection hợp lệ |
| Không `exports` và không `opens` cho caller | Không có quyền truy cập thông thường từ bên ngoài | Không được tự bật truy cập sâu |

Ví dụ module đích cho phép một framework truy cập công khai lẫn private một cách có kiểm soát:

```java
module example.model {
    exports example.model.api;
    opens example.model.api to example.bridge;
}
```

Module gọi:

```java
module example.bridge {
    requires example.model;
}
```

Các điều kiện khác (đọc module, lớp đích, quyền của lookup gốc và trạng thái access override) vẫn cần thỏa mãn. Không nên chỉ nhìn thấy `public` hoặc `getDeclared...` thành công rồi suy ra `unreflect` luôn được phép.

**Gợi ý thiết kế:** mở đúng package cho đúng module cần reflection (`opens ... to ...`) nếu ứng dụng thực sự cần truy cập sâu. Tránh dựa vào package nội bộ JDK hoặc yêu cầu mở toàn bộ module như một điều kiện vận hành bình thường.

## 7. `MethodHandle` vẫn mang ngữ nghĩa thực thi của phương thức

Sau khi tạo handle hợp lệ, hành vi khi gọi còn phụ thuộc loại member:

| Member phản chiếu | Kiểu handle | Cách thực thi |
|---|---|---|
| Phương thức instance bình thường có thể override | `(DeclaringClass,args...)Result` | Receiver ở tham số đầu; có virtual dispatch theo kiểu đối tượng thực tế |
| Phương thức instance `final` | `(DeclaringClass,args...)Result` | Không có override để lựa chọn |
| Phương thức `static` | `(args...)Result` | Không có receiver |
| Constructor | `(args...)DeclaringClass` | Tạo đối tượng mới |
| Phương thức private được truy cập hợp lệ | `(DeclaringClass,args...)Result` | Private method không tham gia override thông thường |

### Kiểm chứng virtual dispatch

```java
public static class Parent {
    public String kind() { return "parent"; }
}

public static class Child extends Parent {
    @Override
    public String kind() { return "child"; }
}
```

Giả sử hai lớp nằm trong một lớp thử nghiệm hợp lệ, có import cần thiết. Phần gọi:

```java
Method m = Parent.class.getMethod("kind");
MethodHandle mh = MethodHandles.lookup().unreflect(m);

Parent receiver = new Child();
String result = (String) mh.invokeExact(receiver);
System.out.println(result); // child
```

`m.getDeclaringClass()` vẫn là `Parent.class`, nhưng handle của phương thức instance có thể override sẽ chọn triển khai `Child.kind()` theo receiver thực tế. `unreflect` không phải cách mặc định để ép gọi thân hàm lớp cha như `super.kind()`; trường hợp cần ngữ nghĩa special invocation phải nghiên cứu `Lookup.unreflectSpecial(...)` và điều kiện quyền riêng.

### Lưu ý về đối số và kiểu của `invokeExact`

`invokeExact(...)` đòi **kiểu tại điểm gọi** trùng `handle.type()`. Với handle `(Greeter,int)String`, hai cách sau khác nhau:

```java
String ok = (String) hello.invokeExact(greeter, 2);

// Sai nếu biểu thức bắt buộc return type Object ở điểm gọi.
Object wrong = (Object) hello.invokeExact(greeter, 2);
```

Cách nhận vào `Object` mà vẫn đúng kiểu gốc:

```java
Object okAsObject = (Object) (String) hello.invokeExact(greeter, 2);
```

Hoặc chủ động tạo adapter bằng `asType(...)` như phần 3. Dùng `invoke(...)` cũng có thể áp dụng các chuyển đổi hợp lệ theo quy tắc MethodHandle. Không nên nghĩ rằng `MethodHandle` sẽ tự động đổi mọi kiểu đầu vào như `Method.invoke(Object,Object...)`.

## 8. Ngoại lệ: thất bại khi tra cứu khác với thất bại khi gọi

| Thời điểm | Lỗi | Giải thích |
|---|---|---|
| Tìm metadata | `NoSuchMethodException` | Không có phương thức/constructor với tên và kiểu tham số phù hợp |
| `unreflect(...)` / `unreflectConstructor(...)` | `IllegalAccessException` | Lookup hoặc trạng thái access override không cho phép truy cập member |
| `privateLookupIn(...)` | `IllegalAccessException` | Không thỏa điều kiện truy cập sâu, trong đó có ranh giới module |
| `trySetAccessible()` | `false` | Không thể bật bỏ qua kiểm tra truy cập theo điều kiện hiện tại |
| `setAccessible(true)` | `InaccessibleObjectException` | Bật access override bị từ chối |
| `invokeExact(...)` | `WrongMethodTypeException` | Chữ ký tại điểm gọi không khớp kiểu handle |
| `invoke(...)` / adapter | `WrongMethodTypeException`, `ClassCastException` hoặc lỗi chuyển kiểu phù hợp | Kiểu yêu cầu không chuyển được hoặc giá trị thực tế không hợp lệ |
| Khi chạy mã đích | Ngoại lệ do method/constructor ném | MethodHandle thường truyền ngoại lệ gốc trực tiếp |

Phân biệt cách xử lý ngoại lệ do mã đích ném:

```java
public static class Task {
    public void execute() {
        throw new IllegalStateException("failed");
    }
}
```

Với reflection, `Method.invoke(...)` **bọc** ngoại lệ của target trong `InvocationTargetException`. Với `MethodHandle.invokeExact(...)`, ngoại lệ `IllegalStateException` do target ném thường được truyền trực tiếp:

```java
Method m = Task.class.getMethod("execute");
MethodHandle mh = MethodHandles.lookup().unreflect(m);

try {
    mh.invokeExact(new Task()); // handle có kiểu (Task)void
} catch (IllegalStateException expected) {
    System.out.println(expected.getMessage()); // failed
}
```

Ví dụ đặt trong ngữ cảnh xử lý `Throwable` phù hợp và class `Task` truy cập được. Khác biệt này quan trọng khi chuyển framework từ `Method.invoke(...)` sang MethodHandle: hãy kiểm tra lại nhánh phân loại và bọc ngoại lệ cho tương thích với API ứng dụng.

## 9. Cache handle và adapter mà không phá vỡ hợp đồng quyền

Sau khi chuyển một `Method` hoặc `Constructor` thành handle hợp lệ, framework thường cache handle theo mapping để dùng nhiều lần. Một quy trình hợp lý:

1. Khám phá metadata theo tên, chữ ký hoặc annotation.
2. Xác định cơ chế truy cập: member public, lookup đủ quyền, hoặc access override được cấp hợp lệ.
3. Tạo `MethodHandle` bằng `unreflect` / `unreflectConstructor`.
4. Nếu cần kiểu tổng quát cho framework, tạo `asType(...)` một lần và lưu cùng mapping.
5. Kiểm tra `handle.type()` và các nhánh lỗi trước khi triển khai.
6. Gọi lại handle trong hot path, thay vì lặp metadata lookup và adapter setup mỗi request.

Ví dụ một lớp giữ handle public:

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.reflect.Method;

public final class Invoker {
    private final MethodHandle call;

    public Invoker(Class<?> serviceType) throws ReflectiveOperationException {
        Method method = serviceType.getMethod("run", String.class);
        call = MethodHandles.publicLookup().unreflect(method);
    }

    public Object invoke(Object service, String input) throws Throwable {
        // invoke(...) cho phép chuyển receiver kiểu Object sang
        // lớp khai báo khi tương thích runtime.
        return call.invoke(service, input);
    }
}
```

Ví dụ yêu cầu `serviceType` là kiểu public có `run(String)` public và truy cập được từ `publicLookup()`; không phải lớp/package nào cũng thỏa điều kiện đó. Trường hợp `invoke(...)` có target trả kiểu `void` cần định nghĩa chính sách xử lý kết quả ở API framework, thay vì tùy ý coi mọi method đều trả object.

Về mặt quyền, handle đã được tạo thành công thể hiện một **năng lực có thể gọi**. Không nên công bố tràn lan handle truy cập private member cho những phần mềm không đáng tin; việc giữ `MethodHandle` là một phần của thiết kế ranh giới tin cậy.

Về hiệu năng, JEP 416 không bảo đảm `MethodHandle` luôn nhanh hơn Reflection trên mọi JDK và mọi tình huống. Nếu cần so sánh, hãy tách chi phí tìm metadata, quyền truy cập, tạo adapter và thực thi đích; dùng benchmark phù hợp trên JDK đang chạy. Tránh kết luận theo thời gian một lần gọi riêng lẻ.

## 10. Bài kiểm chứng hợp đồng

Kiểm tra ít nhất các ca sau:

| Ca kiểm tra | Hành động | Kết quả cần quan sát |
|---|---|---|
| Instance method public | `unreflect(Greeter.hello(int))` | `handle.type()` bằng `(Greeter,int)String` |
| Static method public | `unreflect(Greeter.twice(int))` | `handle.type()` bằng `(int)int`, không có receiver |
| Constructor public | `unreflectConstructor(Greeter(String))` | `handle.type()` bằng `(String)Greeter` |
| Lời gọi chính xác | `hello.invokeExact(greeter, 2)` với cast trả `String` | Trả chuỗi mong đợi |
| Adapter tổng quát | `hello.asType((Object,Object)Object)` | Truyền `Object` hợp lệ được chuyển đổi đúng |
| Metadata private | `getDeclaredMethod(...)` | Vẫn trả `Method` nếu member có thật |
| Lookup thiếu quyền | `unreflect(privateMethod)` khi chưa có access override | `IllegalAccessException` |
| Access override hợp lệ | `trySetAccessible()` rồi `unreflect(...)` | Có thể tạo handle trong môi trường được phép |
| Module không mở | Thử deep reflection vào private member thuộc module khác không `opens` | Không thể tự cấp quyền qua reflection |
| Kiểu điểm gọi sai | `invokeExact(...)` với return type không khớp | `WrongMethodTypeException` |
| Target ném lỗi | Gọi method handle có target ném `IllegalStateException` | Ngoại lệ gốc truyền tới caller |

Khi kiểm thử named modules, ghi rõ tên module caller/target, package có `exports` hoặc `opens`, lookup dùng loại nào và trạng thái access override của metadata. Kết quả ở classpath không phải bằng chứng cho mọi cấu hình JPMS.

### Câu hỏi tự kiểm tra

1. Vì sao `getDeclaredMethod("secret")` có thể thành công nhưng `lookup.unreflect(method)` vẫn ném `IllegalAccessException`?
2. Kiểu `MethodHandle` tạo từ instance method khác gì với kiểu của static method? Receiver nằm ở đâu?
3. Vì sao `unreflectConstructor(constructor)` trả handle có return type là lớp được tạo dù bản thân constructor không khai báo giá trị trả về?
4. `trySetAccessible()` và `privateLookupIn(...)` giải quyết vấn đề quyền ra sao, và named module có thể ngăn hai cơ chế này bằng cách nào?
5. Khi chuyển từ `Method.invoke(...)` sang `MethodHandle.invokeExact(...)`, các loại ngoại lệ của target thay đổi thế nào?
6. Khi nào nên cache `MethodHandle` và adapter thay vì tạo lại ở mỗi request?

**Ghi nhớ:** `Lookup.unreflect(Method)` và `Lookup.unreflectConstructor(Constructor)` giúp chuyển metadata Reflection thành `MethodHandle` có kiểu gọi rõ ràng. **Việc tìm được metadata không tự cấp quyền truy cập.** Hãy xác nhận quyền của `Lookup` hoặc access override hợp lệ, kiểm tra `handle.type()`, rồi mới gọi hoặc tạo adapter. Đây là hợp đồng cần duy trì khi dùng JDK hiện đại.
