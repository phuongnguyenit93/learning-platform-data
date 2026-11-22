# Quan sát metadata khác với thực thi hoặc thay đổi đối tượng trong Java Reflection

## 1. Mục tiêu và ranh giới cốt lõi

Java Reflection cho phép chương trình xem thông tin về lớp, field, method, constructor, modifier, kiểu dữ liệu và annotation tại runtime. **Lấy thông tin mô tả (metadata) không đồng nghĩa với gọi method, chạy constructor hoặc sửa trạng thái của một object.** Những hành động đó đòi hỏi API riêng và có thể tạo ra tác dụng phụ.

Ví dụ, khi gọi `getDeclaredMethod("advance")`, ta chỉ nhận một đối tượng `Method` mô tả phương thức tên `advance`. Đến khi gọi `method.invoke(target)`, phương thức đích mới được thực thi. Tương tự, `getDeclaredField("status")` trả metadata của field; `field.set(target, "DONE")` mới là thao tác ghi trạng thái.

Một điểm tinh tế: các API Reflection tự chúng vẫn chạy mã thư viện để truy xuất metadata, đôi khi có thể làm nạp hoặc liên kết lớp. Vì vậy, câu “đọc metadata không thực thi code” phải hiểu chính xác là **không tự gọi logic nghiệp vụ của method/constructor được mô tả**, chứ không phải JVM hoàn toàn không làm việc gì.

## 2. Phân biệt metadata, đọc trạng thái và hành động có tác dụng phụ

| API hoặc thao tác | Nhóm | Ý nghĩa và khả năng tác động |
| --- | --- | --- |
| `SomeType.class`, `obj.getClass()` | Lấy đối tượng `Class` | Xác định kiểu; không tạo instance mới. |
| `Class.getName()`, `getModifiers()`, `getDeclaredFields()`, `getDeclaredMethods()`, `getDeclaredConstructors()` | Quan sát metadata | Đọc khai báo/cấu trúc; không tự chạy method/constructor được tìm thấy. |
| `Class.getAnnotation(...)`, `Field.getName()`, `Method.getParameterTypes()` | Quan sát metadata | Đọc annotation, tên và chữ ký; không gọi logic nghiệp vụ của đối tượng đích. |
| `Field.get(target)` | Đọc giá trị runtime | Đọc **trạng thái hiện tại** của field; không phải chỉ metadata. Đọc field `static` có thể kích hoạt khởi tạo lớp. |
| `Method.invoke(target, args...)` | Thực thi | Thực sự gọi method đích; có thể ghi dữ liệu, in log, ném exception, gọi mạng... |
| `Constructor.newInstance(args...)` | Thực thi/tạo đối tượng | Tạo instance và chạy constructor; constructor có thể gây tác dụng phụ. |
| `Field.set(target, value)` | Thay đổi trạng thái | Ghi giá trị field (nếu được phép); khác với `Field.get`. |
| `AccessibleObject.setAccessible(true)` | Thay đổi quyền truy cập Reflection | Yêu cầu bỏ kiểm tra truy cập Java đối với thao tác Reflection sau đó; **bản thân lời gọi này không sửa giá trị field đích**. Có thể bị từ chối bởi hệ thống module/quy tắc truy cập. |

Điểm mấu chốt: `Method` và `Field` là các **đối tượng mô tả thành viên**. Có trong tay đối tượng mô tả chưa có nghĩa là đã dùng thành viên đó để tác động đến một instance.

## 3. Ví dụ hoàn chỉnh: xem metadata trước, thực thi và sửa dữ liệu sau

Lưu đoạn sau thành file `ReflectionBoundaryDemo.java` (Java 17 trở lên):

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.reflect.Field;
import java.lang.reflect.Method;

