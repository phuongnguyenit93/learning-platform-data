# Java 15 — `ClassOption.STRONG` và quan hệ với class loader trong vòng đời lớp ẩn

## 1. Mục tiêu học tập

**Hidden class** (*lớp ẩn*) là loại lớp được JVM định nghĩa động từ classfile bytes, thường dùng bởi thư viện sinh mã tại runtime. Từ **Java 15 (JEP 371)**, `MethodHandles.Lookup.defineHiddenClass(...)` cho phép quyết định cách lớp ẩn liên hệ với class loader được đánh dấu là **defining loader**. Tùy chọn **`MethodHandles.Lookup.ClassOption.STRONG`** làm quan hệ đó **mạnh**, tương tự lớp Java thông thường.

Đây là kiến thức **vẫn áp dụng trên JDK hiện đại**, không phải preview hay API đã bị loại bỏ. Bài tập trung vào điểm khác biệt dễ nhầm nhất:

> **Mặc định:** lớp ẩn *có thể* bị unload dù defining class loader còn reachable.  
> **Có `STRONG`:** lớp ẩn chỉ *có thể* bị unload khi defining class loader cũng không còn reachable và có thể được GC thu hồi.

Từ khóa “**có thể**” rất quan trọng. Không cấu hình nào buộc GC phải unload class vào một thời điểm xác định.

Sau bài, người học có thể:

- Phân biệt **class unloading** với **GC thu hồi object instance** và **GC thu hồi class loader**.
- Giải thích vai trò của `STRONG` trong liên hệ vòng đời lớp ẩn với class loader.
- Viết và chạy mã Java dùng `defineHiddenClass(bytes, initialize, ClassOption.STRONG)`.
- Hiểu vì sao **cùng `getClassLoader()` không có nghĩa cùng chính sách unloading**.
- Chọn chế độ mặc định hay `STRONG` trong thư viện sinh mã, tránh tích tụ class metadata.
- Biết rằng `STRONG` **độc lập với** `NESTMATE`, quyền truy cập private và khả năng tra tên của class.

## 2. Ngữ cảnh: class loader, hidden class và class unloading

### 2.1. Class loader là gì trong bài này?

Một class loader chịu trách nhiệm tải hoặc định nghĩa các lớp Java theo mô hình JVM. Đối với một **lớp Java có tên thông thường**, vòng đời của class gắn mạnh với **defining class loader**: về nguyên tắc, class chỉ đủ điều kiện unload khi loader của nó không còn reachable và có thể được GC thu hồi. `Class.getClassLoader()` cho biết loader liên quan đến class; đây **không** phải một lệnh yêu cầu load/unload.

Hidden class có điểm đặc biệt:

- Nó vẫn có `Class<?>` và được đánh dấu có class loader, package/module phù hợp.
- Nó **không có binary name thông thường** để tìm lại bằng `Class.forName(...)` hoặc `ClassLoader.loadClass(...)`.
- Nó có thể triển khai interface/superclass đã biết để code nghiệp vụ gọi qua hợp đồng ổn định.
- Theo mặc định, quan hệ giữa hidden class và loader được đánh dấu là defining loader **không mạnh giống class thông thường**. Nhờ đó một hidden class có thể bị unload khi loader vẫn còn sống.

Đặc tính này hữu ích khi runtime sinh ra nhiều class tạm thời — ví dụ các adapter, trình thực thi biểu thức hoặc mã được tạo cho từng cấu hình. Nếu mọi class đều phải sống ít nhất lâu bằng một application class loader tồn tại suốt tiến trình, chi phí class metadata có thể tích tụ.

### 2.2. `ClassOption.STRONG` thay đổi điều gì?

`STRONG` điều chỉnh **quan hệ khả năng sống còn của định nghĩa hidden class** với loader:

~~~text
Lớp có tên thông thường
    -> vòng đời gắn mạnh với defining loader

Hidden class mặc định (không STRONG)
    -> có thể unload độc lập dù defining loader vẫn sống

Hidden class + ClassOption.STRONG
    -> gắn mạnh với defining loader như lớp có tên
    -> không đủ điều kiện unload khi loader còn reachable
~~~

Điều này không có nghĩa “`STRONG` làm mọi object instance trở thành strong reference”. Nó cũng **không biến hidden class thành normal named class**. Nó chỉ thiết lập **một quan hệ vòng đời với class loader** theo hợp đồng JVM.

Để phân biệt ba trường hợp:

| Loại class | Loader vẫn reachable, không còn tham chiếu hữu ích khác | Loader không còn reachable |
| --- | --- | --- |
| Lớp có tên thông thường | Không đủ điều kiện unload chỉ vì hết instance | *Có thể* unload khi các điều kiện GC thỏa |
| Hidden class mặc định | *Có thể* unload độc lập với loader | *Có thể* unload; không có bảo đảm về thời điểm |
| Hidden class với `STRONG` | Không đủ điều kiện unload chừng nào loader vẫn reachable | *Có thể* unload cùng vòng đời loader khi đủ điều kiện |

Bảng mô tả **điều kiện đủ tư cách unload**, không dự đoán sự kiện GC cụ thể. Nếu vẫn giữ `Class<?>`, `MethodHandle`, `Lookup`, instance, thread stack hoặc cache liên quan, những tham chiếu ấy có thể tiếp tục giữ lớp và loader sống. Vì vậy “không có biến local trỏ tới class” **không đủ** để khẳng định lớp đã được unload.

### 2.3. Vì sao tên `STRONG` dễ gây hiểu lầm?

Tên này nói về **quan hệ với class loader**, không phải:

- “Giữ instance sống mãi”;
- “Định nghĩa lớp bất tử, không bao giờ unload”;
- “Lớp trở nên public hoặc có binary name”;
- “Mã trong lớp chạy nhanh hơn”;
- “Được quyền truy cập private của host”;
- “GC sẽ bỏ qua mọi bộ nhớ liên quan”.

Một hidden class có `STRONG` **vẫn có thể unload** nếu loader và những đối tượng giữ nó đều không còn reachable và JVM quyết định tiến hành unloading. Với application class loader thường sống suốt tiến trình, sự khác biệt về chi phí bộ nhớ có thể rất đáng kể.

## 3. API hiện hành: truyền `ClassOption.STRONG` vào `defineHiddenClass`

Cú pháp quan trọng:

~~~java
MethodHandles.Lookup original = MethodHandles.lookup();

MethodHandles.Lookup generated = original.defineHiddenClass(
        classfileBytes,
        false,
        MethodHandles.Lookup.ClassOption.STRONG);

Class<?> generatedType = generated.lookupClass();
~~~

Đây là **đoạn mã minh họa nằm trong method**, không phải file Java chạy độc lập. `classfileBytes` phải là `byte[]` chứa classfile hợp lệ. API chính thức:

~~~java
MethodHandles.Lookup defineHiddenClass(
        byte[] bytes,
        boolean initialize,
        MethodHandles.Lookup.ClassOption... options)
        throws IllegalAccessException
~~~

| Thành phần | Vai trò |
| --- | --- |
| `bytes` | Classfile bytes hợp lệ, package tương thích với lookup class, phiên bản phù hợp JVM |
| `initialize` | `true` yêu cầu khởi tạo hidden class ngay khi định nghĩa; `false` cho phép hoãn đến lúc có active use |
| `ClassOption.STRONG` | Thiết lập quan hệ **mạnh với defining class loader** |
| Không có `ClassOption.STRONG` | Áp dụng chế độ vòng đời mặc định của hidden class |
| Giá trị trả về `Lookup` | Lookup mới có `lookupClass()` là hidden class vừa định nghĩa |

**Lưu ý về quyền:** gọi `defineHiddenClass` cần `Lookup` đủ **full privilege access**. Dùng `MethodHandles.lookup()` trong class chủ của chính mình và bytecode cùng package là cách tạo ví dụ rõ ràng. Một `publicLookup()` đơn thuần không có quyền tùy ý định nghĩa hidden class ở package khác. Classfile bytes sai format, sai package hoặc sai phiên bản có thể gây lỗi định nghĩa/linking.

**`STRONG` được chọn tại thời điểm định nghĩa class**, không phải thuộc tính có thể bật/tắt sau bằng một setter trên đối tượng `Class<?>`. Nếu gọi hai lần với cùng bytes nhưng options khác nhau, JVM tạo **hai định nghĩa hidden class riêng biệt**.

### 3.1. `STRONG` là một lựa chọn về vòng đời, không về cách truy cập

`generated.lookupClass().isHidden()` vẫn bằng `true` khi dùng `STRONG`. Class vẫn không có binary name để các class khác viết vào constant pool như một class có tên thông thường. Những khác biệt về quyền member đến từ ngữ cảnh `Lookup`, module/nest và option `NESTMATE`, không phải từ `STRONG`.

## 4. Ví dụ độc lập Java 15+: hai hidden class, cùng loader, khác tùy chọn

