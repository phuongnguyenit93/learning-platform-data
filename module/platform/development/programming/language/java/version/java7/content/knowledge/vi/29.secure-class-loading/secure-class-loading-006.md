# Java 7 — Nạp lớp an toàn: Khóa theo tên lớp qua getClassLoadingLock

## 1. Bài học này giải quyết điều gì?

Khi nhiều threads đồng thời yêu cầu một `ClassLoader` nạp các lớp, việc quản lý khóa ảnh hưởng trực tiếp tới **tính đúng đắn, khả năng chạy song song và nguy cơ deadlock**. Java 7 đưa vào cơ chế **parallel-capable class loaders** cùng hai API quan trọng:

- `protected Object ClassLoader.getClassLoadingLock(String className)` — lấy monitor dùng để phối hợp việc nạp **tên lớp cụ thể**.
- `protected static boolean ClassLoader.registerAsParallelCapable()` — đăng ký **class của custom loader** có khả năng nạp các tên lớp khác nhau đồng thời.

Chủ đề cha trên lộ trình: **Nạp lớp an toàn**. Đề bài trực tiếp: **Khóa theo tên lớp qua getClassLoadingLock**.

Bài dùng Java 17+ và chỉ các API còn hợp lệ hiện nay. Một số tiện ích trong ví dụ như `ClassLoader.getPlatformClassLoader()` và `isRegisteredAsParallelCapable()` xuất hiện sau Java 7 nhưng vẫn được hỗ trợ. Không dạy dựa vào private JDK fields, `sun.misc.Unsafe`, điều chỉnh các cờ JVM không portable hay các kỹ thuật nạp lớp lỗi thời.

Sau bài học, bạn sẽ có thể:

1. Phân biệt loader-lock trên `this` với **class-name-specific lock**.
2. Giải thích mặc định `ClassLoader.loadClass(name,resolve)` dùng `synchronized(getClassLoadingLock(name))`.
3. Biết điều kiện/đúng vị trí gọi `registerAsParallelCapable()`.
4. Hiểu việc đăng ký của subclass **không tự được kế thừa** chỉ vì superclass đã đăng ký.
5. Hiểu ảnh hưởng của **mọi superclass của custom ClassLoader** tới đăng ký parallel-capable.
6. Phân biệt **cùng tên lớp** phải được phối hợp với **hai tên khác nhau** có thể nạp song song.
7. Tránh `LinkageError` do `defineClass` trùng tên/lỗi bytecode.
8. Ưu tiên override `findClass` khi vẫn dùng delegation chuẩn, thay vì tự viết lại `loadClass` không cần thiết.
9. Nếu buộc override `loadClass`, đặt khóa đúng và kiểm `findLoadedClass` trong critical section.
10. Hiểu class identity: binary name + **defining class loader**.
11. Biết parent delegation, class initialization và class resolution khác với monitor nạp lớp.
12. Thiết kế test concurrent đủ mạnh nhưng không phụ thuộc thread scheduling mỏng manh.
13. Biết giới hạn: per-name locks không tự xử lý shared metadata/package state, cyclic dependencies hoặc application-level side effects.
14. Phân biệt `ClassNotFoundException`, `ClassFormatError` và lỗi khởi tạo class.
15. Có checklist vận hành custom classloaders trong Java 17+.

## 2. Vì sao cần khóa nạp lớp?

Giả sử hai threads cùng gọi:

```java
Class<?> a = loader.loadClass("com.example.Widget");
Class<?> b = loader.loadClass("com.example.Widget");
```

Đây là **mảnh minh họa**; `loader` cần được tạo sẵn và class thực tế phải có. Nếu một custom loader tự tạo class từ bytes, cả hai threads có thể cùng kiểm "chưa nạp" rồi cùng gọi `defineClass`. Java VM **không cho một defining loader định nghĩa cùng một tên nhị phân hai lần**; lần thứ hai có thể gây `LinkageError`.

```text
        Thread A                      Thread B
           |                             |
    loadClass("Widget")           loadClass("Widget")
           |                             |
    acquire lock("Widget")         wait lock("Widget")
           |                             |
       findLoadedClass                   |
           |                             |
         findClass                       |
           |                             |
        defineClass                      |
           |                             |
       release lock                      |
                                         |
                                  acquire same lock
                                         |
                                  findLoadedClass
                                         |
                                 return existing Class
```

Mục tiêu không phải “khóa mọi lúc”. Mục tiêu là:
- **Cùng (loader, tên lớp)**: phối hợp để không định nghĩa trùng.
- **Khác tên lớp**: có thể thực hiện đồng thời nếu loader được đăng ký và code bên trong đủ an toàn.
- **Khác loader**: quản lý class identity và trạng thái riêng; cần thận trọng khi có delegation/cross-loader dependencies.

## 3. Mặc định ClassLoader.loadClass hoạt động ra sao?

Javadoc Java SE 17 mô tả thứ tự mặc định của `protected loadClass(String name, boolean resolve)`:

1. Lấy monitor bằng `getClassLoadingLock(name)` và đi vào vùng đồng bộ.
2. Gọi `findLoadedClass(name)` để tìm lớp đã được ghi nhận là nạp bởi loader này.
3. Nếu chưa thấy, yêu cầu **parent loader** nạp.
4. Nếu parent không tìm được, gọi `findClass(name)` của custom loader.
5. Nếu `resolve == true`, gọi `resolveClass(c)` để liên kết lớp.
6. Trả về `Class<?>`; nhả monitor khi rời vùng đồng bộ.

**Phỏng theo thuật toán**, không phải mã nguồn JDK nguyên văn:

```java
synchronized (getClassLoadingLock(name)) {
    Class<?> c = findLoadedClass(name);
    if (c == null) {
        try {
            c = getParent().loadClass(name);
        } catch (ClassNotFoundException notInParent) {
            c = findClass(name);
        }
    }
    if (resolve) resolveClass(c);
    return c;
}
```

Đây chỉ là **mảnh minh họa**: cách xử lý parent null, bootstrap loader, checked exceptions, module classes và overrides được rút gọn. **Không copy** snippet này vào production thay `ClassLoader.loadClass`. Mặc định JDK đã thực hiện delegation/locking cần thiết.

### 3.1. loadClass(String name) khác protected overload

`public Class<?> loadClass(String name)` thường tương đương `loadClass(name,false)` theo implementation. `resolve` liên quan **liên kết**, không có nghĩa `initialize` static fields/blocks.

### 3.2. Không tự gọi findClass trước khi delegate

Khi bạn chỉ override `findClass`, JDK vẫn chạy parent-first theo mặc định. Khi bạn override `loadClass` để child-first, bạn đang thay cả **thứ tự tìm kiếm, locking và duplicate-definition behavior**; phải review cẩn thận.

## 4. getClassLoadingLock(String) trả về gì?

Trong `ClassLoader` mặc định Java 17:

- Nếu instance được đăng ký là **parallel-capable**, `getClassLoadingLock(name)` trả một monitor **gắn với tên lớp được yêu cầu**.
- Nếu instance **không** parallel-capable, method trả về **chính loader (`this`)**.
- Với loader parallel-capable, tên lớp null gây `NullPointerException`.
- Method là `protected`: production code ngoài loader không nên tự mở rộng quyền hay dùng monitor làm primitive đồng bộ công khai.

```text
SERIAL (chưa đăng ký):
  load("A") ------+
  load("B") ------+----> monitor = loader instance
  load("C") ------+
  -> nạp các tên khác nhau bị serialized tại loader lock

PARALLEL-CAPABLE (đã đăng ký):
  load("A") ----------> monitor for "A"
  load("B") ----------> monitor for "B"
  load("C") ----------> monitor for "C"
  load("A" again) ----> same monitor for "A"
  -> A và B có thể tiến hành đồng thời
  -> A và A vẫn phối hợp qua cùng monitor
```

### 4.1. “Khóa theo tên lớp” thực chất được scope bởi loader

Cần hiểu đúng là **theo (instance của loader, tên nhị phân)**, không phải JVM-global monitor dùng cho mọi custom loader có cùng tên. Hai instances khác nhau có monitor riêng.

### 4.2. Không phải mọi classloader mặc định đều parallel-capable

