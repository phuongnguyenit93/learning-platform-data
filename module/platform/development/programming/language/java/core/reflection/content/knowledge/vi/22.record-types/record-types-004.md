# Khởi tạo record qua constructor thay vì sửa field final

## 1. Record được hoàn thành ngay khi tạo

Một record mô tả dữ liệu bằng các **thành phần record (record component)** trong phần đầu khai báo. Mỗi thành phần tương ứng với một field instance `private final` và một phương thức truy cập.

Ví dụ:

~~~java
record Member(String name, int level) {
}
~~~

Đây là một khai báo record, chưa phải chương trình có `main`. Constructor chuẩn của nó nhận lần lượt `String name` và `int level`.

Một cách tạo đối tượng thường gặp với JavaBean là tạo trước rồi gán các thuộc tính. Cách suy nghĩ ấy không phù hợp với các component của record: dữ liệu phải được đưa qua constructor để đối tượng được khởi tạo đầy đủ.

Khi chỉ biết lớp record lúc chạy, Reflection vẫn thực hiện cùng mô hình:

1. Đọc các component theo thứ tự khai báo.
2. Xác định constructor chuẩn.
3. Chuẩn bị đầy đủ đối số.
4. Gọi constructor để nhận một record mới.

Đừng dùng ghi field final như bước “hoàn thiện” một record đã được tạo. Ngoài giới hạn của API Reflection, cách đó còn bỏ qua nơi tập trung các quy tắc kiểm tra và chuẩn hóa dữ liệu.

## 2. Constructor chuẩn và compact constructor

**Constructor chuẩn (canonical constructor)** có các kiểu tham số tương ứng với component, giữ nguyên thứ tự trong phần đầu record.

Với `record Member(String name, int level)`, danh sách kiểu là:

~~~text
String.class, int.class
~~~

Record có thể khai báo constructor chuẩn bằng dạng đầy đủ hoặc dạng rút gọn, gọi là **compact constructor**. Dạng rút gọn thích hợp cho kiểm tra và chuẩn hóa tham số:

~~~java
public record Member(String name, int level) {
    public Member {
        name = java.util.Objects.requireNonNull(name, "name").strip();
        if (name.isEmpty()) {
            throw new IllegalArgumentException("name is blank");
        }
        if (level < 1) {
            throw new IllegalArgumentException("level must be positive");
        }
    }
}
~~~

Đây là một khai báo minh họa độc lập với khai báo ngắn ở phần trước; không đặt cả hai cùng tên trong một phạm vi.

Trong phần thân compact constructor, `name` và `level` là các tham số ngầm định. Có thể gán lại tham số để chuẩn hóa. Sau khi phần thân kết thúc bình thường, mã do compiler cung cấp sẽ khởi tạo các field từ các tham số tương ứng.

Không viết `this.name = ...` trong compact constructor để tự gán component field. Nếu dùng dạng constructor chuẩn đầy đủ, quy tắc viết phần gán có khác; không trộn hai cách khai báo.

Reflection tìm thấy constructor chuẩn với cùng danh sách kiểu dù nó được khai báo dưới dạng compact. Gọi constructor này vẫn chạy toàn bộ kiểm tra và chuẩn hóa.

Record không tự được cấp một constructor mặc định không tham số theo quy tắc của lớp thông thường. Nếu có constructor khác do tác giả viết, nó phải đi qua chuỗi constructor hợp lệ của record. Vì thế, không giả định mọi record đều có thể được tạo bằng một lời gọi không đối số rồi điền dữ liệu sau.

## 3. Ví dụ chạy được: tìm và gọi constructor chuẩn

Lưu thành `RecordConstructorDemo.java`:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.RecordComponent;
import java.util.Arrays;
import java.util.Objects;
import java.util.stream.Collectors;

