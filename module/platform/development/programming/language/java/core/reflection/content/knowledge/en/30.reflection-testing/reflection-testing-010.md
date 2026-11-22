# Kiểm thử hai ClassLoader định nghĩa lớp cùng tên trong Java

Trong Java, **hai lớp có cùng tên đầy đủ chưa chắc là cùng một kiểu tại runtime**. Đối với một class bình thường, định danh kiểu gồm **binary name và class loader đã *định nghĩa* class đó** (*defining class loader*). Vì vậy, nếu hai class loader khác nhau tự gọi `defineClass` để định nghĩa cùng một tên như `sample.Plugin` từ cùng nội dung bytecode, JVM vẫn tạo ra **hai kiểu khác nhau**.

Bài học này dùng một bài kiểm thử Java 17+ có thể chạy độc lập để kiểm chứng:

- Cùng `Class.getName()` nhưng **`Class<?>` không bằng nhau**.
- Hai kiểu không thể ép kiểu hoặc gán cho nhau chỉ dựa vào tên giống nhau.
- Mỗi loader chỉ nên định nghĩa một class với một tên một lần; một loader khác có thể định nghĩa class trùng tên trong không gian riêng của nó.
- Hai plugin độc lập vẫn có thể cộng tác qua **interface chung được nạp bởi loader cha**, nếu cấu trúc class loader được thiết kế đúng.

Đây là một kỹ năng quan trọng khi kiểm thử plugin, ứng dụng server, thư viện hot reload, hệ thống chạy script và môi trường có nhiều class loader.

## 1. Quy tắc định danh lớp tại runtime

Nhìn hai đoạn thông tin này:

```text
binary name   = sample.Plugin
loader A      = PluginLoader@...
loader B      = PluginLoader@...
```

Dấu `@...` ở đây là ký hiệu minh họa cho hai instance class loader, không phải output xác định của JVM.

Nếu loader A định nghĩa `sample.Plugin` và loader B cũng **tự định nghĩa** `sample.Plugin` thì:

```text
(sample.Plugin, loader A)  !=  (sample.Plugin, loader B)
```

Điều này giải thích vì sao:

```java
Class<?> a = Class.forName("sample.Plugin", false, loaderA);
Class<?> b = Class.forName("sample.Plugin", false, loaderB);

System.out.println(a.getName().equals(b.getName())); // true
System.out.println(a == b);                         // false, nếu A/B tự define
System.out.println(a.isAssignableFrom(b));          // false, nếu không có quan hệ subtype
```

Đây là **đoạn minh họa**: nó giả định `loaderA` và `loaderB` đã được tạo và thực sự định nghĩa class đích độc lập. Nếu cả hai loader chỉ **ủy quyền cho cùng một loader cha**, hai lệnh `Class.forName` có thể trả đúng **một** `Class<?>`.

### Defining loader khác initiating loader

- **Defining loader** là loader thực sự định nghĩa class bằng cơ chế như `defineClass`. Phần định danh runtime phụ thuộc loader này.
- **Initiating loader** là loader mà quá trình yêu cầu load class được gắn với; có thể chỉ ủy quyền và nhận class do loader khác định nghĩa.
- `clazz.getClassLoader()` trả **defining loader** (với một số class nền tảng, kết quả có thể là `null` cho bootstrap loader).

Do đó, **hai đối tượng `ClassLoader` khác nhau không tự động tạo hai runtime class khác nhau**. Bài test phải buộc chúng tự định nghĩa lớp mục tiêu thay vì âm thầm ủy quyền toàn bộ cho cùng loader cha.

## 2. Vì sao mặc định dễ không tái hiện được hiện tượng?

`ClassLoader.loadClass(String)` mặc định thường thực hiện parent-first delegation: kiểm tra class đã load, nhờ loader cha tìm class và chỉ tự tìm khi cần. Nếu hai loader đều có cùng cha và cha đã thấy `sample.Plugin`:

```text
PluginLoader A ──┐
                 ├──> AppClassLoader ──> sample.Plugin
PluginLoader B ──┘

Kết quả: hai đường truy cập trỏ cùng Class<?> do AppClassLoader định nghĩa.
```

Như vậy, đoạn test chỉ gọi:

```java
ClassLoader a = new ClassLoader() {};
ClassLoader b = new ClassLoader() {};
Class<?> typeA = a.loadClass("sample.Plugin");
Class<?> typeB = b.loadClass("sample.Plugin");
```

**không chứng minh** JVM tạo hai kiểu. Hai instance `ClassLoader` bên trên không override cách tìm/nạp nên nhiều khả năng đều được cha phục vụ.

Muốn kiểm thử trường hợp hai kiểu riêng biệt, cần một trong hai cách:

1. Tạo hai loader riêng với nguồn class không thuộc phạm vi loader cha, để mỗi loader tự `findClass` rồi `defineClass`.
2. Viết class loader **ưu tiên tự định nghĩa đúng class mục tiêu**, và vẫn ủy quyền các class khác cho cha.

Bài này dùng cách 2, cố ý giới hạn chỉ tên `sample.Plugin`. Đây là một mô phỏng có kiểm soát; **không nên chuyển toàn bộ loader thành child-first** nếu không hiểu hệ quả với thư viện và API chung.

## 3. Thiết kế bài kiểm thử có kết quả xác định

Ta dùng ba file Java và hai instance của một class loader tùy chỉnh:

```text
src/
├── host/
│   └── Speaker.java          (contract chung, app loader nạp)
├── sample/
│   └── Plugin.java           (class bytecode được định nghĩa lại)
└── TwoLoadersTest.java       (test runner + PluginLoader)
```

Cấu trúc loader mong muốn:

```text
                    AppClassLoader
                 /                  \
        PluginLoader A         PluginLoader B
          sample.Plugin          sample.Plugin
                 \                  /
                  \__ host.Speaker _/
                       (cùng một Class<?>)
```

Hai plugin đều implements `host.Speaker`. Các loader con tự định nghĩa `sample.Plugin` từ **cùng bytecode**, nhưng ủy quyền việc tìm `host.Speaker` cho cùng loader cha. Điều này giúp quan sát hai tính chất cùng lúc:

- Hai class `sample.Plugin` **không cùng type identity**, nên ép đối tượng của bên A sang class bên B thất bại.
- Cả hai instance **cùng tương thích** với `host.Speaker` do cha định nghĩa, nên có thể gọi `hello()` thông qua contract chung.

## 4. Chương trình Java 17+ có thể biên dịch và chạy

### File 1 — `src/host/Speaker.java`

```java
package host;

public interface Speaker {
    String hello();
}
```

Interface `Speaker` nằm trên classpath ứng dụng. Chương trình host dùng interface này như **điểm gặp nhau** giữa các plugin.

### File 2 — `src/sample/Plugin.java`

```java
package sample;

import host.Speaker;

public class Plugin implements Speaker {
    public Plugin() {}

    @Override
    public String hello() {
        return "hello from plugin";
    }
}
```

Ta chỉ cần **một** file nguồn và **một** file bytecode `Plugin.class`. Hai class loader khác nhau sẽ đọc **cùng mảng bytecode** nhưng mỗi loader tự định nghĩa class trong không gian của mình.

### File 3 — `src/TwoLoadersTest.java`

