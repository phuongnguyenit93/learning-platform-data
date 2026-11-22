# Java 15 — Lớp ẩn và mục tiêu hỗ trợ mã sinh ở runtime

## 1. Hidden Class là gì, dùng để giải quyết vấn đề nào?

**Hidden Class** (*lớp ẩn*) là một lớp hoặc giao diện Java được JVM định nghĩa từ bytecode lúc chương trình đang chạy nhưng **không có tên nhị phân thông thường để chương trình khác tìm và liên kết đến nó bằng tên**. Tính năng được chuẩn hóa trong **Java 15, JEP 371** và API vẫn được hỗ trợ ở các JDK hiện đại.

Mục tiêu chính là hỗ trợ các thư viện, framework và runtime **sinh mã theo nhu cầu**: những lớp chỉ phục vụ một lời gọi, một biểu thức, một proxy hoặc một đoạn thực thi nội bộ. Ví dụ điển hình là runtime triển khai lambda hay thư viện sinh bộ chuyển đổi lời gọi. Ứng dụng nghiệp vụ bình thường thường **sử dụng framework đã có** thay vì tự viết bytecode.

Hãy hình dung một hệ thống cần chuyển yêu cầu ở runtime thành mã có thể thực thi:

~~~text
Cấu hình / biểu thức / lệnh gọi runtime
              |
              v
       Sinh bytecode .class
              |
              v
MethodHandles.Lookup.defineHiddenClass(...)
              |
              v
  Lookup / Class<?> của lớp ẩn
              |
              v
Tạo instance / MethodHandle / adapter qua interface
              |
              v
      Thực thi và quản lý vòng đời
~~~

Phần **sinh bytecode** có thể do một công cụ tạo classfile hoặc framework chuyên trách thực hiện. `defineHiddenClass(...)` nhận các byte đã có và **định nghĩa lớp trong JVM**; bản thân nó **không phải trình biên dịch Java source thành bytecode**.

### 1.1. Vì sao không dùng lớp Java có tên cho mọi lần sinh mã?

Một framework có thể cần hàng nghìn triển khai ngắn hạn khác nhau, chẳng hạn mỗi phương thức động hoặc cấu hình được biên dịch thành một lớp mới. Nếu mọi lớp đều là lớp **có tên thông thường**, chúng tham gia không gian tên và các quy tắc liên kết của class loader. Việc đặt tên, tránh xung đột, quản lý phụ thuộc và vòng đời có thể trở nên phức tạp; loại lớp đó cũng thường gắn vòng đời với class loader.

Hidden Class giải quyết ba nhu cầu quan trọng:

1. **Không cần một tên nhị phân để các lớp khác tham chiếu trực tiếp.** Mã sử dụng lớp ẩn qua đối tượng `Class<?>`, `MethodHandle` hoặc một **interface/superclass đã biết**.
2. **Có thể có vòng đời ngắn hơn class loader.** Mặc định một lớp ẩn đủ điều kiện được unload khi không còn được giữ tham chiếu, ngay cả khi class loader còn sống. Đây là **khả năng**, không phải cam kết GC sẽ unload ngay.
3. **Vẫn sử dụng cơ chế JVM chuẩn** để kiểm tra bytecode, liên kết, khởi tạo và thực thi; framework không phải tự tạo một ngôn ngữ thực thi khác chỉ để chạy mã sinh.

Hidden Class là một công cụ cho **runtime implementer**, không phải cách thay thế mọi `class`/`interface` viết sẵn trong dự án.

## 2. Những thuộc tính cốt lõi của lớp ẩn

