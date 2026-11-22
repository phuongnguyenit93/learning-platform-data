# Giữ constructor, setter và bất biến đối tượng làm ranh giới thiết kế khi dùng Reflection

Một `Field` có thể ghi được bằng Reflection nhưng điều đó chưa có nghĩa thao tác ghi là **hợp lệ về nghiệp vụ**. Ví dụ `Registration` yêu cầu sức chứa từ 1 đến 10, số người không vượt sức chứa và danh sách không bị sửa từ bên ngoài. Gán trực tiếp `capacity = 0` phá invariant dù JVM chấp nhận thao tác.

Bài này tập trung vào **ranh giới trạng thái**: tạo qua constructor/factory có kiểm tra, cập nhật qua setter hoặc domain method duy trì invariant, chỉ công bố object sau validation. Với quan hệ nhiều field, hai setter độc lập có thể để lộ trạng thái trung gian sai; một thao tác atomic theo hợp đồng domain thường phù hợp hơn. Ví dụ phản chứng dùng `Field.setInt` để cho thấy vì sao khả năng truy cập không thay thế domain contract.

## 1. Constructor, setter và invariant có vai trò khác nhau

**Invariant** là điều kiện mà một đối tượng được thiết kế để duy trì trong suốt vòng đời quan sát được của nó. Ví dụ một lớp `Registration` có:

- `code` không phải `null` hoặc chuỗi trắng; định danh không thay đổi sau khi tạo.
- `capacity` nằm trong khoảng `1..10`.
- `attendees.size() <= capacity`.
- Danh sách người tham dự không được để mã gọi bên ngoài sửa lén mà không thông qua phương thức kiểm tra.

Những quy tắc này được kiểm tra ở những ranh giới sau:

| Ranh giới | Trách nhiệm | Ví dụ |
|---|---|---|
| Constructor hoặc static factory | Nhận đủ giá trị tối thiểu, kiểm tra trước khi đối tượng được sử dụng | `new Registration("JAVA", 3)` |
| Setter có chủ đích | Kiểm tra một phép thay đổi có hợp lệ so với trạng thái hiện tại | `setCapacity(2)` |
| Phương thức nghiệp vụ | Bảo vệ quy tắc phụ thuộc nhiều field và diễn đạt ý định rõ | `register("Lan")`, `reschedule(start,end)` |
| Getter / view | Cung cấp cách quan sát trạng thái mà không lộ mutable internals | `List.copyOf(...)`, danh sách không sửa được |
| Reflection adapter | Tìm chữ ký, chuyển đối số, **gọi constructor/method công khai** rồi giữ nguyên lỗi | `Constructor.newInstance(...)`, `Method.invoke(...)` |

Một setter công khai **không tự động tốt** chỉ vì có tiền tố `set`. Setter cho phép tùy ý sửa `id` hoặc sửa từng field của một invariant liên trường có thể khiến đối tượng luôn có lúc ở trạng thái sai. Những dữ liệu không nên đổi hãy giữ `final` hoặc chỉ cung cấp một phép cập nhật nguyên khối có validation. Với domain model, ý nghĩa của phương thức thường quan trọng hơn chuẩn tên JavaBeans.

## 2. Ba đường đi qua Reflection và hậu quả

Giả sử runtime đã có `Class<?>` và dữ liệu cấu hình:

~~~text
Đầu vào ngoài (cấu hình / JSON / plugin metadata)
                     |
                     v
       Chuẩn hóa + validate cấu trúc
                     |
          Chọn ranh giới domain
           /                  \
          v                    v
 Constructor/factory      Setter/method
          |                    |
          +---------+----------+
                    v
       Đối tượng với invariant hợp lệ
                    |
                    v
             Hoạt động tiếp
~~~

### Đường nên ưu tiên: gọi constructor phù hợp

~~~java
Constructor<Registration> constructor =
        Registration.class.getConstructor(String.class, int.class);
Registration registration = constructor.newInstance("JAVA", 3);
~~~

Đây là **đoạn trích** từ chương trình đầy đủ ở mục 3. `getConstructor(...)` chỉ tìm **constructor public** có đúng danh sách **kiểu tham số**. `int.class` khác `Integer.class` trong bước tìm chữ ký, dù `newInstance(...)` có thể nhận đối số `Integer` được unbox khi gọi constructor nhận `int`.

