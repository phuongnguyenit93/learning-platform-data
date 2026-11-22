# Vòng đời lớp khác vòng đời đối tượng như thế nào trong Java?

## 1. Hai vòng đời khác nhau, nhưng có liên hệ

Trong Java, **lớp (class)** là định nghĩa kiểu được JVM nạp, liên kết và khởi tạo để chương trình có thể dùng field, method, constructor và tạo instance. **Đối tượng (object/instance)** là một thực thể cụ thể được tạo khi chương trình thực hiện `new` hoặc một cơ chế cấp phát thích hợp. Hai khái niệm có các mốc tồn tại và điều kiện kết thúc khác nhau.

Một lớp có thể đã được khởi tạo dù **chưa có instance nào**; cũng có thể có hàng triệu instance của cùng một lớp mà khối khởi tạo `static` của lớp chỉ chạy **một lần cho mỗi định danh lớp runtime**, nếu lần khởi tạo thành công. Ngược lại, constructor và các instance initializer chạy cho **mỗi lần tạo instance theo quá trình khởi tạo đối tượng thông thường**.

| Tiêu chí | Vòng đời lớp | Vòng đời đối tượng |
|---|---|---|
| Đối tượng quản lý | Định nghĩa kiểu ở runtime, gắn với class loader | Một instance cụ thể của kiểu |
| Điểm khởi đầu thường thấy | JVM nạp kiểu khi cần | Cấp phát đối tượng (thường bằng `new`) |
| Các giai đoạn cốt lõi | Loading → linking → initialization; sau đó có thể unloading | Allocation → giá trị mặc định → instance initialization/constructor → sử dụng → có thể được GC |
| Thực thi mã khởi tạo | `static` initializer/field initializer, một lần cho mỗi lần khởi tạo thành công của định danh lớp | Instance field initializer, instance initializer và constructor theo mỗi lần tạo |
| Trạng thái | Static field thuộc về lớp runtime, chia sẻ giữa các instance tương ứng | Instance field là trạng thái của từng object |
| Kết thúc | Class unloading khi đủ điều kiện và JVM chọn thực hiện | Khi object không còn reachable, JVM **có thể** thu gom |
| Phụ thuộc class loader? | Có: cùng tên nhưng defining loader khác nhau có thể là hai lớp runtime | Instance có kiểu runtime được xác định bởi lớp mà nó thuộc về |

> **Không được đồng nhất** “hết object của lớp” với “lớp được unload”. JVM không bắt buộc unload class ngay khi không còn instance, và garbage collection không chạy theo lịch cố định mà ứng dụng có thể suy ra.

## 2. Vòng đời đối tượng: tạo, dùng và có thể được thu gom

Sau khi kiểu được chuẩn bị/khởi tạo phù hợp, một lời gọi `new` thường dẫn đến:

```text
new Widget(...)
    |
    v
Bảo đảm lớp liên quan đã initialized theo quy tắc JVM
    |
    v
Cấp phát bộ nhớ và gán giá trị mặc định cho instance fields
    |
    v
Chạy chuỗi constructor: superclass -> subclass
    |    (instance field initializers và instance initializer blocks
    |     được thực thi ở từng lớp theo thứ tự cần thiết)
    v
Instance sử dụng được
    |
    v
Không còn strongly reachable từ GC roots
    |
    v
Đủ điều kiện được garbage collector thu gom, tùy JVM/GC
```

Các điểm cốt lõi:

- **Mỗi lần `new` thông thường tạo một object mới** (ngoại trừ JVM có thể tối ưu dựa trên ngữ nghĩa quan sát được; không được dựa vào vị trí cấp phát vật lý).
- **Instance field** thuộc từng object. Gán `a.name` không thay đổi `b.name` của object khác, trừ khi hai tham chiếu đang trỏ cùng object hoặc các field trỏ chung một object mutable khác.
- **Instance initializer** và constructor chạy khi tạo object thông thường; một object không tự chạy constructor lần nữa khi chỉ đọc/ghi field hoặc khi GC hoạt động.
- Constructor **không phải** method `<clinit>`. Trong class file, constructor thể hiện bằng `<init>`; `<clinit>` là phương thức khởi tạo lớp riêng.
- **Reachability** mới quan trọng cho GC: một local variable ra khỏi scope chưa có nghĩa object lập tức bị thu gom; ngược lại gán `null` cho một biến cũng chưa chắc làm object không còn tham chiếu mạnh khác.
- `System.gc()` chỉ là lời đề nghị thu gom, không đảm bảo một object cụ thể sẽ bị thu gom hay finalizer/cleaner chạy ngay.

Một object có thể có nhiều biến cùng giữ tham chiếu:

```java
Widget a = new Widget("first");
Widget b = a;        // hai reference, chỉ một object
a = null;            // b vẫn giữ object reachable
// b = null;          // có thể mất strong reference cuối cùng,
//                     // nhưng thời điểm GC vẫn không xác định
```

Đoạn trên chỉ **minh họa**, cần đặt trong chương trình có định nghĩa `Widget` để biên dịch.

### Có phải mọi object đều đi qua constructor?

Với `new` trong mã nguồn Java thông thường, constructor chain được thực thi. Nhưng không nên khái quát thành “mọi object JVM tạo đều trực tiếp gọi constructor Java”: ví dụ array được tạo bằng `new int[10]`, object tạo bởi một số cơ chế deserialization hoặc runtime nội bộ có ngữ nghĩa khởi tạo khác. Bài học chính là **vòng đời riêng của từng instance** không đồng nhất với initialization một lần của class.

## 3. Java 17 demo: class initialized một lần, object initialized nhiều lần

Tạo file `LifecycleDemo.java`:

```java
public class LifecycleDemo {
    static class Widget {
        static int created;

        static {
            System.out.println("Widget: static init");
        }

        final String name;

        {
            System.out.println("Widget: instance init");
        }

        Widget(String name) {
            this.name = name;
            created++;
            System.out.println("Widget: constructor " + name);
        }

        static void ping() {
            System.out.println("Widget: ping");
        }
    }

    public static void main(String[] args) {
        System.out.println("Start");

        Class<?> type = Widget.class;
        System.out.println("Class literal: " + type.getSimpleName());

        Widget.ping();

        Widget first = new Widget("A");
        Widget second = new Widget("B");

        System.out.println("Same Class: "
                + (first.getClass() == second.getClass()));
        System.out.println("Constructed: " + Widget.created);

        first = null;
        second = null;
        System.out.println("References cleared");
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac LifecycleDemo.java
java LifecycleDemo
```

Stdout:

```text
Start
Class literal: Widget
Widget: static init
Widget: ping
Widget: instance init
Widget: constructor A
Widget: instance init
Widget: constructor B
Same Class: true
Constructed: 2
References cleared
```

Đọc kết quả theo thứ tự:

1. `Widget.class` cho phép lấy đối tượng `Class` và `getSimpleName()` mà **không tự kích hoạt** static initialization. Vì vậy dòng `Class literal: Widget` xuất hiện trước `Widget: static init`.
2. `Widget.ping()` là một lời gọi static method; trước khi chạy method, class được initialization, nên static block in **một lần**.
3. Với mỗi lệnh `new Widget(...)`, instance initializer và constructor chạy **thêm một lần cho object mới**. Static block không chạy lại.
4. `first.getClass() == second.getClass()` in `true` vì cả hai instance có cùng runtime class identity.
5. `Widget.created` là **tổng số object được tạo bởi constructor đã viết**, không phải số object chắc chắn đang còn sống. Sau khi gán hai reference bằng `null`, biến đếm vẫn là `2` vì nó là static state.
6. Dòng `References cleared` không chứng minh GC đã thu gom hai object. GC không được gọi trực tiếp, thời điểm thu gom cũng không thể suy ra từ stdout.

Phân biệt ba thực thể trong ví dụ:

- **Lớp runtime `LifecycleDemo.Widget`**: nơi các quy tắc class loading/linking/initialization áp dụng.
- **`Class<?> type`**: một tham chiếu tới object `Class` phản ánh định nghĩa lớp runtime, không phải instance `Widget` do `new Widget` tạo.
- **`first` và `second`**: hai reference tới hai instance `Widget` riêng biệt.

## 4. Một lớp có thể tồn tại khi không có instance nào?

**Có.** Ví dụ `Math` có các static method, hoặc một utility class người dùng tự định nghĩa có thể hoạt động mà không cần instance của chính class ấy. Chỉ có class literal, reflection metadata hoặc static state cũng không đồng nghĩa với việc đã tạo object thuộc class đó.

Một lớp runtime thường tiếp tục hiện diện khi vẫn còn những thứ giữ nó/class loader của nó reachable. Với JVM hỗ trợ class unloading, điều kiện thu gom/class unloading có liên quan đến việc **defining class loader có thể được GC thu gom**. Ngoài class loader, các reference tới `Class<?>`, instance, method/field reflection objects, thread context class loader hoặc cấu trúc cache có thể kéo dài sự sống của loader và các class do loader định nghĩa.

Không nên hiểu “object hết vòng đời thì class hết vòng đời”:

```text
t0: Load + initialize class A
t1: Tạo object a1
t2: Tạo object a2
t3: a1 không còn reachable, có thể GC
t4: a2 không còn reachable, có thể GC
t5: Class A vẫn còn trong runtime vì loader và metadata liên quan
t6: Nếu loader thật sự có thể reclaim và JVM quyết định unload,
    các class do loader định nghĩa có thể được unload
```

Các mốc t3/t4/t6 là **khả năng**, không phải cam kết về thời điểm. Class do bootstrap class loader định nghĩa thường gắn với toàn bộ thời gian sống của JVM.

### Class unloading không giống garbage collection của instance

Garbage collector có thể thu hồi vùng nhớ của từng object khi không còn reachable, **mà không cần unload lớp của chúng**. Ngược lại, dỡ lớp khỏi JVM là thao tác ở cấp metadata/runtime class và class loader. Trong JVM chạy lâu, ví dụ server liên tục hot-reload plugin, classloader leak có thể khiến metadata cũ vẫn tồn tại dù logic tưởng rằng plugin đã được tháo.

Các nguồn tham chiếu kéo dài class loader thường gặp là thread còn chạy với thread context class loader cũ, `ThreadLocal` chưa dọn, static cache từ code sống lâu giữ `Class<?>` hoặc instance của plugin, hoặc callback/listener chưa hủy đăng ký. Không thể khắc phục chỉ bằng cách `someObject = null` nếu đường tham chiếu khác vẫn tồn tại.

Lưu ý thêm: `Class<?>` **bản thân cũng là một Java object**, nhưng nó đại diện cho một runtime type; việc thu gom object `Class` và unload kiểu được kiểm soát bởi quan hệ reachability với class loader/runtime metadata. Đừng coi mọi `Class<?>` như một instance do constructor của kiểu được đại diện tạo ra.

## 5. Kế thừa: thứ tự static initialization và constructor chain

Một câu hỏi phổ biến là “Nếu `new Child()`, JVM chạy static block, constructor của ai trước?”.

Quy tắc ý nghĩa:

- Đảm bảo khởi tạo các superclass cần thiết trước khi khởi tạo class con; static initializers thuộc từng class chạy một lần khi class đó được khởi tạo.
- Với **mỗi** instance `Child` mới, constructor của superclass được gọi trong constructor chain trước phần thân constructor subclass, theo cơ chế `super(...)`/`this(...)` và quy tắc instance initializers.
- Nếu gọi `new Child()` nhiều lần, constructor chain chạy nhiều lần; static initializers không chạy lại cho cùng các class đã initialized thành công.

Chương trình chạy được, tạo file `InheritanceLife.java`:

```java
public class InheritanceLife {
    static class Parent {
        static {
            System.out.println("Parent static");
        }

        {
            System.out.println("Parent instance");
        }

        Parent() {
            System.out.println("Parent constructor");
        }
    }

    static class Child extends Parent {
        static {
            System.out.println("Child static");
        }

        {
            System.out.println("Child instance");
        }

        Child() {
            System.out.println("Child constructor");
        }
    }

    public static void main(String[] args) {
        new Child();
        System.out.println("---");
        new Child();
    }
}
```

Chạy:

```bash
javac InheritanceLife.java
java InheritanceLife
```

Stdout:

```text
Parent static
Child static
Parent instance
Parent constructor
Child instance
Child constructor
---
Parent instance
Parent constructor
Child instance
Child constructor
```

Lần `new Child()` đầu tiên khiến cả class cha và con được khởi tạo theo quy tắc JVM; hai constructor chain sau đó diễn ra theo từng instance. Lần thứ hai chỉ còn các phần khởi tạo instance/constructor.

## 6. Ứng dụng trong thiết kế và chẩn đoán

- **Thiết kế static state:** nhớ rằng static cache/counter sống gắn với class identity, thường lâu hơn object sử dụng nó; cân nhắc tránh giữ reference không cần thiết đến class loader/module đã ngừng.
- **Reflection/framework:** phân biệt lấy metadata kiểu với thực sự initialization. Khởi tạo class chứa tác dụng phụ (kết nối, đăng ký callback, đọc cấu hình) khi plugin scanning có thể gây hành vi sớm hơn dự kiến; chọn API có cờ `initialize` khi cần kiểm soát.
- **Hiệu năng startup:** việc load, link và initialize class gây chi phí khác nhau; đo đúng mốc cần tối ưu, không giả định mọi class load đã chạy mọi static initializer.
- **Quản lý tài nguyên:** constructor có thể mở file/socket, nhưng GC không phải cơ chế đóng chắc chắn; dùng `AutoCloseable` và `try-with-resources` khi tài nguyên cần giải phóng sớm.
- **Hot redeploy và plugin:** kiểm tra thread, executor, listener, `ThreadLocal`, các cache ở phía host và reference phản chiếu giữ class/loader cũ trước khi kết luận JVM “không unload được class”.
- **Đọc lỗi:** `ClassNotFoundException` thường gắn với yêu cầu tìm class không thành công; `NoClassDefFoundError` còn có thể liên quan lỗi linking hoặc initialization đã xảy ra trước. Đừng suy từ tên exception rằng JVM “chưa bao giờ load” class.

