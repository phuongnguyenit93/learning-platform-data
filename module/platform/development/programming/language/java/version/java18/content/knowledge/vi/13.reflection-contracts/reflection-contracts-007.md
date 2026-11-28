# Method.invoke(): truyền receiver cho method instance và quy tắc của method static

## Mục tiêu bài học

Trong nhóm **Hợp đồng reflection** của mô-đun Java 18, nội dung này tập trung vào một quy tắc vẫn có hiệu lực trên các JDK hiện đại: tham số đầu tiên của `java.lang.reflect.Method.invoke(Object obj, Object... args)` có ý nghĩa khác nhau tùy phương thức được gọi là **instance** hay **static**.

Sau bài học, bạn có thể:

- Chỉ ra receiver nào hợp lệ khi gọi một phương thức instance bằng reflection.
- Giải thích vì sao khi gọi phương thức static, đối số `obj` bị bỏ qua và có thể truyền `null`.
- Phân biệt cơ chế điều phối phương thức instance (dynamic dispatch) với cách chọn phương thức static.
- Dự đoán các lỗi liên quan đến receiver, tham số, quyền truy cập và ngoại lệ phát sinh trong phương thức đích.
- Viết một phép kiểm chứng nhỏ trên JDK đang sử dụng, tránh hiểu nhầm do boxing, varargs hoặc ranh giới module.

> **Bối cảnh phiên bản:** `Method.invoke` không phải API mới của Java 18. Đây là hợp đồng reflection vẫn hữu ích khi học và kiểm chứng hành vi trên JDK hiện đại. Các ví dụ dùng Java API tiêu chuẩn đang được hỗ trợ, không dựa vào những cơ chế reflection nội bộ hoặc đã lỗi thời.

## 1. Chữ ký của `Method.invoke` và ý nghĩa hai nhóm đối số

Phương thức chính cần nhớ:

~~~java
Object invoke(Object obj, Object... args)
        throws IllegalAccessException, InvocationTargetException;
~~~

Bạn lấy một đối tượng `Method` đại diện cho **phương thức đích**; sau đó gọi `invoke` để thực thi phương thức đích đó.

- `obj` là **receiver** được truyền cho lời gọi phản chiếu. Nếu phương thức đích là instance, nó là đối tượng mà phương thức chạy trên đó. Nếu phương thức đích là static, giá trị này bị bỏ qua.
- `args` là danh sách **đối số của phương thức đích** theo đúng thứ tự khai báo. Chúng không bao gồm receiver.
- Kết quả của `invoke` có kiểu khai báo `Object`: giá trị trả về nguyên thủy được đóng hộp (boxing); phương thức trả về `void` cho kết quả `null`.

Ví dụ, nếu có `customer.updateScore(5)` thì phản chiếu tương đương về ý nghĩa là `method.invoke(customer, 5)`. Với `Math.max(2, 7)`, có thể viết `method.invoke(null, 2, 7)` vì `max` là phương thức static.

| Loại phương thức đích | Vai trò của `obj` | Có được truyền `null`? | Yêu cầu với `args` |
| --- | --- | --- | --- |
| Instance | Đối tượng nhận lời gọi | **Không**; `null` gây `NullPointerException` | Khớp số lượng và kiểu tham số khai báo, với các chuyển đổi invocation được cho phép |
| Static | Bị bỏ qua; không dùng để xác định lớp hay instance | **Có**; đây là cách viết dễ hiểu nhất | Tương tự instance: tham số vẫn phải hợp lệ |
| Instance không có tham số | Vẫn phải truyền receiver hợp lệ | **Không** | Có thể gọi `invoke(receiver)` |
| Static không có tham số | Bị bỏ qua | **Có** | Có thể gọi `invoke(null)` |

