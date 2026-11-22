# Nhận diện lớp enum và danh sách hằng enum

## 1. Hai nhu cầu khác nhau

Một công cụ nhận `Class<?>` có thể cần biết đó có phải kiểu enum không để dựng danh sách lựa chọn hoặc kiểm tra giá trị cấu hình. Một công cụ khác đã có một hằng enum và muốn tìm kiểu enum khai báo nó.

Hai câu hỏi này dùng các API khác nhau:

| Câu hỏi | API |
| --- | --- |
| Class này có được khai báo là enum không? | `Class.isEnum()` |
| Enum có những hằng nào? | `Class.getEnumConstants()` |
| Hằng này thuộc kiểu enum khai báo nào? | `Enum.getDeclaringClass()` |
| Tên chính xác của hằng là gì? | `Enum.name()` |

Đừng suy ra kiểu enum bằng cách tìm chuỗi “enum” trong tên lớp hay kiểm tra mọi lớp con của Enum như thể chúng đều là khai báo enum. Java có API trực tiếp cho việc này. [API Class.isEnum](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#isEnum())

Ví dụ dưới đây dùng Java 17 trở lên.

## 2. Nhận diện enum và liệt kê hằng

`getEnumConstants()` trả một mảng hằng theo thứ tự khai báo. Nếu Class không đại diện cho một kiểu enum, kết quả là `null`. Với enum hợp lệ không có hằng, kết quả là **mảng rỗng**, không phải `null`. [API Class.getEnumConstants](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#getEnumConstants())

Ví dụ một đoạn kiểm tra, chưa phải chương trình độc lập:

```java
if (!type.isEnum()) {
    throw new IllegalArgumentException("Expected an enum class");
}

Object[] constants = type.getEnumConstants();
for (Object constant : constants) {
    Enum<?> value = (Enum<?>) constant;
    System.out.println(value.name());
}
```

Ở đây `type` là `Class<?>`. Phép ép từng phần tử thành Enum<?> có cơ sở vì đã xác nhận type là lớp enum. Không ép toàn bộ mảng thành một kiểu enum tùy ý như Status[] khi chưa biết chính xác lớp.

Nếu biết sẵn kiểu, có thể dùng `Status.values()` hoặc `Status.class.getEnumConstants()` để nhận Status[]. `values()` là phương thức được khai báo ngầm cho từng kiểu enum, không phải phương thức instance chung trên `Enum<?>`. [JLS §8.9.3](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.9.3)

## 3. Chương trình đầy đủ

Lưu vào **EnumInspectionDemo.java**:

```java
public class EnumInspectionDemo {
    enum Status {
        QUEUED("Waiting"),
        RUNNING("Working") {
            @Override
            public boolean canCancel() {
                return true;
            }
        },
        DONE("Finished");

        static final Status DEFAULT = QUEUED;

        private final String label;

        Status(String label) {
            this.label = label;
        }

        public boolean canCancel() {
            return this == QUEUED;
        }

        @Override
        public String toString() {
            return label;
        }
    }

    enum Empty {
    }

    public static void main(String[] args) throws Exception {
        inspect(Status.class);
        inspect(Empty.class);
        inspect(String.class);
        inspect(Enum.class);

        System.out.println("details:");
        for (Status value : Status.class.getEnumConstants()) {
            System.out.println(value.name()
                    + ",ordinal=" + value.ordinal()
                    + ",text=" + value
                    + ",canCancel=" + value.canCancel());
        }

        Status running = Status.RUNNING;
        System.out.println("runningIsEnumValue="
                + (running instanceof Enum<?>));
        System.out.println("runningClassIsEnum="
                + running.getClass().isEnum());
        System.out.println("runningDeclaringClass="
                + running.getDeclaringClass().getSimpleName());
        System.out.println("runningClassConstantsNull="
                + (running.getClass().getEnumConstants() == null));
        System.out.println("declaringClassCount="
                + running.getDeclaringClass()
                    .getEnumConstants().length);

        System.out.println("RUNNINGisEnumConstant="
                + Status.class.getDeclaredField("RUNNING")
                    .isEnumConstant());
        System.out.println("DEFAULTisEnumConstant="
                + Status.class.getDeclaredField("DEFAULT")
                    .isEnumConstant());

        Status parsed = Enum.valueOf(Status.class, "RUNNING");
        System.out.println("parsed=" + parsed.name());

        try {
            Enum.valueOf(Status.class, "Working");
        } catch (IllegalArgumentException ex) {
            System.out.println("labelAccepted=false");
        }

        try {
            Enum.valueOf(Status.class, "running");
        } catch (IllegalArgumentException ex) {
            System.out.println("lowercaseAccepted=false");
        }
    }

    private static void inspect(Class<?> type) {
        Object[] values = type.getEnumConstants();
        System.out.println(type.getSimpleName()
                + ": isEnum=" + type.isEnum()
                + ", constants="
                + (values == null ? "<null>" : values.length));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 EnumInspectionDemo.java
java EnumInspectionDemo
```

Kết quả chuẩn:

```text
Status: isEnum=true, constants=3
Empty: isEnum=true, constants=0
String: isEnum=false, constants=<null>
Enum: isEnum=false, constants=<null>
details:
QUEUED,ordinal=0,text=Waiting,canCancel=true
RUNNING,ordinal=1,text=Working,canCancel=true
DONE,ordinal=2,text=Finished,canCancel=false
runningIsEnumValue=true
runningClassIsEnum=false
runningDeclaringClass=Status
runningClassConstantsNull=true
declaringClassCount=3
RUNNINGisEnumConstant=true
DEFAULTisEnumConstant=false
parsed=RUNNING
labelAccepted=false
lowercaseAccepted=false
```

### Đọc kết quả

Status và Empty đều được khai báo bằng từ khóa `enum`, nên `isEnum()` là true. String không phải enum. Chính `java.lang.Enum` là lớp cơ sở chung, cũng không phải một kiểu enum được khai báo bằng cú pháp enum, nên kiểm tra trả false.

Danh sách của Status chỉ có ba hằng QUEUED, RUNNING và DONE. `DEFAULT` là một trường static final tham chiếu lại QUEUED; nó không tạo thêm một hằng enum. Kết quả `Field.isEnumConstant()` giúp phân biệt trường tương ứng với hằng enum với trường thông thường. [API Field.isEnumConstant](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Field.html#isEnumConstant())

## 4. Hằng có thân lớp riêng: getClass khác getDeclaringClass

RUNNING có phần thân ghi đè `canCancel()`. Java biểu diễn hằng có thân riêng bằng một lớp ẩn danh phát sinh từ kiểu enum. Vì vậy:

- `running instanceof Enum<?>` vẫn là true.
- `running.getClass().isEnum()` là false.
- `running.getDeclaringClass()` trả Status.class.
- Muốn liệt kê tất cả hằng cùng kiểu, dùng lớp enum khai báo, không dùng lớp riêng của RUNNING.

Đây không phải lỗi của reflection: `isEnum()` hỏi về lớp được khai báo là enum, trong khi `getClass()` trả lớp runtime cụ thể của đối tượng. [API Class.isEnum](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#isEnum()), [API Enum.getDeclaringClass](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html#getDeclaringClass())

Không dựa vào tên lớp phát sinh như hậu tố `$1`. Nếu đã có một hằng enum, `getDeclaringClass()` là API đúng cho nhu cầu tìm kiểu enum của nó.

## 5. name, toString và ordinal không thay thế nhau

Trong chương trình:

| Hằng | `name()` | `toString()` | `ordinal()` |
| --- | --- | --- | --- |
| QUEUED | `QUEUED` | `Waiting` | 0 |
| RUNNING | `RUNNING` | `Working` | 1 |
| DONE | `DONE` | `Finished` | 2 |

`name()` trả định danh khai báo chính xác. `toString()` có thể được ghi đè để hiển thị thân thiện. `ordinal()` là vị trí bắt đầu từ 0 trong khai báo. [API Enum](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html)

Khi dựng một danh sách lựa chọn, có thể tách tên máy đọc được và nhãn hiển thị. Không dùng nhãn `Working` làm tên hằng nếu hợp đồng cấu hình yêu cầu `RUNNING`.

Không dùng ordinal làm mã dữ liệu bền vững chỉ vì nó là số: chèn hoặc đổi thứ tự hằng làm vị trí thay đổi. Nếu hệ thống cần mã ổn định, hãy khai báo một thuộc tính mã riêng và quy định tính duy nhất. Tên hằng cũng chỉ ổn định chừng nào hợp đồng phiên bản còn giữ tên đó; đổi tên cần xét dữ liệu đã lưu và bên sử dụng.

## 6. Chuyển tên sang hằng enum

Khi đã biết lớp enum cụ thể:

```java
EnumInspectionDemo.Status status =
        Enum.valueOf(EnumInspectionDemo.Status.class, "RUNNING");
```

Đoạn minh họa này dùng kiểu lồng từ chương trình trên.

`Enum.valueOf` yêu cầu tên khớp chính xác một định danh khai báo. Nó không tự bỏ khoảng trắng, không đổi chữ hoa/thường và không dùng `toString()` để tra. Tên không tồn tại gây `IllegalArgumentException`; đầu vào `null` cần được xử lý theo hợp đồng của ứng dụng, không xem nó như một hằng hợp lệ. [API Enum.valueOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Enum.html#valueOf(java.lang.Class,java.lang.String))

Nếu chỉ có Class<?> và muốn trả kết quả không tìm thấy mà không dùng ép kiểu generic không kiểm tra, có thể duyệt danh sách hằng bằng tên.

### Chương trình tra tên khi chỉ biết Class

Lưu thành **DynamicEnumLookupDemo.java**:

```java
import java.util.Objects;
import java.util.Optional;

public class DynamicEnumLookupDemo {
    enum Direction {
        NORTH, SOUTH
    }

    public static Optional<Enum<?>> findByName(
            Class<?> type, String name) {
        Objects.requireNonNull(type, "type");
        Objects.requireNonNull(name, "name");

        if (!type.isEnum()) {
            throw new IllegalArgumentException(
                    "Expected an enum class");
        }

        Object[] constants = type.getEnumConstants();
        for (Object constant : constants) {
            Enum<?> value = (Enum<?>) constant;
            if (value.name().equals(name)) {
                return Optional.of(value);
            }
        }

        return Optional.empty();
    }

    public static void main(String[] args) {
        System.out.println("found="
                + findByName(Direction.class, "NORTH")
                    .map(Enum::name).orElse("<missing>"));
        System.out.println("unknown="
                + findByName(Direction.class, "WEST").isPresent());

        try {
            findByName(String.class, "NORTH");
        } catch (IllegalArgumentException ex) {
            System.out.println("nonEnumRejected=true");
        }
    }
}
```

Chạy:

```shell
javac --release 17 -encoding UTF-8 DynamicEnumLookupDemo.java
java DynamicEnumLookupDemo
```

Kết quả:

```text
found=NORTH
unknown=false
nonEnumRejected=true
```

Hàm phân biệt hai tình huống:

- Kiểu đầu vào không phải enum: lời gọi không đúng hợp đồng, nên báo lỗi.
- Đúng kiểu enum nhưng không có tên: trả Optional.empty().

Hàm giữ so khớp tên chính xác. Nếu sản phẩm muốn chấp nhận khoảng trắng hay chữ thường, hãy thiết kế bước chuẩn hóa riêng; không mô tả khả năng đó như hành vi mặc định của Java.

## 7. Khi nào dùng Field thay vì danh sách hằng?

Nếu chỉ cần các giá trị enum, ưu tiên `getEnumConstants()`: nó đã có đúng danh sách và đúng thứ tự khai báo.

Nếu cần đọc annotation trên từng hằng, có thể lấy hằng theo thứ tự rồi tìm Field bằng `constant.name()`. Các hằng enum có trường tương ứng; `Field.isEnumConstant()` giúp xác nhận đây là trường hằng enum. Không coi mọi trường static final có cùng kiểu enum là hằng, như DEFAULT trong ví dụ.

`getDeclaredFields()` còn có thể chứa trường nghiệp vụ và trường do trình biên dịch sinh. Không dựa vào một tên trường nội bộ hay thứ tự toàn bộ mảng fields để dựng danh sách hằng. [JLS: thành viên của enum](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.9.3)

Các giá trị lấy được là chính các hằng đã được định nghĩa, không phải những đối tượng mới do bộ đọc tự dựng. Khi xây công cụ động, không cố tạo thêm hằng enum bằng constructor reflection để mở rộng danh sách lựa chọn.

### Những lỗi thường gặp

- Không phân biệt `null` cho lớp không phải enum với mảng rỗng của enum rỗng.
- Dùng `constant.getClass()` để tìm kiểu enum và bỏ sót hằng có thân riêng.
- Coi Enum.class là một enum cụ thể.
- Dùng `toString()` rồi mong `Enum.valueOf` tra được nhãn hiển thị.
- Lấy trường DEFAULT làm một hằng bổ sung.
- Dùng ordinal như mã dữ liệu ổn định.
- Sắp xếp lại tên hằng rồi nói đó là thứ tự khai báo.

### Tự thực hành

1. Thêm một hằng giữa QUEUED và RUNNING. Danh sách và ordinal thay đổi ra sao?
2. Bỏ thân riêng của RUNNING. `running.getClass().isEnum()` thay đổi thế nào?
3. Ghi đè `toString()` bằng nhãn tiếng Việt. Vì sao `name()` và cách tra tên vẫn giữ nguyên?
4. Gọi bộ tra động với Empty enum tương tự ví dụ đầu. Kết quả không tìm thấy khác gì với truyền String.class?
5. Thêm một trường static final khác tham chiếu DONE. Vì sao số lượng enum constants không tăng?
6. Dựng danh sách gồm cả tên và nhãn hiển thị, giữ đúng thứ tự khai báo mà không phụ thuộc các trường nội bộ của trình biên dịch.
