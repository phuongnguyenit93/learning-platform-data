# Nhận diện enum bằng isEnum và lấy các hằng bằng getEnumConstants

## 1. Hai câu hỏi khác nhau khi chỉ có Class

Một enum biểu diễn một tập hằng có tên, chẳng hạn `LOW`, `NORMAL`, `HIGH`. Khi biết tên kiểu ngay trong mã nguồn, ta có thể gọi `Priority.values()` để duyệt các hằng. Nhưng một công cụ tạo biểu mẫu, đọc cấu hình hoặc kiểm tra mô hình dữ liệu có thể chỉ nhận được một `Class<?>` lúc chạy.

Trong trường hợp ấy, hai phương thức của `Class` trả lời hai câu hỏi:

- `isEnum()`: đối tượng `Class` này có mô tả **lớp được khai báo bằng enum** hay không?
- `getEnumConstants()`: các **đối tượng hằng enum thực tế** của lớp đó là những đối tượng nào?

Đừng gộp hai câu hỏi thành một. Nhận diện một lớp là enum khác với lấy các đối tượng hằng của nó. Đặc biệt, bước lấy các hằng có thể làm enum được khởi tạo nếu trước đó chưa được khởi tạo.

Bài học dùng Java 17 trở lên và tập trung vào hai API trên. Các thao tác tìm hằng theo tên, đọc annotation của hằng hoặc truy cập field bên trong enum là những nhu cầu khác.

## 2. Hợp đồng cần nhớ

| API | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `Class.isEnum()` | `boolean` | `true` khi lớp được khai báo là enum |
| `Class<T>.getEnumConstants()` | `T[]` | Mảng hằng theo **thứ tự khai báo**, hoặc `null` nếu lớp không phải enum |

Hai kết quả dễ nhầm:

- **Không phải enum:** `getEnumConstants()` trả `null`.
- **Là enum nhưng không có hằng:** phương thức trả một mảng có độ dài `0`.

Enum rỗng là hợp lệ, ví dụ một khai báo riêng:

~~~java
enum Empty {
}
~~~

Không suy ra “không phải enum” chỉ từ việc không có phần tử. Cần phân biệt mảng rỗng với `null`.

Các trường hợp thường gặp, giả sử đã có khai báo `enum Priority { LOW, NORMAL, HIGH }`:

| Đối tượng Class | isEnum() | getEnumConstants() |
| --- | --- | --- |
| `Priority.class` | `true` | Ba hằng `LOW`, `NORMAL`, `HIGH` |
| `Empty.class` | `true` | Mảng rỗng |
| `String.class` | `false` | `null` |
| `Enum.class` | `false` | `null` |
| `Priority[].class` | `false` | `null` |

`java.lang.Enum` là lớp cơ sở chung của các enum, nhưng bản thân nó không phải một lớp được khai báo bằng cú pháp `enum`. Một mảng chứa enum cũng là kiểu mảng, không phải enum.

## 3. Ví dụ hoàn chỉnh: nhận diện, liệt kê và xử lý enum rỗng