Khi constructor tự ném `IllegalArgumentException` vì dữ liệu sai, `Constructor.newInstance` ném `InvocationTargetException` có `getCause()` là exception gốc. Công cụ không được bỏ qua sự từ chối rồi cố gán field bằng đường khác.

### Đường cập nhật: gọi setter hoặc method công khai

~~~java
Method method = Registration.class.getMethod("setCapacity", int.class);
method.invoke(registration, 2);
~~~

`getMethod(...)` tìm method public với tên và kiểu tham số tương ứng. `Method.invoke(...)` thực thi **logic trong setter**: khoảng hợp lệ, tương quan với các field khác, cập nhật và những hậu điều kiện mà lớp tự đảm bảo. Nếu setter từ chối, lỗi target được bọc trong `InvocationTargetException`; việc unwrap cause phục vụ chẩn đoán, không tạo lý do để bỏ validation.

### Đường rủi ro: ghi thẳng field

~~~java
Field field = Registration.class.getDeclaredField("capacity");
field.setAccessible(true); // Chỉ minh họa trong môi trường có quyền phù hợp
field.setInt(registration, 0);
~~~

**Không dùng đoạn này làm chiến lược cập nhật dữ liệu ứng dụng.** Nếu quyền truy cập sâu được cho phép, `Field.setInt(...)` ghi giá trị vào field mà **không gọi `setCapacity`**. Đối tượng có thể mang `capacity = 0` dù setter cấm. Đây là lỗi ở cấp **hợp đồng domain**, ngay cả khi thao tác Reflection thành công về mặt kỹ thuật.

`getDeclaredField` chỉ giúp tìm field được khai báo trực tiếp trên lớp, kể cả field private. Nó không có nghĩa hệ thống cho phép đọc/ghi field đó trong mọi cấu hình Java Platform Module System (JPMS). `setAccessible(true)` có thể bị từ chối nếu package trong named module khác không được mở (`opens`). Quyền truy cập sâu cũng không có nghĩa có quyền sửa mọi `final`; đặc biệt record fields, static final fields và final fields của hidden classes có giới hạn riêng. Đừng coi `setAccessible` là bước mặc định của mọi công cụ.

## 3. Chương trình Java 17+ hoàn chỉnh, có cả ví dụ phản chứng

Tạo file **`ConstructionBoundaryDemo.java`** với toàn bộ mã sau. Trong chương trình, `Registration` là lớp `public static final` lồng trong một chương trình độc lập; invariant được định nghĩa trong constructor, `setCapacity` và `register`. Cuối chương trình có **một thử nghiệm cố ý ghi thẳng field** để chứng minh setter đã bị bypass; sau đó chương trình phục hồi trạng thái qua setter.

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

public class ConstructionBoundaryDemo {
    public static final class Registration {
        private final String code;
        private int capacity;
        private List<String> attendees = List.of();

        public Registration(String code, int capacity) {
            if (code == null || code.isBlank()) {
                throw new IllegalArgumentException("code required");
            }
            this.code = code;
            setCapacity(capacity);
        }

        public void setCapacity(int newCapacity) {
            if (newCapacity < 1 || newCapacity > 10) {
                throw new IllegalArgumentException("capacity must be 1..10");
            }
            if (newCapacity < attendees.size()) {
                throw new IllegalArgumentException("capacity below attendees");
            }
            capacity = newCapacity;
        }

        public void register(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name required");
            }
            if (attendees.size() == capacity) {
                throw new IllegalStateException("full");
            }
            List<String> next = new ArrayList<>(attendees);
            next.add(name);
            attendees = List.copyOf(next);
        }

        public String getCode() {
            return code;
        }

        public int getCapacity() {
            return capacity;
        }

        public List<String> getAttendees() {
            return attendees;
        }