Bản thân `java.lang.ClassLoader` được đăng ký parallel-capable. **Nhưng subclass của bạn phải tự đăng ký** nếu muốn dùng mô hình song song này; không vì superclass được đăng ký mà subclass mặc nhiên có trạng thái đó.

### 4.3. Một khóa ổn định cho cùng tên

`getClassLoadingLock("a.A")` được dùng nhiều lần trên cùng instance parallel-capable cần cho cùng monitor để tránh double `defineClass`. Nếu tự override và mỗi lần `return new Object()`, hai threads nhận hai monitors khác nhau và critical section không còn bảo vệ cùng lớp.

## 5. Chương trình 1 — LockIdentityDemo.java

Ta expose protected API qua một method trong subclass **chỉ để quan sát khi học**, không khuyến khích export monitor cho callers không tin cậy ở production.

```java
public final class LockIdentityDemo {
 static final class Serial extends ClassLoader {
   Object lock(String n){return getClassLoadingLock(n);}
 }
 static final class Parallel extends ClassLoader {
   static {
     if(!registerAsParallelCapable())
       throw new IllegalStateException("registration failed");
   }
   Object lock(String n){return getClassLoadingLock(n);}
 }

 public static void main(String[] args) {
   Serial a=new Serial();
   Parallel b=new Parallel();

   System.out.println("serialRegistered="+
       a.isRegisteredAsParallelCapable());
   System.out.println("serialSameLockAllNames="+
       (a.lock("a.A")==a.lock("a.B")));
   System.out.println("serialLockIsLoader="+
       (a.lock("a.A")==a));
   System.out.println("parallelRegistered="+
       b.isRegisteredAsParallelCapable());
   System.out.println("parallelSameNameSameLock="+
       (b.lock("a.A")==b.lock("a.A")));
   System.out.println("parallelDifferentNamesDistinctLocks="+
       (b.lock("a.A")!=b.lock("a.B")));
   System.out.println("parallelLockNotLoader="+
       (b.lock("a.A")!=b));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 LockIdentityDemo.java
java LockIdentityDemo
```

**Stdout đã kiểm thử:**

```text
serialRegistered=false
serialSameLockAllNames=true
serialLockIsLoader=true
parallelRegistered=true
parallelSameNameSameLock=true
parallelDifferentNamesDistinctLocks=true
parallelLockNotLoader=true
```

**Đọc kết quả:** `Serial` không đăng ký nên mọi tên đều khóa trên `this`. `Parallel` đăng ký thành công trong static initializer và có monitor theo tên. Dấu `==` ở demo chỉ dùng để kiểm **identity của monitors**, không đánh giá nội dung bên trong ClassLoader.

**Lưu ý version:** `getClassLoadingLock`/`registerAsParallelCapable` là API từ Java 7; `isRegisteredAsParallelCapable()` là public final accessor có từ Java 9 và vẫn dùng trên Java 17+.

## 6. Đăng ký parallel-capable đúng cách

Một subclass muốn nạp các tên lớp khác nhau song song nên đăng ký **trong static initializer**, trước khi tạo instance:

```java
public final class MyParallelLoader extends ClassLoader {
    static {
        if (!registerAsParallelCapable()) {
            throw new ExceptionInInitializerError(
                "Cannot register parallel-capable loader");
        }
    }

    public MyParallelLoader(ClassLoader parent) {
        super(parent);
    }
}
```

Đây là **mảnh Java class độc lập để làm mẫu**, không có `main`. Khi đưa vào hệ thống, bạn còn cần `findClass` đọc class bytes từ nguồn đáng tin hoặc delegation phù hợp.

### 6.1. Điều kiện từ tài liệu Java SE 17

`registerAsParallelCapable()` được mô tả có thể thành công khi:

1. Chưa có instance nào của **class loader đang đăng ký** được tạo.
2. Mọi superclass của caller (ngoại trừ Object) đều đã đăng ký parallel-capable.

Đăng ký được gắn với **class của custom loader**, không phải chỉ một instance, và đã thành công thì không có API thu hồi trạng thái ấy. Dùng static initializer trước constructor là cách portable và đúng thiết kế.

**Không** trì hoãn đến `loadClass` lần đầu hoặc constructor để thử đăng ký. Đừng dùng một test trên một phiên bản JVM làm cớ bỏ qua yêu cầu của Java SE 17 documentation.

### 6.2. Tại sao các class cha cũng phải đăng ký?

Một subclass không thể tự chứng minh thread safety của code nạp lớp có thể được kế thừa từ superclass chưa tương thích với concurrent loading. Do đó Java yêu cầu cả chain classloaders đã đăng ký.

```text
ClassLoader [parallel capable by default]
   |
BaseParallelLoader [registerAsParallelCapable()]
   |
ChildParallelLoader [registerAsParallelCapable()]
   -> fine-grained named locks

ClassLoader [parallel capable by default]
   |
BaseSerialLoader [no registration]
   |
ChildAttemptsRegister [registerAsParallelCapable() -> false]
   -> loader-wide lock
```

## 7. Chương trình 2 — HierarchyRegistrationDemo.java

```java
public final class HierarchyRegistrationDemo {
 static class SerialBase extends ClassLoader {}

 static class ChildOfSerial extends SerialBase {
   static final boolean REGISTERED=
       registerAsParallelCapable();
 }

 static class ParallelBase extends ClassLoader {
   static final boolean REGISTERED=
       registerAsParallelCapable();
 }

 static class ParallelChild extends ParallelBase {
   static final boolean REGISTERED=
       registerAsParallelCapable();
 }

 public static void main(String[] args) {
   ChildOfSerial a=new ChildOfSerial();
   ParallelChild b=new ParallelChild();

   System.out.println("unregisteredParentCausesFailure="+
       (!ChildOfSerial.REGISTERED));
   System.out.println("serialChildRegistered="+
       a.isRegisteredAsParallelCapable());
   System.out.println("parallelBaseRegistered="+
       ParallelBase.REGISTERED);
   System.out.println("parallelChildRegistrationSucceeded="+
       ParallelChild.REGISTERED);
   System.out.println("parallelChildRegistered="+
       b.isRegisteredAsParallelCapable());
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 HierarchyRegistrationDemo.java
java HierarchyRegistrationDemo
```

**Stdout đã kiểm thử:**

```text
unregisteredParentCausesFailure=true
serialChildRegistered=false
parallelBaseRegistered=true
parallelChildRegistrationSucceeded=true
parallelChildRegistered=true
```

**Quan sát:** `ChildOfSerial` có method đăng ký nhưng superclass `SerialBase` chưa registered, nên không thể bật chế độ này. `ParallelChild` có ancestor `ParallelBase` đăng ký thành công và bản thân cũng đăng ký nên có thể dùng per-name locks.

### 7.1. Có nên bỏ qua return value?

Không. Với một loader được thiết kế bắt buộc parallel, static initializer nên kiểm kết quả và fail-fast nếu false, thay vì chạy như thể dùng được per-name locks.

### 7.2. Thêm lớp cha trong refactor có thể đổi behavior

Nếu đổi inheritance hierarchy, ví dụ chèn một `BaseLoader` không đăng ký giữa `ClassLoader` và `MyLoader`, khả năng đăng ký của subclass có thể mất. Hãy có tests kiểm cấu trúc classloader chain và registration state.

## 8. Ổn định monitor theo tên và theo từng instance

Một instance parallel-capable có thể trả cùng một object monitor khi được gọi cùng tên nhiều lần. Hai tên khác nhau nhận locks khác nhau, và **hai instances loader** không chia sẻ một pool monitor chung theo tên class.

Khi subclass tự xây map khóa:
- Dùng dữ liệu thread-safe nếu thật sự override.
- Bảo đảm `same instance + same name` → cùng monitor ổn định.
- Không bỏ/xóa monitor khi class có thể đang được nạp hoặc còn threads giữ/wait trên lock.
- Tránh `synchronized(this)` quanh toàn bộ `loadClass` nếu muốn fine-grained parallelism.
- Không để caller bên ngoài giữ monitor rồi khóa theo thứ tự tùy ý.
- Khi dùng mặc định JDK, **không cần tự xây một ConcurrentHashMap khóa mới**.

