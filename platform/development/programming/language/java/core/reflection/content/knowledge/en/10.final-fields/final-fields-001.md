# Phân biệt đọc `final` field với thay đổi `final` field trong Java Reflection

`final` thể hiện ý định **giá trị của một biến không được gán lại sau khi hoàn tất khởi tạo theo quy tắc ngôn ngữ Java**. Khi dùng Reflection, người học thường nhầm rằng nếu đã đọc được một field `private final` bằng `Field#get(...)` thì cũng có thể thay đổi nó bằng `Field#set(...)`. Hai thao tác này có các điều kiện và giới hạn khác nhau.

**Trọng tâm của bài:** Reflection có thể cho phép **đọc** field `final` sau khi thỏa quy tắc truy cập; điều đó **không chứng minh** Reflection được phép **ghi** field `final`. Một số nhóm field `final` luôn thuộc loại không cho ghi thông qua `Field#set` dù đã bật quyền truy cập, còn việc ghi `final` instance thông thường là khả năng đặc biệt bị hạn chế ngày càng chặt hơn từ JDK 26.

## 1. `final` đảm bảo gì ở mức khai báo Java?

Một field được khai báo `final` chỉ có thể được gán theo các quy tắc khởi tạo cho phép:

~~~java
class Configuration {
    private final int timeoutSeconds;              // blank final
    private static final String PRODUCT = "Demo";  // static final

    Configuration(int timeoutSeconds) {
        this.timeoutSeconds = timeoutSeconds;
    }

    int timeoutSeconds() {
        return timeoutSeconds;
    }
}
~~~

Đây là **đoạn mã minh họa**, không có `main` độc lập. Sau khi constructor `Configuration` kết thúc, Java source thông thường không được viết `configuration.timeoutSeconds = 10;` vì field này là `final`.

Phân biệt:

- **`final` instance field:** mỗi instance có trạng thái riêng; giá trị thường được xác lập trong field initializer, instance initializer hoặc constructor.
- **`static final` field:** gắn với lớp thay vì một instance; chỉ được khởi tạo theo quy tắc cho static field.
- **`private` và `final` độc lập:** `private` chi phối quyền truy cập ở cấp Java, còn `final` chi phối khả năng gán. Một field có thể là `public final`, `private final`, `static final`, v.v.
- **`final` không làm đối tượng được tham chiếu trở nên bất biến sâu:** `private final List<String> names` giữ cố định **tham chiếu** sau khởi tạo bằng Java source, nhưng nếu danh sách có thể thay đổi thì `names.add(...)` vẫn có thể sửa nội dung.

Các đảm bảo của Java Memory Model dành cho `final` field giúp chương trình có mô hình khởi tạo đáng tin cậy. Việc thay đổi `final` bằng Reflection sau khởi tạo có thể phá vỡ các giả định của compiler/JVM và của những luồng đang đọc dữ liệu. Vì vậy không nên xem kỹ thuật mutation là cách cập nhật cấu hình thông thường.

## 2. Hai thao tác Reflection: đọc và ghi

Đối tượng `java.lang.reflect.Field` hỗ trợ cả metadata lẫn thao tác với giá trị:

| Nhu cầu | API | Điểm cần kiểm tra |
| --- | --- | --- |
| Nhận biết field có `final` | `Modifier.isFinal(field.getModifiers())` | Chỉ đọc modifier, **không** cho biết có thể ghi hay không |
| Tìm field không `public` | `type.getDeclaredField("name")` | Chỉ tìm metadata của field khai báo trực tiếp, không tự cấp quyền |
| Kiểm tra quyền truy cập hiện tại | `field.canAccess(target)` | Instance dùng object; static dùng `null` |
| Thử bật bỏ qua kiểm tra truy cập Java | `field.trySetAccessible()` | Trả `true`/`false`; không bảo đảm khả năng ghi field `final` |
| Đọc một field | `field.get(target)`, `getInt(target)`... | Cần đáp ứng quyền truy cập; trả giá trị tương ứng |
| Thử ghi một field | `field.set(target, value)`, `setInt(target, n)`... | Cần quyền ghi thực tế; `final` có thêm hạn chế và quy tắc phụ thuộc phiên bản JDK |

*Ghi nhớ:* có ít nhất **hai câu hỏi** khi dùng `Field`: có được **truy cập** thành viên qua Reflection hay không, và có được **sửa** chính field này hay không. Hai câu trả lời có thể lần lượt là "có" và "không".

### `getDeclaredField` chỉ tra cứu, chưa thao tác giá trị

