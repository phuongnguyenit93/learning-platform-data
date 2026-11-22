# registerAsParallelCapable và điều kiện đăng ký

## 1. Vấn đề: nhiều thread cùng yêu cầu nạp class

Trong ứng dụng Java có plugin, application server, proxy framework hoặc nhiều tác vụ nền, hai thread có thể đồng thời yêu cầu một `ClassLoader` nạp hai lớp khác nhau. Nếu mọi lần nạp đều giữ **cùng một khóa của toàn loader**, những yêu cầu độc lập cũng phải chờ nhau. Điều này có thể giảm throughput và, trong một topology ClassLoader ủy quyền không thuần cây, còn làm tăng nguy cơ deadlock.

Java cho phép tác giả một subclass của `ClassLoader` khai báo rằng loại loader ấy có thể hỗ trợ **parallel class loading** bằng phương thức:

~~~java
protected static boolean ClassLoader.registerAsParallelCapable()
~~~

Dòng trên mô tả chữ ký API, **không phải cú pháp Java để gọi phương thức**. Trong class kế thừa `ClassLoader`, cách thường dùng là gọi `registerAsParallelCapable()` ngay trong **static initializer**, trước khi có bất kỳ instance nào của class đó được tạo.

~~~java
public final class MyLoader extends ClassLoader {
    static {
        if (!registerAsParallelCapable()) {
            throw new ExceptionInInitializerError(
                    "Cannot register MyLoader as parallel capable");
        }
    }

    public MyLoader(ClassLoader parent) {
        super(parent);
    }
}
~~~

Đây là ví dụ lớp có thể biên dịch khi lưu thành `MyLoader.java`, nhưng nó **chưa triển khai nguồn bytecode của riêng mình**; nếu muốn loader nạp class plugin thực sự, cần bổ sung `findClass` hoặc dùng loader chuẩn như `URLClassLoader`. Mẫu này minh họa **thời điểm đăng ký và xử lý kết quả**, không phải một loader plugin hoàn chỉnh.

**Thông điệp chính:** `registerAsParallelCapable()` khai báo khả năng phối hợp nạp đồng thời của **class loader type**, chứ không phải gọi trên một instance để bật tùy chọn runtime cho mỗi loader.

## 2. Hai điều kiện đăng ký theo Javadoc Java 17

Javadoc `ClassLoader.registerAsParallelCapable()` quy định đăng ký thành công **khi và chỉ khi cả hai điều kiện** cùng đúng:

1. **Chưa có bất kỳ instance nào của class loader gọi phương thức đăng ký được tạo.**
2. **Mọi superclass của class loader đó, trừ `Object`, đều đã được đăng ký parallel capable.**

Phương thức trả về:

- `true` nếu đăng ký thành công;
- `false` nếu các điều kiện đăng ký không được đáp ứng.

Một loader type sau khi đã đăng ký parallel capable **không thể hủy đăng ký để chuyển ngược về non-parallel capable**.

`ClassLoader` của Java **đã được đăng ký parallel capable mặc định**, nhưng **mỗi subclass muốn tham gia vẫn phải tự đăng ký**. Không được suy ra “vì class cha `ClassLoader` đã registered nên subclass cũng tự động registered”.

| Trường hợp | Kết quả thường gặp |
|---|---|
| `MyLoader extends ClassLoader` và gọi đăng ký trong `static` block trước khi tạo instance | `true` |
| `ChildLoader extends MyLoader`; `MyLoader` đã registered và `ChildLoader` tự đăng ký sớm | `true` |
| `ChildLoader` quên tự đăng ký dù parent registered | `ChildLoader` vẫn non-parallel capable |
| `ChildLoader` đăng ký nhưng có superclass loader **không** registered | `false` |
| Gọi đăng ký lần đầu khi instance của chính caller class đã được tạo | `false` |
| Đăng ký thành công rồi tạo nhiều instance của cùng loader class | Những instance thuộc loader type đã registered |
| Muốn “tắt” đăng ký sau đó | Không có API chuyển ngược |

Lưu ý thuật ngữ **caller** ở đây là **class loader subclass thực sự gọi phương thức đăng ký**, không phải một object được truyền làm tham số. Phương thức là `protected static`, không phải `public` instance setter.

## 3. Vì sao phải gọi trong `static initializer`?