## 9. Chương trình 3 — LockScopeDemo.java

```java
public final class LockScopeDemo {
 static final class Parallel extends ClassLoader {
   static {
     if(!registerAsParallelCapable())
       throw new IllegalStateException();
   }
   Object monitor(String name){
     return getClassLoadingLock(name);
   }
 }

 public static void main(String[] args) {
   Parallel a=new Parallel(),b=new Parallel();

   System.out.println("sameInstanceSameNameSameLock="+
       (a.monitor("p.A")==a.monitor("p.A")));
   System.out.println("sameInstanceDifferentNamesDifferentLocks="+
       (a.monitor("p.A")!=a.monitor("p.B")));
   System.out.println("differentInstancesSameNameDifferentLocks="+
       (a.monitor("p.A")!=b.monitor("p.A")));

   boolean nullRejected=false;
   try { a.monitor(null); }
   catch(NullPointerException e) { nullRejected=true; }

   System.out.println("nullNameRejectedForParallel="+
       nullRejected);
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 LockScopeDemo.java
java LockScopeDemo
```

**Stdout đã kiểm thử:**

```text
sameInstanceSameNameSameLock=true
sameInstanceDifferentNamesDifferentLocks=true
differentInstancesSameNameDifferentLocks=true
nullNameRejectedForParallel=true
```

**Giới hạn:** Một `null` không phải tên nhị phân hợp lệ. Với parallel-capable default implementation, `getClassLoadingLock(null)` ném `NullPointerException`. Không dùng null để phát hiện capabilities trong production; `isRegisteredAsParallelCapable()` rõ nghĩa hơn.

## 10. Synchronized đúng mức: cùng tên chỉ define một lần

Một custom loader thực hiện parent-first bình thường **nên override `findClass(String)`**, để inherited `loadClass` tự đồng bộ đúng theo `getClassLoadingLock`, kiểm `findLoadedClass`, delegate parent và resolve.

```text
8 threads request the SAME class name
               |
       one parallel loader
               |
    synchronized(lock for "Payload")
               |
       findLoadedClass?
        /            \
     absent         already found
       |                 |
   findClass & define    return
       |
    return Class
               |
all callers observe SAME Class<?> for the pair (loader,name)
```

Điều quan trọng không phải 8 threads lần lượt tạo 8 objects hay 8 classes. Chúng có thể cùng lấy **một `Class<?>`**, với định nghĩa chỉ một lần.

### 10.1. Tại sao test nên kiểm số lần findClass thực tế?

Một test chỉ gọi `loadClass` một lần không phát hiện race. Test dưới đây dùng 8 tasks bắt đầu gần nhau và kiểm **số lần `findClass` đã được gọi để định nghĩa lớp**. Kết quả mong muốn là **1**.

## 11. Chương trình 4 — ConcurrentDefineDemo.java

Ví dụ tự chứa: nested `Payload` được `javac` tạo thành file `ConcurrentDefineDemo$Payload.class`. Custom loader có **platform loader** làm parent, nên parent không định nghĩa application payload. `findClass` đọc class bytes từ resource nằm cạnh demo.

```java
import java.io.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class ConcurrentDefineDemo {
 public static final class Payload {}

 static final class ByteLoader extends ClassLoader {
   static {
     if(!registerAsParallelCapable())
       throw new IllegalStateException();
   }

   final AtomicInteger definitions=new AtomicInteger();

   ByteLoader(){
     super(ClassLoader.getPlatformClassLoader());
   }

   boolean definedHere(String n){
     return findLoadedClass(n)!=null;
   }

   @Override
   protected Class<?> findClass(String name)
       throws ClassNotFoundException {
     if(!name.equals("ConcurrentDefineDemo$Payload"))
       throw new ClassNotFoundException(name);

     definitions.incrementAndGet();
     try(InputStream in=ClassLoader.getSystemResourceAsStream(
         name.replace('.','/')+".class")) {
       if(in==null)throw new ClassNotFoundException(name);
       byte[] bytes=in.readAllBytes();
       return defineClass(name,bytes,0,bytes.length);
     }catch(IOException e){
       throw new ClassNotFoundException(name,e);
     }
   }
 }

 public static void main(String[] args)throws Exception {
   ByteLoader loader=new ByteLoader();
   ExecutorService pool=Executors.newFixedThreadPool(8);
   CountDownLatch start=new CountDownLatch(1);
   List<Future<Class<?>>> jobs=new ArrayList<>();

   try {
     for(int i=0;i<8;i++)jobs.add(pool.submit(()->{
       start.await();
       return loader.loadClass(
           "ConcurrentDefineDemo$Payload");
     }));
     start.countDown();

     Class<?> first=jobs.get(0).get(
         15,TimeUnit.SECONDS);
     boolean same=true;
     for(Future<Class<?>> f:jobs)
       same &= first==f.get(15,TimeUnit.SECONDS);

     System.out.println("allReturnedSameClass="+same);
     System.out.println("definitionCalls="+
         loader.definitions.get());
     System.out.println("definedByCustomLoader="+
         (first.getClassLoader()==loader));
     System.out.println("findLoadedClassRecognizesIt="+
         loader.definedHere(
             "ConcurrentDefineDemo$Payload"));
   }finally{
     pool.shutdownNow();
     if(!pool.awaitTermination(
         15,TimeUnit.SECONDS))
       throw new IllegalStateException(
           "pool not stopped");
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ConcurrentDefineDemo.java
java ConcurrentDefineDemo
```

**Stdout đã kiểm thử:**

```text
allReturnedSameClass=true
definitionCalls=1
definedByCustomLoader=true
findLoadedClassRecognizesIt=true
```

### 11.1. Giải thích từng bước

- `registerAsParallelCapable` trong static initializer đảm bảo per-name monitor.
- `ByteLoader` chọn `ClassLoader.getPlatformClassLoader()` làm parent, còn bytes của nested Payload được lấy từ **system resource** chỉ để tạo ví dụ.
- Inherited `loadClass` làm parent-first rồi gọi `findClass` khi parent không tìm được.
- Dù 8 tasks đồng thời, chỉ một task define Payload; các tasks sau thấy class đã nạp.
- `AtomicInteger` dùng để đếm lời gọi trong test, **không phải** một giải pháp thay cho class loading locks.
- Khi task thất bại, `Future.get` propagate lỗi qua `ExecutionException`. `finally` shutdown executor.

### 11.2. Đừng sao chép resource loader thành production loader

Demo đọc bytes từ system classpath để tránh external dependencies. Production loader phải xét nguồn bytes đáng tin, package sealing, code source/protection domain, modules, class format, kiểm soát quyền và memory lifecycle. Dùng loader chuẩn/framework khi không thật sự cần custom one.

### 11.3. Phân biệt findLoadedClass và “định nghĩa bởi loader”

`findLoadedClass` báo một class đã được ghi nhận là loaded/initiated đối với loader theo Javadoc, **không nên tự diễn giải giá trị non-null là bằng chứng tuyệt đối rằng nó đã được define tại loader này** trong mọi tình huống delegation. Kiểm `c.getClassLoader()` khi cần biết **defining loader**.

## 12. Hai tên lớp khác nhau có thể đi vào findClass đồng thời

Một loader parallel-capable cho phép:

```text
Thread 1: lock("Alpha") -> findClass("Alpha") -> defineClass("Alpha")
Thread 2: lock("Beta")  -> findClass("Beta")  -> defineClass("Beta")
                  ^ independent per-name locks ^
```

Điều đó **không** có nghĩa mọi custom `findClass` đã an toàn:
- Nếu `findClass` dùng shared mutable map không đồng bộ, vẫn có race.
- Nếu `findClass` gọi `synchronized(this)`, toàn bộ lợi ích parallelization có thể biến mất.
- Nếu mọi tác vụ cần I/O từ một resource global có khóa riêng, vẫn có contention.
- Nếu hai classes phụ thuộc/initialize lẫn nhau, vẫn có thể deadlock ở các khóa khác.
- Nếu dùng custom delegate graph có vòng, cần phân tích lock ordering.

### 12.1. Kiểm concurrent mà không so thời gian benchmark