        public boolean validState() {
            return capacity >= 1 && capacity <= 10
                    && attendees.size() <= capacity;
        }
    }

    @FunctionalInterface
    interface ReflectionAction {
        void run() throws ReflectiveOperationException;
    }

    static void showRejection(String label, ReflectionAction action)
            throws ReflectiveOperationException {
        try {
            action.run();
        } catch (InvocationTargetException ex) {
            Throwable cause = ex.getCause();
            System.out.println(label + " -> " +
                    cause.getClass().getSimpleName() + ": " + cause.getMessage());
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Constructor<Registration> constructor =
                Registration.class.getConstructor(String.class, int.class);
        Method register = Registration.class.getMethod("register", String.class);
        Method setCapacity = Registration.class.getMethod("setCapacity", int.class);

        Registration r = constructor.newInstance("JAVA", 3);
        register.invoke(r, "Lan");
        register.invoke(r, "Minh");
        System.out.println("created = " + r.getCode() + ", " + r.getCapacity()
                + ", " + r.getAttendees() + ", valid=" + r.validState());

        showRejection("bad setter", () -> setCapacity.invoke(r, 1));
        showRejection("bad constructor", () -> constructor.newInstance(" ", 3));

        try {
            r.getAttendees().add("An");
        } catch (UnsupportedOperationException ex) {
            System.out.println("external list mutation -> " +
                    ex.getClass().getSimpleName());
        }

        setCapacity.invoke(r, 2);
        System.out.println("setter success = " + r.getCapacity()
                + ", valid=" + r.validState());

        Field capacityField = Registration.class.getDeclaredField("capacity");
        capacityField.setAccessible(true);  // DEMO ONLY: breaks encapsulation.
        capacityField.setInt(r, 0);          // Deliberately bypasses setter.
        System.out.println("field bypass = " + r.getCapacity()
                + ", valid=" + r.validState());

        setCapacity.invoke(r, 2);
        System.out.println("restored = " + r.validState());
    }
}
~~~

Biên dịch và chạy trong thư mục có file:

~~~bash
javac --release 17 -encoding UTF-8 ConstructionBoundaryDemo.java
java ConstructionBoundaryDemo
~~~

**Stdout đã kiểm chứng khi chạy Java 17-compatible trong unnamed module:**

~~~text
created = JAVA, 3, [Lan, Minh], valid=true
bad setter -> IllegalArgumentException: capacity below attendees
bad constructor -> IllegalArgumentException: code required
external list mutation -> UnsupportedOperationException
setter success = 2, valid=true
field bypass = 0, valid=false
restored = true
~~~

**Diễn giải từng nhóm kết quả:**

1. Constructor kiểm tra `code` rồi gọi `setCapacity`. Hai lần `register.invoke(...)` thêm người vào danh sách mới, cập nhật lại bằng `List.copyOf(...)`; trạng thái ban đầu hợp lệ.
2. `setCapacity.invoke(r, 1)` chạy setter, nhưng một nhóm đã có hai người nên bị từ chối. `InvocationTargetException.getCause()` là `IllegalArgumentException("capacity below attendees")`. Không có thay đổi một phần vào `capacity`.
3. `constructor.newInstance(" ", 3)` thực thi constructor; mã rỗng khiến constructor từ chối. Đây là trường hợp **target constructor** ném exception, được wrapper Reflection giữ cause.
4. `getAttendees().add("An")` thất bại vì danh sách trả về không sửa được. Nếu getter lộ `ArrayList` nội bộ có thể sửa, caller đã có cách phá invariant **không cần Reflection**.
5. `setCapacity.invoke(r, 2)` thành công vì `2` đủ cho hai người, sau đó `validState()` tiếp tục bằng `true`.
6. Ví dụ phản chứng `Field.setInt(r, 0)` ghi trực tiếp vào `capacity`, không gọi logic setter, kết quả `valid=false`. Đoạn cuối khôi phục bằng setter hợp lệ.
7. Chương trình chạy trong một unnamed module. Trong named-module application, đoạn `setAccessible(true)` có thể thất bại; điều đó càng nhấn mạnh rằng công cụ không nên thiết kế dựa trên việc luôn có quyền mở private field.

`showRejection` chỉ bắt `InvocationTargetException` của ví dụ. Trong một binder thực tế, cần xử lý riêng `NoSuchMethodException`, `IllegalAccessException`, `InstantiationException`, `IllegalArgumentException` do sai đối số gọi Reflection, và những lỗi liên quan đến hệ thống module. Không gom mọi lỗi vào một nhãn “validation thất bại”.

## 4. Ranh giới thiết kế cho công cụ Reflection