~~~java
Field field = SomeType.class.getDeclaredField("value");
boolean isFinal = Modifier.isFinal(field.getModifiers());
~~~

Đây là **đoạn minh họa**, giả sử `SomeType` có field `value` và đã import `Field`, `Modifier`. Lời gọi `getDeclaredField` có thể trả đối tượng `Field` đại diện cho field `private final`. Nhưng `Field` là metadata, nên **không tự suy ra** rằng `get` hay `set` sau đó đã được cấp quyền.

## 3. Đọc `final` instance và `static final` field

Đọc field `final` qua Reflection về cơ bản tuân theo quy tắc truy cập của `Field`:

1. Lấy `Field` đúng đối tượng `Class<?>`. Dùng `getDeclaredField` nếu cần field `private` được khai báo trực tiếp.
2. Với **instance field**, truyền instance đúng loại vào `canAccess`/`get`. Với **static field**, truyền `null`.
3. Nếu chưa được phép truy cập theo trạng thái hiện tại, kiểm tra khả năng bật quyền bằng `trySetAccessible()` khi thật sự cần.
4. Khi đã được phép, gọi `get`, `getInt`, `getLong` hoặc phương thức đọc chuyên biệt. Đọc một field `final` **không làm thay đổi** giá trị của nó.

Lưu ý về Java modules: từ Java 9, `trySetAccessible()` có thể bị từ chối bởi ranh giới JPMS. Trong ví dụ của bài, tất cả lớp nằm trong **unnamed module của cùng class loader**, nên việc bật quyền sâu vào lớp ứng dụng được phép. Không nên mặc định kết quả này khi chuyển `Field` tới helper ở module khác hoặc truy cập module thư viện chưa mở package.

### Ví dụ chạy được: đọc ba loại `final` field

Tạo tệp **`ReadFinalDemo.java`**, dùng Java 17+:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Modifier;

class FinalData {
    private final int count;
    private static final String LABEL = "fixed";

    FinalData(int count) {
        this.count = count;
    }
}

record FinalRecord(int value) {}