```java
import host.Speaker;
import java.nio.file.Files;
import java.nio.file.Path;

public class TwoLoadersTest {
    private static final String TARGET = "sample.Plugin";

    static final class PluginLoader extends ClassLoader {
        private final byte[] bytecode;

        PluginLoader(byte[] bytecode) {
            super(TwoLoadersTest.class.getClassLoader());
            this.bytecode = bytecode.clone();
        }

        @Override
        protected Class<?> loadClass(String name, boolean resolve)
                throws ClassNotFoundException {
            if (!TARGET.equals(name)) {
                return super.loadClass(name, resolve);
            }

            synchronized (getClassLoadingLock(name)) {
                Class<?> found = findLoadedClass(name);
                if (found == null) {
                    found = defineClass(name, bytecode, 0, bytecode.length);
                }
                if (resolve) resolveClass(found);
                return found;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Use: java -cp out TwoLoadersTest out/sample/Plugin.class");
        }

        byte[] bytes = Files.readAllBytes(Path.of(args[0]));
        ClassLoader one = new PluginLoader(bytes);
        ClassLoader two = new PluginLoader(bytes);

        Class<?> a = Class.forName(TARGET, false, one);
        Class<?> b = Class.forName(TARGET, false, two);

        System.out.println("Same binary name: "
                + a.getName().equals(b.getName()));
        System.out.println("Same Class object: " + (a == b));
        System.out.println("Distinct defining loaders: "
                + (a.getClassLoader() != b.getClassLoader()));
        System.out.println("A assignable from B: "
                + a.isAssignableFrom(b));
        System.out.println("Interface accepts A: "
                + Speaker.class.isAssignableFrom(a));
        System.out.println("Interface accepts B: "
                + Speaker.class.isAssignableFrom(b));

        Object instanceA = a.getDeclaredConstructor().newInstance();
        Object instanceB = b.getDeclaredConstructor().newInstance();

        System.out.println("Instance A is B: "
                + b.isInstance(instanceA));
        try {
            b.cast(instanceA);
            System.out.println("Cast unexpectedly succeeded");
        } catch (ClassCastException expected) {
            System.out.println("Cast B <- instance A: ClassCastException");
        }

        Speaker first = Speaker.class.cast(instanceA);
        Speaker second = Speaker.class.cast(instanceB);
        System.out.println("Shared interface: "
                + first.hello() + " | " + second.hello());
    }
}
```

### Biên dịch và chạy

Đứng tại thư mục chứa `src/`. Với JDK 17 hoặc mới hơn, thực hiện:

```bash
javac -encoding UTF-8 -d out src/host/Speaker.java src/sample/Plugin.java src/TwoLoadersTest.java
java -cp out TwoLoadersTest out/sample/Plugin.class
```

Lệnh `javac -d out` tạo:

```text
out/
├── host/
│   └── Speaker.class
├── sample/
│   └── Plugin.class
├── TwoLoadersTest.class
└── TwoLoadersTest$PluginLoader.class
```

Các file class của runner và interface chung nằm trên application classpath; trong chương trình, mỗi `PluginLoader` chỉ giữ bytecode đọc từ `out/sample/Plugin.class`.

### Kết quả thực tế

```text
Same binary name: true
Same Class object: false
Distinct defining loaders: true
A assignable from B: false
Interface accepts A: true
Interface accepts B: true
Instance A is B: false
Cast B <- instance A: ClassCastException
Shared interface: hello from plugin | hello from plugin
```

Kết quả được kiểm tra bằng cách biên dịch và chạy chương trình Java tương ứng. Tên file, class và những chuỗi in ra khớp với mã nguồn bên trên.

## 5. Giải thích chính xác từng kết quả

### 5.1. Cùng tên, khác `Class<?>`

`a.getName().equals(b.getName())` trả `true` vì cả hai class đều mang binary name `sample.Plugin`.

`a == b` trả `false` vì hai đối tượng `Class<?>` biểu diễn hai kiểu khác nhau: class do loader A định nghĩa và class do loader B định nghĩa.

Cùng bytecode **không** buộc Java hợp nhất hai class từ hai loader. Việc mỗi loader định nghĩa bytecode tạo ra một không gian type riêng cho tên đó.

### 5.2. `getClassLoader()` chỉ ra nguồn định danh

`a.getClassLoader() != b.getClassLoader()` là `true`. Trong test, loader A và B khác nhau và mỗi loader thật sự gọi `defineClass` cho `sample.Plugin`.