**Lưu ý cách đọc:** `obj` là tham số của `Method.invoke`, còn `this` (đối với phương thức instance) là tham chiếu bên trong phương thức đích. Chúng liên quan vì receiver hợp lệ trở thành đối tượng thực thi, nhưng không phải hai tham số độc lập mà bạn cần truyền.

## 2. Receiver của phương thức instance

Với phương thức instance, `Method.invoke` cần một đối tượng thực sự tương thích với lớp hoặc giao diện **khai báo phương thức đó**.

- Nếu `Method` được lấy từ lớp `Account`, receiver có thể là một `Account` hoặc đối tượng thuộc lớp con của `Account`.
- Nếu `Method` đại diện cho một phương thức instance của interface, receiver có thể là đối tượng của lớp hiện thực interface đó.
- Receiver bằng `null` không hợp lệ: Java ném `NullPointerException`.
- Receiver không phải instance của lớp/giao diện khai báo phương thức sẽ gây `IllegalArgumentException`.
- Không cần receiver cùng đúng lớp runtime với đối tượng `Method`; quan hệ kế thừa/implements hợp lệ mới là điều quan trọng.

Hợp đồng này không phụ thuộc vào việc receiver có trường dữ liệu cùng tên hay phương thức cùng chữ ký. Hai lớp **không liên quan về kiểu** sẽ không thay thế nhau chỉ vì nhìn giống nhau.

### Ví dụ hoàn chỉnh: instance hợp lệ và receiver sai

Tạo file `MethodInvokeDemo.java`:

~~~java
import java.lang.reflect.Method;

public class MethodInvokeDemo {
    public static class Counter {
        private int count = 10;

        public int add(int delta) {
            count += delta;
            return count;
        }