Với HotSpot, có thể quan sát hoạt động nạp/dỡ lớp bằng Unified Logging (`-Xlog:class+load=info,class+unload=info`), hoặc dùng `jcmd <pid> VM.classloader_stats` để khảo sát thống kê loader trên JVM có hỗ trợ lệnh này. Kết quả phụ thuộc phiên bản, trạng thái tiến trình và quyền attach; những công cụ này hỗ trợ điều tra, không biến thời điểm unload thành một lời hứa.

## 7. Bài tập tự kiểm tra

**Câu 1.** Nếu gọi `A.class` rồi `new A()` hai lần, static block của `A` chạy mấy lần, còn constructor?

**Đáp án:** Nếu trước đó `A` chưa initialized và khởi tạo thành công, static block chạy một lần (khi active use làm class được initialized); constructor thông thường chạy hai lần. Riêng `A.class` không yêu cầu initialization.

**Câu 2.** Hai object `a` và `b` đều thuộc class `Foo`, sau khi cả hai đủ điều kiện GC, class `Foo` có chắc chắn bị unload?

**Đáp án:** Không. Class/loader có thể còn reachable từ nhiều nơi; JVM cũng không hứa unload tại thời điểm xác định.

**Câu 3.** Hai plugin có class cùng binary name `org.example.Task` do hai defining loaders khác nhau định nghĩa. `Task.counter` là static field. Chúng có dùng chung `counter` không?

**Đáp án:** Không. Hai runtime classes khác nhau nên có static state riêng, dù tên kiểu trong source giống nhau.

**Câu 4.** `Class.forName("com.example.Service", false, loader)` và `Class.forName("com.example.Service")` giống nhau ở điểm nào, khác nhau ở điểm nào?

**Đáp án:** Cả hai đều nhằm tìm lớp mang tên nhị phân được chỉ định và trả về `Class<?>` nếu thành công. Overload ba tham số với `false` không yêu cầu initialization; overload một tham số yêu cầu initialization và dùng loader của caller theo API. Việc hai lệnh thực sự tham chiếu cùng runtime class còn phụ thuộc loader.

**Câu 5.** `static final int CODE = 7` và `static final Integer CODE = 7` có chắc chắn kích hoạt initialization giống nhau khi đọc field từ class khác?

**Đáp án:** Không. Field `int` dạng compile-time constant có thể được inline mà không kích hoạt initialization; `Integer` không phải constant variable kiểu primitive hoặc `String` theo JLS, nên static field access thông thường có thể kích hoạt initialization class khai báo.

**Câu 6.** Tại sao `Widget.created` vẫn là `2` trong ví dụ `LifecycleDemo` sau khi `first` và `second` được gán `null`?

**Đáp án:** Đây là static counter số lần constructor đã tăng, không phải bộ đếm object đang sống. GC không tự trừ field đó, kể cả khi hai object thực sự được thu gom.

## 8. Ghi nhớ và tài liệu tham khảo

**Nhớ theo hai trục độc lập:**

- **Class:** load/link/initialize theo quy tắc JVM; initializing static state và `<clinit>`; danh tính gắn với defining class loader; có thể unload khi loader đủ điều kiện.
- **Object:** cấp phát, instance initialization và constructor; tiếp tục sống theo reachability; đủ điều kiện GC khi không còn reachable, nhưng thời điểm thu gom không bảo đảm.
- **Mối quan hệ:** một runtime class có thể tạo nhiều object; class initialized thành công không cần làm lại mỗi khi có object mới; việc instance bị thu gom không tự động kết thúc vòng đời class.

Tài liệu chuẩn để tra cứu chính xác quy tắc:

- [Java Language Specification 17, Chapter 12 — Execution](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html): loading, linking, initialization, tạo instance và kết thúc tồn tại class.
- [Java Virtual Machine Specification 17, Chapter 5 — Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): ngữ nghĩa loader, class identity, preparation, resolution, initialization và unloading.
- [Java SE 17 — Class.forName](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): overload liên quan cờ `initialize` và class loader.
- [Java SE 17 — System.gc()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html): lời đề nghị thu gom, không bảo đảm diễn ra ngay.