Đây là bước kiểm chứng cần thiết. Nếu chỉ in hai loader variable được tạo khác nhau mà không kiểm tra **defining loader của kết quả `Class<?>`**, bài test có thể vô tình chỉ chứng minh hai instance loader, chưa chứng minh class đã được định nghĩa riêng.

### 5.3. `isAssignableFrom` và `isInstance` không chỉ nhìn tên

`a.isAssignableFrom(b)` là `false`. Hai class độc lập không có quan hệ kế thừa kiểu với nhau dù tên trùng.

`b.isInstance(instanceA)` cũng là `false`: instanceA được tạo bởi class A, không phải instance của class B.

Việc gọi `b.cast(instanceA)` ném `ClassCastException` như mong đợi. Lỗi không đến từ method `hello()`, không phải do chuỗi tên khác nhau, mà do **khác runtime type identity**.

### 5.4. Vì sao cả hai vẫn được coi là `Speaker`?

Cả `sample.Plugin` từ loader A và loader B đều implements **cùng `host.Speaker` của parent loader**. Do `Speaker` do loader cha định nghĩa nên:

```java
Speaker.class.isAssignableFrom(a);  // true
Speaker.class.isAssignableFrom(b);  // true
```

Hai đối tượng có thể được nhìn qua `Speaker`:

```java
Speaker left = Speaker.class.cast(instanceA);
Speaker right = Speaker.class.cast(instanceB);
```

Đây là lợi ích thực tế của kiến trúc plugin: **giữ contract chung ở host/parent loader, chỉ nạp implementation riêng ở plugin loader**. Qua interface chung, chương trình host không cần ép kiểu về `sample.Plugin` của một loader cụ thể.

## 6. Tìm hiểu kỹ phương thức `loadClass` được override

Trong `PluginLoader`, điều kiện:

```java
if (!TARGET.equals(name)) {
    return super.loadClass(name, resolve);
}
```

giữ **parent delegation** cho tất cả class ngoài `sample.Plugin`: Java API, `host.Speaker`, `java.lang.String` và các dependency chung. Với `sample.Plugin`, loader sẽ tự định nghĩa.

Đoạn chính:

```java
synchronized (getClassLoadingLock(name)) {
    Class<?> found = findLoadedClass(name);
    if (found == null) {
        found = defineClass(name, bytecode, 0, bytecode.length);
    }
    if (resolve) resolveClass(found);
    return found;
}
```

Có bốn ý cần hiểu:

1. `getClassLoadingLock(name)` giúp phối hợp các lời gọi load đồng thời cho cùng binary name của một loader. Đây là quy trình phù hợp với hợp đồng khóa trong `ClassLoader`.
2. `findLoadedClass(name)` tránh **định nghĩa trùng lần hai trong cùng loader**. Sau khi loader đã định nghĩa class có tên đó, các lần yêu cầu tiếp theo trả lại đối tượng `Class<?>` đã tạo.
3. `defineClass(name, bytecode, 0, bytecode.length)` dùng bytecode để tạo runtime class với **defining loader chính là instance `PluginLoader` hiện tại**. Bytecode có binary name phải phù hợp tên `name`; nếu không, JVM có thể báo lỗi như `NoClassDefFoundError`.
4. `resolveClass(found)` được gọi khi đối số `resolve` yêu cầu linking/resolution bổ sung; không đồng nghĩa ép khởi tạo class.

**Vì sao clone bytecode?** Constructor `PluginLoader` dùng `bytecode.clone()` để hai loader giữ dữ liệu bất biến theo ý đồ ví dụ trước những sửa đổi từ bên ngoài. Không phải cứ clone bytecode là tạo class riêng; điều quyết định là **hai lời gọi `defineClass` bởi hai loader khác nhau**.

**Vì sao không override `findClass` cho mọi tên?** Bài học muốn trình bày hiện tượng trong phạm vi duy nhất `sample.Plugin`. Trong ứng dụng lớn, thường triển khai `findClass`/`loadClass` theo chiến lược rõ, với dependency resolution và bảo vệ namespace. Mẫu tối giản này là fixture kiểm thử, không phải class loader hoàn chỉnh cho production.