| Thuộc tính | Hidden Class | Ý nghĩa trong hệ thống sinh mã |
| --- | --- | --- |
| Được tạo từ classfile bytes | Có | Framework cần tạo hoặc lấy được bytecode hợp lệ |
| Có đối tượng `Class<?>` | Có | Vẫn có thể reflection, xây `MethodHandle`, kiểm tra kiểu |
| `Class.isHidden()` | `true` | Xác định rõ loại lớp ở runtime |
| Có tên nhị phân có thể tra bằng `Class.forName` | **Không** | Không thiết kế API dựa trên việc tìm lại lớp ẩn theo tên |
| Có thể implement interface đã biết | Có | Trả về `Runnable`, `Function` hoặc hợp đồng khác cho code nghiệp vụ |
| Có thể dùng `instanceof` với interface đã biết | Có | Lớp ẩn vẫn là một kiểu Java có kiểm tra kiểu |
| Có thể unload khi loader vẫn còn sống | Mặc định có thể | Phù hợp mã ngắn hạn; còn phụ thuộc tham chiếu và JVM |
| Là sandbox hoặc cơ chế giấu dữ liệu bí mật | **Không** | Bytecode vẫn chạy với quyền JVM thông thường |

**Tên hiển thị khác tên nhị phân.** `Class.getName()` của lớp ẩn có thể trả chuỗi chứa phần hậu tố riêng do JVM tạo, thường có dấu `/`. Chuỗi đó hữu ích cho chẩn đoán nhưng **không phải tên nhị phân** để gọi `Class.forName(...)` hoặc `ClassLoader.loadClass(...)`. Không đưa phần hậu tố động vào logic nghiệp vụ hay test yêu cầu khớp chuỗi tuyệt đối.

**Lớp ẩn là một kiểu thực sự.** Nó vẫn có constructor, method, field và superclass; nó có thể triển khai interface, và Java reflection / Method Handles vẫn có thể làm việc khi người gọi giữ được đối tượng `Class<?>` hoặc `Lookup`. Từ “ẩn” nói về **khả năng truy xuất bằng tên/linking**, không phải bảo vệ source, mã hóa classfile hoặc cô lập mã nguy hiểm.

### 2.1. Hai lần định nghĩa cùng bytecode vẫn tạo hai kiểu

Khi gọi `defineHiddenClass(bytes, ...)` hai lần trên cùng mảng byte hợp lệ, kết quả là **hai định nghĩa lớp khác nhau**. `Class<?>` thứ nhất và thứ hai không đồng nhất; static state, kiểm tra kiểu cụ thể và các instance tương ứng có thể thuộc hai class riêng. Điều này hữu ích khi tạo nhiều triển khai độc lập nhưng cũng là lý do không nên sinh lớp mới vô hạn nếu một triển khai có thể được tái sử dụng.

## 3. API trung tâm: `MethodHandles.Lookup.defineHiddenClass`

Từ Java 15, lời gọi chính là:

~~~java
MethodHandles.Lookup hiddenLookup =
        MethodHandles.lookup()
                .defineHiddenClass(classFileBytes, true);

Class<?> hiddenType = hiddenLookup.lookupClass();
boolean hidden = hiddenType.isHidden();
~~~

**Đây chỉ là đoạn mã đặt trong phương thức**: biến `classFileBytes` phải là `byte[]` chứa một file `.class` hợp lệ và phù hợp với package của lookup. Các phần liên quan:

- `MethodHandles.lookup()` tạo một `Lookup` có ngữ cảnh quyền truy cập của **class đang gọi**.
- `defineHiddenClass(byte[] bytes, boolean initialize, ClassOption... options)` định nghĩa và liên kết một lớp ẩn; trả về một **Lookup mới** có lookup class chính là lớp ẩn ấy.
- `hiddenLookup.lookupClass()` lấy đối tượng `Class<?>` của lớp vừa tạo.
- `initialize == true` yêu cầu khởi tạo class ngay trong quá trình định nghĩa; `false` trì hoãn khởi tạo cho đến khi điều kiện khởi tạo Java thông thường xảy ra.
- `Class.isHidden()` là phép kiểm tra có thể dùng trong code/test, tốt hơn việc suy diễn từ chuỗi tên.

Khi định nghĩa lớp ẩn, API áp dụng những ràng buộc quan trọng: `Lookup` phải có **full privilege access** cần thiết; classfile phải hợp lệ và có phiên bản được JVM hỗ trợ; class trong mảng byte phải cùng **package** với lookup class. Đây là điều kiện kiểm soát quyền và ngữ cảnh runtime, nên không thể dùng một `publicLookup()` bất kỳ để định nghĩa lớp ẩn trong package tùy ý.