Đo thời gian 2 threads đôi khi không đáng tin trên CI bận. Ví dụ kế tiếp dùng `CyclicBarrier(2)` trong `findClass`: mỗi thread chỉ được đi tiếp khi **cả hai đã cùng vào `findClass`**. Loader serial có một khóa duy nhất sẽ không cho hai call đó cùng đi vào khi một call chưa ra; loader parallel với tên khác nhau mới đáp ứng được.

## 13. Chương trình 5 — DifferentNamesConcurrencyDemo.java

```java
import java.io.*;
import java.util.concurrent.*;

public final class DifferentNamesConcurrencyDemo {
 public static final class Alpha {}
 public static final class Beta {}

 static final class Loader extends ClassLoader {
   static {
     if(!registerAsParallelCapable())
       throw new IllegalStateException();
   }

   final CyclicBarrier both=new CyclicBarrier(2);

   Loader(){
     super(ClassLoader.getPlatformClassLoader());
   }

   @Override
   protected Class<?> findClass(String name)
       throws ClassNotFoundException {
     if(!name.equals(
             "DifferentNamesConcurrencyDemo$Alpha")
         &&!name.equals(
             "DifferentNamesConcurrencyDemo$Beta"))
       throw new ClassNotFoundException(name);

     try {
       both.await(10,TimeUnit.SECONDS);
       try(InputStream in=ClassLoader.getSystemResourceAsStream(
           name.replace('.','/')+".class")) {
         if(in==null)throw new ClassNotFoundException(name);
         byte[] bytes=in.readAllBytes();
         return defineClass(name,bytes,0,bytes.length);
       }
     }catch(InterruptedException ex){
       Thread.currentThread().interrupt();
       throw new ClassNotFoundException(name,ex);
     }catch(BrokenBarrierException
           |TimeoutException
           |IOException ex){
       throw new ClassNotFoundException(name,ex);
     }
   }
 }

 public static void main(String[] args)throws Exception {
   Loader loader=new Loader();
   ExecutorService pool=Executors.newFixedThreadPool(2);

   try {
     Future<Class<?>> a=pool.submit(()->loader.loadClass(
         "DifferentNamesConcurrencyDemo$Alpha"));
     Future<Class<?>> b=pool.submit(()->loader.loadClass(
         "DifferentNamesConcurrencyDemo$Beta"));

     Class<?> ca=a.get(15,TimeUnit.SECONDS);
     Class<?> cb=b.get(15,TimeUnit.SECONDS);

     System.out.println(
         "differentNamesEnteredFindClassTogether="+
         (loader.both.getNumberWaiting()==0));
     System.out.println("bothDefinedByCustomLoader="+
         (ca.getClassLoader()==loader
             && cb.getClassLoader()==loader));
     System.out.println("classesDistinct="+(ca!=cb));
   }finally{
     pool.shutdownNow();
     if(!pool.awaitTermination(
         15,TimeUnit.SECONDS))
       throw new IllegalStateException(
           "pool not stopped");
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 DifferentNamesConcurrencyDemo.java
java DifferentNamesConcurrencyDemo
```

**Stdout đã kiểm thử:**

```text
differentNamesEnteredFindClassTogether=true
bothDefinedByCustomLoader=true
classesDistinct=true
```

**Vì sao chứng minh được concurrency?** `CyclicBarrier` có hai parties, và mỗi `findClass` phải chờ một call khác đi vào. Cả hai futures đã hoàn tất trong thời hạn chứng minh có lúc hai different-name calls cùng tiến vào vùng `findClass`. Dòng `getNumberWaiting()==0` chỉ xác nhận trạng thái sau khi barrier đã qua; **bằng chứng quan trọng là cả hai calls thực sự qua barrier mà không timeout**.

**Không phải benchmark:** Không dùng demo này để khẳng định throughput cải thiện N lần. Nếu máy CI rất chậm, timeout 10 giây có thể là nguồn flaky test; điều chỉnh timeout phù hợp và dùng test frameworks quản lý deadlines.

## 14. Parent-first delegation ảnh hưởng khóa và identity

Mô hình mặc định của ClassLoader:

```text
loader.loadClass("java.lang.String")
       |
findLoadedClass?
       |
parent.loadClass(...)
       |
Bootstrap / platform supplies String
       |
return java.lang.String Class object
```

Nếu parent đã có class, `findClass` của child có thể **không được gọi**. Điều này quan trọng khi custom loader dùng để load plugins:
- Parent-first tránh định nghĩa lại core Java classes.
- Child-first chỉ nên dùng với names/packages được chọn và được đánh giá.
- Một tên class có thể được parent define thay vì custom loader.
- Concurrency của child có thể bị giới hạn bởi parent hoặc resource loader.
- Không suy class đã được “load qua child” nghĩa child đã “define” class.

## 15. Chương trình 6 — ParentDelegationDemo.java

```java
import java.util.concurrent.atomic.AtomicInteger;

public final class ParentDelegationDemo {
 static final class Loader extends ClassLoader {
   AtomicInteger finds=new AtomicInteger();

   @Override
   protected Class<?> findClass(String name)
       throws ClassNotFoundException {
     finds.incrementAndGet();
     throw new ClassNotFoundException(name);
   }

   boolean definedHere(String n){
     return findLoadedClass(n)!=null;
   }
 }

 public static void main(String[] args)throws Exception {
   Loader loader=new Loader();
   Class<?> a=loader.loadClass("java.lang.String");
   Class<?> b=loader.loadClass("ParentDelegationDemo");

   System.out.println("stringFromParent="+
       (a==String.class));
   System.out.println("appClassFromParent="+
       (b==ParentDelegationDemo.class));
   System.out.println("findClassCalls="+
       loader.finds.get());
   System.out.println("stringNotDefinedHere="+
       (!loader.definedHere("java.lang.String")));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ParentDelegationDemo.java
java ParentDelegationDemo
```

**Stdout đã kiểm thử trong môi trường chuẩn của demo:**

```text
stringFromParent=true
appClassFromParent=true
findClassCalls=0
stringNotDefinedHere=true
```

**Giải thích:** `String` và chính demo đã được loader cha/bootstrap cung cấp, nên custom `findClass` không cần chạy. Giá trị `stringNotDefinedHere` là điều quan sát được trong cấu hình này; không dùng nó để định nghĩa lại contract đầy đủ của `findLoadedClass` trong mọi VM/delegation path. Để xác nhận defining loader, xem `a.getClassLoader()` (bootstrap thường là `null`).

## 16. Class identity: tên giống nhau vẫn có thể là hai lớp khác nhau

Trong JVM, class identity liên quan tới **binary name và defining loader**. Hai loaders khác nhau có thể define hai classes cùng binary name. Khi đó:

```text
Loader A --- defines ---> demo.Plugin  ---> Class<?> A
Loader B --- defines ---> demo.Plugin  ---> Class<?> B

same text name, different defining loader
A != B
Instances may not be assignable across class boundaries.
```

Đây là nguyên nhân phổ biến của `ClassCastException` trong hệ plugin/app server dù log in class name có vẻ giống nhau.

### 16.1. Khóa getClassLoadingLock không bao trùm hai loader

Lock của loader A cho `"demo.Plugin"` không đồng bộ với lock của loader B cho cùng tên. Điều đó hợp lý vì hai loaders được phép define **hai class identities riêng** (trong giới hạn delegation/module/security rules).

## 17. Chương trình 7 — ClassIdentityDemo.java

```java
import java.io.*;

public final class ClassIdentityDemo {
 public static final class Payload {}

 static final class Isolated extends ClassLoader {
   static {
     if(!registerAsParallelCapable())
       throw new IllegalStateException();
   }

   Isolated(){
     super(ClassLoader.getPlatformClassLoader());
   }

   @Override
   protected Class<?> findClass(String name)
       throws ClassNotFoundException {
     if(!name.equals("ClassIdentityDemo$Payload"))
       throw new ClassNotFoundException(name);
     try(InputStream in=ClassLoader.getSystemResourceAsStream(
         name.replace('.','/')+".class")) {
       if(in==null)throw new ClassNotFoundException(name);
       byte[] b=in.readAllBytes();
       return defineClass(name,b,0,b.length);
     }catch(IOException ex){
       throw new ClassNotFoundException(name,ex);
     }
   }
 }

 public static void main(String[] args)throws Exception {
   Isolated a=new Isolated(),b=new Isolated();
   Class<?> ca=a.loadClass("ClassIdentityDemo$Payload");
   Class<?> cb=b.loadClass("ClassIdentityDemo$Payload");

   System.out.println("sameBinaryName="+
       ca.getName().equals(cb.getName()));
   System.out.println("distinctClassObjects="+
       (ca!=cb));
   System.out.println("separateDefiningLoaders="+
       (ca.getClassLoader()==a
           && cb.getClassLoader()==b));
   System.out.println("notAssignable="+
       (!ca.isAssignableFrom(cb)));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ClassIdentityDemo.java
java ClassIdentityDemo
```