Static initializer chạy trong giai đoạn **class initialization**, trước khi constructor tạo instance đầu tiên có thể hoàn thành. Đặt đăng ký ở đó phù hợp chính xác với điều kiện “chưa có instance”:

~~~java
class ParallelDirectoryLoader extends ClassLoader {
    static {
        boolean ok = registerAsParallelCapable();
        if (!ok) {
            throw new ExceptionInInitializerError(
                    "Parent hierarchy is not parallel capable");
        }
    }

    ParallelDirectoryLoader(ClassLoader parent) {
        super(parent);
    }
}
~~~

Nếu đăng ký thất bại và bạn **tiếp tục chạy** như không có chuyện gì, loader type vẫn có thể vận hành với cơ chế khóa coarse-grained. Nhưng nếu thiết kế của bạn **phụ thuộc bắt buộc** vào parallel capability, nên fail fast như ví dụ.

Đừng gọi `registerAsParallelCapable()` trong constructor để “đăng ký instance này”, hoặc từ một nút bấm/config runtime để chuyển chế độ sau khi loader đã được sử dụng. Đăng ký thuộc **vòng đời class**, không thuộc vòng đời object.

Một điểm Java căn bản: static initializer của superclass chạy trước initializer của subclass theo quy tắc initialization. Nhờ thế, nếu cha đăng ký trong static initializer và không có instance cha bị tạo trước đó, subclass có thể gọi đăng ký trong static initializer sau khi cha đã được initialized. Nhưng **class cha vẫn phải thực sự đăng ký thành công**; chỉ extends một cha “có ý định đăng ký” không đủ.

## 4. Quan hệ kế thừa: đăng ký phải xuyên suốt chuỗi cha

Hãy xét hai cây:

~~~text
Cây hợp lệ                              Cây thất bại

ClassLoader [registered]                ClassLoader [registered]
       │                                        │
       ▼                                        ▼
BaseLoader [registered]                 LegacyLoader [NOT registered]
       │                                        │
       ▼                                        ▼
ChildLoader [registered]                ChildLoader [attempts registration]
                                                │
                                                ▼
                                           returns false
~~~

Trong cây thứ nhất:

- `ClassLoader` được JDK đăng ký sẵn.
- `BaseLoader` gọi đăng ký sớm và nhận `true`.
- `ChildLoader` cũng gọi đăng ký sớm, thấy tất cả superclass loader đều registered → `true`.

Trong cây thứ hai:

- `LegacyLoader` không đăng ký.
- Dù `ChildLoader` gọi `registerAsParallelCapable()` trong static initializer trước khi tạo instance, **điều kiện superclass vẫn sai**.
- Kết quả là `false`; đăng ký ở một subclass không thể “nhảy qua” superclass chưa registered.

Điều này quan trọng khi bạn kế thừa một thư viện ClassLoader do người khác viết. Nếu base class chưa được thiết kế và đăng ký parallel capable, subclass của bạn không thể sửa chỉ bằng cách tự gọi đăng ký.

### 4.1. Phân biệt parent loader và superclass

Hai khái niệm Java rất dễ bị nhầm:

**Superclass** là quan hệ kế thừa *giữa các class trong mã nguồn*: `MyLoader extends BaseLoader`. Đây là yếu tố trong **điều kiện registerAsParallelCapable**.

**Parent ClassLoader** là **tham chiếu object dùng để delegation** khi loader tải class: `new MyLoader(parent)`. Đây là cấu hình **mỗi instance**.

~~~java
// Mã minh họa:
MyLoader loader = new MyLoader(ClassLoader.getPlatformClassLoader());
~~~

Việc truyền platform loader làm parent **không làm cho một superclass chưa đăng ký trở thành registered**. Ngược lại, việc tất cả superclass registered **không chứng minh** parent loader instance có bất kỳ cấu hình tùy biến nào bạn mong muốn.

| Câu hỏi | Phải kiểm tra |
|---|---|
| “MyLoader có đủ điều kiện registerAsParallelCapable?” | Chuỗi **superclass của MyLoader** và thời điểm tạo instance |
| “Loader A hỏi loader nào trước khi nạp?” | `getParent()` của **instance** A và delegation logic |
| “Hai yêu cầu cùng loader có thể lấy hai khóa riêng?” | Registration trạng thái **loader class**, `getClassLoadingLock(name)` |
| “Hai plugin loaders có thấy cùng interface?” | Parent/delegation và defining loader của shared API |