        public static String label(String value) {
            return "ID:" + value;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Method add = Counter.class.getMethod("add", int.class);
        Counter counter = new Counter();

        Object result = add.invoke(counter, 5);
        System.out.println(result); // 15 (Integer sau boxing)

        try {
            add.invoke(null, 1);
        } catch (NullPointerException expected) {
            System.out.println("instance: receiver null");
        }

        try {
            add.invoke(new Object(), 1);
        } catch (IllegalArgumentException expected) {
            System.out.println("instance: receiver sai kieu");
        }

        Method label =
                Counter.class.getMethod("label", String.class);

        System.out.println(label.invoke(null, "A"));         // ID:A
        System.out.println(label.invoke(new Object(), "B")); // ID:B
    }
}
~~~

Chạy trên JDK đang sử dụng:

~~~sh
javac MethodInvokeDemo.java
java MethodInvokeDemo
~~~

Đầu ra:

~~~text
15
instance: receiver null
instance: receiver sai kieu
ID:A
ID:B
~~~

Ở lời gọi `add.invoke(counter, 5)`, `counter` là receiver hợp lệ, còn `5` là tham số `delta` của `add`. Lời gọi `add.invoke(null, 1)` lỗi trước khi có thể thực thi phần thân `add`; nó không mang nghĩa “hãy tự tạo đối tượng Counter”.

## 3. Quy tắc dành cho phương thức static

Một phương thức static thuộc về **lớp khai báo** chứ không chạy trên receiver instance. Vì thế, theo hợp đồng của `Method.invoke`:

1. `obj` bị **bỏ qua hoàn toàn** đối với phương thức static; truyền `null` là bình thường.
2. Nếu truyền một đối tượng khác `null`, đối tượng đó cũng bị bỏ qua, kể cả khi không thuộc lớp khai báo phương thức.
3. `Method` mà bạn đang giữ xác định **phương thức static nào** được gọi; kiểu runtime của `obj` không làm Java chọn lại static method.
4. Nếu lớp khai báo phương thức static **chưa được khởi tạo**, lời gọi phản chiếu sẽ kích hoạt việc khởi tạo lớp trước khi thực thi phương thức.

Ví dụ từ chương trình trên:

~~~java
Method label = Counter.class.getMethod("label", String.class);

label.invoke(null, "A");         // ID:A
label.invoke(new Object(), "B"); // ID:B; receiver bi bo qua
~~~

Cách viết `label.invoke(null, "A")` nên được ưu tiên trong mã thực tế: nó thể hiện rõ bạn chủ động gọi **static method**. Việc một đối tượng không tương thích vẫn được chấp nhận ở vị trí `obj` là một quy tắc API, không phải khuyến nghị sử dụng.

**Không nhầm:** receiver bị bỏ qua **không có nghĩa** các đối số của phương thức static cũng bị bỏ qua. Ví dụ `label.invoke(null, 42)` gây lỗi về kiểu đối số, bởi tham số khai báo của `label` là `String`.

### Khởi tạo lớp khi gọi phương thức static

Cần phân biệt ba việc:

- Tạo một đối tượng `Method` bằng `getMethod(...)` là thao tác tìm metadata.
- Truyền `null` vào `Method.invoke` của phương thức static là thao tác chọn receiver **không cần instance**.
- Chính **việc gọi** phương thức static có thể khiến JVM khởi tạo lớp khai báo, nếu lớp đó chưa được khởi tạo.

Do đó, `method.invoke(null)` vẫn có thể chạy static initializer hoặc gặp lỗi khởi tạo lớp. `null` không phải cơ chế bỏ qua quá trình khởi tạo lớp.

Để tự kiểm chứng mốc này một cách chắc chắn, cần kiểm soát cả cách tải lớp: `Class.forName("ten.Lop")` mặc định có thể khởi tạo lớp ngay trong bước tra cứu; dạng `Class.forName(name, false, loader)` cho phép yêu cầu tải lớp mà chưa chủ động khởi tạo nó.

## 4. Instance dispatch và static hiding

Khi `Method` đại diện cho một phương thức instance có thể override, lời gọi qua `invoke` tuân theo **dynamic dispatch**: JVM có thể chạy bản override ở lớp của receiver.

Ngược lại, phương thức static **không override** theo kiểu instance. Khi lớp con khai báo một static method cùng chữ ký, đó là **method hiding**. Đối tượng `Method` được lấy từ lớp nào sẽ quyết định phiên bản static cần gọi.

Ví dụ:

~~~java
import java.lang.reflect.Method;

public class DispatchDemo {
    public static class Parent {
        public String kind() {
            return "Parent instance";
        }

        public static String category() {
            return "Parent static";
        }
    }

    public static class Child extends Parent {
        @Override
        public String kind() {
            return "Child instance";
        }