Lưu thành `EnumInspectionDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class EnumInspectionDemo {
    enum Priority {
        LOW, NORMAL, HIGH
    }

    enum Empty {
    }

    static List<String> enumNames(Class<?> type) {
        Objects.requireNonNull(type, "type");
        if (!type.isEnum()) {
            throw new IllegalArgumentException("Expected an enum class");
        }

        List<String> names = new ArrayList<>();
        for (Object value : type.getEnumConstants()) {
            Enum<?> constant = (Enum<?>) value;
            names.add(constant.name());
        }
        return List.copyOf(names);
    }

    public static void main(String[] args) {
        Class<?> type = Priority.class;
        Object[] constants = type.getEnumConstants();

        System.out.println("isEnum=" + type.isEnum());
        System.out.println("constants=" + constants.length);
        for (Object value : constants) {
            Enum<?> constant = (Enum<?>) value;
            System.out.println(constant.name() + ":" + constant.ordinal());
        }

        System.out.println("sameFirst=" + (constants[0] == Priority.LOW));

        Priority[] typed = Priority.class.getEnumConstants();
        System.out.println("typedSecond=" + typed[1].name());

        System.out.println("empty.isEnum=" + Empty.class.isEnum());
        System.out.println("empty.length="
                + Empty.class.getEnumConstants().length);
        System.out.println("String.isEnum=" + String.class.isEnum());
        System.out.println("String.constants="
                + String.class.getEnumConstants());
        System.out.println("Enum.isEnum=" + Enum.class.isEnum());
        System.out.println("array.isEnum=" + Priority[].class.isEnum());
        System.out.println("names=" + enumNames(type));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 EnumInspectionDemo.java
java EnumInspectionDemo
~~~

Kết quả chính xác:

~~~text
isEnum=true
constants=3
LOW:0
NORMAL:1
HIGH:2
sameFirst=true
typedSecond=NORMAL
empty.isEnum=true
empty.length=0
String.isEnum=false
String.constants=null
Enum.isEnum=false
array.isEnum=false
names=[LOW, NORMAL, HIGH]
~~~

Những điều chương trình chứng minh:

1. Duyệt bằng `getEnumConstants()` giữ thứ tự `LOW`, `NORMAL`, `HIGH`, đúng thứ tự khai báo.
2. Phần tử đầu tiên chính là `Priority.LOW`, không phải một bản sao mới của hằng ấy.
3. Với `Class<Priority>`, kết quả được định kiểu thành `Priority[]`. Với `Class<?>`, có thể duyệt qua `Object[]` rồi xử lý theo hợp đồng enum.
4. Enum rỗng vẫn nhận diện được bằng `isEnum()`.
5. Hàm `enumNames` từ chối đầu vào không phải enum, thay vì biến đầu vào sai thành một danh sách rỗng khó phân biệt.

Phép ép sang `Enum<?>` trong `enumNames` dựa trên điều kiện đã kiểm tra: `type` là lớp enum và các phần tử được lấy trực tiếp từ `type.getEnumConstants()`. Không áp dụng phép ép ấy cho một mảng `Object[]` bất kỳ.

Trong `main`, `type` được gán trực tiếp từ `Priority.class`, nên chương trình biết chắc kết quả khác `null`. Nếu nhận `Class<?>` từ nơi khác, cần kiểm tra như hàm `enumNames` trước khi duyệt.

## 4. Thứ tự khai báo, tên và nhãn

`getEnumConstants()` trả các hằng theo **thứ tự khai báo**. `ordinal()` là vị trí bắt đầu từ 0; `name()` trả tên khai báo, còn `toString()` có thể bị ghi đè để tạo nhãn hiển thị. Vì thế, công cụ cần khóa tên chính xác nên dùng `name()` và công cụ cần thứ tự khác phải tự sắp xếp kết quả để hiển thị.

Không lưu `ordinal()` như mã nghiệp vụ bền vững: thêm hoặc đổi chỗ hằng có thể thay đổi các vị trí. Sắp xếp mảng `getEnumConstants()` cục bộ cũng không thay đổi thứ tự thực của enum. Bài tiếp theo kiểm tra chi tiết việc sắp xếp, thứ tự và sự khác nhau giữa mảng rỗng với `null`.

## 5. Khi hằng enum có thân lớp riêng

Hằng enum có thể khai báo một thân lớp riêng để ghi đè hành vi; lớp thực tế của đối tượng lúc đó là **lớp con ẩn danh**, nên `constant.getClass().isEnum()` có thể trả `false`. Điều này không phủ nhận việc đối tượng là một hằng enum. Khi đã có `Enum<?>`, dùng `constant.getDeclaringClass()` để lấy **lớp khai báo enum** rồi mới gọi `getEnumConstants()`.

Ví dụ độc lập về sự khác biệt:

~~~java
enum Mode {
    FAST {
        @Override public String toString() { return "Fast mode"; }
    },
    SAFE
}

Enum<?> constant = Mode.FAST;
System.out.println(constant.getClass().isEnum());          // false
System.out.println(constant.getDeclaringClass().isEnum()); // true
System.out.println(constant.getDeclaringClass() == Mode.class); // true
~~~

Các câu lệnh sau khai báo `Mode` là đoạn minh họa phải đặt trong phương thức hoặc khối thích hợp; trường hợp `SAFE` không có thân riêng sẽ có lớp thực tế là `Mode`. Nếu nhận `Object value` bất kỳ, trước tiên kiểm tra `value instanceof Enum<?> constant` để nhận diện cả các hằng có thân riêng.

Muốn khảo sát phần thực hiện riêng của hằng, `getClass()` vẫn hữu ích. Muốn phân loại và liệt kê **kiểu enum chung**, dùng `getDeclaringClass()`; bài riêng về thân lớp của hằng phân tích thêm quan hệ này và sự khác biệt giữa `Enum.getDeclaringClass()` với `Class.getDeclaringClass()`.

## 6. Lấy các hằng có thể khởi tạo enum

`isEnum()` là bước phân loại kiểu. `getEnumConstants()` phải cung cấp các hằng thực tế; nếu enum chưa được khởi tạo, việc lấy các hằng có thể làm chạy quá trình khởi tạo, gồm việc tạo các hằng và thực hiện khối `static`.

Lưu thành `EnumInitializationDemo.java`:

~~~java
public class EnumInitializationDemo {
    enum Level {
        FIRST, SECOND;

        static {
            System.out.println("Level initialized");
        }
    }

    public static void main(String[] args) throws ClassNotFoundException {
        Class<?> type = Class.forName(
                "EnumInitializationDemo$Level",
                false,
                EnumInitializationDemo.class.getClassLoader());

        System.out.println("isEnum=" + type.isEnum());
        System.out.println("before constants");
        Object[] constants = type.getEnumConstants();
        System.out.println("count=" + constants.length);
    }
}
~~~

Biên dịch và chạy trong một tiến trình mới:

~~~bash
javac --release 17 EnumInitializationDemo.java
java EnumInitializationDemo
~~~

Kết quả:

~~~text
isEnum=true
before constants
Level initialized
count=2
~~~

Đối số `false` của `Class.forName` trong ví dụ yêu cầu lấy lớp mà chưa khởi tạo nó. Tên có `$` ở đây là tên nhị phân chính xác của enum lồng trong lớp minh họa, không phải thuật toán suy ra tên enum từ một hằng.

Dòng `Level initialized` xuất hiện khi lấy các hằng. Vì vậy, một công cụ chỉ muốn phân loại kiểu có thể dừng ở `isEnum()`; nếu cần danh sách đối tượng hằng thì phải chấp nhận bước lấy các giá trị có ngữ nghĩa khởi tạo.

Nếu enum đã được khởi tạo thành công trước đó, lấy lại các hằng không có nghĩa là tạo lại từng hằng hoặc chạy lại khối `static` cho mỗi lần gọi. Nếu quá trình khởi tạo thất bại, chương trình có thể nhận lỗi khởi tạo; đừng đồng nhất lỗi ấy với kết quả `null` dành cho lớp không phải enum.

Ví dụ này cũng cho thấy không nên mô tả mọi API Reflection có tên bắt đầu bằng `get` là hoàn toàn không gây tác dụng phụ.

## 7. Chọn đúng API cho từng tình huống

**Đã biết kiểu cụ thể trong mã nguồn:** gọi `Priority.values()` để duyệt trực tiếp. Không cần tìm phương thức `values` bằng Reflection rồi gọi `Method.invoke`.

**Chỉ có Class lúc chạy:** dùng `isEnum()` và `getEnumConstants()`. Đây là trường hợp một bộ tạo biểu mẫu nhận kiểu của thuộc tính nhưng không biết trước enum nào được dùng.

**Đã có một hằng:** dùng `getDeclaringClass()` để chuẩn hóa về lớp enum, nhất là khi hằng có thân lớp riêng.

**Cần tên các lựa chọn:** chuyển từng hằng bằng `Enum.name()` nếu cần tên khai báo; tạo nhãn hiển thị theo quy tắc riêng nếu ứng dụng yêu cầu bản địa hóa hoặc nhãn dễ đọc.

**Cần metadata của field khai báo hằng:** đó là công việc khác với lấy giá trị. `getDeclaredFields()` có thể bao gồm cả field thông thường và field do trình biên dịch sinh ra; không thay thế việc gọi `getEnumConstants()` bằng cách duyệt mọi field rồi cho rằng đó đều là hằng enum.

Kết quả của hai API này cũng không cho biết mọi lựa chọn đều được phép trong mọi tình huống nghiệp vụ. Ví dụ một trạng thái có trong enum chưa chắc là trạng thái được phép chuyển đến từ trạng thái hiện tại. Bước liệt kê kiểu và bước kiểm tra quy tắc nghiệp vụ cần được phân biệt.

## 8. Các lỗi cần tránh

| Sai lầm | Hậu quả hoặc cách sửa |
| --- | --- |
| Gọi `getEnumConstants().length` trên một Class chưa kiểm tra | Có thể gặp `NullPointerException` khi lớp không phải enum |
| Coi mảng rỗng là bằng chứng không phải enum | Bỏ sót enum không có hằng |
| Cho rằng `Enum.class.isEnum()` phải là `true` | Nhầm lớp cơ sở với lớp enum khai báo |
| Dùng `constant.getClass().isEnum()` cho mọi hằng | Bỏ sót hằng có thân lớp riêng; lấy `getDeclaringClass()` |
| Dùng `toString()` làm tên khai báo | Có thể nhận chuỗi đã được ghi đè |
| Dùng `ordinal()` làm mã ổn định mặc định | Mã có thể thay đổi khi thứ tự khai báo đổi |
| Cho rằng lấy hằng chỉ là đọc metadata | Bỏ qua việc khởi tạo enum |
| Ép mọi kết quả sang một enum cụ thể như `Priority[]` | Có thể sai kiểu khi Class đầu vào là enum khác |
| Duyệt mọi field để lấy danh sách hằng | Lẫn field khác và mất hợp đồng thứ tự của `getEnumConstants()` |

Nếu hàm của bạn nhận `Class<?>`, nên quyết định rõ hợp đồng: từ chối lớp không phải enum, hay trả một kết quả có trạng thái phân biệt được “không phải enum” với “enum rỗng”. Không âm thầm gộp hai trường hợp nếu mã sử dụng cần phân biệt chúng.

## 9. Tự kiểm tra

1. `Empty.class.isEnum()` là `true` hay `false` nếu enum không có hằng?
2. `String.class.getEnumConstants()` trả mảng rỗng hay `null`?
3. Khi một hằng ghi đè `toString()` trong thân lớp riêng, vì sao `getClass().isEnum()` có thể là `false`?
4. Muốn lấy cả hai hằng `FAST`, `SAFE` khi đang giữ `Mode.FAST`, nên bắt đầu bằng API nào?
5. Lấy danh sách hằng có bảo đảm không chạy mã khởi tạo hay không?

Đáp án:

1. `true`; enum rỗng vẫn là enum, còn mảng hằng có độ dài 0.
2. `null`, vì `String` không phải lớp enum.
3. Lớp thực tế lúc ấy là lớp con ẩn danh của enum, không phải lớp enum khai báo.
4. `Mode.FAST.getDeclaringClass()`, sau đó gọi `getEnumConstants()` trên lớp nhận được.
5. Không. Nếu chưa khởi tạo enum, bước lấy các hằng có thể kích hoạt việc khởi tạo.

Hãy giữ riêng ba ý: lớp enum được khai báo, lớp thực tế của một hằng và tập các đối tượng hằng. `isEnum()`, `getDeclaringClass()` và `getEnumConstants()` giải quyết ba phần ấy với những hợp đồng khác nhau.

## Tài liệu đối chiếu

- [Java 17 — Class.isEnum](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isEnum()).
- [Java 17 — Class.getEnumConstants](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getEnumConstants()).
- [Java 17 — Enum và getDeclaringClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html#getDeclaringClass()).
- [JLS 17 — Enum, thân lớp riêng của hằng và values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.9).
- [JLS 17 — Khởi tạo lớp và interface](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4).