## 5. Đăng ký thay đổi khóa thế nào?
Đối với `loadClass` mặc định, `getClassLoadingLock(name)` trả **`this`** nếu subclass không registered; khi registered, nó trả **một khóa ổn định theo binary name**. Do đó A/B khác tên có thể load đồng thời, còn hai yêu cầu A vẫn phải dùng cùng khóa và kiểm tra `findLoadedClass` trước khi `defineClass`.
Việc đăng ký không đảm bảo tăng hiệu năng hoặc làm `findClass` thread-safe. Thí nghiệm §6 kiểm tra khóa bằng identity và phân biệt registration thành công, superclass chưa đăng ký và trường hợp đăng ký muộn.

## 6. Chương trình Java 17+ kiểm chứng hai điều kiện đăng ký

Đây là một file **độc lập** minh họa bốn trường hợp:

1. Class trực tiếp extends `ClassLoader` đăng ký sớm: thành công.
2. Subclass của loader đã đăng ký tiếp tục đăng ký: thành công.
3. Subclass của loader chưa đăng ký cố đăng ký: thất bại.
4. ClassLoader đã có instance rồi mới thử đăng ký: thất bại.

Chương trình còn kiểm tra khóa cho cùng tên và khác tên, để nhìn thấy hệ quả của registration mà không dựa vào race đa luồng hoặc đo thời gian không ổn định.

Tạo file **`ParallelRegistrationDemo.java`**:

~~~java
public final class ParallelRegistrationDemo {
    private ParallelRegistrationDemo() {
    }

    static class RegisteredParent extends ClassLoader {
        static final boolean REGISTERED = registerAsParallelCapable();

        RegisteredParent() {
            super(ClassLoader.getSystemClassLoader());
        }

        Object lock(String name) {
            return getClassLoadingLock(name);
        }
    }

    static final class RegisteredChild extends RegisteredParent {
        static final boolean REGISTERED = registerAsParallelCapable();

        RegisteredChild() {
            super();
        }
    }

    static class LegacyParent extends ClassLoader {
        // Không gọi registerAsParallelCapable.
        LegacyParent() {
            super(ClassLoader.getSystemClassLoader());
        }

        Object lock(String name) {
            return getClassLoadingLock(name);
        }
    }

    static final class BlockedChild extends LegacyParent {
        static final boolean REGISTERED = registerAsParallelCapable();

        BlockedChild() {
            super();
        }
    }

    static final class LateAttempt extends ClassLoader {
        // Cố ý không đăng ký trong static initializer.
        LateAttempt() {
            super(ClassLoader.getSystemClassLoader());
        }

        static boolean registerTooLate() {
            return registerAsParallelCapable();
        }
    }

    public static void main(String[] args) {
        RegisteredParent parent = new RegisteredParent();
        RegisteredChild child = new RegisteredChild();
        LegacyParent legacy = new LegacyParent();
        BlockedChild blocked = new BlockedChild();
        LateAttempt late = new LateAttempt();

        System.out.println("RegisteredParent registration: "
                + RegisteredParent.REGISTERED);
        System.out.println("RegisteredChild registration: "
                + RegisteredChild.REGISTERED);
        System.out.println("LegacyParent registered: "
                + legacy.isRegisteredAsParallelCapable());
        System.out.println("BlockedChild registration: "
                + BlockedChild.REGISTERED);
        System.out.println("BlockedChild registered: "
                + blocked.isRegisteredAsParallelCapable());

        System.out.println("RegisteredChild registered: "
                + child.isRegisteredAsParallelCapable());
        System.out.println("Same name uses same lock: "
                + (child.lock("demo.A") == child.lock("demo.A")));
        System.out.println("Different names use different locks: "
                + (child.lock("demo.A") != child.lock("demo.B")));

        System.out.println("Legacy lock is loader: "
                + (legacy.lock("demo.A") == legacy));
        System.out.println("Blocked lock is loader: "
                + (blocked.lock("demo.B") == blocked));

        System.out.println("Late initially registered: "
                + late.isRegisteredAsParallelCapable());
        System.out.println("Late registration after instance: "
                + LateAttempt.registerTooLate());
        System.out.println("Late finally registered: "
                + late.isRegisteredAsParallelCapable());

        // Dùng biến parent để kiểm tra trạng thái của instance base:
        System.out.println("RegisteredParent instance registered: "
                + parent.isRegisteredAsParallelCapable());
    }
}
~~~