**Stdout đã kiểm thử:**

```text
sameBinaryName=true
distinctClassObjects=true
separateDefiningLoaders=true
notAssignable=true
```

**Lưu ý:** Ví dụ dùng custom loader cho application class theo tên riêng phục vụ thí nghiệm, không tự define `java.*` classes. Production plugin systems cần parent delegation, package/module boundaries, isolation policies và kiểm class loader leaks.

## 18. loadClass, resolveClass và class initialization khác nhau

Một sự nhầm lẫn liên quan trực tiếp khi suy “loader lock giữ đến khi nào”:

- **Loading:** tìm hoặc định nghĩa đối tượng `Class<?>`.
- **Linking:** verification/preparation/resolution; `resolveClass` liên kết.
- **Initialization:** thực thi static initializers và một số static field initialization khi class được sử dụng theo quy tắc Java.

`loadClass` không có nghĩa static initializer chạy ngay. `Class.forName(name,false,loader)` yêu cầu không initialize, trong khi `Class.forName(name,true,loader)` yêu cầu initialize class.

**Quan trọng:** JVM có cơ chế đồng bộ **class initialization** riêng, không được thay thế bằng per-name `getClassLoadingLock` monitor. Deadlocks do cyclic static initialization/dependencies vẫn có thể xảy ra dù loader parallel-capable.

## 19. Chương trình 8 — InitializationBoundaryDemo.java

```java
public final class InitializationBoundaryDemo {
 static int initCount=0;

 public static final class Payload {
   static {
     InitializationBoundaryDemo.initCount++;
   }
 }

 public static void main(String[] args)throws Exception {
   ClassLoader loader=
       ClassLoader.getSystemClassLoader();
   Class<?> loaded=loader.loadClass(
       "InitializationBoundaryDemo$Payload");

   System.out.println("loadedClassFound="+
       (loaded!=null));
   System.out.println("afterLoadInitCount="+
       initCount);

   Class.forName(
       "InitializationBoundaryDemo$Payload",
       false,loader);
   System.out.println("afterForNameFalseInitCount="+
       initCount);

   Class.forName(
       "InitializationBoundaryDemo$Payload",
       true,loader);
   System.out.println("afterForNameTrueInitCount="+
       initCount);
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 InitializationBoundaryDemo.java
java InitializationBoundaryDemo
```

**Stdout đã kiểm thử:**

```text
loadedClassFound=true
afterLoadInitCount=0
afterForNameFalseInitCount=0
afterForNameTrueInitCount=1
```

**Bài học:** Có thể có `Class<?>` và link class nhưng vẫn chưa chạy static initializer. Đừng dùng class-loading-lock để đồng bộ những static side effects của initializer.

## 20. synchronized là reentrant trên cùng monitor

Java intrinsic monitors là **reentrant**: một thread đã giữ monitor có thể vào lại `synchronized(monitor)` trước khi nhả. Với cùng tên lớp, mặc định parallel-capable loader cấp **cùng monitor**, nên một thread có thể đi vào vùng synchronized nested với chính monitor đó.

Reentrancy tránh deadlock do **một thread tự cố acquire lại đúng monitor**, nhưng không giải quyết:
- Hai threads mỗi bên giữ monitor A/B và chờ monitor còn lại.
- Reentrant calls lặp vô hạn do thuật toán sai.
- Cyclic class initialization.
- Shared metadata races khi nạp hai tên lớp khác nhau.

## 21. Chương trình 9 — ReentrantMonitorDemo.java

```java
public final class ReentrantMonitorDemo {
 static final class Parallel extends ClassLoader {
   static {
     if(!registerAsParallelCapable())
       throw new IllegalStateException();
   }

   Object monitor(String name){
     return getClassLoadingLock(name);
   }
 }

 public static void main(String[] args) {
   Parallel loader=new Parallel();
   Object lock=loader.monitor("example.Widget");
   int counter=0;

   synchronized(lock) {
     counter++;
     synchronized(loader.monitor("example.Widget")) {
       counter++;
     }
   }

   System.out.println("sameMonitorReentrant="+
       (counter==2));
   System.out.println("sameNameIdentity="+
       (lock==loader.monitor("example.Widget")));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ReentrantMonitorDemo.java
java ReentrantMonitorDemo
```

**Stdout đã kiểm thử:**

```text
sameMonitorReentrant=true
sameNameIdentity=true
```

**Chỉ để học:** Không chia sẻ object monitor này ra application code hoặc synchronize business state lên nó. Loader implementation được quyền thay đổi cách quản lý locks; tránh tạo external lock-order dependencies.

## 22. Khi nào bắt buộc override loadClass?

Javadoc Java 17 **khuyến khích override `findClass`** trong custom loaders vẫn tuân parent-first delegation. Inherited `loadClass` đã thực hiện:
- Kiểm `findLoadedClass` trong critical section.
- Parent delegation.
- Fallback sang `findClass`.
- Gọi `resolveClass` khi resolve=true.
- Dùng `getClassLoadingLock(name)` đúng scope.

Chỉ override `loadClass` khi cần thực sự thay đổi delegation strategy, ví dụ **child-first cho một prefix class name có chủ đích** trong môi trường plugin, với security review phù hợp.

### 22.1. Nếu tự override, không được bỏ khóa

Mẫu protected override **có giới hạn**:

```java
@Override
protected Class<?> loadClass(String name,boolean resolve)
    throws ClassNotFoundException {
    if(!name.equals("MySpecialPlugin"))
        return super.loadClass(name,resolve);

    synchronized(getClassLoadingLock(name)) {
        Class<?> c=findLoadedClass(name);
        if(c==null) c=findClass(name);
        if(resolve) resolveClass(c);
        return c;
    }
}
```

Đây là **mảnh minh họa**, cần có classloader subclass hỗ trợ `findClass`. Đây không phải mẫu child-first tổng quát cho mọi package. Không được override cả `java.*` và core platform packages tùy ý; không tự nạp bytes từ nguồn không đáng tin hoặc bỏ parent delegation cho shared APIs.

### 22.2. Vì sao findLoadedClass phải ở trong khóa?

Một chuỗi không an toàn:

```java
if (findLoadedClass(name) == null) {
    // Another thread could define the same class here.
    return findClass(name);
}
```

Đây là **anti-pattern minh họa**, chưa có đầy đủ method wrapper. Hai threads có thể cùng quan sát “chưa có” rồi định nghĩa trùng. Phải bao cả **check → find/define → resolve** trong cùng per-name monitor theo thiết kế.

### 22.3. Đừng synchronized toàn bộ instance method

`synchronized protected Class<?> loadClass(...)` hoặc `synchronized(this)` quá rộng có thể biến loader parallel-capable thành **serial** ở tầng implementation, làm mất lợi ích per-name locks. Một số custom loaders vẫn cần locks khác cho shared state, nhưng hãy dùng đúng ownership và critical sections.

## 23. Chương trình 10 — OverrideLoadClassDemo.java

Ví dụ có child-first **chỉ cho một binary name trong demo**, còn mọi class khác delegate mặc định. Đây là một trường hợp có lý do thật để override protected `loadClass`.