public class ReflectionBoundaryDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @interface Topic {
        String value();
    }

    @Topic("demo")
    static class Counter {
        private String status = "NEW";
        private int count = 0;

        public void advance() {
            count++;
            System.out.println("advance executed");
        }

        public String snapshot() {
            return status + ":" + count;
        }
    }

    public static void main(String[] args) throws Exception {
        Class<Counter> type = Counter.class;
        Field field = type.getDeclaredField("status");
        Method method = type.getDeclaredMethod("advance");
        Topic annotation = type.getAnnotation(Topic.class);

        System.out.println("Class: " + type.getSimpleName());
        System.out.println("Field: " + field.getName() + " (" + field.getType().getSimpleName() + ")");
        System.out.println("Method: " + method.getName() + " -> " + method.getReturnType().getSimpleName());
        System.out.println("Annotation: " + annotation.value());

        Counter counter = new Counter();
        System.out.println("State before: " + counter.snapshot());

        method.invoke(counter);
        System.out.println("State after invoke: " + counter.snapshot());

        field.setAccessible(true);
        System.out.println("Read field: " + field.get(counter));

        field.set(counter, "DONE");
        System.out.println("State after field.set: " + counter.snapshot());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ReflectionBoundaryDemo.java
java ReflectionBoundaryDemo
~~~

Kết quả chuẩn:

~~~text
Class: Counter
Field: status (String)
Method: advance -> void
Annotation: demo
State before: NEW:0
advance executed
State after invoke: NEW:1
Read field: NEW
State after field.set: DONE:1
~~~

Giải thích theo từng mốc:

1. `getDeclaredField`, `getDeclaredMethod`, `getAnnotation` và các lời gọi lấy tên/kiểu trả về đều phục vụ **quan sát metadata**. Chúng không gọi `advance()`, nên không có dòng `advance executed` trong phần đầu.
2. `new Counter()` là bước **tạo object bằng Java thông thường**. `counter.snapshot()` là lời gọi method thông thường để kiểm tra trạng thái, không phải metadata inspection.
3. `method.invoke(counter)` thực thi `advance()`, tăng `count` từ `0` lên `1` và in ra thông báo.
4. `field.setAccessible(true)` cho phép ví dụ này truy cập field `private`; nó không đổi chuỗi `status`.
5. `field.get(counter)` đọc giá trị đang tồn tại (`NEW`); `field.set(counter, "DONE")` mới đổi thành `DONE`.

Ví dụ dùng một lớp lồng nhau trong cùng file nên thao tác truy cập private ở đây hoạt động trên Java 17+. Khi phản chiếu vào lớp thuộc một module khác, `setAccessible(true)` có thể ném `InaccessibleObjectException` nếu package chưa được mở phù hợp; không nên xem Reflection là cách vô điều kiện vượt qua đóng gói.

## 4. Đọc metadata khác với khởi tạo lớp

Phân biệt thêm ba khái niệm dễ bị gộp chung:

- **Nạp (loading):** JVM tìm và định nghĩa biểu diễn của lớp.
- **Liên kết (linking):** JVM xác minh, chuẩn bị và có thể phân giải tham chiếu.
- **Khởi tạo (initialization):** chạy static initializer và các phép gán khởi tạo tĩnh theo quy tắc Java.

Tham chiếu `SomeType.class` hoặc truy vấn metadata qua `Class` thông thường không tự khởi tạo lớp đó. Ngược lại, `Class.forName("ten.day.du")` một tham số **mặc định yêu cầu khởi tạo lớp**. Điều này rất quan trọng nếu static initializer mở kết nối, thay đổi cấu hình hoặc ghi log.

File `InitializationBoundaryDemo.java` minh họa:

~~~java
public class InitializationBoundaryDemo {
    static class Target {
        static {
            System.out.println("Target initialized");
        }
    }

    public static void main(String[] args) throws Exception {
        Class<?> type = Target.class;
        System.out.println("Class literal resolved");

        type.getDeclaredFields();
        System.out.println("Metadata inspected");

        Class.forName(Target.class.getName());
        System.out.println("Class.forName completed");
    }
}
~~~

~~~bash
javac InitializationBoundaryDemo.java
java InitializationBoundaryDemo
~~~

~~~text
Class literal resolved
Metadata inspected
Target initialized
Class.forName completed
~~~

Trong chương trình này, dòng khởi tạo tĩnh chỉ xuất hiện ở bước `Class.forName`. Nếu cần lấy `Class` từ tên lớp mà **chưa yêu cầu khởi tạo**, có thể sử dụng overload `Class.forName(className, false, classLoader)`; vẫn cần xử lý `ClassNotFoundException` và các lỗi nạp/liên kết có thể xảy ra. Không suy diễn rằng mọi API đọc thông tin hoặc mọi cách lấy `Class` đều tuyệt đối không có tác dụng phụ ở cấp JVM.

## 5. Biết rõ chính xác mình đang quan sát gì

### 5.1. Metadata của lớp khác với trạng thái của instance

`Field.getType()` nói field **được khai báo** có kiểu nào; `Field.get(obj)` đọc **giá trị hiện tại** trên object tương ứng. Một metadata field có thể được dùng để đọc nhiều instance khác nhau:

~~~java
Field statusField = Counter.class.getDeclaredField("status");
statusField.setAccessible(true);
Counter first = new Counter();
Counter second = new Counter();
statusField.set(first, "DONE");

System.out.println(statusField.get(first));  // DONE
System.out.println(statusField.get(second)); // NEW
~~~

Đoạn trên chỉ là phần **minh họa thêm trong phạm vi lớp `ReflectionBoundaryDemo`**, không phải một chương trình độc lập; cần các import, khai báo `Counter` và ngữ cảnh truy cập ở ví dụ trước. Hai instance có cùng cấu trúc field nhưng giữ giá trị riêng. Dòng `set` chỉ thay đổi `first`, không tác động `second`.

### 5.2. Khai báo trực tiếp và thành viên kế thừa

| API | Thành viên nhìn thấy |
| --- | --- |
| `getDeclaredFields()` / `getDeclaredMethods()` | Các field/method được **khai báo trực tiếp trong chính lớp**, kể cả private; không gom các thành viên kế thừa. |
| `getFields()` / `getMethods()` | Các field/method **public** có thể truy cập trong lớp và phần kế thừa (bao gồm thành viên public phù hợp từ interface). |
| `getDeclaredConstructors()` | Constructor của lớp đang xét; constructor không được kế thừa. |
| `getConstructors()` | Các constructor public của lớp đang xét. |

Lưu ý `getDeclaredMethods()` có thể bao gồm method tổng hợp (`synthetic`) hoặc bridge method do compiler sinh ra. Trước khi hiển thị metadata cho người học/người dùng, cân nhắc `Method.isSynthetic()`, `Method.isBridge()`, `Modifier` và các annotation cần thiết. **Không dựa vào thứ tự** mảng trả về từ `getDeclaredFields()` hay `getDeclaredMethods()`; nếu cần output ổn định, hãy tự sắp xếp.

### 5.3. Annotation mô tả, không mặc nhiên thực thi hành vi

Annotation có `@Retention(RetentionPolicy.RUNTIME)` mới đọc được ở runtime bằng Reflection. Đọc annotation không tự biến nội dung annotation thành luật xử lý. Ví dụ annotation `@Topic("demo")` trong chương trình chỉ cung cấp chuỗi `demo`; chính mã dùng annotation (framework hoặc ứng dụng) mới quyết định có đăng ký bean, chạy kiểm tra hay gọi hàm hay không. `getAnnotations()` và `getDeclaredAnnotations()` còn khác nhau về cách xét phần tử được kế thừa theo quy tắc `@Inherited` đối với annotation của lớp.

## 6. Ứng dụng: tách pha khám phá và pha thực thi

Giả sử xây công cụ liệt kê command trên một plugin:

1. **Pha khám phá:** dùng `Class`, `Method`, annotation và modifier để xác định tên command, số tham số, kiểu trả về; kiểm tra chữ ký và xây menu lựa chọn.
2. **Pha kiểm tra:** xác minh quyền chạy, dữ liệu đầu vào, phạm vi plugin được phép, tình trạng đối tượng và cách xử lý lỗi.
3. **Pha thực thi:** chỉ khi có yêu cầu hợp lệ mới tạo đối tượng (nếu cần) và gọi `Method.invoke`.

Cách phân pha này giúp ứng dụng **hiển thị tài liệu hoặc liệt kê API** mà không vô ý kích hoạt hành động. Đặc biệt, UI “xem cấu trúc lớp” không nên gọi thử mọi method để khám phá kết quả: getter cũng có thể tính toán nặng, ghi cache, đọc file hoặc ném exception. Tên bắt đầu bằng `get` không bảo đảm một method không có side effect.

Trong dependency injection, serializer, ORM hoặc framework kiểm thử, việc **quét annotation/field** thường là bước mô tả; **khởi tạo object, gọi lifecycle callback, đọc/ghi field** là những bước tiếp theo có ngữ nghĩa runtime khác. Khi debug, hãy xác định chính xác bước nào đã xảy ra.

## 7. Lỗi thường gặp và giới hạn thực tế

- **Nhầm “tìm method” với “gọi method”:** `getMethod`/`getDeclaredMethod` không gọi method đích. Muốn gọi phải dùng `invoke`, hoặc cú pháp gọi Java thông thường.
- **Nhầm “field metadata” với “field value”:** `getDeclaredField` cho tên, kiểu, modifier và annotation; `Field.get` đọc giá trị runtime; `Field.set` ghi giá trị runtime.
- **Bỏ qua side effect của khởi tạo:** `Class.forName(String)`, truy cập một số thành viên `static`, tạo object hoặc gọi method có thể kích hoạt khởi tạo lớp. “Chỉ đang khám phá” cần được kiểm chứng bằng API thực tế.
- **Giả định private luôn truy cập được:** việc tìm thấy private member không có nghĩa là được đọc/ghi/gọi. `setAccessible` có thể thất bại với các module đóng; ưu tiên public API và thiết kế quyền truy cập tường minh.
- **Coi Reflection là miễn kiểm tra kiểu:** `Method.invoke` phải nhận đúng receiver, số và kiểu đối số; `Field.set` phải nhận giá trị phù hợp. Các lời gọi có thể ném `IllegalAccessException`, `IllegalArgumentException` hoặc `InvocationTargetException`; lỗi từ method được gọi thường nằm trong `InvocationTargetException.getCause()`.
- **Đoán thứ tự metadata:** API trả các mảng field/method không bảo đảm thứ tự nguồn. Hãy sắp xếp nếu cần kết quả determinism.
- **Sửa field không nên sửa:** không coi Reflection là cơ chế hợp lệ để thay mọi field `final`, invariant, field ẩn hoặc cấu trúc nội bộ của JDK. Thay đổi trực tiếp có thể phá tính nhất quán của đối tượng và vướng giới hạn truy cập.
- **Đồng nhất annotation với hành vi:** annotation cung cấp dữ liệu mô tả; logic xử lý annotation mới thực hiện tác vụ thực tế.

## 8. Checklist khi đọc hoặc viết mã Reflection

Trước mỗi lời gọi, tự trả lời:

1. Mình đang hỏi **lớp/thành viên được khai báo thế nào** (`Class`, `Field`, `Method`, annotation), hay đang lấy **giá trị của một instance** (`Field.get`)?
2. API này có **gọi constructor/method** hoặc **ghi giá trị** không (`newInstance`, `invoke`, `set`)?
3. Có khả năng **khởi tạo lớp**, kích hoạt static initializer, gọi lifecycle callback hoặc thực hiện I/O không?
4. Mình đã xử lý đúng **public/private, inherited/declared, module access, receiver và exception** chưa?
5. Nếu chỉ muốn xem metadata, có thể dừng ở các API lấy mô tả mà không tạo instance hay gọi code nghiệp vụ không?

**Tự kiểm tra:** Trong ví dụ `ReflectionBoundaryDemo`, nếu bỏ hai dòng `method.invoke(counter)` và `field.set(counter, "DONE")` (cùng các dòng in trạng thái chỉ dùng để quan sát sau chúng), thì không có thao tác Reflection nào làm tăng `count` hoặc đổi `status`. Việc thu thập `Method` và `Field` vẫn hoàn toàn thực hiện được.

**Kết luận:** Reflection giúp **biết chương trình được cấu trúc như thế nào**; việc **cho chương trình làm gì** thuộc về các lời gọi thực thi hoặc thay đổi trạng thái. Tách rõ hai lớp trách nhiệm này giúp viết công cụ introspection đáng tin cậy, debug chính xác và kiểm soát tác dụng phụ.