### 6.1. Biên dịch và chạy

Dùng JDK **17 trở lên** và chạy trong thư mục chứa `ParallelRegistrationDemo.java`:

~~~bash
javac -encoding UTF-8 ParallelRegistrationDemo.java
java ParallelRegistrationDemo
~~~

Hai lệnh hoạt động trên Bash, PowerShell và Command Prompt khi JDK có trong `PATH`; source không dùng dependency ngoài JDK và không cần `--module-path`.

### 6.2. Stdout chính xác

~~~text
RegisteredParent registration: true
RegisteredChild registration: true
LegacyParent registered: false
BlockedChild registration: false
BlockedChild registered: false
RegisteredChild registered: true
Same name uses same lock: true
Different names use different locks: true
Legacy lock is loader: true
Blocked lock is loader: true
Late initially registered: false
Late registration after instance: false
Late finally registered: false
RegisteredParent instance registered: true
~~~

**Giải thích chi tiết:**

- `RegisteredParent.REGISTERED`: `ClassLoader` registered sẵn, chưa có instance `RegisteredParent` trước khi static initializer đăng ký → `true`.
- `RegisteredChild.REGISTERED`: superclass `RegisteredParent` đã đăng ký, subclass cũng gọi sớm → `true`.
- `LegacyParent`: không gọi đăng ký, nên mặc định **không** registered dù extends `ClassLoader`.
- `BlockedChild.REGISTERED`: không có instance `BlockedChild` trước khi static initializer chạy, nhưng superclass `LegacyParent` không registered → `false`.
- `child.lock("demo.A")` được gọi hai lần trả cùng dedicated lock; `child.lock("demo.B")` trả lock khác, phù hợp default `getClassLoadingLock` cho registered loader.
- `legacy.lock(...) == legacy` và `blocked.lock(...) == blocked` chứng minh default lock trên loader object với non-parallel capable types.
- `LateAttempt` được khởi tạo bằng `new LateAttempt()` trước khi gọi `registerTooLate()`. Điều kiện “chưa có instance” đã bị vi phạm → `false`, loader type vẫn non-parallel capable.

Ví dụ **không** thực hiện benchmark: nó quan sát contract registration/lock identity, không chạy hai thread tranh chấp. Từ kết quả này không nên suy ra cải thiện throughput bao nhiêu phần trăm trên máy thật.

## 7. Một điểm tinh tế về phương thức `static` và caller

`registerAsParallelCapable()` không phải phương thức instance kiểu:

~~~java
// SAI ý nghĩa API, không phải cách bật/tắt cho object:
loader.registerAsParallelCapable();
~~~

Nó là `protected static`, phải được gọi từ phạm vi subclass phù hợp. Cách đăng ký được khuyến nghị là **gọi trực tiếp trong static initializer của chính loader type**:

~~~java
class AppPluginLoader extends ClassLoader {
    static {
        if (!registerAsParallelCapable()) {
            throw new ExceptionInInitializerError(
                    "AppPluginLoader registration failed");
        }
    }
}
~~~

Nếu gọi một **static helper do superclass định nghĩa**, đừng tự suy ra helper đó đang đăng ký subclass theo tên dynamic của object. Java `static` không có dynamic dispatch như instance method; caller của việc đăng ký cần được hiểu theo class định nghĩa lời gọi.

Đó là lý do mỗi subclass muốn parallel capable nên có bước đăng ký **riêng**, thay vì coi constructor hoặc helper chung của base class là đủ cho cả cây kế thừa.

## 8. Registration phải gắn với implementation thực sự thread-safe

Tên gọi “parallel capable” là **lời cam kết của tác giả loader** về khả năng nạp class đồng thời, không phải một phép biến đổi tự động làm mọi đoạn mã an toàn đa luồng.

Ví dụ nếu `findClass` dùng một buffer instance chung và không bảo vệ:

~~~java
// Mã minh họa nguy hiểm, không phải chương trình độc lập.
private byte[] sharedBuffer;

@Override
protected Class<?> findClass(String name)
        throws ClassNotFoundException {
    sharedBuffer = readBytes(name); // thread khác có thể ghi đè
    return defineClass(name, sharedBuffer, 0, sharedBuffer.length);
}
~~~