```java
import java.io.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

public final class OverrideLoadClassDemo {
 public static final class Payload {}

 static final class ChildFirst extends ClassLoader {
   static {
     if(!registerAsParallelCapable())
       throw new IllegalStateException();
   }

   final AtomicInteger defines=new AtomicInteger();

   ChildFirst(){
     super(ClassLoader.getPlatformClassLoader());
   }

   @Override
   protected Class<?> loadClass(String name,boolean resolve)
       throws ClassNotFoundException {
     if(!name.equals("OverrideLoadClassDemo$Payload"))
       return super.loadClass(name,resolve);

     synchronized(getClassLoadingLock(name)) {
       Class<?> result=findLoadedClass(name);
       if(result==null)result=findClass(name);
       if(resolve)resolveClass(result);
       return result;
     }
   }

   @Override
   protected Class<?> findClass(String name)
       throws ClassNotFoundException {
     if(!name.equals("OverrideLoadClassDemo$Payload"))
       throw new ClassNotFoundException(name);

     defines.incrementAndGet();
     try(InputStream in=ClassLoader.getSystemResourceAsStream(
         name.replace('.','/')+".class")) {
       if(in==null)throw new ClassNotFoundException(name);
       byte[] b=in.readAllBytes();
       return defineClass(name,b,0,b.length);
     }catch(IOException ex){
       throw new ClassNotFoundException(name,ex);
     }
   }
 }

 public static void main(String[] args)throws Exception {
   ChildFirst loader=new ChildFirst();
   ExecutorService e=Executors.newFixedThreadPool(4);

   try {
     Future<?>[] futures=new Future<?>[8];
     for(int i=0;i<futures.length;i++) {
       futures[i]=e.submit(()->{
         try {
           return loader.loadClass(
               "OverrideLoadClassDemo$Payload");
         }catch(ClassNotFoundException ex){
           throw new IllegalStateException(ex);
         }
       });
     }

     Object expected=futures[0].get(
         15,TimeUnit.SECONDS);
     boolean same=true;
     for(Future<?> f:futures)
       same &= f.get(15,TimeUnit.SECONDS)==expected;

     System.out.println("sameClassForSameName="+same);
     System.out.println("defineCalls="+
         loader.defines.get());
     System.out.println("customClassLoader="+
         (((Class<?>)expected).getClassLoader()==loader));
   }finally{
     e.shutdownNow();
     if(!e.awaitTermination(
         15,TimeUnit.SECONDS))
       throw new IllegalStateException();
   }
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 OverrideLoadClassDemo.java
java OverrideLoadClassDemo
```

**Stdout đã kiểm thử:**

```text
sameClassForSameName=true
defineCalls=1
customClassLoader=true
```

**Giải thích:** 8 tasks đi vào loader; vì cùng binary name, chỉ một lần `defineClass`. Khi trả kết quả, mỗi Future nhận cùng Class object. Những class names khác tiếp tục dùng parent-first default.

**Cảnh báo:** Việc đổi class delegation order là một quyết định security/compatibility lớn; ví dụ nhỏ không thay thế review cho OSGi/JPMS/app server plugin framework. Thường vẫn nên **chỉ override `findClass`**.

## 24. Trường hợp không tìm thấy class: ClassNotFoundException

Nếu parent không tìm được và `findClass` cũng không tìm được binary name, `loadClass` ném `ClassNotFoundException`. Ví dụ sai tên, thiếu jar/module/resource hoặc thiếu dependency.

Không nên bắt `ClassNotFoundException` rồi lập tức:
- Bỏ qua tính năng bảo mật bắt buộc.
- Thử load từ một server HTTP không tin cậy.
- Định nghĩa tùy tiện class khác có cùng tên.
- Cho phép nạp mọi class từ đường dẫn user nhập.

Nên chẩn đoán classpath/modulepath, jar, dịch vụ plugin, dependency versions, classloader parent/visibility và tên nhị phân đúng.

## 25. Chương trình 11 — MissingClassDemo.java

```java
public final class MissingClassDemo {
 static final class Simple extends ClassLoader {
   @Override
   protected Class<?> findClass(String name)
       throws ClassNotFoundException {
     throw new ClassNotFoundException(name);
   }
 }

 public static void main(String[] args) {
   Simple loader=new Simple();
   boolean notFound=false;
   try {
     loader.loadClass("not.existing.Dummy");
   }catch(ClassNotFoundException e){
     notFound=true;
   }

   System.out.println("unknownBinaryNameNotFound="+
       notFound);
   System.out.println("unregisteredSerialLoader="+
       (!loader.isRegisteredAsParallelCapable()));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 MissingClassDemo.java
java MissingClassDemo
```

**Stdout đã kiểm thử:**

```text
unknownBinaryNameNotFound=true
unregisteredSerialLoader=true
```

Demo có loader chưa đăng ký parallel, nhưng lỗi không tìm thấy lớp **không phải hệ quả tất yếu** của việc serial: nguồn bytes đơn giản là không tồn tại. Phân biệt lỗi cấu hình/classpath với lỗi locking.

## 26. ClassFormatError khác ClassNotFoundException

Một tên class có thể được tìm thấy nhưng bytes không phải một class file hợp lệ. Khi `defineClass` nhận bytes không hợp lệ, `ClassFormatError` có thể xảy ra.

- `ClassNotFoundException`: hệ thống không tìm thấy class hợp lệ qua lookup path.
- `ClassFormatError`: có dữ liệu không đúng định dạng class.
- `NoClassDefFoundError`: một định nghĩa class trước đó/việc resolution có vấn đề hoặc class phụ thuộc không tìm thấy tại runtime; phân tích nguyên nhân cụ thể.
- `LinkageError`: nhóm lỗi linking, bao gồm nhiều trường hợp định nghĩa trùng hoặc không tương thích.
- `ExceptionInInitializerError`: static initialization thất bại.
- `SecurityException`: vi phạm quyền/quy tắc bảo mật của class/package/protection domain.

**Quan trọng:** Không catch rộng `Error` rồi tiếp tục chạy như thể class có thể sử dụng bình thường. Log nguyên nhân, hạn chế retry tùy tiện và xử lý lỗi khởi tạo/verification nghiêm túc.

## 27. Chương trình 12 — BadClassBytesDemo.java

```java
public final class BadClassBytesDemo {
 static final class BadLoader extends ClassLoader {
   @Override
   protected Class<?> findClass(String n)
       throws ClassNotFoundException {
     if(!n.equals("InvalidPayload"))
       throw new ClassNotFoundException(n);

     byte[] bad={1,2,3,4};
     return defineClass(n,bad,0,bad.length);
   }
 }

 public static void main(String[] args) {
   boolean caught=false,wrongCatch=false;
   try {
     new BadLoader().loadClass("InvalidPayload");
   }catch(ClassFormatError e){
     caught=true;
   }catch(ClassNotFoundException e){
     wrongCatch=true;
   }

   System.out.println("classFormatErrorCaught="+caught);
   System.out.println("notClassNotFoundException="+
       (!wrongCatch));
 }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 BadClassBytesDemo.java
java BadClassBytesDemo
```

**Stdout đã kiểm thử:**

```text
classFormatErrorCaught=true
notClassNotFoundException=true
```

**Chỉ để học:** Chương trình cố tình cung cấp class bytes hỏng. Trong production không dùng code catch `ClassFormatError` để tiếp tục execution một plugin không đáng tin; phải từ chối nạp/kiểm nguồn bytes, ghi chẩn đoán thích hợp và cách ly thành phần lỗi.

## 28. Deadlock: per-name locks làm giảm một số rủi ro, không chữa mọi rủi ro

Với loader **không** parallel-capable, toàn bộ quá trình nạp class có thể giữ monitor loader duy nhất. Khi các loaders có non-hierarchical delegation hoặc callback vòng, các threads có thể khóa lẫn nhau:

```text
Thread A:
  hold loader-X lock -> request loader-Y

Thread B:
  hold loader-Y lock -> request loader-X

Both wait on the lock held by the other.
```

Parallel-capable loaders dùng per-class-name monitors giúp **loại một số điểm nghẽn/chu kỳ khóa loader-wide**, nhất là khi hai threads nạp **hai tên khác nhau**. Tuy nhiên:
- Hai threads có thể lần lượt giữ lock(A) và lock(B) rồi yêu cầu ngược lại.
- Static initializers có JVM initialization locks khác.
- Shared maps, package definitions, resource loaders, caches có locks riêng.
- Threads có thể chờ I/O, network, futures hoặc database locks.
- Thread pool starvation cũng làm tasks chờ nhau dù monitors không deadlock.