Khi viết mapper, DI container nhỏ, plugin loader hoặc tool nhập cấu hình, nên ra quyết định theo **hợp đồng khởi tạo/cập nhật**.

| Nhu cầu | Hướng ưu tiên | Tránh |
|---|---|---|
| Tạo đối tượng có trường bắt buộc | Constructor tham số, named factory, builder có bước `build()` kiểm tra | Tạo object rỗng rồi nhồi private fields |
| Đổi một giá trị độc lập | Method công khai có kiểm tra, ví dụ `setCapacity(...)` | `Field.set(...)` bỏ qua setter |
| Đổi nhiều field phụ thuộc nhau | Method cập nhật nguyên khối, tạo immutable object mới | Gọi nhiều setter làm lộ trạng thái trung gian sai |
| Nạp một value object bất biến | Constructor/canonical constructor của record | Ghi trực tiếp `final` field sau khi dựng |
| Điền collection | Chuyển đổi dữ liệu đầu vào và sao chép bảo vệ | Giữ tham chiếu `List` mutable của caller |
| Schema thiếu method cần thiết | Báo mapping không hỗ trợ, hoặc dùng adapter do chủ lớp định nghĩa | Thử `setAccessible(true)` để “lách” hợp đồng |
| Sai giá trị domain | Trả validation error giữ cause và tên property | Bỏ validation để cố tạo object |
| DTO chứa dữ liệu thuần | Có thể dùng binder/Bean convention đã thống nhất | Áp dụng cùng giả định cho mọi domain entity |

**Metadata không phải hợp đồng đủ mạnh.** Biết field có kiểu `int` chỉ bảo đảm điều kiện kiểu ở mức Java; nó không nói rằng số chỗ phải thuộc khoảng nào hoặc phụ thuộc bao nhiêu người đã đăng ký. Kể cả annotation `@NotNull` hoặc `@Min`, tool phải biết rõ lúc nào và bằng cơ chế nào validator được chạy. Đọc annotation bằng Reflection **không tự kích hoạt validation**. Nếu công cụ quyết định dùng Bean Validation, nó cần gọi validator theo kiến trúc thực tế và kiểm soát thời điểm object trở nên visible.

Một mapping pipeline hợp lý:

~~~text
Untrusted input
    |
    v
Parse theo schema -> chuyển kiểu -> lỗi cấu trúc nếu sai
    |
    v
Chọn constructor/factory theo contract đã cho phép
    |
    v
Gọi constructor -> validation ở domain
    |
    +-- Reject -> trả lỗi, giữ cause, không publish object
    |
    v
Gọi các method cập nhật cho phép (nếu có)
    |
    +-- Reject -> bỏ object chưa publish / rollback theo kiến trúc
    |
    v
Xác nhận object hợp lệ, sau đó mới publish
~~~

Nếu một tool tạo object thành công rồi nhiều setter về sau gây lỗi, tool phải đảm bảo **đối tượng chưa được công bố hoặc lưu vào hệ thống** trước khi hoàn tất. Không có transaction tự động chỉ nhờ dùng Reflection. Với update trên object đã tồn tại và được chia sẻ, cần thiết kế atomic operation hoặc transaction/domain command phù hợp; nếu fail giữa chừng có thể còn trạng thái trung gian.

## 5. Bất biến phụ thuộc nhiều field: setter rời rạc có thể chưa đủ

Xét khoảng thời gian:

~~~java
public record TimeWindow(LocalDate start, LocalDate end) {
    public TimeWindow {
        if (start == null || end == null || end.isBefore(start)) {
            throw new IllegalArgumentException("invalid window");
        }
    }
}
~~~

Đây là **mảnh mã minh họa** cần đặt trong một tệp Java hợp lệ và `import java.time.LocalDate;` nếu chạy riêng. Record có canonical constructor kiểm tra rằng `start <= end`. Khi cần cập nhật, tạo một record mới qua constructor hợp lệ:

~~~java
TimeWindow next = new TimeWindow(newStart, newEnd);
~~~