Khi hai thread nạp hai tên khác nhau cùng lúc, dữ liệu `sharedBuffer` có thể bị ghi đè; class A có thể nhận bytecode B, dẫn tới `ClassFormatError`, `NoClassDefFoundError` hoặc lỗi không ổn định.

Thiết kế tốt hơn:

~~~java
// Mã minh họa; readBytes(...) do loader triển khai và có
// quyền truy cập nguồn dữ liệu an toàn khi gọi đồng thời.
@Override
protected Class<?> findClass(String name)
        throws ClassNotFoundException {
    byte[] bytes = readBytes(name); // biến cục bộ mỗi lời gọi
    return defineClass(name, bytes, 0, bytes.length);
}
~~~

Ngoài byte array, phải kiểm tra:

- Bản đồ tên class tới bytes/URL được cache và cập nhật đồng thời.
- `JarFile`, ZIP reader, network client hoặc database connection được chia sẻ.
- State package-definition, code source, security domain, signer/sealing và metadata.
- Hàng đợi callback và event log nếu `findClass` phát event.
- Đường nạp resource và các stream đang mở khi plugin shutdown.
- Việc `close()` hoặc reload loader diễn ra đồng thời với class loading.
- Lock order khi các loader tùy chỉnh gọi chéo nhau hoặc dùng nhiều khóa.

**Không đăng ký chỉ vì muốn “nhanh hơn” nếu implementation hiện tại không thread-safe.** Chuyển từ một khóa loader toàn cục sang khóa theo tên có thể làm lộ race vốn bị serialization tình cờ che giấu.

## 9. Nếu override `loadClass` thì vẫn phải khóa đúng
`registerAsParallelCapable()` giúp triển khai **mặc định** dùng khóa theo tên; nó không chèn khóa vào bất kỳ override nào. Nếu bắt buộc viết child-first, đặt toàn bộ **`findLoadedClass` → delegation/`findClass` → `resolveClass` (khi cần)** trong `synchronized(getClassLoadingLock(name))`. Xử lý parent `null`, shared API và lỗi `ClassNotFoundException` chính xác; không nuốt `LinkageError`. Tránh `public synchronized loadClass` vì khóa toàn instance làm mất lợi ích per-name locks.
Với mục đích bổ sung nguồn bytecode, nên chỉ override `findClass` và để `loadClass` chuẩn quản lý locking/delegation.

## 10. Tại sao hai thread cùng tên vẫn cần được tuần tự hóa?

Một loader không được tự do định nghĩa cùng binary name hai lần:

~~~text
Thread A: child.loadClass("plugin.Widget")
Thread B: child.loadClass("plugin.Widget")
             │
             ▼
      Cùng lock của tên Widget
             │
             ▼
     Kiểm tra findLoadedClass
             │
             ▼
    Chỉ một định nghĩa Class<?> hợp lệ
~~~

Nếu cả hai cùng gọi `defineClass` mà không kiểm tra và phối hợp đúng, có thể gặp `LinkageError: duplicate class definition`. `registerAsParallelCapable` **không cho phép** tạo nhiều runtime type cùng tên trong **cùng defining loader**.

Hai loader instance khác nhau có thể tự định nghĩa class cùng binary name và tạo **hai runtime types khác nhau**. Đó là vấn đề class identity theo `(binary name, defining loader)`, không phải mục đích của parallel-capable registration.

## 11. Khi delegation không phân cấp
Trong đồ thị loader có gọi chéo, T1 giữ khóa A chờ B và T2 giữ khóa B chờ A có thể deadlock. Parallel-capable giảm contention khi các tên khác nhau, nhưng không chữa vòng chờ thực sự. Bài **Deadlock khi nhiều loader ủy quyền chéo** tập trung vào cách tái hiện và chẩn đoán; quy tắc đăng ký vẫn là: chọn loader hierarchy đủ điều kiện **và** làm an toàn mọi shared state.

## 12. Trạng thái có thể quan sát bằng `isRegisteredAsParallelCapable()`

Java 9+ cung cấp:

~~~java
public final boolean isRegisteredAsParallelCapable()
~~~

Phương thức là **instance API**, trả về `true` khi **class của loader object** đã đăng ký parallel capable. Đây là cách dễ kiểm tra trạng thái:

~~~java
// Mã minh họa, cần một đối tượng customLoader:
System.out.println(customLoader.isRegisteredAsParallelCapable());
~~~

Không nhầm với `registerAsParallelCapable()`, là **protected static** để đăng ký class. Sự khác biệt:

| API | Static hay instance? | Công dụng |
|---|---|---|
| `registerAsParallelCapable()` | `protected static` | Đăng ký **loader type**; thường trong static initializer |
| `isRegisteredAsParallelCapable()` | `public final` instance method | Đọc trạng thái đăng ký của **loader object/type** |
| `getClassLoadingLock(name)` | `protected` instance method | Lấy khóa mà default `loadClass` sẽ dùng |
| `loadClass(name)` | Instance method | Yêu cầu nạp class với delegation và locking |

Ví dụ `ParallelRegistrationDemo` dùng cả hai loại API để kiểm tra status và lock identity mà không cần reflection vào internals của JDK.

## 13. Những lỗi thường gặp

| Sai lầm | Hậu quả | Cách đúng |
|---|---|---|
| “`ClassLoader` registered nên mọi subclass tự registered” | Subclass vẫn non-parallel capable nếu không tự đăng ký | Đăng ký trong từng loader subclass cần parallel |
| Chỉ gọi register trong subclass, bỏ qua base loader chưa đăng ký | `registerAsParallelCapable()` trả `false` | Đăng ký toàn bộ chuỗi superclass trước |
| Gọi đăng ký sau khi đã tạo instance | Điều kiện thời điểm không còn đúng | Đăng ký ở static initializer trước khi tạo instance |
| Coi `getParent()` là superclass | Phân tích sai điều kiện đăng ký | Phân biệt type inheritance và instance delegation |
| Bỏ qua giá trị boolean của đăng ký | Tưởng đang parallel nhưng thực tế khóa toàn loader | Kiểm tra `true` và fail fast nếu cần |
| Cho rằng đăng ký làm mọi field tự thread-safe | Race khi `findClass` dùng shared state | Rà soát mutable state và concurrency |
| `synchronized loadClass(...)` trên toàn object | Serializes mọi class name dù đã registered | Dùng default `loadClass`/`getClassLoadingLock(name)` |
| Hai thread nạp cùng class name rồi define hai lần | `LinkageError` do duplicate definition | Đồng bộ theo tên và `findLoadedClass` đúng cách |
| Dùng parallel capability làm bảo đảm không deadlock | Có thể còn lock inversion ở parent/dependency | Kiểm tra topology delegation và thứ tự lock |
| Nhầm parallel loading với class initialization song song | Nhầm giai đoạn class lifecycle | Tách loading, linking và initialization |
| Benchmark thấy không nhanh hơn nên cho rằng API vô dụng | Bị giới hạn bởi I/O, parent lock hoặc workload | Quan sát contention và phân tích loader thực tế |

## 14. Khi nào nên đăng ký và khi nào không cần?

**Nên cân nhắc đăng ký** khi:

- Viết custom loader thực sự cần nạp nhiều class từ nhiều thread.
- Loader có thể được dùng bởi plugin host, application server hoặc framework có đường ủy quyền phức tạp.
- `findClass` được thiết kế thread-safe, sử dụng trạng thái/lưu trữ được đồng bộ phù hợp.
- Toàn bộ superclass chain đã registered và bạn kiểm soát được vòng đời static initialization.

**Không nhất thiết tự đăng ký** khi:

- Chỉ sử dụng loader chuẩn đã hỗ trợ việc cần làm; ví dụ `URLClassLoader` có thiết kế/đăng ký của JDK, không cần tạo subclass chỉ để “bật parallel”.
- Viết ứng dụng Java bình thường không tạo subclass của `ClassLoader`.
- Chưa kiểm chứng thread safety, đặc biệt nếu loader dùng shared byte buffer, resource handles hoặc cache mutable.
- Một superclass trong thư viện cũ không registered và bạn không thể thay class đó; gọi đăng ký ở subclass vẫn thất bại.

Nếu đơn giản chỉ cần nạp plugin JAR, ưu tiên `URLClassLoader` hoặc module/plugin mechanism phù hợp trước khi tự thiết kế ClassLoader cùng concurrency.

## 15. Lời khuyên kiểm thử concurrency

Trước khi đưa custom loader parallel capable vào production:

1. Xác nhận `registerAsParallelCapable()` **trả `true`** ở mỗi loader subclass cần thiết.
2. Xác nhận instance trả `isRegisteredAsParallelCapable() == true`.
3. Kiểm thử nạp **hai tên class khác nhau** đồng thời, và cả **cùng tên class** từ nhiều thread.
4. Kiểm tra không có `LinkageError` do define cùng tên, không có dữ liệu class bị lẫn giữa requests.
5. Kiểm thử các dependency cross-loader có thể tạo vòng chờ, với timeout và thread dump khi cần.
6. Rà soát `findClass`, `findResource(s)`, cache, filesystem/JAR/network read, close/shutdown lifecycle.
7. Không dùng số mili-giây của một lần chạy để kết luận thread safety hoặc mức tăng hiệu năng.
8. Nếu có lỗi, phân biệt **deadlock**, contention chậm, class initialization lock, I/O lock và circular class dependency.
9. Tránh đo đạc bằng cách override synchronization ngoài ý muốn làm thay đổi tính chất cần kiểm chứng.

**Giám sát:** thread dump, Java Flight Recorder, class-loading logs và các phép đo contention có thể giúp xác định nút thắt; không cần phỏng đoán dựa trên một console log.

## 16. Câu hỏi tự kiểm tra

**1. Điều kiện nào phải đúng để `registerAsParallelCapable()` thành công?**

**Đáp án:** Chưa có instance của caller loader class và mọi superclass loader của class đó (trừ `Object`) đã đăng ký parallel capable.

**2. `ClassLoader` đã registered. Vì sao subclass `MyLoader` vẫn cần đăng ký?**

**Đáp án:** Registration không tự kế thừa. Mỗi subclass có ý định parallel capable cần đăng ký riêng và thỏa điều kiện hierarchy.

**3. `Child extends LegacyParent`, LegacyParent không registered. Child gọi đăng ký trong static initializer; kết quả?**

**Đáp án:** `false` dù Child chưa có instance, vì superclass chưa registered.

**4. Một registered loader nạp `A` và `B`. Default lock cho hai tên có giống nhau không?**

**Đáp án:** Không. Default `getClassLoadingLock` trả khóa riêng theo class name; hai lời gọi cùng tên được phối hợp bằng cùng khóa.

**5. `registerAsParallelCapable()` có giúp code `findClass` dùng chung mutable byte buffer trở nên thread-safe không?**

**Đáp án:** Không. Tác giả loader phải tự bảo đảm shared state được truy cập an toàn. Registration chỉ ảnh hưởng cơ chế khóa loading của `ClassLoader`.

**6. Muốn bật parallel cho một loader object đã tồn tại bằng cách gọi instance method có được không?**

**Đáp án:** Không. Registration là static theo loader type và phải xảy ra khi chưa có instance; `isRegisteredAsParallelCapable()` chỉ dùng để kiểm tra trạng thái.

**7. Nếu parent ClassLoader instance là platform loader, superclass không registered có được bỏ qua không?**

**Đáp án:** Không. Điều kiện đăng ký xét **superclass của loader class**, không xét object parent được truyền vào constructor.

## 17. Tài liệu đối chiếu

- [Java SE 17 — ClassLoader](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): tổng quan parallel capable loaders, `registerAsParallelCapable`, `isRegisteredAsParallelCapable`, `getClassLoadingLock` và `loadClass`.
- [Java SE 17 — registerAsParallelCapable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#registerAsParallelCapable()): điều kiện “chưa có instance” và “mọi superclass đã registered”.
- [Java SE 17 — getClassLoadingLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#getClassLoadingLock(java.lang.String)): khóa toàn loader so với khóa theo tên.
- [Java SE 17 — isRegisteredAsParallelCapable](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html#isRegisteredAsParallelCapable()): kiểm tra trạng thái ở runtime.
- [JVMS 17 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): class identity, loading và linking.

**Ghi nhớ:** `registerAsParallelCapable()` phải được gọi **sớm trong static initializer của từng loader subclass**; chỉ thành công khi chưa có instance của caller và **mọi superclass loader đã registered**. Nó cho default `loadClass` dùng **khóa theo tên class** thay vì một khóa chung cho loader, nhưng **không tự làm custom loader thread-safe** và không bảo đảm mọi class loading sẽ chạy song song hoặc không deadlock.