**Không** có quy tắc “đăng ký parallel-capable thì mọi deadlock biến mất”. Phải phân tích toàn bộ delegation graph, class dependencies, lock ordering và lifecycle.

### 28.1. Không viết test cố ý deadlock vô hạn

Một ví dụ thực hành về deadlock cố ý có thể làm JVM/CI treo. Hãy dùng thread dumps hoặc công cụ quan sát với **timeout**, không chạy code lock-cycle không giới hạn trên production hoặc CI.

### 28.2. Một loader parallel-capable có thể vẫn chậm

Mặc dù monitors theo tên khác nhau, cả hai classes có thể cùng cần:
- Một parent loader serial.
- Một jar stream/file system lock.
- Một global transform cache.
- Một network service hoặc trust validation.
- Một synchronized `findClass` hoặc synchronized helper.

Tối ưu cần profile, không suy “per-name lock = tốc độ N lần”.

## 29. Race ngoài per-name lock: package và metadata

Khi nạp các lớp khác tên **trong cùng package**, cả hai threads có thể cùng cập nhật **package metadata**, signer/certificate info, cache, loader-local metrics, transformed bytes cache, package sealing information.

Nếu custom `findClass` tự làm:

```java
if (getDefinedPackage("com.example") == null) {
    definePackage("com.example",
        null,null,null,null,null,null,null);
}
```

Đây là **mảnh minh họa** nằm trong custom ClassLoader, không phải chương trình độc lập. Một check-then-act như thế có thể race khi hai tên lớp khác nhau cùng định nghĩa package.

**Lời khuyên:**
- Tránh tự định nghĩa package nếu không cần; `defineClass` mặc định có xử lý package theo contract.
- Nếu cần sealed/versioned package, bảo vệ hoạt động definePackage theo **package-level coordination**, không chỉ per-class-name lock.
- Không catch tất cả `IllegalArgumentException` rồi mặc định “package đã tồn tại thì an toàn”; cần kiểm metadata/sealing.
- Dùng concurrent data structures cho shared cache, hoặc immutable snapshots.
- Phân biệt class-level lock và những invariants scope lớn hơn.

## 30. Vì sao tránh override getClassLoadingLock khi không cần?

Mặc định của `ClassLoader` đã có per-name monitor cho loader parallel-capable. Tự override không cần thiết tạo rủi ro:

1. `return new Object()` mỗi lần → cùng tên không còn cùng monitor, dẫn tới duplicate definition race.
2. `return this` dù registered → khóa toàn loader, mất parallelism.
3. Dùng `HashMap` không synchronized → races hoặc map corruption.
4. Remove entries trong khi threads còn giữ lock → hai locks cho cùng tên.
5. Lấy một global lock khác trong `getClassLoadingLock` và ở `findClass` theo thứ tự ngược → deadlock.
6. Dùng monitor của một object lifecycle ngắn và xóa map tùy tiện.
7. Expose monitor publicly → callers ngoài loader có thể hold lock lâu hoặc deadlock.
8. Bảo đảm monitor ổn định nhưng cache class bytes/defines không thread-safe → vẫn lỗi.
9. Sử dụng tên input chưa được validate làm resource path trên filesystem.
10. Tạo state quản lý monitors không cho lifecycle GC của loader.

Nếu thật sự cần locking scheme khác, phải chứng minh **stable per-name identity, safe publication, no double definition, package state safety, and delegation correctness** qua tests.

## 31. Phân biệt lớp cần nạp với resource cần đọc

Binary name là như `"com.example.Foo"`. Resource class file thường có tên `"com/example/Foo.class"`, **không phải cùng một string**. Với nested class:

```text
Binary name:  com.example.Outer$Inner
Resource:     com/example/Outer$Inner.class
```

Trong demos dùng:

```java
name.replace('.','/') + ".class"
```

Đây là mảnh minh họa chuyển tên thành resource path. Khi nạp external files, phải có **allowlist paths/names**, chống path traversal, quản lý resources, hạn chế kích thước bytes và kiểm provenance. Không chỉ tin người dùng nhập một className hợp lệ rồi đọc một file bất kỳ.

### 31.1. Không mọi tài nguyên đều hiện diện qua getSystemResourceAsStream

Đối với Java modules, class loaders/cùng packages có thể có quy tắc visibility/encapsulation khác; tài nguyên có thể nằm trong jar, module image, custom storage hoặc embedded assets. Test demos dùng file .class trên application classpath; production loaders dùng cơ chế resource phù hợp với deployment.

## 32. Khả năng song song và tính đúng đắn của findClass

Một custom loader đăng ký parallel-capable **tuyên bố** rằng nó có thể xử lý calls nạp các tên lớp khác nhau đồng thời. Điều này yêu cầu:

- Không có mutable state dùng chung không được đồng bộ.
- Class bytes transformations thread-safe.
- Shared caches có cơ chế publish/ownership.
- Không override `loadClass` mà bỏ `findLoadedClass` check.
- Không gọi `defineClass` trùng (loader,name).
- Package sealing/protection domain/metadata được quản lý đúng.
- Class bytes/source được kiểm soát và validate.
- Parent/resource delegation không tạo vòng bất ngờ.
- Không lock ngược chiều giữa các class names hoặc loaders.
- Error paths không để lại state “đang nạp” vĩnh viễn.
- Threads interrupted/cancelled không bỏ dở resource handles.
- Test thực tế với nhiều threads và plugin dependencies.

Nếu chưa tự tin về các điều kiện trên, **không đăng ký parallel-capable chỉ vì benchmark**. Hãy sửa thiết kế và test thread safety trước; việc đăng ký không tự đồng bộ shared maps.

## 33. Những sai lầm phổ biến

1. Nghĩ `getClassLoadingLock` là method public của mọi loader.
2. Nghĩ ClassLoader con tự parallel-capable khi ClassLoader gốc có registration.
3. Quên static initializer đăng ký.
4. Quên superclass trong hierarchy cũng phải registered.
5. Không kiểm boolean trả về `registerAsParallelCapable`.
6. Gọi registration sau khi loader đã sử dụng thay vì class initialization.
7. Nghĩ per-name lock là JVM-global lock cho cùng class name.
8. Nghĩ một loader parallel có thể define cùng (loader,name) nhiều lần.
9. Bỏ `findLoadedClass` rồi `defineClass` ngay.
10. Check `findLoadedClass` ở ngoài synchronized block rồi define ở trong.
11. `synchronized(this)` quanh toàn bộ `loadClass` dù đã registered.
12. `return new Object()` mỗi lần getClassLoadingLock.
13. Xóa lock-map entry khi threads còn chờ.
14. Dùng unsynchronized HashMap trong concurrent findClass.
15. Không test two-names concurrency.
16. Không test same-name single definition.
17. Tự gọi findClass trước parent mà không có compatibility reason.
18. Child-first mọi packages, kể cả core Java packages.
19. Nhầm loadClass với static class initialization.
20. Nhầm `Class.forName(...,true,...)` với `loadClass` không khởi tạo.
21. Nghĩ `findLoadedClass` là luôn proof defining loader.
22. So sánh class name Strings mà không xem `getClassLoader` khi debug ClassCastException.
23. Gọi `defineClass` với binary name khác bytes.
24. Dùng `defineClass(byte[],int,int)` overload deprecated không có name thay cho API có name.
25. Dùng class bytes từ nguồn không tin cậy.
26. Bỏ package sealing/signature/security checks.
27. Bắt `ClassNotFoundException` và giấu lỗi `LinkageError`.
28. Nghĩ `ClassFormatError` là “jar không có class” giống CNFE.
29. Chỉ đo thời gian một test để kết luận concurrent safety.
30. Dùng `Thread.sleep` làm đồng bộ chính của tests.
31. Nghĩ per-name locks loại mọi deadlock/cyclic initialization.
32. Nghĩ parallel class loading cũng làm business static fields thread-safe.
33. Giữ references tới loader/class mãi gây classloader leaks.
34. Dùng Thread Context ClassLoader làm bằng chứng class identity.
35. Dùng SecurityManager API đã deprecated như giải pháp mới cho plugin isolation.
36. Đánh đồng package lock với class-name lock.
37. Override getClassLoadingLock dù default đủ.
38. Bỏ timeout/cleanup khi stress test concurrency.
39. Log raw secrets/code source từ plugin untrusted.
40. Xây custom class loader trong production khi `URLClassLoader`/module/plugin framework đã đáp ứng đúng nhu cầu.