Nếu vi phạm, lỗi có thể là `IllegalAccessException` (lookup thiếu quyền), `IllegalArgumentException` (sai package), `ClassFormatError` (bytecode không hợp lệ), `UnsupportedClassVersionError` (classfile mới hơn JVM hỗ trợ) hoặc lỗi verification/linking. Xử lý lỗi theo nguồn dữ liệu, quyền và phiên bản thật, không bỏ qua bằng cách tắt kiểm tra.

## 4. Ví dụ độc lập Java 15+: tạo Hidden Class từ bytecode đã biên dịch

Để quan sát `defineHiddenClass` mà không phải tự viết một bộ sinh bytecode, ví dụ đầu tiên **lấy bytes của một nested class do `javac` biên dịch**. Đây là một mô phỏng có chủ đích: ở framework thực, `classFile` thường là kết quả của trình sinh bytecode ở runtime.

Lưu tệp **`HiddenClassDemo.java`**:

~~~java
import java.io.InputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.function.IntUnaryOperator;

public class HiddenClassDemo {
    public static class GeneratedTask implements IntUnaryOperator {
        public GeneratedTask() {}

        @Override
        public int applyAsInt(int value) {
            return value * 2 + 1;
        }
    }

    public static void main(String[] args) throws Throwable {
        byte[] classFile;
        try (InputStream in = HiddenClassDemo.class
                .getResourceAsStream("HiddenClassDemo$GeneratedTask.class")) {
            if (in == null) {
                throw new IllegalStateException(
                        "Missing compiled class resource");
            }
            classFile = in.readAllBytes();
        }

        MethodHandles.Lookup host = MethodHandles.lookup();
        MethodHandles.Lookup firstLookup =
                host.defineHiddenClass(classFile, true);
        Class<?> first = firstLookup.lookupClass();
        Class<?> second = host.defineHiddenClass(classFile, true)
                .lookupClass();

        MethodHandle constructor = firstLookup.findConstructor(
                first, MethodType.methodType(void.class));
        IntUnaryOperator task = (IntUnaryOperator) constructor.invoke();

        System.out.println("hidden=" + first.isHidden());
        System.out.println("sameAsNamed=" +
                (first == GeneratedTask.class));
        System.out.println("differentDefinitions=" + (first != second));
        System.out.println("apply(21)=" + task.applyAsInt(21));

        try {
            Class.forName(first.getName());
            System.out.println("discoverable=true");
        } catch (ClassNotFoundException expected) {
            System.out.println("discoverable=false");
        }
    }
}
~~~

Biên dịch và chạy **từ thư mục chứa tệp nguồn**:

~~~bash
javac --release 15 HiddenClassDemo.java
java HiddenClassDemo
~~~

Kết quả stdout chính xác:

~~~text
hidden=true
sameAsNamed=false
differentDefinitions=true
apply(21)=43
discoverable=false
~~~

Giải thích:

1. `javac` sinh ra `HiddenClassDemo.class` và `HiddenClassDemo$GeneratedTask.class`. Dòng `getResourceAsStream` đọc byte của class thứ hai ở cùng package/runtime classpath; `try-with-resources` đóng stream sau khi đọc.
2. `defineHiddenClass(classFile, true)` được gọi **hai lần** để tạo hai định nghĩa hidden class riêng từ cùng dữ liệu. `first.isHidden()` trả `true` và `first != second`.
3. `GeneratedTask.class` là class **có tên** do `javac` sinh, còn `first` là **một class khác** do JVM định nghĩa từ bytes đó, nên `sameAsNamed=false`.
4. `firstLookup.findConstructor(...)` tạo `MethodHandle` cho constructor không tham số. Gọi handle tạo instance, ép qua interface **`IntUnaryOperator`** đã biết rồi dùng `applyAsInt`. Đây là kiểu kết nối phù hợp giữa runtime-generated code và code nghiệp vụ.
5. `Class.forName(first.getName())` thất bại vì lớp ẩn **không được tra theo tên** như class bình thường. Trong thực tế, phải giữ `firstLookup`, `Class<?>`, `MethodHandle` hoặc instance/interface cần dùng.