## 7. Phép kiểm thử bị sai thường gặp: cả hai loader đều ủy quyền cho cha

Nếu dùng code như:

```java
ClassLoader parent = TwoLoadersTest.class.getClassLoader();
ClassLoader childA = new ClassLoader(parent) {};
ClassLoader childB = new ClassLoader(parent) {};

// Nếu app classpath có sample.Plugin, cả hai thường ủy quyền lên cha.
Class<?> a = Class.forName("sample.Plugin", false, childA);
Class<?> b = Class.forName("sample.Plugin", false, childB);
```

Đây là **đoạn minh họa phụ thuộc vào dự án có sẵn `TwoLoadersTest`/`sample.Plugin`**. Với parent-first mặc định và class `sample.Plugin` nằm trên application classpath, `a == b` có thể là `true`.

Đừng kết luận “JVM không hỗ trợ hai class cùng tên”. Fixture chưa tạo ra hai **defining loader** khác nhau.

Để test đúng:

- Đảm bảo class mục tiêu được định nghĩa cục bộ trong từng loader (như ví dụ).
- In `a.getClassLoader()` và `b.getClassLoader()` hoặc so sánh trực tiếp.
- Xác nhận `a != b` và `a.getName().equals(b.getName())`.
- Tạo instance từ đúng `Class<?>` tương ứng và thử `isInstance`/`cast`.

## 8. Những biến thể kiểm thử nên biết

### 8.1. Cùng loader gọi lại cùng tên

Sau khi A đã load `sample.Plugin`, lệnh:

```java
Class<?> again = Class.forName("sample.Plugin", false, one);
System.out.println(again == a); // true
```

là đoạn minh họa trong ngữ cảnh `main` của ví dụ; nó cho thấy **cùng loader không định nghĩa thêm một bản** sau khi đã cache class thành công. Các lần gọi lại vẫn là một `Class<?>`.

Nếu cố gọi `defineClass` một lần thứ hai với đúng binary name trong **cùng loader**, JVM có thể ném `LinkageError` do duplicate definition; không nên thiết kế hot reload bằng cách cố định nghĩa đè class cũ ngay trong loader đang sống.

### 8.2. Thử ép kiểu trực tiếp theo tên class từ host

Nếu host import `sample.Plugin` rồi cast một instance do plugin loader A định nghĩa:

```java
// Minh họa ý tưởng, đòi hỏi host biên dịch nhìn thấy sample.Plugin.
sample.Plugin p = (sample.Plugin) instanceA;
```

Kết quả cũng có thể ném `ClassCastException` vì `sample.Plugin` được tham chiếu trực tiếp từ host thường là class do application loader định nghĩa, **khác** `sample.Plugin` của plugin loader A. Một message exception có thể nhắc đến hai loader, dù cả hai type đều in cùng tên class.

### 8.3. Nếu interface chung cũng bị định nghĩa hai lần?

Giả sử loader A tự định nghĩa cả `sample.Plugin` và `host.Speaker`, còn loader B cũng tự định nghĩa hai class đó. Khi ấy:

```text
(host.Speaker, loader A) != (host.Speaker, loader B)
```

Host gọi `Speaker.class.isAssignableFrom(a)` có thể trả `false`, làm mất đường giao tiếp chung. Đây là lỗi thường gặp khi một plugin đóng gói trùng API chung trong JAR riêng và class loader giải quyết API theo hướng child-first.

Thiết kế plugin đáng tin cậy nên chọn rõ **nhóm package được chia sẻ/ủy quyền** và **nhóm package do plugin tự định nghĩa**, đồng thời bảo đảm tương thích phiên bản interface.

### 8.4. Cùng tên nhưng bytecode khác nhau

Hai loader có thể nạp các phiên bản bytecode khác nhau cho cùng binary name. Chúng vẫn khác type identity. Nếu bytecode khác method, field hoặc API signature, runtime còn có thể xảy ra các lỗi compatibility hoặc linkage khi cố trộn object, lời gọi và class loader.