Nếu thiết kế một mutable class có cả `setStart` và `setEnd` độc lập, thứ tự gọi có thể tạm thời vi phạm `start <= end`. Ví dụ đang là ngày 10 đến ngày 20, muốn đổi thành ngày 21 đến ngày 30: gọi `setStart(21)` trước sẽ có lúc `start > end`; gọi `setEnd(30)` trước có thể được nhưng phụ thuộc vào dữ liệu. Một phương thức `reschedule(newStart, newEnd)` kiểm tra cặp giá trị **trước khi commit cả hai** sẽ rõ ràng hơn.

Bài học cho công cụ tạo object từ nhiều field: **“Có setter” không đồng nghĩa “có thể set theo thứ tự tùy ý”.** Công cụ phải biết protocol được định nghĩa bởi chủ lớp. Constructor nhận đủ tham số, immutable value object hoặc builder thường phù hợp hơn khi invariant là quan hệ liên trường.

### Đừng gọi method có thể override từ constructor một cách vô ý

Trong demo, `Registration` là `final` nên không có subclass override `setCapacity`. Nhưng ở một lớp **không `final`**, gọi setter có thể override từ constructor sẽ dispatch sang method của subclass trước khi phần subclass được khởi tạo đầy đủ. Đây có thể là nguồn lỗi hoặc rò rỉ `this`.

Thiết kế tổng quát an toàn hơn: constructor dùng **private helper không override được** để validate, rồi gán field; setter gọi lại cùng helper ấy. Ví dụ mảnh minh họa:

~~~java
private static int requireCapacity(int value) {
    if (value < 1 || value > 10) {
        throw new IllegalArgumentException("capacity must be 1..10");
    }
    return value;
}

// Bên trong constructor hoặc setter:
this.capacity = requireCapacity(value);
~~~

Đoạn trên không biên dịch độc lập vì giả sử nằm trong lớp có field `capacity` và biến `value`. Không nên xây abstraction Reflection buộc mọi class phải có no-args constructor chỉ để gán field sau đó.

## 6. Setter, field, accessor và Java Platform Module System

Các API Reflection thường gặp:

| API | Phạm vi tìm | Đảm bảo gì? |
|---|---|---|
| `type.getConstructor(paramTypes)` | Constructor **public** với chữ ký chính xác | Có metadata constructor; việc gọi còn chịu access rules |
| `type.getDeclaredConstructor(paramTypes)` | Constructor được khai báo trong type, bất kể modifier | Có metadata; có thể không gọi được nếu non-public |
| `type.getMethod(name, paramTypes)` | Method **public** có thể thấy, bao gồm inherited phù hợp | Có metadata method; `invoke` vẫn có thể thất bại |
| `type.getDeclaredMethod(name, paramTypes)` | Method khai báo trực tiếp trong type | Bao gồm non-public; không tự cấp quyền gọi |
| `type.getField(name)` | Field public có thể thấy | Không chạy setter khi `Field.set` |
| `type.getDeclaredField(name)` | Field khai báo trực tiếp, gồm private | Không tự cấp quyền đọc/ghi hoặc validation |
| `AccessibleObject.trySetAccessible()` | Thử mở quyền truy cập nếu runtime cho phép | Trả `false` khi không thể mở, không biến member thành domain API |

**JPMS:** `exports` và `opens` là hai khái niệm khác nhau. Package `exports` cho phép sử dụng public API từ module khác theo điều kiện tương ứng; deep Reflection vào non-public members của module khác thường cần package `opens` tới module công cụ. Thêm `--add-opens` cho JVM có thể giúp một trường hợp tích hợp cụ thể, nhưng là quyết định triển khai/module policy, **không phải cách sửa mặc định** khi công cụ không tìm thấy setter.

**`final` không phải giấy phép ghi ngược:** Từ `Field` Java 17, một số loại final field không thể sửa qua Reflection, chẳng hạn `static final`, final fields trong record và final fields trong hidden class. Với những final instance field khác, Javadoc cảnh báo việc sửa sau khi object đã được công bố có thể cho kết quả không dự đoán được. Thiết kế công cụ không nên dựa vào sửa final field để “re-hydrate” domain entity.

**`private` không tự làm object bất biến:** Nếu getter trả lại một `List` có thể sửa do object giữ nội bộ, caller vẫn có thể thay đổi dữ liệu mà không cần Reflection. Trong demo, `List.copyOf` tạo danh sách không sửa được để giữ ranh giới; khi nhận input mutable, có thể chủ động tạo snapshot thay vì giữ tham chiếu của caller.