Để minh họa mà không cần cài bytecode generator, chương trình sau đọc classfile của một **nested class được `javac` biên dịch sẵn**, rồi định nghĩa một hidden class mặc định và một hidden class có `STRONG` từ cùng bytes.

Lưu vào file **`StrongHiddenDemo.java`**:

~~~java
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.function.IntUnaryOperator;

public class StrongHiddenDemo {
    public static final class Task implements IntUnaryOperator {
        public Task() {}

        @Override
        public int applyAsInt(int value) {
            return value * 2 + 1;
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes;
        try (InputStream in = StrongHiddenDemo.class
                .getResourceAsStream("StrongHiddenDemo$Task.class")) {
            if (in == null) {
                throw new IllegalStateException("Missing class bytes");
            }
            bytes = in.readAllBytes();
        }

        MethodHandles.Lookup host = MethodHandles.lookup();
        MethodHandles.Lookup regularHidden =
                host.defineHiddenClass(bytes, false);
        MethodHandles.Lookup strongHidden =
                host.defineHiddenClass(
                        bytes,
                        false,
                        MethodHandles.Lookup.ClassOption.STRONG);

        Class<?> normal = Task.class;
        Class<?> weak = regularHidden.lookupClass();
        Class<?> strong = strongHidden.lookupClass();

        System.out.println("weakHidden=" + weak.isHidden());
        System.out.println("strongHidden=" + strong.isHidden());
        System.out.println("sameLoader=" +
                (weak.getClassLoader() == strong.getClassLoader()));
        System.out.println("loaderIsHost=" +
                (strong.getClassLoader() ==
                        StrongHiddenDemo.class.getClassLoader()));
        System.out.println("threeDifferent=" +
                (weak != strong && strong != normal && weak != normal));

        MethodHandle constructor = strongHidden.findConstructor(
                strong, MethodType.methodType(void.class));
        IntUnaryOperator task =
                (IntUnaryOperator) constructor.invoke();
        System.out.println("result=" + task.applyAsInt(21));

        try {
            Class.forName(strong.getName());
            System.out.println("strongFindableByName=true");
        } catch (ClassNotFoundException expected) {
            System.out.println("strongFindableByName=false");
        }
    }
}
~~~

Chạy bằng một JDK hiện đại hỗ trợ biên dịch Java 15:

~~~bash
javac --release 15 StrongHiddenDemo.java
java StrongHiddenDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
weakHidden=true
strongHidden=true
sameLoader=true
loaderIsHost=true
threeDifferent=true
result=43
strongFindableByName=false
~~~

### 4.1. Giải thích từng kết quả

**`weakHidden=true` và `strongHidden=true`**: cả hai định nghĩa đều là hidden class. `STRONG` **không biến class thành class thường**, chỉ thay đổi quan hệ vòng đời với loader.

**`sameLoader=true` và `loaderIsHost=true`**: hai hidden class và host được đánh dấu có cùng class loader trong ví dụ. Điều này **không** có nghĩa hai class có chế độ unload giống nhau. Sự khác biệt nằm trong **option khi định nghĩa**, không nằm ở kết quả `getClassLoader()`.

**`threeDifferent=true`**: `Task.class` có tên do `javac` tạo, còn hai lần `defineHiddenClass` tạo ra hai định nghĩa riêng. Chúng không phải cùng `Class<?>` dù bytes nguồn giống nhau. Nếu muốn tái sử dụng một generated class, phải cache factory/handle/class phù hợp, không gọi define lại rồi chờ JVM tự gộp lớp.

**`result=43`**: returned `Lookup` của hidden class có thể tìm constructor và tạo instance. Instance được gọi qua interface `IntUnaryOperator` mà code bên ngoài đã biết, không cần tham chiếu trực tiếp đến tên riêng của hidden class.

**`strongFindableByName=false`**: ngay cả khi dùng `STRONG`, `Class.forName(strong.getName())` vẫn không tìm được hidden class theo tên. `STRONG` không làm cho hidden class có một binary name thông thường.

**Điều ví dụ này không và không thể chứng minh bằng stdout cố định:** thời điểm class được garbage collector unload. Chương trình giữ nhiều tham chiếu mạnh (`Class<?>`, `Lookup`, method handle, instance) tới class trong lúc chạy và kết thúc nhanh. Nó chứng minh **cách tạo, danh tính, loader và việc gọi class**, chứ không đo vòng đời bằng GC.

## 5. Chọn mặc định hay `STRONG` theo nhu cầu runtime

### 5.1. Mặc định: phù hợp generated class ngắn hạn

Khi mỗi request hoặc biểu thức có thể sinh một implementation mới và class ấy không cần sống lâu bằng defining loader, mặc định **không truyền `STRONG`** thường phù hợp hơn.

Ví dụ một engine động sinh nhiều adapter cho các biểu thức tạm thời:

~~~java
MethodHandles.Lookup temporary =
        host.defineHiddenClass(classfileBytes, true);
Class<?> generated = temporary.lookupClass();
~~~

Đây là **đoạn mã minh họa** với `host` và `classfileBytes` đã hợp lệ. Lớp mới không có strong relationship với loader được đánh dấu, cho phép JVM xem xét unload ngay cả khi loader còn sống, nếu không còn tham chiếu giữ class.

Tuy nhiên, nếu framework đưa mọi `Class<?>` hoặc `MethodHandle` vào một `static Map` không giới hạn, chúng vẫn có thể bị giữ lại. **Không có `STRONG` không đồng nghĩa tự động hết memory leak.**

### 5.2. `STRONG`: khi cần cùng vòng đời với defining loader

Trong một số runtime, generated class là một phần lâu dài của một component hoặc framework host:

- Nó thực hiện một adapter dùng trong suốt vòng đời của một plugin loader;
- Nó có tính trạng thái/hợp đồng yêu cầu tồn tại khi loader còn tồn tại;
- Runtime chủ động muốn hidden class **cùng vòng đời với một nhóm class thông thường** có chung loader;
- Framework có hệ thống quản lý số lượng generated classes và chấp nhận chi phí metadata trong vòng đời loader.

Khi ấy:

~~~java
MethodHandles.Lookup stable = host.defineHiddenClass(
        classfileBytes,
        true,
        MethodHandles.Lookup.ClassOption.STRONG);
~~~

là quyết định có cơ sở. Javadoc mô tả `STRONG` cho các trường hợp hidden class cần **coterminous** (cùng vòng đời) với class/nhóm class thông thường dưới cùng defining loader.

**Chú ý:** `STRONG` không phải lựa chọn “ổn định hơn nên luôn bật”. Với application class loader tồn tại suốt tiến trình, mỗi hidden class strong có thể tiếp tục giữ class metadata cho đến khi tiến trình hoặc loader phù hợp thực sự không còn. Nếu số class sinh tăng không giới hạn, memory pressure có thể tăng dù object instance của chúng đã được GC.

### 5.3. Quy tắc lựa chọn nhanh

| Câu hỏi thiết kế | Hướng lựa chọn |
| --- | --- |
| Generated class là triển khai tạm thời cho biểu thức/request? | Cân nhắc mặc định **không `STRONG`** |
| Cần class được giữ lâu bằng một plugin/component loader? | Cân nhắc **`STRONG`**, có kế hoạch dỡ loader |
| Chỉ cần gọi một functional interface từ code nghiệp vụ? | Có thể không cần tự sinh hidden class; dùng lambda/class thường |
| Mỗi request đều định nghĩa class mới mà không tái sử dụng? | Xem lại cache/factory trước khi chọn `STRONG` |
| Muốn class có tên và tìm lại bằng `Class.forName`? | Hidden class, dù `STRONG`, **không phù hợp** |
| Muốn hidden class có quyền private của host? | Xem `NESTMATE` và quyền `Lookup`; `STRONG` không quyết định |
| Muốn đảm bảo “GC phải unload sau N ms”? | **Không thể** đảm bảo bằng các tùy chọn này |

## 6. Quan hệ strong/weak và tham chiếu ở runtime

### 6.1. Vì sao vẫn không unload nếu đã bỏ biến local?

Một hidden class mặc định có thể tiếp tục sống nếu các thực thể runtime giữ nó reachable:

- Một biến `Class<?>`, `MethodHandles.Lookup` hoặc `MethodHandle` có liên hệ tới class;
- Instance của hidden class hoặc callback vẫn được sử dụng;
- Cache của framework còn giữ constructor, factory, lambda hoặc metadata có tham chiếu tới class;
- Thread, task hoặc cấu trúc dữ liệu đang thực thi/giữ code thuộc class;
- Các tham chiếu mạnh khác làm hidden class vẫn reachable.

Ví dụ framework giữ một `MethodHandle` trong cache để tái sử dụng thì đó chính là **mục đích tồn tại hợp lệ** của class, không nhất thiết là lỗi. Vấn đề xảy ra khi cache không giới hạn và các entry không còn cần nhưng vẫn không được bỏ.

### 6.2. `STRONG` khác `java.lang.ref.WeakReference`

`ClassOption.STRONG` mô tả quan hệ giữa **hidden class và defining class loader**. Trong khi đó, `WeakReference<T>` là một loại tham chiếu Java dùng ở tầng object. Chúng cùng liên quan đến reachability, nhưng **không phải hai tùy chọn đối lập cùng API**.

Ngay cả nếu code giữ:

~~~java
java.lang.ref.WeakReference<Class<?>> ref =
        new java.lang.ref.WeakReference<>(generatedType);
~~~

trong đó `generatedType` là `Class<?>` của một hidden class, điều đó **không tự vô hiệu hóa quan hệ strong với loader** do `ClassOption.STRONG` tạo ra. Ngược lại, hidden class mặc định vẫn có thể được giữ bởi một tham chiếu mạnh ở nơi khác. Đây là **đoạn minh họa, không có output cố định**.

### 6.3. “Loader không còn reachable” là điều kiện, không phải sự kiện bắt buộc

Đối với hidden class có `STRONG`, điều kiện đủ tư cách unload phụ thuộc vào defining loader có thể được GC thu hồi. Nếu loader còn sống, class chưa đủ điều kiện unload **chỉ vì hết instance**. Khi loader không còn reachable, các class liên quan *có thể* được unload nhưng JVM không buộc phải làm việc ấy ngay tức thì.

Vì tham chiếu tới `Class<?>` cũng liên quan đến class loader của class đó, chỉ đặt một biến loader thành `null` trong khi còn giữ `Class<?>`/instance chưa đủ để nói loader đã hết reachable.

**Không nên viết unit test yêu cầu**:

~~~java
System.gc();
// Không có bảo đảm rằng class đã bị unload tại dòng này!
~~~

`System.gc()` chỉ là một yêu cầu/hint tới JVM; phụ thuộc collector, cấu hình và tình trạng reachability. Test có thể chạy “đúng” ở máy này và thất bại ở máy khác nếu giả định unload tức thì.

## 7. `STRONG` và `NESTMATE` là hai mục đích độc lập

`MethodHandles.Lookup.ClassOption` có các option thường gặp sau:

| Option | Mục tiêu |
| --- | --- |
| `STRONG` | Quan hệ vòng đời **mạnh với defining loader** |
| `NESTMATE` | Thêm hidden class vào **nest của lookup class**, liên quan quyền truy cập private giữa nestmates |
| Không option | Hidden class mặc định, không tự động chọn hai đặc tính trên |

Hai option có thể được truyền **cùng lúc** dưới dạng varargs, vì chúng điều khiển **hai khía cạnh độc lập**. Không dùng `STRONG` để “sửa” `IllegalAccessException` do thiếu quyền private; đó là vấn đề ngữ cảnh `Lookup`, nest, package và module.

### 7.1. Ví dụ Java 15+: kết hợp `STRONG` với `NESTMATE`

Lưu vào **`StrongNestmateDemo.java`**:

~~~java
import java.io.InputStream;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.function.Supplier;

public class StrongNestmateDemo {
    private static String secret() {
        return "nestmate-ok";
    }

