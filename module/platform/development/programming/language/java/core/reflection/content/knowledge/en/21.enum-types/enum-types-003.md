# Field.isEnumConstant: nhận diện trường biểu diễn hằng enum

## 1. Một enum có nhiều loại trường

Một lớp enum không chỉ có các hằng được liệt kê ở đầu phần khai báo. Nó còn có thể có trường dữ liệu của từng đối tượng, trường tĩnh do người viết bổ sung và trường hỗ trợ do trình biên dịch sinh ra.

Vì vậy, khi duyệt `getDeclaredFields()`, câu hỏi “trường này có thuộc một enum không?” chưa đủ. Công cụ sinh tài liệu hoặc khảo sát metadata thường cần câu hỏi chính xác hơn: **trường này có biểu diễn một hằng enum được khai báo hay không?**

`Field.isEnumConstant()` trả lời câu hỏi đó:

~~~java
// Phương thức của java.lang.reflect.Field:
public boolean isEnumConstant();
~~~

- Trả về `true` nếu trường biểu diễn một hằng enum.
- Trả về `false` với các trường khác.
- Kết quả là `boolean`, không phải đối tượng enum và không phải giá trị đang được lưu trong trường.

Định nghĩa API có trong tài liệu [Field.isEnumConstant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html#isEnumConstant()).

Điểm cần giữ rõ ngay từ đầu: đây là phép phân loại **khai báo trường**, không phải phép kiểm tra “giá trị của trường có phải đối tượng enum hay không”.

## 2. Vì sao hằng enum được nhìn thấy như Field?

Xét khai báo:

~~~java
enum Priority {
    LOW, HIGH;

    static final Priority DEFAULT = LOW;
}
~~~

`LOW` và `HIGH` là các hằng enum. Java có các trường tương ứng tên `LOW` và `HIGH`, kiểu khai báo `Priority`, với các thuộc tính `public static final` được khai báo ngầm.

`DEFAULT` cũng là trường kiểu `Priority`, nhưng do người viết khai báo sau dấu chấm phẩy. Nó giữ tham chiếu đến `LOW`; nó không tạo thêm một hằng trong tập `LOW, HIGH`.

Có thể hình dung:

~~~text
Khai báo hằng LOW
    -> trường LOW biểu diễn hằng enum
    -> isEnumConstant() = true

Khai báo trường DEFAULT = LOW
    -> trường thông thường tham chiếu đến một hằng đã có
    -> isEnumConstant() = false
~~~

Quy tắc các trường ngầm định tương ứng hằng enum được mô tả tại [JLS §8.9.3](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.9.3).

Không nên đồng nhất “hằng enum” với thuật ngữ **biến hằng (constant variable)** trong các quy tắc biểu thức hằng của Java. Theo nghĩa này, biến hằng là biến `final` có kiểu nguyên thủy hoặc `String`, được khởi tạo bằng biểu thức hằng. Trường kiểu enum không thuộc nhóm đó; chỉ nhìn `final` không xác định nó là hằng enum.

## 3. Ví dụ đầy đủ: hằng enum, bí danh và dữ liệu thường

Tạo tệp `EnumConstantFieldDemo.java`:

~~~java
import java.lang.reflect.Field;
import java.util.Arrays;

public class EnumConstantFieldDemo {
    public enum Status {
        NEW(10),
        DONE(20) {
            @Override
            public String toString() {
                return "finished";
            }
        };

        public static final Status DEFAULT = NEW;
        public static final String LABEL = "status";
        private final int code;

        Status(int code) {
            this.code = code;
        }
    }

    static void inspect(String name) throws NoSuchFieldException {
        Field field = Status.class.getDeclaredField(name);
        System.out.println(name
                + " -> enumConstant=" + field.isEnumConstant()
                + ", synthetic=" + field.isSynthetic()
                + ", type=" + field.getType().getSimpleName());
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        inspect("NEW");
        inspect("DONE");
        inspect("DEFAULT");
        inspect("LABEL");
        inspect("code");

        System.out.println("constant fields (name order): "
                + Arrays.stream(Status.class.getDeclaredFields())
                        .filter(Field::isEnumConstant)
                        .map(Field::getName)
                        .sorted()
                        .toList());

        System.out.println("constants (declaration order): "
                + Arrays.stream(Status.class.getEnumConstants())
                        .map(Status::name)
                        .toList());

        Field newField = Status.class.getDeclaredField("NEW");
        Field aliasField = Status.class.getDeclaredField("DEFAULT");
        System.out.println("NEW and DEFAULT same object: "
                + (newField.get(null) == aliasField.get(null)));

        Status done = Status.DONE;
        System.out.println("DONE runtime class is enum: "
                + done.getClass().isEnum());
        System.out.println("DONE declaring enum: "
                + (done.getDeclaringClass() == Status.class));
        System.out.println("DONE name: " + done.name());
        System.out.println("DONE display: " + done);
    }
}
~~~

Chương trình dùng Java 17 trở lên. Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 EnumConstantFieldDemo.java
java EnumConstantFieldDemo
~~~

Kết quả chính xác:

~~~text
NEW -> enumConstant=true, synthetic=false, type=Status
DONE -> enumConstant=true, synthetic=false, type=Status
DEFAULT -> enumConstant=false, synthetic=false, type=Status
LABEL -> enumConstant=false, synthetic=false, type=String
code -> enumConstant=false, synthetic=false, type=int
constant fields (name order): [DONE, NEW]
constants (declaration order): [NEW, DONE]
NEW and DEFAULT same object: true
DONE runtime class is enum: false
DONE declaring enum: true
DONE name: DONE
DONE display: finished
~~~

Các tên trường trong `inspect(...)` được chỉ định rõ để kết quả không phụ thuộc thứ tự trả về của `getDeclaredFields()`. Khi cần in danh sách trường hằng, chương trình chủ động sắp xếp theo tên.

### 3.1. NEW và DONE là hằng enum

Hai hằng được khai báo trước dấu chấm phẩy trong `Status`. Vì vậy, hai trường tương ứng đều có `isEnumConstant() == true`.

`DONE` có phần thân riêng để ghi đè `toString()`. Điều đó không làm mất vai trò hằng enum của trường `Status.DONE`.

### 3.2. DEFAULT là bí danh tham chiếu

`DEFAULT` được khai báo như sau:

~~~java
public static final Status DEFAULT = NEW;
~~~

Nó có cùng kiểu khai báo với trường `NEW`, và giá trị của nó là cùng đối tượng với `Status.NEW`. Tuy nhiên:

- Trường `NEW` biểu diễn hằng enum `NEW`.
- Trường `DEFAULT` là trường tĩnh thông thường tham chiếu đến đối tượng đó.
- `DEFAULT` không làm tăng số hằng enum và không xuất hiện trong `Status.values()`.

Đây là lý do dòng `NEW and DEFAULT same object: true` có thể xuất hiện cùng với `DEFAULT -> enumConstant=false`. Hai kết quả nói về hai khía cạnh khác nhau, không mâu thuẫn.

### 3.3. LABEL và code đều không phải hằng enum

`LABEL` là trường tĩnh chứa một chuỗi. `code` là trường dữ liệu riêng của mỗi đối tượng `Status`. Cả hai đều được khai báo bên trong enum, nhưng đều có `isEnumConstant() == false`.

Nói “mọi field của enum đều là enum constant” sẽ khiến công cụ nhầm cả trường dữ liệu lẫn trường cấu hình vào danh sách lựa chọn.

## 4. Không thay API bằng các phép đoán

| Cách kiểm tra | Vì sao chưa đủ? |
| --- | --- |
| Tên trường viết hoa | Chỉ là quy ước đặt tên; `DEFAULT` và `LABEL` cũng viết hoa |
| Trường có `static final` | Trường thông thường cũng có hai modifier này |
| Trường là `public static final` | Bí danh `DEFAULT` trong ví dụ đáp ứng nhưng không phải hằng enum |
| `field.getType().isEnum()` | Trường `DEFAULT` có kiểu `Status` và vẫn cho kết quả `false` khi hỏi `isEnumConstant()` |
| `field.getDeclaringClass().isEnum()` | Cả `code` và `LABEL` đều được khai báo trong `Status` |
| Giá trị đọc ra là `instanceof Enum<?>` | Giá trị của bí danh cũng là đối tượng enum; lại phải đọc giá trị |
| `!field.isSynthetic()` | Nhiều trường do người viết khai báo không synthetic nhưng cũng không phải hằng enum |

Ở cấp class file, trường biểu diễn hằng enum có cờ `ACC_ENUM`. Đây là thông tin phân loại được chuẩn hóa; dùng `isEnumConstant()` giúp mã thể hiện đúng ý định mà không tự viết kiểm tra bit. Cờ của trường được mô tả tại [JVMS §4.5](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.5).

### isSynthetic không phải phép phủ định của isEnumConstant

Trong chương trình mẫu, cả năm trường được in đều có `isSynthetic() == false`, nhưng chỉ `NEW` và `DONE` là hằng enum.

Trình biên dịch cũng có thể tạo trường hỗ trợ, chẳng hạn mảng nội bộ phục vụ `values()`. Trường hỗ trợ đó không phải một hằng enum. Không nên tìm nó theo tên cố định như `$VALUES`, vì tên và chi tiết triển khai không phải giao diện để ứng dụng phụ thuộc.

Việc các trường hằng được Java khai báo ngầm không có nghĩa chúng phải được đánh dấu synthetic. Chúng đại diện cho các hằng có mặt trong khai báo ngôn ngữ; hãy hỏi từng thuộc tính bằng API tương ứng.

## 5. Phân biệt Field.isEnumConstant với Class.isEnum

Hai phương thức có đối tượng nhận lời gọi và ý nghĩa khác nhau:

- `field.isEnumConstant()`: trường này có biểu diễn một hằng enum không?
- `type.isEnum()`: token lớp này có biểu diễn chính lớp khai báo enum không?

Trong chương trình, `DONE` có phần thân riêng:

~~~java
DONE(20) {
    @Override
    public String toString() {
        return "finished";
    }
}
~~~

Đây là phần trích từ khai báo enum, không phải một chương trình Java độc lập.

Phần thân riêng tạo một lớp con vô danh cho hằng đó. Do vậy:

| Biểu thức | Kết quả trong ví dụ |
| --- | --- |
| `Status.class.isEnum()` | `true` |
| `Status.class.getDeclaredField("DONE").isEnumConstant()` | `true` |
| `Status.class.getDeclaredField("DONE").getType() == Status.class` | `true` |
| `Status.DONE.getClass().isEnum()` | `false` |
| `Status.DONE.getDeclaringClass() == Status.class` | `true` |

`getType()` trên trường đọc **kiểu được khai báo của trường**. `getClass()` trên đối tượng đọc **lớp thực tế của đối tượng**. Hai lớp này có thể khác nhau khi hằng enum có phần thân riêng.

Nếu đã có một đối tượng `Enum<?>` và muốn tìm lớp khai báo enum của nó, dùng `enumValue.getDeclaringClass()`. Không mặc định `enumValue.getClass()` luôn là token thích hợp để liệt kê các hằng.

Cũng đừng nhầm hai phương thức cùng tên:

- `Field.getDeclaringClass()` trả về lớp khai báo trường.
- `Enum.getDeclaringClass()` trả về lớp enum khai báo hằng mà đối tượng đại diện.

Trong ví dụ, chúng cùng có thể trả về `Status.class`, nhưng xuất phát từ hai loại đối tượng khác nhau.

## 6. Metadata khác với giá trị: khi nào enum được khởi tạo?

Có thể hỏi một trường có phải hằng enum mà không cần đọc đối tượng chứa trong trường:

~~~java
// Đoạn minh họa trong ngữ cảnh chương trình mẫu.
Field field = Status.class.getDeclaredField("NEW");
boolean constant = field.isEnumConstant();
~~~

Không cần `field.get(...)` hoặc `setAccessible(true)` cho phép phân loại này.

Nếu cần đọc giá trị trường tĩnh, có thể dùng `field.get(null)`. Với trường tĩnh, đối số đối tượng nhận bị bỏ qua; truyền `null` làm ý định rõ ràng. Việc đọc vẫn chịu kiểm soát truy cập. Trường là `public` không có nghĩa mọi lớp khai báo và ranh giới module đều tự động truy cập được từ mọi nơi.

Quan trọng hơn, đọc trường tĩnh qua Reflection có thể khởi tạo lớp khai báo nếu lớp chưa được khởi tạo. Thí nghiệm sau thể hiện sự khác biệt.

Tạo tệp `EnumMetadataInitializationDemo.java`:

~~~java
import java.lang.reflect.Field;

public class EnumMetadataInitializationDemo {
    public enum Mode {
        ON;

        static {
            System.out.println("Mode initialized");
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Field field = Mode.class.getDeclaredField("ON");
        System.out.println("metadata: " + field.isEnumConstant());
        System.out.println("before reading value");
        System.out.println("value: " + field.get(null));
    }
}
~~~

Biên dịch và chạy trong một tiến trình Java mới:

~~~bash
javac --release 17 -encoding UTF-8 EnumMetadataInitializationDemo.java
java EnumMetadataInitializationDemo
~~~

Kết quả:

~~~text
metadata: true
before reading value
Mode initialized
value: ON
~~~

Hai dòng đầu xuất hiện trước `Mode initialized`. Lấy token `Mode.class`, tìm metadata trường và gọi `isEnumConstant()` chưa làm chạy khối tĩnh trong thí nghiệm này. Đến `field.get(null)`, lớp enum mới được khởi tạo và giá trị `Mode.ON` được đọc.

Đây là khác biệt hữu ích với công cụ khảo sát: nếu chỉ cần phân loại trường, đừng đọc giá trị không cần thiết. Khởi tạo lớp có thể chạy mã do ứng dụng định nghĩa. Nếu quá trình khởi tạo thất bại, thao tác đọc có thể thất bại theo các quy tắc khởi tạo lớp, chứ không còn đơn thuần là truy vấn một cờ metadata.

Ví dụ không chỉnh sửa hằng enum. `isEnumConstant()` không cấp quyền thay giá trị trường, và việc tìm được `Field` không phải lý do để cố ghi vào các trường hằng `final`.

## 7. Chọn cách liệt kê theo mục đích

| Mục đích | Cách phù hợp |
| --- | --- |
| Đang có một `Field`, cần phân loại | `field.isEnumConstant()` |
| Cần các trường hằng để đọc tên hoặc annotation | Duyệt `getDeclaredFields()`, lọc `Field::isEnumConstant` |
| Biết enum ở lúc biên dịch, cần các giá trị | Gọi `Status.values()` |
| Chỉ biết token lớp khi chạy, cần các giá trị | Gọi `enumType.getEnumConstants()` |
| Cần metadata một hằng đã biết tên | `enumType.getDeclaredField(name)`, rồi xác minh bằng `isEnumConstant()` |

`getDeclaredFields()` không cam kết thứ tự khai báo. Trong ví dụ, ta sắp xếp trường theo tên để có kết quả ổn định `[DONE, NEW]`.

Ngược lại, `values()` và `Class.getEnumConstants()` trả về các hằng theo thứ tự khai báo, nên kết quả là `[NEW, DONE]`. Nếu token không biểu diễn lớp enum, `getEnumConstants()` trả về `null`; với enum không có hằng, nó trả về mảng rỗng. Hai tình huống đó khác nhau.

Nếu cần cả **thứ tự khai báo** lẫn metadata trường, hãy đi từ các giá trị enum sang tên khai báo. Ví dụ sau đặt trong `main()` của chương trình thứ nhất:

~~~java
for (Status value : Status.class.getEnumConstants()) {
    Field field = Status.class.getDeclaredField(value.name());
    System.out.println(field.getName() + ": " + field.isEnumConstant());
}
~~~

Kết quả của riêng đoạn thêm này:

~~~text
NEW: true
DONE: true
~~~

Dùng `name()` để tìm trường, không dùng `toString()`. Trong ví dụ:

- Tên khai báo của hằng là `DONE`.
- Chuỗi trình bày của đối tượng là `finished`, vì đã ghi đè `toString()`.
- Không có trường hằng tên `finished`.

Cách đi qua các giá trị có thể khởi tạo lớp enum. Hãy chọn cách này khi cần thứ tự khai báo và chấp nhận việc lấy các giá trị; nếu chỉ cần phân loại metadata, việc lọc các trường đã đủ.

`getFields()` chỉ xét các trường `public` và có thể bao gồm trường được kế thừa. `getDeclaredFields()` tập trung vào các trường được khai báo ngay trong lớp, bao gồm cả các mức truy cập khác và trường hỗ trợ. Với bài toán nhận diện các hằng của chính enum đang xét, bắt đầu từ `getDeclaredFields()` rồi dùng predicate rõ ràng thường dễ kiểm soát hơn.

## 8. Ví dụ áp dụng: lấy metadata hằng cho công cụ

Một công cụ sinh tài liệu có thể cần các `Field` để đọc annotation gắn trên từng hằng, thay vì chỉ lấy các đối tượng enum.

Phương thức sau nhận **token của lớp khai báo enum**, trả về các trường hằng sắp xếp theo tên. Đây là phương thức hỗ trợ, không phải tệp Java độc lập. Thêm các import `java.lang.reflect.Field`, `java.util.Arrays`, `java.util.Comparator`, `java.util.List` và `java.util.Objects` vào lớp chứa nó.

~~~java
static List<Field> enumConstantFields(Class<?> enumType) {
    Objects.requireNonNull(enumType, "enumType");

    if (!enumType.isEnum()) {
        throw new IllegalArgumentException(
                "Expected an enum declaration class: " + enumType.getName());
    }

    return Arrays.stream(enumType.getDeclaredFields())
            .filter(Field::isEnumConstant)
            .sorted(Comparator.comparing(Field::getName))
            .toList();
}
~~~

Ví dụ lời gọi trong ngữ cảnh chương trình mẫu:

~~~java
List<Field> fields = enumConstantFields(Status.class);
for (Field field : fields) {
    System.out.println(field.getName());
}
~~~

Kết quả của đoạn gọi:

~~~text
DONE
NEW
~~~

Nếu đầu vào là `Status.DONE.getClass()`, phương thức hỗ trợ sẽ từ chối vì đó là lớp con riêng của hằng, không phải lớp khai báo enum. Khi xuất phát từ đối tượng enum, hãy truyền `value.getDeclaringClass()` nếu mục đích là khảo sát enum chứa hằng đó.

Việc lọc `isEnumConstant()` giúp tránh đưa `DEFAULT`, `LABEL`, `code` và trường hỗ trợ vào danh sách hằng. Công cụ có thể đọc tiếp các annotation của từng `Field` bằng API annotation tương ứng; khả năng đọc annotation khi chạy còn phụ thuộc chính sách lưu giữ của annotation.

## 9. Những lỗi nên tránh

1. **Dùng kiểu trường để kết luận nó là hằng enum.** `DEFAULT` có kiểu enum nhưng chỉ là một bí danh.
2. **Đọc giá trị rồi kiểm tra đối tượng để phân loại trường.** Cách đó nhầm giá trị với vai trò khai báo và có thể gây khởi tạo lớp không cần thiết.
3. **Lọc mọi trường không synthetic.** Trường dữ liệu thông thường cũng thường không synthetic.
4. **Tin rằng mảng từ getDeclaredFields có thứ tự khai báo.** Muốn thứ tự ổn định thì sắp xếp; muốn thứ tự hằng enum thì dùng API giá trị và ánh xạ lại theo tên.
5. **Dùng toString làm tên trường.** Chuỗi trình bày có thể bị ghi đè hoặc bản địa hóa; `name()` là tên khai báo cần dùng để tìm trường hằng.
6. **Lấy getClass của hằng có phần thân riêng để quét enum.** Hãy phân biệt lớp con của hằng với lớp khai báo enum.
7. **Cho rằng nhận diện được hằng nghĩa là có thể sửa nó.** API này chỉ trả lời câu hỏi phân loại.

## 10. Tự kiểm tra

Với enum `Status` trong chương trình mẫu:

1. Vì sao `NEW` và `DEFAULT` có thể chứa cùng một đối tượng nhưng cho kết quả `isEnumConstant()` khác nhau?
2. `code` được khai báo trong enum; điều đó có làm nó thành hằng enum không?
3. `Status.DONE.getClass().isEnum()` trả về `false` có khiến trường `DONE` mất vai trò hằng enum không?
4. Vì sao danh sách trường sắp xếp theo tên bắt đầu bằng `DONE`, còn danh sách giá trị theo thứ tự khai báo bắt đầu bằng `NEW`?
5. Muốn tìm metadata trường của `Status.DONE`, nên dùng `done.name()` hay `done.toString()`?
6. Chỉ cần biết trường có phải hằng enum thì có cần gọi `field.get(null)` không?
7. Nếu `enumType.getEnumConstants()` trả về `null`, có nên hiểu là enum không có hằng không?

Đáp án:

1. `NEW` là trường biểu diễn một hằng được khai báo trong danh sách hằng; `DEFAULT` là trường thông thường tham chiếu đến hằng đã có. Predicate xét vai trò của trường.
2. Không. Nó là dữ liệu của từng đối tượng enum.
3. Không. Lớp thực tế riêng của đối tượng khác với vai trò khai báo của trường.
4. Hai danh sách dùng hai quy tắc thứ tự khác nhau; `getDeclaredFields()` tự nó không bảo đảm thứ tự khai báo.
5. Dùng `name()`, cho chuỗi `DONE`. `toString()` trong ví dụ cho `finished`.
6. Không. `isEnumConstant()` đọc thông tin phân loại trường; đọc giá trị là thao tác riêng.
7. Không. `null` cho biết token không phải lớp enum; enum không có hằng cho mảng rỗng.