### Method signature phải đúng, không suy luận từ tên

Reflection tìm method theo **tên và mảng kiểu tham số**, ví dụ `getMethod("setCapacity", int.class)`. `getMethod("setCapacity", Integer.class)` sẽ không tự khớp với tham số `int`. Giá trị đưa cho `Method.invoke` có thể trải qua invocation conversions như unboxing nhưng bước tra cứu chữ ký là riêng biệt. Với overload, tự lấy method đầu tiên có tên “set...” có thể dẫn tới chọn sai contract. Một binder nên chọn method theo schema rõ ràng hoặc fail với thông báo có ích.

## 7. Validation và exception không được phép biến mất

Nếu constructor hay setter từ chối dữ liệu, thao tác phản chiếu sẽ có ngoại lệ ở tầng gọi:

~~~java
try {
    method.invoke(target, value);
} catch (InvocationTargetException ex) {
    Throwable cause = ex.getCause();
    throw new IllegalStateException("Could not update property", cause);
}
~~~

Đây là **đoạn xử lý minh họa**: các biến `method`, `target`, `value` giả định đã có và cần xử lý thêm `IllegalAccessException`. Cách bọc trong `IllegalStateException(String, Throwable)` giữ cause, giúp log và caller truy ngược lỗi domain. Có thể ném lại chính loại ngoại lệ gốc nếu hợp đồng API cho phép. Không lấy mỗi `cause.getMessage()` rồi tạo một exception mới không có cause.

Phân biệt:

- **Sai schema hoặc conversion:** JSON string `"abc"` không đổi được thành `int`, method không tồn tại hoặc receiver sai kiểu. Đây là lỗi adapter/binding; `Method.invoke` có thể ném `IllegalArgumentException` trực tiếp vì đối số sai.
- **Đầu vào đúng kiểu nhưng trái domain invariant:** `setCapacity(0)` tồn tại, đối số `int` hợp lệ về mặt kiểu, nhưng setter ném `IllegalArgumentException("capacity must be 1..10")`; Reflection bọc lỗi target trong `InvocationTargetException`.
- **Thiếu quyền truy cập:** `IllegalAccessException` hoặc `InaccessibleObjectException` liên quan đến accessibility/module boundary. Không sửa bằng cách bỏ validator.
- **Lỗi hệ thống:** `LinkageError`, `ExceptionInInitializerError` hoặc `Error` có thể không được xử lý như validation errors; đừng bắt `Throwable` rồi giả như chỉ một property không hợp lệ.

Nếu binder trả danh sách lỗi cho người dùng, nên ghi **tên property, kiểu mong đợi, giá trị được phép hoặc message domain an toàn**, đồng thời giữ cause cho log nội bộ khi thích hợp. Không công khai stack trace hoặc bí mật cấu hình ra phản hồi bên ngoài.

## 8. Lựa chọn thiết kế theo loại đối tượng

**DTO / JavaBean thuần:** Có thể phù hợp với no-args constructor và setters, nếu chính lớp đó chủ ý là cấu trúc nhận dữ liệu. Nếu áp dụng validation, cần chạy rõ bước validate sau binding và trước publish/execute.

**Domain entity:** Ưu tiên constructor/factory cho trạng thái bắt buộc và domain methods thay vì setter đại trà. Entity có thể bị ràng buộc bởi vòng đời, transaction, aggregate invariants; một generic Reflection binder ít khi biết hết.

**Immutable value object / record:** Constructor/canonical constructor và defensive copy bảo đảm mỗi object được tạo với trạng thái đúng. Khi cần đổi, tạo object mới; không “chọc” field `final`. Với record có component là `List`, cần chủ động `List.copyOf` trong constructor nếu muốn chống sửa collection.

**Third-party class không có setter:** Đọc API của thư viện, tìm constructor/builder/factory hoặc adapter chính thức. Không coi thiếu setter là lỗi cần khắc phục bằng deep field access.

**Serialization và ORM:** Một số framework có cơ chế khởi tạo đặc thù, proxy, bytecode enhancement hoặc field access theo mapping công bố. Đây là những lựa chọn có đánh đổi, **không suy ra thành quy tắc cho mọi công cụ Reflection**. Nếu framework chủ động sử dụng field access, trách nhiệm bảo đảm invariant ở điểm hợp lệ hóa/lifecycle được chỉ định phải được thiết kế, tài liệu hóa và kiểm thử.