Ví dụ có dùng tên `GeneratedTask` **chỉ để chuẩn bị sẵn classfile**; bản thân `defineHiddenClass` không đọc Java source và không tự viết code. Nếu thay nguồn bytes bằng output từ một bytecode generator, phần API định nghĩa lớp vẫn cùng ý nghĩa.

### 4.1. Vì sao chọn một interface có sẵn?

Code phía ngoài biết hợp đồng `IntUnaryOperator` và có thể gọi `task.applyAsInt(21)` mà không cần biết tên cụ thể của lớp được sinh. Cách làm tương tự với `Runnable`, `Supplier<T>` hoặc interface riêng cho framework.

Không nên để code nghiệp vụ phụ thuộc vào chuỗi tên của class sinh ra; nếu cần registry để tái sử dụng, dùng một **khóa ổn định cho biểu thức/cấu hình**, ánh xạ sang đối tượng factory/`MethodHandle`/instance phù hợp. Không dùng tên lớp ẩn động như ID nghiệp vụ.

## 5. Khởi tạo lớp: tham số `initialize` có ý nghĩa gì?

**Định nghĩa và liên kết** một class không đồng nghĩa với việc chạy ngay static initializer `<clinit>`. Boolean `initialize` trong `defineHiddenClass` giúp thư viện chọn thời điểm khởi tạo:

- `true`: JVM khởi tạo class trong thao tác định nghĩa, nên static initializer có thể chạy **trước** khi `defineHiddenClass(...)` trả về.
- `false`: định nghĩa lớp nhưng **chưa bắt buộc khởi tạo**; khi dùng class theo quy tắc Java (ví dụ tạo instance), JVM sẽ khởi tạo nếu cần.

Lưu **`HiddenInitializationDemo.java`** để thấy sự khác biệt. Ví dụ chọn `false`:

~~~java
import java.io.InputStream;
import java.lang.invoke.MethodHandles;

public class HiddenInitializationDemo {
    public static class Action implements Runnable {
        static {
            System.out.println("hidden class initialized");
        }

        public Action() {}

        @Override
        public void run() {
            System.out.println("action executed");
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes;
        try (InputStream in = HiddenInitializationDemo.class
                .getResourceAsStream(
                        "HiddenInitializationDemo$Action.class")) {
            if (in == null) {
                throw new IllegalStateException("Missing class bytes");
            }
            bytes = in.readAllBytes();
        }

        var hiddenLookup = MethodHandles.lookup()
                .defineHiddenClass(bytes, false);

        System.out.println("hidden class defined");

        Runnable action = (Runnable) hiddenLookup.lookupClass()
                .getDeclaredConstructor()
                .newInstance();
        action.run();
    }
}
~~~

~~~bash
javac --release 15 HiddenInitializationDemo.java
java HiddenInitializationDemo
~~~

Kết quả:

~~~text
hidden class defined
hidden class initialized
action executed
~~~

Thông báo `hidden class defined` xuất hiện **trước** lời in từ static initializer vì class đã được định nghĩa nhưng chưa được khởi tạo. Việc tạo instance kích hoạt khởi tạo, sau đó `run()` được gọi. Nếu đổi tham số thành `true`, thứ tự hai thông báo đầu sẽ đảo lại. Cần nhớ **static initializer có thể có tác dụng phụ**; framework nên xác định thời điểm khởi tạo phù hợp thay vì mặc định mọi class mới đều vô hại.

## 6. Quyền truy cập nội bộ: tùy chọn `NESTMATE`

Trong hệ thống sinh mã, một adapter đôi khi cần gọi các thành viên `private` của lớp chủ quản, chẳng hạn triển khai lambda hoặc tối ưu gọi method. JVM có khái niệm **nest**: các class cùng một nest có thể truy cập private members của nhau theo quy tắc JVM.

Mặc định, một hidden class thuộc về nest riêng. Tham số:

~~~java
MethodHandles.Lookup.ClassOption.NESTMATE
~~~

cho phép hidden class được **thêm vào nest của lookup class**. Đây là quyền truy cập có chủ đích, không phải quyền “đọc mọi private trong JVM”.

Ví dụ độc lập **`HiddenNestmateDemo.java`**:

~~~java
import java.io.InputStream;
import java.lang.invoke.MethodHandles;
import java.util.function.Supplier;

public class HiddenNestmateDemo {
    private static String privateMessage() {
        return "private-access-ok";
    }