public class RecordConstructorDemo {
    public record Member(String name, int level) {
        public Member {
            name = Objects.requireNonNull(name, "name").strip();
            if (name.isEmpty()) {
                throw new IllegalArgumentException("name is blank");
            }
            if (level < 1) {
                throw new IllegalArgumentException("level must be positive");
            }
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Class<Member> type = Member.class;
        RecordComponent[] components = type.getRecordComponents();

        Class<?>[] parameterTypes = Arrays.stream(components)
                .map(RecordComponent::getType)
                .toArray(Class<?>[]::new);

        Constructor<Member> constructor =
                type.getDeclaredConstructor(parameterTypes);

        System.out.println("components="
                + Arrays.stream(components)
                      .map(RecordComponent::getName)
                      .collect(Collectors.joining(",")));
        System.out.println("signature="
                + Arrays.stream(parameterTypes)
                      .map(Class::getSimpleName)
                      .collect(Collectors.joining(",")));

        Member member = constructor.newInstance(" Lan ", 3);
        System.out.println("name=" + member.name());
        System.out.println("level=" + member.level());
        System.out.println("sameAsDirect="
                + member.equals(new Member("Lan", 3)));

        try {
            constructor.newInstance("   ", 3);
        } catch (InvocationTargetException exception) {
            Throwable cause = exception.getCause();
            System.out.println("constructorCause="
                    + cause.getClass().getSimpleName()
                    + ":" + cause.getMessage());
        }

        try {
            constructor.newInstance("Lan", "3");
        } catch (IllegalArgumentException exception) {
            System.out.println("arguments="
                    + exception.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 RecordConstructorDemo.java
java RecordConstructorDemo
~~~

Kết quả:

~~~text
components=name,level
signature=String,int
name=Lan
level=3
sameAsDirect=true
constructorCause=IllegalArgumentException:name is blank
arguments=IllegalArgumentException
~~~

Các điểm cần quan sát:

- `getRecordComponents()` trả component theo thứ tự phần đầu record. Không cần đoán từ thứ tự field.
- `getType()` cung cấp kiểu để tìm đúng constructor: component `int` cần `int.class`, không phải `Integer.class`.
- `newInstance(" Lan ", 3)` chạy compact constructor, nên tên nhận được là `Lan`.
- Chuỗi chỉ có khoảng trắng bị constructor từ chối. Lỗi từ phần thân constructor được bọc trong `InvocationTargetException`.
- Chuỗi `"3"` không tự chuyển thành số `int`. Đây là lỗi đối số Reflection, được báo bằng `IllegalArgumentException` trước khi có một lời gọi constructor hợp lệ.

Tìm constructor và truyền đối số là hai bước có quy tắc khác nhau. Tìm kiếm dùng các đối tượng `Class` của kiểu khai báo chính xác; lúc gọi, Reflection có thể mở hộp giá trị `Integer` để truyền cho tham số `int`, như số `3` trong ví dụ.

## 4. Tên component quyết định vị trí đối số khi đầu vào là Map

Constructor chuẩn gắn với thứ tự component trong header. Nếu có `record Address(String city, String street) {}`, đảo hai chuỗi vẫn đúng kiểu nhưng lại tạo địa chỉ sai nghĩa. Với dữ liệu đầu vào có tên thuộc tính, hãy chọn giá trị theo **tên component**, rồi đặt vào đúng chỉ số:

~~~java
// Mảnh mã trong một phương thức: type là Class<?> của record,
// source là Map<String, ?>; đã kiểm tra type.isRecord().
RecordComponent[] components = type.getRecordComponents();
Object[] arguments = new Object[components.length];
for (int i = 0; i < components.length; i++) {
    String name = components[i].getName();
    if (!source.containsKey(name)) {
        throw new IllegalArgumentException("Missing component: " + name);
    }
    arguments[i] = source.get(name);
}
~~~

Đoạn này chỉ chuẩn bị đối số. Phần tìm và gọi canonical constructor theo `RecordComponent.getType()` đã được minh họa ở phần 3; một mapper hoàn chỉnh còn phải kiểm tra khóa lạ và chuyển đổi giá trị cho đúng kiểu trước khi gọi.

Không lấy `source.values().toArray()` làm đối số: thứ tự duyệt Map không phải hợp đồng thứ tự của header record. `containsKey` cũng giúp phân biệt thiếu tên với một khóa có mặt nhưng mang giá trị `null`. Nếu component có kiểu primitive thì `null` không thể làm đối số hợp lệ; còn `null` ở kiểu tham chiếu có thể bị chính constructor từ chối.

## 5. Vì sao setAccessible(true) không giải quyết field final của record?

Field final được khai báo trong record thuộc nhóm **final không thể sửa bằng Field.set** theo hợp đồng Reflection. `setAccessible(true)` không biến chúng thành field ghi được.

Cờ accessible liên quan đến kiểm tra quyền truy cập Java. Quyền truy cập và khả năng sửa một field final của record là hai điều kiện khác nhau.

Lưu thành `RecordFinalFieldDemo.java`:

~~~java
import java.lang.reflect.Field;

public class RecordFinalFieldDemo {
    public record Note(String text) {
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Note note = new Note("before");
        Field field = Note.class.getDeclaredField("text");

        field.setAccessible(true);
        System.out.println("read=" + field.get(note));

        try {
            field.set(note, "after");
        } catch (IllegalAccessException exception) {
            System.out.println("write="
                    + exception.getClass().getSimpleName());
        }

        System.out.println("value=" + note.text());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 RecordFinalFieldDemo.java
java RecordFinalFieldDemo
~~~

Kết quả trên JDK 17:

~~~text
read=before
write=IllegalAccessException
value=before
~~~

Ví dụ được đặt trong cùng lớp ngoài để việc bật truy cập không bị vướng ranh giới module của thư viện khác. Dù bật thành công và đọc được field, thao tác ghi vẫn bị từ chối.

Không diễn giải lỗi này là “cần gọi setAccessible thêm lần nữa”. Với record, hướng khởi tạo đúng là tìm và gọi constructor phù hợp. Nếu cần dữ liệu khác, tạo một record mới qua constructor để các quy tắc của record tiếp tục được áp dụng.

## 6. Cập nhật dữ liệu bằng cách tạo giá trị mới

Một record biểu diễn một tập dữ liệu đã được khởi tạo. Nếu muốn đổi một component, hãy tạo giá trị mới, giữ lại các component còn lại cần thiết.

Đoạn sau là một phương thức đặt trong phạm vi `RecordConstructorDemo`, sử dụng record `Member` của ví dụ đầu:

~~~java
static Member withLevel(Member current, int nextLevel) {
    return new Member(current.name(), nextLevel);
}
~~~

Lời gọi vẫn đi qua constructor, nên `nextLevel < 1` bị từ chối. Đối tượng `current` giữ giá trị cũ.

Nếu kiểu chỉ được biết lúc chạy, nguyên tắc vẫn như vậy: lấy dữ liệu hiện có bằng accessor phù hợp, thay giá trị đầu vào cần đổi, sắp theo component và gọi constructor chuẩn để tạo đối tượng mới. Không sửa trực tiếp field của đối tượng cũ.

Điểm này có ý nghĩa với các **điều kiện luôn phải đúng (invariant)**. Ví dụ record của một khoảng thời gian có thể yêu cầu thời điểm bắt đầu không sau thời điểm kết thúc. Đưa toàn bộ dữ liệu qua constructor cho phép kiểm tra quan hệ giữa các component trước khi trả về một đối tượng hợp lệ.

Constructor không tự tạo ra các quy tắc nghiệp vụ: tác giả record phải viết chúng nếu cần. Reflection chỉ bảo đảm lời gọi đi qua phần constructor được chọn, không tự biết dữ liệu nào có ý nghĩa trong ứng dụng.

## 7. Các chi tiết dễ gây lỗi khi gọi constructor

### 7.1. Tìm đúng kiểu khai báo

`getDeclaredConstructor` và `getConstructor` tìm theo danh sách kiểu tham số, không tìm “gần đúng”. Với component `int level`, tìm bằng `Integer.class` sẽ không tìm thấy constructor chuẩn ấy.

Khi gọi `Constructor.newInstance`, giá trị primitive được biểu diễn trong `Object[]` bằng đối tượng đóng hộp. Reflection hỗ trợ các chuyển đổi lời gọi phù hợp, nhưng không phải một bộ chuyển đổi tùy ý từ chuỗi hoặc mọi loại số.

Ví dụ `Integer` có thể được mở hộp cho `int`; `null` không thể cung cấp giá trị cho tham số `int`. Không dựa vào Reflection để tự phân tích `"42"` thành số.

### 7.2. Một component kiểu mảng vẫn là một đối số

`Constructor.newInstance` nhận `Object...`. Nếu record có một component `String[]`, cần tránh vô tình truyền các phần tử của mảng thành nhiều đối số.

Ví dụ minh họa trong một phương thức có constructor phù hợp:

~~~java
Object[] arguments = {new String[] {"A", "B"}};
Object record = constructor.newInstance(arguments);
~~~

Biến `constructor` ở đây là `Constructor<?>` của record có đúng một component `String[]`. Mảng ngoài có một ô, nên lời gọi nhận đúng một đối số là mảng chuỗi.

Cách xây `Object[] arguments` theo component ở ví dụ ánh xạ Map cũng giữ đúng cấu trúc này. Với component varargs trong phần đầu record, constructor chuẩn vẫn có tham số kiểu mảng tương ứng; chuẩn bị một giá trị mảng ở vị trí đối số ấy.

### 7.3. Tìm thấy constructor chưa đồng nghĩa với được phép gọi

`getDeclaredConstructor` có thể tìm constructor không public, nhưng lời gọi vẫn chịu kiểm tra truy cập. Record và constructor trong ví dụ đầu đều public, nên không cần tắt kiểm tra truy cập.

Với kiểu không public hoặc ranh giới module khác, cần thiết kế đường truy cập hợp lệ của thư viện hoặc dùng API tạo đối tượng được cung cấp. Không lấy việc nhìn thấy metadata làm bằng chứng rằng mọi nơi gọi đều có quyền khởi tạo.

### 7.4. Final của component không phải bất biến sâu

Nếu một component giữ tham chiếu đến một collection có thể thay đổi, `final` không tự làm collection ấy bất biến. Constructor có thể tạo bản sao phù hợp nếu hợp đồng record cần giữ dữ liệu ổn định.

Ví dụ khai báo, với import `java.util.List`:

~~~java
record Team(List<String> members) {
    Team {
        members = List.copyOf(members);
    }
}
~~~

Bước sao chép được thực hiện khi đi qua constructor, kể cả khi gọi bằng Reflection. Đây là một lý do nữa để đặt việc chuẩn hóa dữ liệu tại đường khởi tạo, thay vì tìm cách gán field sau đó. `List.copyOf` không phải phép sao chép sâu mọi đối tượng có thể nằm trong một cấu trúc dữ liệu.

## 8. Phân biệt các nhóm lỗi

| Lỗi | Ý nghĩa thường gặp trong luồng này |
| --- | --- |
| `NoSuchMethodException` | Danh sách kiểu không khớp constructor, hoặc tìm public constructor nhưng không có constructor public tương ứng |
| `IllegalAccessException` khi gọi constructor | Không được phép truy cập constructor từ nơi gọi |
| `IllegalArgumentException` từ Reflection | Sai số đối số hoặc giá trị không chuyển được sang kiểu tham số |
| `InvocationTargetException` | Constructor đã được gọi và phần thân ném ngoại lệ; xem `getCause()` |
| `IllegalAccessException` từ `Field.set` trên component final | Đang dùng đường ghi field không được hỗ trợ cho record |

Nếu constructor từ chối dữ liệu, không nên bỏ qua lỗi rồi cố tạo đối tượng bằng ghi field. Điều đó làm mất chính điều kiện mà record đang bảo vệ.

Khi báo lỗi trong một bộ ánh xạ dữ liệu, nên giữ được tên record, tên component liên quan khi xác định được và nguyên nhân gốc từ constructor. Không thay mọi lỗi bằng một thông báo chung khiến người dùng không biết đang sai kiểu hay sai quy tắc dữ liệu.

## 9. Tự kiểm tra

1. Vì sao dùng `getRecordComponents()` để xây danh sách tham số constructor chuẩn thay vì dùng thứ tự `getDeclaredFields()`?
2. Với component `int`, tìm constructor bằng `Integer.class` có đúng không?
3. Nếu compact constructor loại bỏ khoảng trắng trong tên, lời gọi bằng Reflection có thực hiện bước đó không?
4. `InvocationTargetException` khác gì với `IllegalArgumentException` do sai kiểu đối số?
5. Bật `setAccessible(true)` thành công có cho phép sửa field final của record không?
6. Muốn một component có giá trị mới, nên sửa đối tượng cũ hay tạo đối tượng mới?

Đáp án:

1. Component có hợp đồng thứ tự theo phần đầu record; thứ tự field Reflection không phải nguồn để suy ra thứ tự constructor.
2. Không; tìm theo `int.class`. Việc mở hộp giá trị lúc gọi là quy tắc khác.
3. Có; `Constructor.newInstance` thực sự gọi constructor.
4. Ngoại lệ thứ nhất bọc lỗi từ phần thân constructor; lỗi đối số có thể ngăn lời gọi hợp lệ diễn ra ngay từ đầu.
5. Không; component field final của record không trở thành field ghi được qua `Field.set`.
6. Tạo đối tượng mới qua constructor, giữ lại các component khác và áp dụng lại kiểm tra cần thiết.

## Tài liệu đối chiếu

- [JLS 17 — Constructor của record và compact constructor](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10.4).
- [Java 17 — Class.getRecordComponents và tìm constructor chuẩn](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getRecordComponents()).
- [Java 17 — Constructor.newInstance](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html#newInstance(java.lang.Object...)).
- [Java 17 — AccessibleObject và final field không thể sửa](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/AccessibleObject.html#setAccessible(boolean)).