## 34. Checklist phát triển custom ClassLoader Java 17+

- [ ] Có lý do rõ ràng cần custom loader.
- [ ] Đặt parent/delegation policy trước.
- [ ] Ưu tiên override `findClass`; giữ inherited `loadClass`.
- [ ] Nếu cần parallel-capable, register trong static initializer.
- [ ] Mọi superclass ClassLoader đã registered.
- [ ] Registration trả true; có test `isRegisteredAsParallelCapable()`.
- [ ] Biết lock là theo **instance + binary name**, không global.
- [ ] Same name → same stable monitor; different names → independent monitors.
- [ ] Không dùng `new Object()` làm lock tạm mỗi call.
- [ ] Không dùng `synchronized(this)` làm bottleneck nếu muốn parallel.
- [ ] Trong override `loadClass`, bọc check → find/define → resolve bằng named lock.
- [ ] Không gọi `defineClass` hai lần cho cùng loader/name.
- [ ] Shared state/cache/metrics/packages thread-safe.
- [ ] Package sealing, certificates và code source được xử lý.
- [ ] Không define `java.*` từ custom untrusted loader.
- [ ] Nguồn bytes được tin cậy và giới hạn tài nguyên.
- [ ] Không leak privileged handles/classes/loaders.
- [ ] Biết `getClassLoader()` là defining loader identity indicator.
- [ ] Không nhầm loading/linking với initialization.
- [ ] Không dựa vào ClassLoader lock để bảo vệ static initializer side effects.
- [ ] Có tests same-name concurrent 8+ workers.
- [ ] Có test different-name concurrent progress khi cần.
- [ ] Có tests delegation, identity, bad/missing bytes.
- [ ] Không tự tạo deadlock test không timeout.
- [ ] Có thread dumps/diagnostic plan cho production.
- [ ] Dùng APIs Java SE 17+ vẫn được hỗ trợ.
- [ ] Không sửa JDK internals, module encapsulation hoặc dùng legacy hacks.
- [ ] Chỉ tối ưu performance sau khi đo thật.

## 35. Câu hỏi tự kiểm tra

**1.** `getClassLoadingLock` có `public` không? **Không, protected**.

**2.** ClassLoader không đăng ký parallel, `getClassLoadingLock("A")` trả gì? **this**.

**3.** Registered loader trả gì khi gọi hai lần cùng name? **Cùng monitor cho tên đó theo default implementation**.

**4.** Registered loader có cùng monitor cho hai names khác nhau không? **Không, default có dedicated per-name monitor**.

**5.** Các monitors có dùng chung giữa hai loader instances không? **Không theo default, scope theo instance**.

**6.** Method nào đăng ký loader parallel-capable? **registerAsParallelCapable()**.

**7.** Nên đặt đăng ký ở đâu? **Static initializer của subclass**.

**8.** Chỉ ClassLoader superclass registered là subclass tự registered? **Không**.

**9.** Nếu superclass trung gian chưa registered thì child register có thành công? **Không theo contract**.

**10.** Cần kiểm boolean kết quả register không? **Có**.

**11.** Public method kiểm trạng thái registration Java 17? **isRegisteredAsParallelCapable()**.

**12.** Default `loadClass` dùng monitor nào? **getClassLoadingLock(name)**.

**13.** Thứ tự mặc định trước `findClass`? **findLoadedClass, parent delegation, sau đó findClass**.

**14.** Nên override `findClass` hay `loadClass` cho parent-first loader thông thường? **findClass**.

**15.** Override `loadClass` phải giữ check nào trong lock? **findLoadedClass và define/resolve**.

**16.** Có thể define cùng tên 2 lần trong cùng defining loader không? **Không**.

**17.** Hai loaders define cùng binary name thì Class objects có giống nhau không? **Không nhất thiết; có thể khác**.

**18.** Hai classes cùng name nhưng khác defining loader có assignable mặc định không? **Không**.

**19.** `ClassLoader.loadClass` có chạy static initializer? **Không mặc định**.

**20.** `Class.forName(name,true,loader)` có yêu cầu initialize? **Có**.

**21.** Khóa class initialization có là `getClassLoadingLock` monitor không? **Không nên đánh đồng, JVM có cơ chế riêng**.

**22.** `getClassLoadingLock(null)` trên parallel-capable default? **NPE**.

**23.** `synchronized(this)` quanh mọi loadClass có ảnh hưởng concurrency? **Serialize tất cả names qua loader lock**.

**24.** `return new Object()` trong getClassLoadingLock có an toàn? **Không cho cùng name, locks không ổn định**.

**25.** `CyclicBarrier(2)` được dùng để test điều gì? **Hai different-name findClass calls có thể tiến vào đồng thời**.

**26.** AtomicInteger definition counter thay cho named locks không? **Không**.

**27.** Parent-first load java.lang.String có thể gọi child findClass không? **Thông thường không nếu parent đã tìm được**.

**28.** `ClassNotFoundException` và `ClassFormatError` giống nhau? **Không, không tìm được vs bytes sai định dạng**.

**29.** Có thể xảy ra deadlock dù class loader parallel-capable không? **Có**.

**30.** Package metadata cần lock riêng không? **Có thể, khi có shared mutation qua different names**.

**31.** Có phải tên class nested dùng dấu chấm `Outer.Inner` trong binary name không? **Không, thường là `Outer$Inner`**.

**32.** `ClassLoader.getPlatformClassLoader()` có từ Java 7? **Không, được bổ sung sau; có trong Java 17**.

**33.** `isRegisteredAsParallelCapable()` có từ Java 7? **Không, từ Java 9; còn hiện hành Java 17**.

**34.** Nếu muốn plugin isolation, có nên tùy tiện override `java.*` classes không? **Không**.

**35.** Muốn nạp class an toàn, chỉ cần getClassLoadingLock không? **Không; còn delegation, byte trust, packages, modules và lifecycle**.

## 36. Tài liệu Java 17 chính thức

- [ClassLoader — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `getClassLoadingLock`, `registerAsParallelCapable`, `isRegisteredAsParallelCapable`, `loadClass`, `findClass`, `findLoadedClass`, `defineClass`, `resolveClass`, `getPlatformClassLoader`.
- [Class — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `Class.forName(name,initialize,loader)`, `getClassLoader`, class initialization và resolution.
- [ClassNotFoundException — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassNotFoundException.html): class lookup failure.
- [ClassFormatError — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassFormatError.html): malformed class bytes.
- [LinkageError — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/LinkageError.html): class linkage errors.
- [ConcurrentHashMap — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): thread-safe caching khi thật sự cần.
- [CyclicBarrier — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html): deterministic concurrency coordination trong test.
- [ExecutorService — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): futures, lifecycle, shutdown.
- [InputStream — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/InputStream.html): đọc bytes và try-with-resources.
- [The Java Language Specification, Java SE 17, Chapter 12](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): loading, linking, initialization.
- [The Java Virtual Machine Specification, Java SE 17, Chapter 5](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): loading, defining loaders và class identity.

**Tổng kết:** `getClassLoadingLock(name)` phối hợp việc nạp **cùng tên lớp** theo monitor ổn định. Với custom loader chưa đăng ký parallel-capable, monitor là `this`; với loader đã đăng ký, mặc định có lock riêng theo tên, cho phép các classes khác tên tiến hành đồng thời mà vẫn tránh double-definition trong cùng loader. Đăng ký đúng trong static initializer, lưu ý mọi superclass, và ưu tiên override `findClass` để tái sử dụng thuật toán `loadClass` chuẩn. Nếu tự override `loadClass`, toàn bộ `findLoadedClass → find/define → resolve` phải nằm trong synchronized(named lock). Khóa theo tên giúp giải quyết một phần concurrency và deadlock, nhưng **không tự bảo đảm class byte security, package state, class initialization, module compatibility hoặc thread safety của code ứng dụng**.