    public static class Reader implements Supplier<String> {
        public Reader() {}

        @Override
        public String get() {
            return privateMessage();
        }
    }

    public static void main(String[] args) throws Exception {
        byte[] bytes;
        try (InputStream in = HiddenNestmateDemo.class
                .getResourceAsStream(
                        "HiddenNestmateDemo$Reader.class")) {
            if (in == null) {
                throw new IllegalStateException("Missing class bytes");
            }
            bytes = in.readAllBytes();
        }

        Class<?> hidden = MethodHandles.lookup()
                .defineHiddenClass(bytes, true,
                        MethodHandles.Lookup.ClassOption.NESTMATE)
                .lookupClass();

        @SuppressWarnings("unchecked")
        Supplier<String> reader = (Supplier<String>) hidden
                .getDeclaredConstructor()
                .newInstance();

        System.out.println(reader.get());
        System.out.println("sameNestHost=" +
                (hidden.getNestHost() == HiddenNestmateDemo.class));
    }
}
~~~

~~~bash
javac --release 15 HiddenNestmateDemo.java
java HiddenNestmateDemo
~~~

Kết quả:

~~~text
private-access-ok
sameNestHost=true
~~~

Ở đây, bytes xuất phát từ nested class `Reader` có method gọi `privateMessage()`. Hidden class được định nghĩa với `NESTMATE` nên nó có thể truy cập `private` của nest host, và `getNestHost()` trỏ về `HiddenNestmateDemo.class`.

**Cảnh báo quan trọng:** `NESTMATE` làm quyền truy cập rộng hơn trong nest, vì vậy **không trao Lookup có đặc quyền cho plugin hoặc code chưa tin cậy**. Việc cho sinh class trong một package/module là quyết định về quyền. Không sử dụng `NESTMATE` chỉ để “cho code chạy được” khi không hiểu trust boundary.

## 7. Vòng đời class: mặc định và `ClassOption.STRONG`

Phần lớn ứng dụng Java có các lớp thông thường do class loader định nghĩa. Một class có tên thông thường có quan hệ **mạnh** với defining loader: chỉ khi loader phù hợp không còn reachable thì class mới có thể được unload.

Với hidden class, JVM cho phép quan hệ yếu hơn **theo mặc định**: hidden class có thể unload **dù class loader vẫn đang sống**, nếu không còn tham chiếu giữ class và các thực thể liên quan. Điều này giúp framework giảm tích tụ class metadata khi nhiều đoạn mã sinh có vòng đời ngắn.

| Cấu hình | Ý nghĩa vòng đời | Khi nên cân nhắc |
| --- | --- | --- |
| Không truyền `STRONG` | Hidden class **có thể** unload độc lập với class loader | Mã sinh ngắn hạn; muốn giảm nguy cơ giữ nhiều class tới khi loader bị thu hồi |
| Truyền `ClassOption.STRONG` | Hidden class có quan hệ mạnh với defining loader như class thường | Runtime cần lớp tồn tại suốt vòng đời loader hoặc có lý do thiết kế cụ thể |

Cú pháp khi **cần strong**:

~~~java
var defined = MethodHandles.lookup()
        .defineHiddenClass(classFileBytes, true,
                MethodHandles.Lookup.ClassOption.STRONG);
~~~

Đây là **đoạn code minh họa**, trong đó `classFileBytes` phải là classfile bytes hợp lệ cùng package và lookup có quyền phù hợp.

Không nên hiểu “mặc định có thể unload” thành “sẽ unload ngay khi phương thức kết thúc”. JVM/GC quyết định thời điểm; các tham chiếu còn sống qua `Class<?>`, `MethodHandle`, object instance, static cache, thread hoặc cấu trúc dữ liệu khác có thể giữ định nghĩa lớp. Ngược lại, `STRONG` giữ quan hệ mạnh với loader và có thể làm tích tụ class metadata nếu tạo quá nhiều lớp. Không sử dụng `STRONG` như một cờ tối ưu tốc độ chung cho mọi ứng dụng.

**Nguyên tắc vận hành:** nếu sinh số lượng lớn lớp ở runtime, cần giới hạn cardinality, theo dõi heap/metaspace và hoạt động class loading/unloading, đồng thời thiết kế cache có chính sách rõ ràng. Không đánh đồng heap object với class metadata: lớp sinh có thể tốn metaspace ngay cả khi instance nhỏ.

## 8. Dòng chảy thực tế trong framework sinh mã runtime

Một thư viện phát triển lâu dài thường tách các trách nhiệm:

1. **Phân tích yêu cầu:** xác định biểu thức, interface đích, kiểu tham số, kết quả và quyền truy cập cần thiết.
2. **Sinh classfile:** tạo bytes tương thích phiên bản JVM, cùng package runtime cần thiết. Có thể dùng thư viện bytecode hoặc API classfile được JDK hiện đại hỗ trợ; `defineHiddenClass` không tự biến Java source thành bytes.
3. **Định nghĩa trong ngữ cảnh quyền phù hợp:** dùng một `Lookup` thuộc package/module được phép, chọn `initialize` và chỉ thêm `NESTMATE` hay `STRONG` khi yêu cầu thật sự cần.
4. **Liên kết với code nghiệp vụ:** giữ `Lookup`/`Class<?>` khi cần truy cập nội bộ, tạo `MethodHandle` hoặc constructor, triển khai interface đã biết và cung cấp một factory/adapter có hợp đồng rõ ràng.
5. **Tái sử dụng có giới hạn:** nếu cùng một biểu thức được gọi nhiều lần, cân nhắc cache factory thay vì tạo hidden class mới mỗi request. Tính đến vòng đời bộ nhớ và thread safety của cache.
6. **Chẩn đoán:** ghi nhận danh tính logic (mã biểu thức, key cấu hình, phiên bản bytecode) và nguyên nhân lỗi từ classfile/lookup; không dựa vào hậu tố lớp ẩn do JVM tạo làm định danh ổn định.

### Khi nào hidden class thật sự mang lại lợi ích?

- Một framework cần **nhiều class sinh động** và class ấy không có nhu cầu được các module khác tham chiếu bằng tên.
- Generated implementation có thể được cung cấp qua **interface, superclass hoặc method handle** đã biết.
- Việc **dỡ tải độc lập** hoặc tránh liên kết theo tên là quan trọng cho vòng đời runtime.
- Framework kiểm soát được classfile bytes, quyền `Lookup` và vòng đời của instance/cache.

Đối với quy tắc nghiệp vụ bình thường như “đổi nhiệt độ” hay “lọc danh sách”, một lambda, method reference, interface implementation hoặc class thông thường thường dễ đọc, dễ debug và dễ kiểm thử hơn. Hidden Class dành cho lớp hạ tầng cần sinh và quản lý mã.

## 9. Giới hạn và tình huống thất bại cần hiểu

### 9.1. Không có tên để tìm lại qua `Class.forName`

Giữ `Class<?>` hoặc `MethodHandle` được trả về từ lúc định nghĩa. Không ghi tên lớp ẩn vào cấu hình để lần chạy sau lấy lại bằng `Class.forName(...)`; lớp ẩn không có tên nhị phân truy xuất theo cơ chế ấy.

Tương tự, **serialization Java mặc định dựa trên tên class** không nên được xem là cách an toàn hoặc ổn định để tái tạo instance của một hidden class. Nếu framework thật sự cần lưu trạng thái, hãy thiết kế biểu diễn dữ liệu bên ngoài và cơ chế khôi phục do framework kiểm soát; đừng cố biến tên hidden class thành contract lưu trữ.

### 9.2. Bytecode vẫn bị JVM kiểm tra

JVM không miễn quy tắc xác minh classfile vì class ẩn. Lỗi phổ biến gồm bytecode sai định dạng, phiên bản cao hơn runtime, package không khớp với lookup, hoặc tham chiếu kiểu/method không liên kết được. Một lớp ẩn **có thể thất bại khi định nghĩa, liên kết, khởi tạo hoặc thực thi**, nên framework cần bắt lỗi ở đúng tầng và cung cấp thông báo chẩn đoán hữu ích.

### 9.3. Quyền `Lookup` và ranh giới module vẫn áp dụng

API cần lookup có đủ đặc quyền để định nghĩa class trong ngữ cảnh package/module được chọn. Không có quyền để định nghĩa hidden class vào package bất kỳ chỉ bằng cách đổi tên trong classfile; `publicLookup()` bị giới hạn, và API kiểm tra quyền truy cập. Khi cần thao tác trong module hoặc package khác, phải có quyền được cấp hợp lệ theo Java Platform Module System; không tự ý mở truy cập riêng tư bừa bãi.

### 9.4. “Hidden” không phải ranh giới bảo mật

Hidden class vẫn có thể chạy mã tùy ý mà bytecode cho phép trong ngữ cảnh JVM hiện hữu; không cô lập IO, network, native code hoặc tài nguyên. **Không thực thi bytes từ bên chưa tin cậy chỉ vì API có chữ “hidden”.** Cần kiểm soát nguồn bytes, quyền công cụ sinh mã và giới hạn đầu vào tương ứng với thiết kế bảo mật của ứng dụng.

### 9.5. Không giả định GC có tốc độ cố định

Hidden class tạo điều kiện unload độc lập với loader khi không dùng `STRONG`, nhưng **không hứa hẹn thời điểm**; đừng viết bài test assert “vừa bỏ tham chiếu thì class chắc chắn bị unload ngay”. Với ứng dụng cần nhiều class động, đo số lượng class được nạp, metaspace, retention từ cache và áp lực tài nguyên trong tải gần production.

## 10. Phân biệt với cơ chế runtime quen thuộc

| Công cụ | Chức năng chính | Khi nào chọn |
| --- | --- | --- |
| `new MyClass()` / class viết sẵn | Tạo instance của class có tên đã biên dịch | Hầu hết code nghiệp vụ thông thường |
| Lambda / method reference | Biểu đạt hành vi ngắn gọn qua functional interface | Khi không cần tự quản lý bytecode |
| `Proxy.newProxyInstance(...)` | Tạo proxy cho interface thông qua API chuẩn | Chặn/ủy quyền các lời gọi interface mà không cần tự thiết kế classfile |
| `MethodHandle` | Tham chiếu và gọi method/constructor với kiểm tra quyền lúc tạo handle | Adapter lời gọi động, tối ưu dispatch, truy cập runtime |
| `Lookup.defineHiddenClass(...)` | Định nghĩa **kiểu ẩn mới** từ classfile bytes | Khi framework cần một class sinh runtime không liên kết theo tên và có vòng đời phù hợp |
| `ClassLoader#defineClass(...)` / `Lookup.defineClass(...)` | Định nghĩa **lớp thông thường có tên** theo quyền tương ứng | Khi thật sự cần danh tính có tên và quy tắc loading/liên kết tương ứng |

Các cơ chế có thể phối hợp: ví dụ tạo hidden class, rồi lấy `MethodHandle` của constructor để instantiate và cung cấp instance như một interface. Không nên nghĩ `MethodHandle` và Hidden Class là hai tên gọi của cùng một công nghệ: một bên là cơ chế **lời gọi**, một bên là **định nghĩa kiểu mới**.

## 11. Quy tắc thiết kế và checklist triển khai

Trước khi thêm một đoạn sinh lớp ẩn vào framework hoặc thư viện, hãy kiểm tra:

- **Có nhu cầu định nghĩa class thật hay không?** Một interface implementation đã biên dịch, lambda hoặc method handle thường đơn giản hơn.
- **Classfile bytes có hợp lệ, đáng tin và cùng package không?** Khớp phiên bản JDK sẽ chạy; compiler/bytecode generator phải tạo cấu trúc classfile hợp lệ.
- **`Lookup` có đúng quyền không?** Không chuyển `Lookup` đặc quyền cho code chưa tin cậy.
- **Hợp đồng truy cập từ ngoài là gì?** Có interface/superclass/method handle rõ ràng, không cần tìm lớp ẩn bằng tên.
- **Có cần `NESTMATE` không?** Chỉ bổ sung khi thực sự cần quyền nestmate.
- **Có cần `STRONG` không?** Quyết định dựa trên yêu cầu giữ lớp và chi phí class metadata; mặc định thường phù hợp mã ngắn hạn.
- **Class được khởi tạo lúc nào?** Chọn `initialize` có chủ đích khi static initializer có tác dụng phụ.
- **Khi nào cache, khi nào unload?** Tránh tạo một lớp mới cho mọi lần gọi nếu có thể tái sử dụng; theo dõi cache và metaspace.
- **Đã kiểm thử đúng giới hạn JDK chưa?** API có từ Java 15; kiểm thử thực tế trên phiên bản JDK, quyền module và cách đóng gói của môi trường đích.
- **Có logging và xử lý lỗi định nghĩa/khởi tạo không?** Ghi id logic và nguyên nhân lỗi; không dựa vào tên hậu tố riêng của hidden class.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao runtime sinh class thường cần Hidden Class thay vì mọi class đều có tên thông thường?  
**Đáp án:** Khi cần nhiều triển khai tạm thời có thể truy cập qua interface/method handle, hidden class tránh phụ thuộc vào việc liên kết theo tên và có khả năng unload độc lập với class loader theo mặc định.

**Câu 2.** `defineHiddenClass(...)` có tự biên dịch một chuỗi Java source không?  
**Đáp án:** Không. Nó nhận **byte[] chứa classfile hợp lệ**. Việc tạo bytecode thuộc thành phần khác.

**Câu 3.** Hai lần `defineHiddenClass` trên cùng bytes có tạo cùng một đối tượng `Class<?>` không?  
**Đáp án:** Không. Mỗi lần định nghĩa tạo một class runtime khác, như `differentDefinitions=true` trong ví dụ.

**Câu 4.** Có thể tìm lớp ẩn bằng `Class.forName(hiddenType.getName())` không?  
**Đáp án:** Không. Hidden Class không có tên nhị phân thông thường để tra bằng API ấy; giữ `Class<?>` hoặc handle trực tiếp.

**Câu 5.** `initialize=false` bảo đảm static initializer không bao giờ chạy đúng không?  
**Đáp án:** Không. Nó không yêu cầu khởi tạo tại lúc định nghĩa; JVM sẽ khởi tạo khi việc sử dụng class đòi hỏi.

**Câu 6.** `NESTMATE` có cho phép truy cập private của mọi class trong JVM không?  
**Đáp án:** Không. Nó thêm hidden class vào **nest của lookup class**, chỉ tác động quyền truy cập private trong nest tương ứng.

**Câu 7.** Mặc định Hidden Class có chắc chắn unload ngay khi hàm tạo class trả về không?  
**Đáp án:** Không. JVM quyết định GC/unloading và còn xét các tham chiếu sống. Mặc định chỉ **cho phép** unload khi loader vẫn tồn tại, nếu điều kiện phù hợp.

**Câu 8.** Tại sao không dùng Hidden Class để thực thi classfile không tin cậy?  
**Đáp án:** Hidden Class không phải sandbox, không cấp cơ chế cách ly nguồn bytes hoặc thu hẹp quyền thực thi của code.

## 13. Tài liệu chuẩn còn áp dụng

- [OpenJDK JEP 371 — Hidden Classes](https://openjdk.org/jeps/371): mục tiêu thiết kế, lớp ẩn và vòng đời trong JVM.
- [Java SE 26 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineHiddenClass`, `defineHiddenClassWithClassData`, `lookupClass`, ràng buộc package và quyền truy cập.
- [Java SE 26 — `MethodHandles.Lookup.ClassOption`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.ClassOption.html): định nghĩa chính thức của `NESTMATE` và `STRONG`.
- [Java SE 26 — `Class.isHidden()`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Class.html): phân biệt hidden class với class thông thường và khả năng tra tên.
- [Java SE 15 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): đối chiếu API gốc từ Java 15.
- [Java SE 26 — `MethodHandles.classData`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.html): hướng mở rộng **từ Java 16** qua `defineHiddenClassWithClassData(...)` để gắn dữ liệu với hidden class, khi framework hiện đại thật sự cần.