**Plugin loader / configurable service:** Ưu tiên interface/factory contract hoặc `ServiceLoader` khi có thể; chỉ dùng Reflection tạo lớp từ tên runtime nếu kiểm soát nguồn class và xác minh contract. Gọi constructor công khai đáng tin cậy giúp tránh tạo instance ở trạng thái nửa vời.

## 9. Checklist cho người viết công cụ Reflection

Trước khi hỗ trợ một loại đối tượng mới, xác định:

1. **Đối tượng hợp lệ là gì?** Liệt kê invariant của từng field và quan hệ giữa các field.
2. **Ai sở hữu validation?** Constructor, factory, domain method, validator ngoài, hay một kết hợp được định nghĩa rõ?
3. **Bước nào cho phép publish object?** Chỉ công bố sau khi mọi bước tạo/cập nhật và validation cần thiết thành công.
4. **Tool dùng API nào?** Ưu tiên public constructor/method hợp lệ; không fallback sang private field writes khi bị từ chối.
5. **Có alias mutable không?** Kiểm tra defensive copies của collections, arrays, date/time mutable types và nested objects nếu cần.
6. **Có nhiều field phụ thuộc nhau không?** Dùng method atomic, constructor đủ tham số hoặc builder thay vì setter theo thứ tự ngẫu nhiên.
7. **Có quyền JPMS không?** Xác minh access trước khi gọi, thông báo rõ thiếu access; không dựa vào `setAccessible` mặc định.
8. **Ngoại lệ có giữ cause không?** Tách lỗi schema/Reflection và validation domain, không nuốt lỗi target.
9. **Cần tránh áp đặt JavaBeans không?** Kiểu domain không nhất thiết phải lộ setter cho mọi property.
10. **Có kiểm thử trạng thái xấu không?** Xác nhận dữ liệu sai bị từ chối và object đã công bố không chuyển sang trạng thái bất hợp lệ.

### Bài tập áp dụng

1. Trong ví dụ `Registration`, thử `constructor.newInstance("JAVA", 0)`. Phân biệt exception ngoài cùng với cause và giải thích tại sao constructor gọi `setCapacity`.
2. Đổi `setCapacity.invoke(r, 1)` thành `Field.setInt(r, 1)` trong một test tách biệt. Bất biến nào bị vi phạm và vì sao?
3. Thay `getAttendees()` bằng cách trả trực tiếp một `ArrayList` mutable bên trong. Hãy mô tả cách caller có thể phá invariant mà không sử dụng Reflection.
4. Thiết kế lệnh `replaceAttendees(List<String>)` bảo đảm cả danh sách và số chỗ vẫn hợp lệ, chỉ commit khi kiểm tra xong.
5. Từ một cặp ngày `start/end`, viết một phương thức `reschedule(start,end)` kiểm tra cả hai trước khi cập nhật. Giải thích điểm yếu của hai setter độc lập.
6. Khi chạy trong named module, hãy mô tả vì sao `getDeclaredField` có thể thành công nhưng `trySetAccessible()` lại trả `false`.
7. Đối với một record chứa `List<String>`, viết canonical constructor kiểm tra dữ liệu và dùng `List.copyOf`. Thử sửa collection từ caller.

**Điểm cần nhớ:** Reflection giúp tìm và gọi code tại runtime; nó **không thay thế** contract của lớp. Với object có bất biến, constructor/factory và các phương thức cập nhật có kiểm tra là ranh giới chính. Tránh biến `Field.set` thành lối tắt khi model từ chối một thay đổi, và thiết kế thời điểm publish, tính nguyên tử, defensive copy, access policy cùng chẩn đoán exception một cách có chủ đích.

### Tài liệu tham khảo

- [Javadoc Java 17 — `Constructor.newInstance`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...))
- [Javadoc Java 17 — `Method.invoke`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#invoke(java.lang.Object,java.lang.Object...))
- [Javadoc Java 17 — `Field` và giới hạn ghi final field](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html)
- [Javadoc Java 17 — `AccessibleObject` và giới hạn JPMS](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Javadoc Java 17 — `List.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection))