public class ReadFinalDemo {
    public static void main(String[] args) throws ReflectiveOperationException {
        FinalData data = new FinalData(7);
        Field count = FinalData.class.getDeclaredField("count");
        System.out.println("Instance final: "
                + Modifier.isFinal(count.getModifiers()));
        System.out.println("Read before: " + count.canAccess(data));
        System.out.println("Open for read: " + count.trySetAccessible());
        System.out.println("Instance value: " + count.getInt(data));

        Field label = FinalData.class.getDeclaredField("LABEL");
        System.out.println("Static final: "
                + Modifier.isFinal(label.getModifiers()));
        System.out.println("Open static: " + label.trySetAccessible());
        System.out.println("Static value: " + label.get(null));

        FinalRecord record = new FinalRecord(42);
        Field recordValue = FinalRecord.class.getDeclaredField("value");
        System.out.println("Record final: "
                + Modifier.isFinal(recordValue.getModifiers()));
        System.out.println("Open record: "
                + recordValue.trySetAccessible());
        System.out.println("Record value: " + recordValue.getInt(record));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 ReadFinalDemo.java
java ReadFinalDemo
~~~

**Stdout (đã kiểm chứng trên JDK 21):**

~~~text
Instance final: true
Read before: false
Open for read: true
Instance value: 7
Static final: true
Open static: true
Static value: fixed
Record final: true
Open record: true
Record value: 42
~~~

**Phân tích:**

- `Modifier.isFinal(...)` đọc cờ modifier của `count`, `LABEL` và field backing cho thành phần record `value`; cả ba đều là `final`.
- `count` là `private final` của một lớp khác `ReadFinalDemo`, nên `canAccess(data)` ban đầu là `false`. Sau khi `trySetAccessible()` thành công, `getInt(data)` đọc được số `7`.
- `LABEL` là `static final`: truyền `null` vào `get(null)` vì field gắn với lớp, không gắn với instance.
- Thành phần `value` của record cũng có field `private final` do compiler tạo; ví dụ đọc field đó sau khi bật quyền.
- Chương trình **không dùng `Field#set`**. Sự thành công của cả ba thao tác đọc **không cung cấp bằng chứng** rằng ba field có thể được ghi bằng Reflection.

**Tại sao ví dụ không dùng lớp lồng bên trong `ReadFinalDemo`?** Các lớp lồng có thể là *nestmates*, có quyền truy cập `private` của nhau theo quy tắc Java, khiến `canAccess(...)` ban đầu trả `true` và che mất ý nghĩa của việc thử mở quyền. Các lớp cấp cao nhất `FinalData` và `ReadFinalDemo` trong ví dụ là hai nest khác nhau.

## 4. Đọc thành công không cấp quyền ghi

Ví dụ ở mục 3 đã chứng minh có thể đọc ba field `final` khác nhau. Để quyết định có nên gọi `Field.set`, còn phải xét **loại field** và **runtime đang chạy**. `trySetAccessible()` chỉ xử lý bước xin bỏ qua kiểm tra truy cập Java; nó không loại bỏ giới hạn ghi của `final`.

| Field | `Field.get` khi đủ quyền | `Field.set` sau khi mở quyền |
| --- | --- | --- |
| Instance `final` của class thông thường | Có thể đọc | Trên JDK 17–25 có đường ghi đặc biệt khi đủ điều kiện; không phải API cập nhật trạng thái |
| `static final` | Có thể đọc | Không được ghi qua setter Reflection |
| `final` trong record | Có thể đọc | Không được ghi qua setter Reflection |
| `final` trong hidden class | Có thể đọc | Không được ghi qua setter Reflection |
| Field không `final` | Có thể đọc | Có thể ghi nếu quyền truy cập, receiver và kiểu dữ liệu phù hợp |

**Cách diễn giải:** nếu `label.trySetAccessible()` thành công rồi `label.get(null)` trả về `"fixed"`, ta mới biết thao tác **đọc** trên `static final LABEL` là hợp lệ trong ngữ cảnh đó. Thử `label.set(null, "changed")` vẫn bị từ chối bằng `IllegalAccessException`. Tương tự, record có thể cho đọc component field nhưng không cho viết lại field ấy.

JDK 26 bổ sung chính sách JEP 500 cho việc ghi **ordinary final instance field** bằng deep reflection: thao tác không được cấp phép có thể phát cảnh báo hoặc bị chặn tùy cấu hình. Các tùy chọn đó không biến `static final`, record-final hay hidden-class-final thành writable. Vì vậy đừng lấy kết quả ghi từ một JDK để đoán cho mọi JDK khác.

## 5. Chọn cách đọc phù hợp

- Nếu lớp đã có **getter/accessor public**, hãy ưu tiên nó. Với record, accessor như `recordValue.value()` thể hiện rõ contract của đối tượng.
- Nếu cần **metadata**, dùng `getDeclaredField`, `getModifiers` hoặc `getDeclaredFields` mà không cần tự ý mở quyền đọc giá trị.
- Nếu công cụ thật sự cần đọc **private field**, xác định đúng declaring class, receiver (instance hoặc `null` cho static) và quyền truy cập qua module. `trySetAccessible() == false` có thể là kết quả hợp lệ khi package không mở cho caller.
- Nếu yêu cầu thật sự là **cập nhật giá trị**, đừng chuyển quy trình đọc thành lời gọi `set` theo quán tính. Tìm constructor/factory, phương thức cập nhật hoặc tạo instance mới; các bài tiếp theo sẽ phân tích sâu các giới hạn và lựa chọn đó.

## 6. Tự kiểm tra

1. `getDeclaredField("count")` trả về một `Field` cho `private final int count`. Có thể khẳng định `getInt(data)` sẽ chạy ngay không? **Không**; cần kiểm tra quyền truy cập của caller.
2. `trySetAccessible()` trả `true` cho `private static final String LABEL`. Có thể `Field.set(null, "new")` không? **Không**; `static final` không có quyền ghi bằng cách mở accessible.
3. Đọc `record FinalRecord(int value)` qua `getInt(record)` thành công, có thể suy ra sửa component field không? **Không**; record final field thuộc loại không thể ghi qua `Field.set`.
4. `final List<String>` trỏ tới một `ArrayList`. Nếu gọi `add` thành công, có phải vừa gán lại field không? **Không**; chỉ nội dung object được tham chiếu thay đổi.

**Điều cần nhớ:** tra cứu metadata, xin mở quyền, đọc và ghi là **bốn thao tác khác nhau**. Bài này dạy đường **đọc** và cách nhận ra ranh giới sang **ghi**; khi cần ghi, phải kiểm tra riêng từng loại `final` cùng phiên bản Java trước khi quyết định thiết kế.

### Tài liệu tham khảo

- [Java SE 17 — Field API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html)
- [Java SE 17 — AccessibleObject API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [JEP 500 — Prepare to Make Final Mean Final](https://openjdk.org/jeps/500)