        public static String category() {
            return "Child static";
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Method instance = Parent.class.getMethod("kind");
        Method parentStatic = Parent.class.getMethod("category");
        Method childStatic = Child.class.getMethod("category");

        Child child = new Child();

        System.out.println(instance.invoke(child));
        System.out.println(parentStatic.invoke(child));
        System.out.println(childStatic.invoke(null));
    }
}
~~~

Kết quả:

~~~text
Child instance
Parent static
Child static
~~~

- `instance.invoke(child)` chạy `Child.kind()` vì `kind` là instance method được override.
- `parentStatic.invoke(child)` vẫn chạy `Parent.category()`; `child` bị bỏ qua khi gọi static method.
- `childStatic.invoke(null)` chạy `Child.category()` vì đối tượng `Method` trỏ tới phương thức static khai báo tại `Child`.

Đây là phép thử tốt khi người học cho rằng “truyền một Child làm receiver thì Java sẽ chọn mọi phương thức của Child”. Nhận định đó sai với static method.

## 5. Quy tắc đối số, boxing và varargs

Receiver đúng chưa đủ để `invoke` thành công. Các đối số `args` phải phù hợp với chữ ký **phương thức đích**.

### Tìm đúng chữ ký

~~~java
Method add = Counter.class.getMethod("add", int.class);
~~~

`getMethod("add", int.class)` tìm tham số nguyên thủy `int`. Thay `int.class` bằng `Integer.class` sẽ tìm **chữ ký khác** và có thể gặp `NoSuchMethodException`. Reflection không làm phân giải overload theo giá trị thực tế của `args` như cú pháp gọi Java thông thường; bạn cần lấy đúng `Method` trước.

Khi thực thi `invoke`, Java có thể thực hiện **unboxing** và **widening primitive conversion** được hợp đồng cho phép. Ví dụ một phương thức nhận `long` có thể nhận đối số `Integer` và chuyển thành `long`. Java không thực hiện narrowing primitive conversion tùy ý như ép `Long` xuống `int`.

~~~java
Method add = Counter.class.getMethod("add", int.class);
Counter counter = new Counter();

add.invoke(counter, Integer.valueOf(2)); // hop le: unboxing Integer -> int
// add.invoke(counter, Long.valueOf(2));  // IllegalArgumentException
// add.invoke(counter, (Object) null);    // IllegalArgumentException
~~~

### Hai tầng varargs cần phân biệt

Bản thân `Method.invoke` được khai báo `Object... args`. Tuy nhiên, điều đó **không** có nghĩa Java sẽ tự gom một số đối số bất kỳ vào mảng varargs của **phương thức đích**.

Giả sử có:

~~~java
public static String merge(String... parts) {
    return String.join("/", parts);
}
~~~

Bạn lấy phương thức bằng:

~~~java
Method merge = Example.class.getMethod("merge", String[].class);
~~~

Đối tượng `Method` tương ứng có **một tham số** kiểu `String[]`. Muốn truyền mảng đó dưới dạng **một đối số** qua `invoke`, hãy ép về `Object`:

~~~java
Object result = merge.invoke(null, (Object) new String[] {"a", "b"});
// "a/b"
~~~

Trong ví dụ này, `Example` là tên lớp khai báo `merge`. Ép kiểu `(Object)` giúp compiler hiểu mảng `String[]` là một phần tử trong danh sách `Object...` của `invoke`. Không được giả định `merge.invoke(null, "a", "b")` sẽ tự gom hai chuỗi thành mảng `String[]` để gọi phương thức đích.

## 6. Ngoại lệ và giá trị trả về

Các ngoại lệ quan trọng xảy ra tại những tầng khác nhau:

| Tình huống | Ngoại lệ / kết quả |
| --- | --- |
| `obj == null` khi gọi instance method | `NullPointerException` |
| `obj` sai kiểu với instance method | `IllegalArgumentException` |
| Sai số lượng đối số, kiểu không tương thích hoặc truyền `null` cho tham số primitive | `IllegalArgumentException` |
| Không đủ quyền truy cập vào phương thức đích | `IllegalAccessException` |
| **Phần thân phương thức đích** ném ngoại lệ | `InvocationTargetException` bọc nguyên nhân từ phương thức đích |
| Khởi tạo lớp của static method thất bại | Có thể phát sinh `ExceptionInInitializerError` |
| Phương thức đích trả về `int` hoặc kiểu primitive khác | `Object` nhận một giá trị boxed như `Integer` |
| Phương thức đích trả về `void` | `invoke` trả về `null` |

Ví dụ tách lỗi **do gọi reflection** và lỗi **do code nghiệp vụ**:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class FailureDemo {
    public static class Service {
        public void fail() {
            throw new IllegalStateException("business error");
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Method fail = Service.class.getMethod("fail");

        try {
            fail.invoke(new Service());
        } catch (InvocationTargetException e) {
            Throwable cause = e.getCause();
            System.out.println(cause.getClass().getSimpleName());
            System.out.println(cause.getMessage());
        }
    }
}
~~~

Kết quả:

~~~text
IllegalStateException
business error
~~~

`IllegalStateException` đến từ phương thức `Service.fail()` nên được bọc bởi `InvocationTargetException`. Trong khi đó, `fail.invoke(null)` gặp vấn đề với receiver trước khi thực thi phần thân, nên không trở thành `InvocationTargetException` theo kịch bản này.

**Khi xử lý lỗi:** dùng `InvocationTargetException.getCause()` để xem lỗi của phương thức đích. Không nên gom mọi ngoại lệ reflection thành “method đã chạy và thất bại”, vì lỗi receiver, quyền truy cập hoặc đối số có thể xảy ra trước khi method được thực thi.

## 7. Quyền truy cập vẫn có hiệu lực

`Method.invoke` không tự vượt qua quy tắc visibility hay đóng gói module. Việc có được một đối tượng `Method` không bảo đảm bạn có quyền thực thi phương thức mà nó đại diện.

- `getMethod(...)` tìm các phương thức `public` phù hợp, kể cả phương thức public được thừa kế.
- `getDeclaredMethod(...)` tìm phương thức khai báo trực tiếp trong lớp, kể cả `private`, nhưng tìm được metadata **không đồng nghĩa** với được phép gọi.
- `IllegalAccessException` có thể xuất hiện khi `invoke` không đủ quyền truy cập.
- `trySetAccessible()` hoặc `setAccessible(true)` phải tuân thủ quy tắc truy cập và **strong encapsulation** của hệ module Java. Không thể mặc nhiên mở quyền truy cập sâu vào các package không được `opens` phù hợp.

Ví dụ kiểm tra quyền mà không tự giả định truy cập sâu luôn thành công:

~~~java
Method method = SomeType.class.getDeclaredMethod("hidden");

if (method.trySetAccessible()) {
    // Chi invoke khi viec bo access checks duoc cho phep.
    Object value = method.invoke(receiver);
} else {
    System.out.println("Khong duoc mo quyen truy cap");
}
~~~

Trong đoạn này, `SomeType` và `receiver` là các giá trị minh họa. Khi kiểm thử thực tế, hãy thay bằng kiểu và instance phù hợp. `trySetAccessible()` trả về `false` khi không thể bật chế độ truy cập theo quy định; trong một số trường hợp phương thức còn có thể ném ngoại lệ bảo mật tương ứng với môi trường.

Ưu tiên API public có hợp đồng rõ ràng. Khi cần phản chiếu mã của chính ứng dụng qua ranh giới module, cấu hình `exports`/`opens` theo nhu cầu cụ thể; tránh thiết kế giải pháp phụ thuộc vào việc truy cập các lớp nội bộ của JDK.

## 8. Cách kiểm chứng có hệ thống trên JDK đang dùng

Có thể dùng bảng sau để lên kịch bản kiểm tra. Mỗi kịch bản nên chạy trên cùng phiên bản JDK mà ứng dụng triển khai, ghi rõ lớp khai báo, modifier của phương thức, kiểu receiver và danh sách đối số.

| Kiểm chứng | Cách gọi | Kết quả cần quan sát |
| --- | --- | --- |
| Instance đúng kiểu | `add.invoke(new Counter(), 2)` | Gọi được phần thân `Counter.add` |
| Instance sai kiểu | `add.invoke(new Object(), 2)` | `IllegalArgumentException` |
| Instance null | `add.invoke(null, 2)` | `NullPointerException` |
| Static receiver null | `label.invoke(null, "x")` | Gọi được `Counter.label` |
| Static receiver khác kiểu | `label.invoke(new Object(), "x")` | Vẫn gọi được cùng `Counter.label` |
| Dynamic dispatch instance | `Parent.kind` gọi trên `Child` | Kết quả của bản override ở `Child` |
| Static hiding | `Parent.category` gọi với receiver `Child` | Vẫn là kết quả của `Parent.category` |
| Tham số primitive | `add.invoke(counter, Integer.valueOf(2))` | Unboxing hợp lệ, kết quả boxed |
| Code đích ném lỗi | `fail.invoke(new Service())` | `InvocationTargetException` với `getCause()` đúng |
| Member không có quyền truy cập | `invoke` không bật access phù hợp | `IllegalAccessException` khi kiểm tra truy cập không thành công |

### Các sai lầm cần tránh

**1. “Static method yêu cầu receiver đúng lớp.”** Sai: tham số `obj` bị bỏ qua khi phương thức đích là static. Điều cần đúng vẫn là đối số khai báo và quyền truy cập.

**2. “`obj == null` luôn hợp lệ vì invoke là reflection.”** Sai: `null` được phép ở vị trí receiver cho static method; với instance method, nó gây `NullPointerException`.

**3. “Truyền một object của lớp con luôn chạy phương thức lớp con.”** Chỉ đúng theo quy tắc dynamic dispatch cho các instance method có thể override. Static method đã được xác định bằng đối tượng `Method`.

**4. “Reflection sẽ tự ép mọi kiểu đối số.”** Sai: chỉ các chuyển đổi invocation được cho phép mới diễn ra; narrowing primitive không tự áp dụng.

**5. “Có `getDeclaredMethod` nghĩa là gọi private method thoải mái.”** Sai: quyền truy cập và ranh giới module vẫn được kiểm tra.

## 9. Câu hỏi ôn tập

**Câu 1.** Vì sao `Counter.label` static vẫn chạy khi gọi `label.invoke(new Object(), "X")`?

**Trả lời:** Vì đối số `obj` bị bỏ qua đối với static method. Đối tượng `Method` xác định `Counter.label`; `"X"` là tham số đầu tiên của phương thức đích.

**Câu 2.** Với `Method kind = Parent.class.getMethod("kind")`, kết quả của `kind.invoke(new Child())` là gì?

**Trả lời:** Nếu `Child` override `kind`, Java gọi bản override ở `Child` theo dynamic dispatch của instance method.

**Câu 3.** Tại sao `add.invoke(counter, Long.valueOf(5))` không phải phép gọi tương đương `add(5)` khi `add` nhận `int`?

**Trả lời:** `invoke` không cho phép chuyển hẹp primitive từ `long` sang `int`. Phép gọi phản chiếu yêu cầu đối số phù hợp với chữ ký và quy tắc chuyển đổi được phép.

**Câu 4.** Điều gì xảy ra nếu phương thức instance được gọi thành công nhưng chính phần thân của nó ném `IllegalArgumentException`?

**Trả lời:** Ngoại lệ do **phương thức đích** ném được bọc trong `InvocationTargetException`. Khác với `IllegalArgumentException` phát sinh trực tiếp ở `invoke` do truyền receiver/đối số không hợp lệ.

## Tổng kết

- `Method.invoke(obj, args)` dùng `obj` làm **receiver bắt buộc** cho phương thức instance; receiver phải tương thích kiểu và khác `null`.
- Với phương thức **static**, `obj` bị **bỏ qua**, có thể là `null` hoặc đối tượng thuộc kiểu không liên quan. Phương thức được gọi là phương thức mà đối tượng `Method` đại diện.
- Instance method có thể dùng dynamic dispatch khi receiver thuộc lớp con override; static method không được chọn theo receiver.
- Một lời gọi phản chiếu hợp lệ vẫn phải tuân thủ chữ ký đối số, chuyển đổi kiểu, kiểm soát truy cập và hợp đồng ngoại lệ.
- Kiểm chứng trên JDK hiện hành cần phân biệt rõ lỗi phát sinh trong `invoke` và ngoại lệ do chính phương thức đích ném.

**Tài liệu đối chiếu:** Java API `java.lang.reflect.Method.invoke`, `java.lang.reflect.AccessibleObject.trySetAccessible`; Java Language Specification về method invocation, method overriding và method hiding. Xem API của đúng phiên bản JDK đang chạy khi kiểm chứng hành vi trong dự án.