Trong bài này dùng **cùng bytecode** để cô lập một nguyên nhân duy nhất: loader khác nhau.

### 8.5. Unload/hot reload

Một loader mới có thể định nghĩa thế hệ `sample.Plugin` mới. Class thế hệ cũ và thế hệ mới vẫn là hai kiểu khác nhau ngay cả khi giữ tên. Class unloading phụ thuộc việc class/loader liên quan còn được tham chiếu hay không, GC và điều kiện runtime; không thể chắc chắn unload ngay chỉ vì xóa file JAR.

Sau hot reload, tránh giữ những reference cũ trong static caches, thread context class loader, thread hoặc registry; nếu không, loader cũ và toàn bộ class của nó có thể tiếp tục tồn tại.

## 9. Mối liên hệ với Reflection và kiểm thử thực tế

Reflection thường trả về `Class<?>`, `Method`, `Field` hoặc `Constructor`. Những metadata object này **thuộc về class cụ thể do loader cụ thể định nghĩa**. Vì vậy, khi framework quét plugin rồi gọi `Method.invoke`, cần dùng receiver của **đúng runtime class**, không chỉ đối tượng có `getClass().getName()` giống tên phương thức khai báo.

Kiểm tra đúng:

```java
// Trong ngữ cảnh ví dụ trên:
Class<?> targetClass = a;
Object target = targetClass.getDeclaredConstructor().newInstance();
boolean receiverMatches = targetClass.isInstance(target); // true
```

Kiểm tra sai:

```java
// Không đủ để xác nhận compatibility:
boolean nameMatches = target.getClass().getName()
        .equals(b.getName()); // true, nhưng b.cast(target) vẫn thất bại
```

**Trong cache Reflection:** Đừng chỉ lấy `String className` làm cache key nếu ứng dụng có nhiều loader. Dùng `Class<?>` hoặc key gắn rõ loader/đời class, tùy chính sách lifecycle. Ngược lại, cache toàn cục giữ `Class<?>`/`Method` mãi cũng có thể cản class unloading; cache cần quản lý vòng đời plugin.

### Gợi ý các assertion của một bài test tự động

Với `a`, `b`, `instanceA`, `instanceB` và `one`/`two` trong chương trình:

```java
// Đây là nhóm assertion để đưa vào test có cùng fixture, không phải file độc lập.
if (!a.getName().equals(b.getName())) throw new AssertionError();
if (a == b) throw new AssertionError();
if (a.getClassLoader() == b.getClassLoader()) throw new AssertionError();
if (a.isAssignableFrom(b)) throw new AssertionError();
if (b.isInstance(instanceA)) throw new AssertionError();
if (!Speaker.class.isInstance(instanceA)) throw new AssertionError();
if (!Speaker.class.isInstance(instanceB)) throw new AssertionError();
```

Các điều kiện này kiểm thử **hành vi quan trọng**, không phụ thuộc việc `ClassLoader.toString()` in hash code nào. Nếu dùng JUnit, chuyển thành `assertEquals`/`assertNotSame`/`assertFalse`/`assertTrue`/`assertThrows`; việc chọn framework không đổi bản chất kiểm thử.

## 10. Cảnh báo khi chuyển fixture sang hệ thống thật