    public static class Worker implements Supplier<String> {
        public Worker() {}

        @Override
        public String get() {
            return secret();
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] bytes;
        try (InputStream in = StrongNestmateDemo.class
                .getResourceAsStream(
                        "StrongNestmateDemo$Worker.class")) {
            if (in == null) {
                throw new IllegalStateException("Missing class bytes");
            }
            bytes = in.readAllBytes();
        }

        MethodHandles.Lookup hiddenLookup =
                MethodHandles.lookup().defineHiddenClass(
                        bytes,
                        true,
                        MethodHandles.Lookup.ClassOption.NESTMATE,
                        MethodHandles.Lookup.ClassOption.STRONG);

        Class<?> hidden = hiddenLookup.lookupClass();
        Supplier<?> action = (Supplier<?>) hiddenLookup
                .findConstructor(hidden,
                        MethodType.methodType(void.class))
                .invoke();

        System.out.println("hidden=" + hidden.isHidden());
        System.out.println("sameNestHost=" +
                (hidden.getNestHost() == StrongNestmateDemo.class));
        System.out.println("message=" + action.get());
    }
}
~~~

~~~bash
javac --release 15 StrongNestmateDemo.java
java StrongNestmateDemo
~~~

**Stdout đã kiểm chứng:**

~~~text
hidden=true
sameNestHost=true
message=nestmate-ok
~~~

Giải thích: `NESTMATE` cho phép lớp ẩn tham gia nest của `StrongNestmateDemo` và gọi private method `secret()`; `STRONG` đồng thời thiết lập quan hệ mạnh với loader. `hidden=true` xác nhận đây **vẫn là hidden class**, không biến thành named class. Kết quả ví dụ chứng minh **sự kết hợp hợp lệ của hai option**, không thể trực tiếp quan sát GC/unload.

## 8. Class loader, quyền định nghĩa và danh tính lớp

### 8.1. Defining loader được đánh dấu, không phải tên để tải lại

Cả hidden class mặc định và có `STRONG` đều có loader được JVM đánh dấu là defining loader. Trong ví dụ `StrongHiddenDemo`, cả hai trả cùng giá trị từ `getClassLoader()`. Nhưng hidden class vẫn **không được tìm lại bằng tên** từ loader ấy.

Do đó:

~~~java
Class<?> hidden = returnedLookup.lookupClass();
System.out.println(hidden.isHidden()); // true
~~~

là cách kiểm tra trực tiếp khi có returned `Lookup`. **Đừng** dùng `Class.forName(hidden.getName())` hoặc `loader.loadClass(hidden.getName())` như cơ chế truy xuất lại; `ClassOption.STRONG` không thay đổi quy tắc này.

### 8.2. Tạo lớp ẩn yêu cầu Lookup phù hợp

`defineHiddenClass(...)` yêu cầu `Lookup` có đủ quyền và bytecode đúng package/module theo hợp đồng API. `ClassOption.STRONG` không mở thêm phạm vi quyền cho phép tạo lớp, và cũng không khiến bytecode chưa đáng tin trở nên an toàn.

Những lỗi cần xử lý đúng nguyên nhân bao gồm:

- Lookup thiếu full privilege → `IllegalAccessException`;
- Classfile sai package so với lookup → `IllegalArgumentException`;
- Bytecode lỗi hoặc không hợp lệ → lỗi class format/verification;
- Classfile có phiên bản cao hơn JVM → `UnsupportedClassVersionError`;
- Class đã được định nghĩa nhưng method/constructor cần tìm không có hoặc không đủ quyền → lỗi method-handle lookup phù hợp.

Hidden class **không phải sandbox**. Không thực thi bytes chưa tin cậy chỉ vì class không thể tra bằng tên. Tài nguyên, IO và hiệu ứng của bytecode vẫn cần được quản lý như mã Java khác.

### 8.3. Tùy chọn lúc định nghĩa không phải đặc tính có thể suy luận từ `isHidden()`

`Class.isHidden()` có thể phân biệt hidden với non-hidden class, nhưng **không phân biệt** hidden class được định nghĩa có `STRONG` hay không. Nếu framework cần ghi nhận lựa chọn vòng đời, hãy lưu **metadata của chính framework** về options lúc tạo, không suy ra qua `isHidden()` hoặc `getClassLoader()`.

## 9. Tác động lên metadata và quản lý tài nguyên

Một hệ thống tạo class ở runtime sử dụng nhiều loại tài nguyên:

- **Heap:** instance của class, đối tượng `Class<?>`, cache, factory, dữ liệu đầu vào;
- **Class metadata / metaspace:** cấu trúc và thông tin JVM cần để biểu diễn class đã được định nghĩa;
- **Code cache và tài nguyên biên dịch/JIT:** có thể liên quan khi phương thức được thực thi nhiều lần.

Việc garbage collector thu hồi **instance** không tự chứng minh metadata của **class** đã unload. Nếu loader còn sống và nhiều hidden class được đánh dấu `STRONG`, class metadata có thể tồn tại lâu ngay cả khi không còn instance thực tế.

### 9.1. Các nguyên tắc vận hành

1. **Giảm số class phải sinh:** nếu cùng cấu hình/biểu thức có thể tái sử dụng factory, đừng định nghĩa một hidden class mới mỗi lần gọi.
2. **Giới hạn cache:** quy định size, TTL hoặc scope của key và làm rõ việc bỏ entry có thể giải phóng tham chiếu nào.
3. **Chọn option có chủ đích:** giữ mặc định cho class ngắn hạn; chỉ dùng `STRONG` nếu thật sự cần co-lifetime với loader.
4. **Có chiến lược unload custom class loader:** khi hệ thống có plugin/module loader, dỡ loader phải đi kèm đóng task, thread, callback và cache liên quan.
5. **Theo dõi class loading/unloading và metaspace:** phát hiện xu hướng tăng liên tục trong bài stress test, không chỉ xem dung lượng heap.
6. **Không biến GC timing thành business logic:** class unloading là hoạt động của JVM, không phải thao tác đồng bộ do chương trình chủ động gọi.

### 9.2. Quan sát bằng Unified Logging

Trên các JVM HotSpot hiện đại, có thể bật log để **quan sát**, ví dụ:

~~~bash
java -Xlog:class+load=info,class+unload=info StrongHiddenDemo
~~~

Điều kiện: đã biên dịch `StrongHiddenDemo.class` và file nested class cùng thư mục/classpath; lệnh trên dùng classpath hiện tại. Log có thể rất nhiều dòng do JVM cũng tải các class thư viện. **Không xuất hiện log unload trong chương trình ngắn không chứng minh cấu hình sai**: chưa chắc có GC hoặc có class đủ điều kiện unload trong khoảng quan sát.

Đối với thí nghiệm đúng nghĩa, cần tạo workload sinh nhiều class, loại bỏ tham chiếu ứng dụng theo thiết kế rồi quan sát hoạt động trong điều kiện tải gần thực tế. Dùng tooling/profiler của JDK và số liệu class/metaspace để đánh giá; luôn ghi rõ phiên bản JDK, collector, phạm vi đo và điều kiện tham chiếu. Không dựng giả thuyết “đếm được đúng N class unload ngay sau `System.gc()`”.

## 10. Những nhầm lẫn phổ biến

**Nhầm lẫn 1: “`STRONG` = class không bao giờ unload.”**  
Sai. Nó gắn hidden class với defining loader giống class thường. Khi loader không còn reachable và có thể bị thu hồi, class *có thể* unload theo quyết định JVM.

**Nhầm lẫn 2: “Không truyền `STRONG` thì hidden class chắc chắn unload khi method kết thúc.”**  
Sai. Nó chỉ cho phép unload độc lập với loader nếu các điều kiện reachability phù hợp. Lookup, Class, instance hoặc MethodHandle còn sống có thể giữ class.

**Nhầm lẫn 3: “Hai hidden class có cùng `getClassLoader()` thì có cùng vòng đời.”**  
Sai. Ví dụ đã chứng minh cùng loader, nhưng một class dùng mặc định và một class dùng `STRONG`.

**Nhầm lẫn 4: “`STRONG` làm hidden class thành named class.”**  
Sai. `isHidden()` vẫn true và `Class.forName(strong.getName())` không tìm lại được.

**Nhầm lẫn 5: “`STRONG` tăng quyền private giống `NESTMATE`.”**  
Sai. `STRONG` quản lý vòng đời; `NESTMATE` liên quan quan hệ nest và quyền truy cập private.

**Nhầm lẫn 6: “`STRONG` giữ mọi instance sống.”**  
Sai. GC có thể thu hồi instance không reachable; việc class metadata còn được giữ không có nghĩa object instance nào cũng được giữ.

**Nhầm lẫn 7: “Không còn instance thì cũng không còn class metadata.”**  
Sai. Metadata thuộc vòng đời định nghĩa class; class có thể còn sống lâu hơn mọi instance.

**Nhầm lẫn 8: “Mặc định weak có nghĩa phải dùng `WeakReference<Class<?>>`.”**  
Sai. Quan hệ weak của hidden class với loader là cơ chế JVM. `WeakReference` là một API tham chiếu object khác, không phải yêu cầu để định nghĩa hidden class mặc định.

**Nhầm lẫn 9: “`System.gc()` là phép thử chắc chắn unload.”**  
Sai. Nó không đảm bảo collector thực thi/unload ngay. Đừng viết assert dựa vào thời gian cụ thể.

**Nhầm lẫn 10: “Cứ có nhiều generated class thì bật `STRONG` để an toàn.”**  
Không phải lúc nào cũng đúng: nếu loader sống lâu, strong relationship có thể làm tồn tại nhiều class metadata không còn hữu ích. Cần thiết kế vòng đời, giới hạn cache và đo đạc.

**Nhầm lẫn 11: “Chỉ cần đổi classfile hoặc loader là `STRONG` cấp quyền định nghĩa.”**  
Không. Quyền của `Lookup`, package và module vẫn được kiểm tra. Option không phải cơ chế bỏ qua an toàn JVM.

## 11. Checklist khi review một runtime sinh hidden class

- [ ] Đã xác định **vòng đời mong muốn** của từng generated class.
- [ ] Đã kiểm tra nó cần sống bằng defining loader hay có thể unload sớm.
- [ ] Khi dùng `STRONG`, có lý do cụ thể và kiểm soát số lượng class định nghĩa.
- [ ] Khi không dùng `STRONG`, vẫn quản lý cache/instance/handles để tránh retention vô tình.
- [ ] Không dùng `Class.forName` để tìm hidden class theo tên.
- [ ] Hợp đồng bên ngoài dùng interface/superclass/MethodHandle ổn định.
- [ ] Classfile bytes được sinh/đọc từ nguồn đáng tin, đúng package và phiên bản JVM.
- [ ] `MethodHandles.Lookup` đủ quyền để định nghĩa, không trao Lookup đặc quyền bừa bãi.
- [ ] `NESTMATE` chỉ được dùng khi có nhu cầu thực sự về nest access, độc lập với `STRONG`.
- [ ] Có bài thử tải đo số class, metaspace, khả năng unload; không assert thời điểm GC chính xác.
- [ ] Nếu có custom plugin loader, đã xem xét task/thread/callback/cache ngăn loader hết reachable.
- [ ] Kiểm thử trên JDK đích; các API của Java 15 vẫn còn được hỗ trợ.

## 12. Bài tập tự kiểm tra

**Câu 1.** Hidden class mặc định có thể unload khi loader còn reachable không?  
**Đáp án:** Có thể, nếu không còn tham chiếu giữ class và JVM quyết định unload. Không bảo đảm xảy ra ngay.

**Câu 2.** Với `ClassOption.STRONG`, hidden class có chắc chắn tồn tại vĩnh viễn không?  
**Đáp án:** Không. Nó có quan hệ mạnh với defining loader, nên chỉ đủ điều kiện unload khi loader có thể được thu hồi, tùy GC/JVM.

**Câu 3.** Hai class do `defineHiddenClass` tạo với cùng bytes, một mặc định và một `STRONG`, có cùng `Class<?>` không?  
**Đáp án:** Không. Mỗi lần định nghĩa là một class mới. Cùng bytes và loader không đồng nghĩa cùng kiểu.

**Câu 4.** `strongType.isHidden()` trả gì?  
**Đáp án:** `true`. `STRONG` không làm hidden class có tên thông thường.

**Câu 5.** Một app giữ hàng nghìn `STRONG` hidden class dưới application loader sống lâu, có rủi ro gì?  
**Đáp án:** Class metadata/metaspace có thể tích tụ dù instance đã được thu hồi. Phải giới hạn số class và kiểm soát vòng đời loader/cache.

**Câu 6.** `STRONG` có thể thay thế `NESTMATE` khi generated code cần gọi private method của host không?  
**Đáp án:** Không. Hai option có mục đích khác nhau; `NESTMATE` liên quan quan hệ truy cập trong nest.

**Câu 7.** Nếu `System.gc()` xong mà không thấy log unload của hidden class mặc định, có thể kết luận class không bao giờ unload không?  
**Đáp án:** Không. GC timing không được bảo đảm, và có thể còn tham chiếu sống.

**Câu 8.** Trong ví dụ, `sameLoader=true` có đủ để biết class nào có `STRONG` không?  
**Đáp án:** Không. Phải biết option được sử dụng lúc `defineHiddenClass(...)`, hoặc metadata do framework ghi nhận.

**Câu 9.** Nếu muốn gọi class sinh động từ code bên ngoài, có nên phụ thuộc `strongClass.getName()` không?  
**Đáp án:** Không. Nên dùng interface hoặc factory/MethodHandle đã biết. Hidden class không được tìm lại theo tên thông thường.

## 13. Tài liệu chính thức còn hiệu lực

- [OpenJDK JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): mục tiêu lớp ẩn và lựa chọn vòng đời.
- [Java SE 26 — `MethodHandles.Lookup.ClassOption`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): định nghĩa `STRONG`, `NESTMATE` và tác động lên defining loader; `Since: 15`.
- [Java SE 26 — `MethodHandles.Lookup.defineHiddenClass(...)`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): hợp đồng định nghĩa class ẩn, lookup trả về, loader, điều kiện quyền và tính ẩn.
- [Java SE 15 — `MethodHandles.Lookup.ClassOption`](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): đối chiếu tính năng xuất hiện từ Java 15.
- [Java SE 26 JLS `12.7 — Unloading of Classes and Interfaces](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-12.html#jls-12.7): quy tắc và tính không bảo đảm về thời điểm unloading của các class thông thường.