- **Không nạp bytecode không đáng tin cậy chỉ để thử nghiệm.** `defineClass` không phải sandbox an toàn. Code được nạp có thể thực thi khi khởi tạo hoặc khi gọi method; kiểm soát nguồn bytecode và quyền chạy.
- **Không tùy tiện child-first mọi class.** Nếu nhân bản `java.*` hoặc API của host, loader có thể gặp lỗi bảo vệ package, loader constraint, incompatibility hoặc `ClassCastException`. JVM có quy tắc bảo vệ các namespace như `java.*`.
- **Giữ API chia sẻ ở loader cha hoặc một loader dùng chung.** Với hệ thống plugin, truyền DTO kiểu có hợp đồng rõ hoặc qua serialization thay vì truyền thẳng implementation nội bộ.
- **Chú ý Java modules (JPMS).** Module readability, `exports` và `opens` có thể ảnh hưởng Reflection; classpath test trong ví dụ là **unnamed module** và không thay thế test trong named-module deployment.
- **Loader constraints.** Khi nhiều loader cùng tham gia resolve chữ ký method/field, JVM có thể áp đặt ràng buộc về identity của các kiểu được chia sẻ. Một thiết kế liên kết sai có thể gây `LinkageError` bên cạnh `ClassCastException`.
- **Thread context class loader** có thể khác class loader định nghĩa code của thread. `Thread.currentThread().getContextClassLoader()` thường được framework dùng để khám phá resource/service, nhưng không làm hai kiểu cùng tên tự động hợp nhất.
- **Đừng so sánh chỉ `getName()`.** Khi debug, ghi tên class, mô tả loader định nghĩa và module khi cần; luôn kiểm tra quyền và tránh lộ thông tin nhạy cảm trong log.

## 11. Khi nào nên chọn một loader chung?

Nếu mục tiêu là **chia sẻ cùng một type** giữa các phần của hệ thống, cho chúng cùng ủy quyền việc load lớp đó tới một loader phù hợp. Điều này làm cho runtime type identity thống nhất.

Nếu mục tiêu là **cô lập plugin/phiên bản**, cho mỗi plugin loader tự định nghĩa implementation, nhưng thống nhất contract trong một nơi dùng chung. Cách này cho phép plugin trùng binary name mà không khiến host nhầm các implementation với nhau.

| Mục tiêu | Kiến trúc loading | Kiểm chứng |
| --- | --- | --- |
| Dùng chung một class | Hai child loader ủy quyền cho cùng defining loader | `a == b` |
| Hai bản implementation tách biệt | A và B tự định nghĩa cùng binary name | `a.getName().equals(b.getName())` và `a != b` |
| Hai plugin cùng thực thi contract | Interface chung do parent/host loader định nghĩa | `SharedApi.class.isAssignableFrom(a/b)` |
| Hot reload không xung đột class cũ | Tạo loader mới cho implementation mới, điều phối vòng đời | Class cũ và mới khác identity, dọn reference khi ngừng dùng |

## 12. Câu hỏi tự kiểm tra

1. Vì sao hai class có cùng `getName()` vẫn không thể ép kiểu cho nhau?
2. Nếu hai `ClassLoader` khác nhau đều delegate class đích cho cùng parent, kết quả `a == b` ra sao?
3. `Class.getClassLoader()` thể hiện *defining loader* hay luôn là loader được dùng ở lời gọi đầu tiên?
4. Trong ví dụ, vì sao `Speaker.class.isAssignableFrom(a)` và `Speaker.class.isAssignableFrom(b)` cùng đúng dù `a.isAssignableFrom(b)` sai?
5. Tại sao phải dùng `findLoadedClass` khi định nghĩa class theo yêu cầu?
6. Vì sao hot reload thường dùng loader mới, thay vì gọi `defineClass` lần nữa trên loader cũ?
7. Khi ứng dụng cache metadata Reflection của plugin theo tên class, lỗi nào có thể xảy ra sau reload?
8. Nếu cùng interface API cũng bị hai loader tự define, host còn cast hai plugin về interface của host một cách an toàn không?

## 13. Tài liệu tham khảo

- [Java SE 17: `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findLoadedClass`, `defineClass`, `getClassLoadingLock`.
- [Java SE 17: `Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getName`, `getClassLoader`, `isAssignableFrom`, `isInstance`, `cast`.
- [Java Language Specification §12.2: Loading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2): tính duy nhất của runtime class identity và các class loader.
- [Java Virtual Machine Specification §5.3: Creation of Classes and Interfaces](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): defining loader và initiating loader.
