# Đọc kiểu generic của trường, tham số và giá trị trả về

## Metadata của khai báo khác lớp thực của dữ liệu

Khi một trường được khai báo là `List<String>`, bộ đọc reflection có thể cần biết không chỉ đó là `List`, mà còn đối số kiểu `String`. Tương tự, một phương thức có thể trả về `Map<String, List<T>>` và nhận tham số `List<? super T>`.

Thông tin này nằm trong chữ ký generic của **khai báo**. Nó khác với việc gọi `getClass()` trên một đối tượng danh sách rồi cố suy ra mọi phần tử của danh sách có kiểu gì. Reflection không tự duyệt dữ liệu để xác nhận một `List` chỉ chứa `String`.

Bài dùng Java 17+ để đọc ba vị trí: trường, tham số phương thức và kiểu trả về. Các ví dụ không cần framework hoặc tùy chọn mở quyền truy cập.

## Chọn API đúng mục đích

| Vị trí | API trả kiểu sau xóa kiểu | API đọc chữ ký generic |
| --- | --- | --- |
| Trường `Field` | `getType()` → `Class<?>` | `getGenericType()` → `Type` |
| Tham số của `Method` | `getParameterTypes()` → `Class<?>[]` | `getGenericParameterTypes()` → `Type[]` |
| Giá trị trả về của `Method` | `getReturnType()` → `Class<?>` | `getGenericReturnType()` → `Type` |

Ví dụ, `getType()` của trường `List<String> names` cho `List.class`, còn `getGenericType()` biểu diễn đầy đủ `List<String>` nếu thông tin chữ ký tương ứng có trong lớp đã biên dịch. Xem [`Field.getGenericType()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Field.html#getGenericType()).

Kiểu trả về và tham số cũng có cặp API tương tự. Xem [`Method.getGenericReturnType()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html#getGenericReturnType()) và [`Executable.getGenericParameterTypes()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Executable.html#getGenericParameterTypes()).

`Type` là giao diện mô tả kiểu; không được ép mọi kết quả generic thành `Class<?>`. Kiểu lồng, biến kiểu, wildcard và mảng generic đều cần cách đọc tương ứng.

## Những dạng `Type` thường gặp

| Dạng | Ví dụ | Phần thông tin cần đọc |
| --- | --- | --- |
| `Class<?>` | `String`, `Number`, `String[]` | Metadata của kiểu lớp/interface, primitive hoặc mảng cụ thể |
| `ParameterizedType` | `List<String>`, `Map<String, List<T>>` | `getRawType()`, `getActualTypeArguments()`, khi cần thêm `getOwnerType()` |
| `TypeVariable<?>` | `T`, `E` | Tên, các cận trên, nơi khai báo biến kiểu |
| `WildcardType` | `?`, `? extends Number`, `? super T` | Các cận trên và cận dưới |
| `GenericArrayType` | `T[]`, `List<String>[]` | `getGenericComponentType()` |

Đối số kiểu của `ParameterizedType` tiếp tục là `Type`, nên có thể cần đọc nhiều cấp. Chẳng hạn trong `Map<String, List<T>>`, đối số thứ hai không phải `Class`, mà là một `ParameterizedType` khác. Xem [`ParameterizedType`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/ParameterizedType.html).

## Ví dụ hoàn chỉnh

Lưu toàn bộ mã dưới đây trong `GenericSignatureDemo.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.lang.reflect.WildcardType;
import java.util.List;
import java.util.Map;

public final class GenericSignatureDemo {
    private GenericSignatureDemo() {
    }

    static class Store<T extends Number> {
        List<String> names;
        List<? extends Number> limits;
        T current;
        T[] history;

        public Map<String, List<T>> group(List<? super T> target, T[] input) {
            return Map.of();
        }

        public <E extends CharSequence> List<E> copy(List<E> input) {
            return List.copyOf(input);
        }
    }

    private static String kind(Type type) {
        if (type instanceof Class<?>) {
            return "Class";
        }
        if (type instanceof ParameterizedType) {
            return "ParameterizedType";
        }
        if (type instanceof TypeVariable<?>) {
            return "TypeVariable";
        }
        if (type instanceof WildcardType) {
            return "WildcardType";
        }
        if (type instanceof GenericArrayType) {
            return "GenericArrayType";
        }
        throw new IllegalArgumentException("unsupported Type: " + type);
    }

    private static void show(String label, Type type) {
        System.out.println(label + ": " + kind(type) + " | " + type.getTypeName());
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        for (String name : List.of("names", "limits", "current", "history")) {
            Field field = Store.class.getDeclaredField(name);
            System.out.println(name + ".raw: " + field.getType().getTypeName());
            show(name + ".generic", field.getGenericType());
        }

        Field names = Store.class.getDeclaredField("names");
        if (names.getGenericType() instanceof ParameterizedType parameterized) {
            show("names.argument", parameterized.getActualTypeArguments()[0]);
        }

        Method group = Store.class.getDeclaredMethod("group", List.class, Number[].class);
        show("group.return", group.getGenericReturnType());
        Type[] parameters = group.getGenericParameterTypes();
        show("group.parameter0", parameters[0]);
        show("group.parameter1", parameters[1]);
        System.out.println("group.rawReturn: " + group.getReturnType().getTypeName());

        ParameterizedType targetType = (ParameterizedType) parameters[0];
        WildcardType wildcard = (WildcardType) targetType.getActualTypeArguments()[0];
        show("target.lowerBound", wildcard.getLowerBounds()[0]);
        show("target.upperBound", wildcard.getUpperBounds()[0]);

        TypeVariable<?> classVariable = Store.class.getTypeParameters()[0];
        show("T.bound", classVariable.getBounds()[0]);

        Method copy = Store.class.getDeclaredMethod("copy", List.class);
        show("copy.return", copy.getGenericReturnType());
        TypeVariable<Method> methodVariable = copy.getTypeParameters()[0];
        show("E.bound", methodVariable.getBounds()[0]);
        System.out.println("E.declaredBy: "
                + methodVariable.getGenericDeclaration().getName());
    }
}
```

`Store` có các trường để khảo sát metadata. Phương thức `group` trả một map rỗng và `copy` tạo bản sao danh sách để ví dụ có phần thân hợp lệ; chương trình chính không cần tạo `Store` hay gọi hai phương thức này.

Chạy tại thư mục chứa tệp bằng JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror GenericSignatureDemo.java
java GenericSignatureDemo
```

Stdout chính xác:

```text
names.raw: java.util.List
names.generic: ParameterizedType | java.util.List<java.lang.String>
limits.raw: java.util.List
limits.generic: ParameterizedType | java.util.List<? extends java.lang.Number>
current.raw: java.lang.Number
current.generic: TypeVariable | T
history.raw: java.lang.Number[]
history.generic: GenericArrayType | T[]
names.argument: Class | java.lang.String
group.return: ParameterizedType | java.util.Map<java.lang.String, java.util.List<T>>
group.parameter0: ParameterizedType | java.util.List<? super T>
group.parameter1: GenericArrayType | T[]
group.rawReturn: java.util.Map
target.lowerBound: TypeVariable | T
target.upperBound: Class | java.lang.Object
T.bound: Class | java.lang.Number
copy.return: ParameterizedType | java.util.List<E>
E.bound: Class | java.lang.CharSequence
E.declaredBy: copy
```

Chương trình lấy từng trường theo tên để đầu ra có thứ tự rõ ràng. Nó phân loại theo các giao diện reflection công khai, không dựa vào tên lớp triển khai nội bộ của đối tượng `Type`.

Hàm `show` dùng `getTypeName()` để trình bày. Khi viết bộ phân tích thật, hãy dùng cấu trúc `Type`; không tách chuỗi tên theo dấu `<`, `>` hoặc dấu phẩy để suy luận các thành phần.

## Đọc trường: giữ riêng kiểu bị xóa và kiểu khai báo

`names.raw` chỉ là `List`; `names.generic` là `List<String>`. Bên trong `ParameterizedType` của trường này, `getActualTypeArguments()[0]` trả một `Type` biểu diễn `String`, và trong trường hợp cụ thể đó nó là `Class<?>`.

`current` được khai báo là `T`, với `T extends Number`. Vì vậy `getType()` của trường cho `Number`, còn `getGenericType()` giữ biến kiểu `T`. Cận không đồng nghĩa với giá trị cụ thể: biết `T extends Number` không chứng minh `T` phải là `Integer`.

`history` thể hiện cùng khác biệt ở mảng: kiểu sau xóa kiểu là `Number[]`, còn chữ ký generic là `T[]`, được biểu diễn bằng `GenericArrayType`. Để đọc thành phần generic, dùng `getGenericComponentType()`; không ép trực tiếp `T[]` thành một `Class` mô tả mảng cụ thể. Xem [`GenericArrayType`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/GenericArrayType.html).

Ngược lại, với một trường được khai báo `String[]`, `getGenericType()` có thể là `Class<?>` của `String[]`; không phải cứ thấy mảng là dùng `GenericArrayType`.

Việc đọc metadata của một trường bằng `getGenericType()` không giống đọc giá trị trường bằng `get(obj)`. Trường của ví dụ không `public`, nhưng ta vẫn lấy khai báo và khảo sát chữ ký mà không sửa khả năng truy cập để đọc dữ liệu bên trong.

## Tìm phương thức bằng kiểu đã xóa, rồi đọc chữ ký generic

Lời gọi:

```java
Store.class.getDeclaredMethod("group", List.class, Number[].class);
```

tìm phương thức theo tên và các `Class` của tham số sau xóa kiểu. Tham số đầu bị xóa thành `List`; tham số `T[]` bị xóa thành `Number[]` vì cận trái nhất của `T` là `Number`.

Không truyền `String.class` hoặc `Integer[].class` chỉ vì tưởng tượng một lần sử dụng `Store<Integer>`. Khai báo đang được tìm vẫn là phương thức trong `Store`; các kiểu dùng để tra cứu phải khớp chữ ký sau xóa kiểu.

Sau khi có `Method`, `getGenericReturnType()` cho cấu trúc `Map<String, List<T>>`. `getGenericParameterTypes()` trả các kiểu theo thứ tự tham số khai báo: `List<? super T>` rồi `T[]`.

Các phép ép `ParameterizedType` và `WildcardType` trong phần đọc `target` của ví dụ có căn cứ vì mã đang khảo sát chính chữ ký cố định vừa khai báo. Với bộ đọc dùng cho lớp bất kỳ, phải kiểm tra `instanceof` ở từng bước trước khi ép.

## Wildcard và biến kiểu không phải kiểu cụ thể

Tham số `List<? super T>` chứa wildcard. `getLowerBounds()` của wildcard trả `T`, còn `getUpperBounds()` trả `Object`. Đây là hai phía của thông tin cận; không thay `? super T` bằng `T` rồi kết luận danh sách có đúng một kiểu phần tử cố định. Xem [`WildcardType`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/WildcardType.html).

Với `? extends Number`, cận trên là `Number` và không có cận dưới được khai báo; `getLowerBounds()` trả mảng rỗng. Với `?` không giới hạn, cận trên là `Object`. Vì các API cận trả mảng, mã phân tích nên xử lý mảng đúng nghĩa, không mặc định mọi kết quả luôn có phần tử tại chỉ số `0`.

`T` thuộc khai báo lớp `Store`; `E` lại thuộc khai báo phương thức `copy`. `copy.getTypeParameters()` chỉ liệt kê các biến kiểu do chính phương thức khai báo, không phải mọi biến kiểu có thể xuất hiện trong chữ ký của nó.

`getGenericDeclaration()` cho biết biến kiểu thuộc lớp, phương thức hay hàm tạo nào. Hai biến cùng tên `T` ở hai nơi khai báo khác nhau không phải vì cùng tên mà là cùng biến kiểu. Với việc ánh xạ biến kiểu, dùng `TypeVariable` và quy tắc bình đẳng của nó thay cho khóa tên chuỗi hoặc danh tính đối tượng. Xem [`TypeVariable`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/TypeVariable.html).

## Duyệt một cấu trúc kiểu có nhiều cấp

Một bộ đọc tổng quát cần đi theo từng loại:

1. Gặp `Class<?>`: ghi nhận kiểu cụ thể; nếu là mảng và cần phân tích sâu, xét kiểu thành phần.
2. Gặp `ParameterizedType`: xử lý kiểu gốc, kiểu chủ nếu có và từng đối số kiểu.
3. Gặp `WildcardType`: xử lý cả cận trên và cận dưới theo mục tiêu phân tích.
4. Gặp `GenericArrayType`: xử lý kiểu thành phần generic.
5. Gặp `TypeVariable<?>`: giữ danh tính biến kiểu và nơi khai báo; chỉ mở các cận khi mục tiêu cần đến chúng.

Cẩn thận khi duyệt đệ quy cận biến kiểu. Khai báo như `T extends Comparable<T>` chứa lại chính `T`; nếu luôn mở cận mà không theo dõi các biến đã thăm, bộ đọc có thể lặp vô hạn. Một bộ in cấu trúc có thể in tên `T` tại lần gặp lại thay vì mở cận lần nữa.

`getOwnerType()` cũng có ý nghĩa với kiểu thành viên của một kiểu khác. Không chỉ đọc `getActualTypeArguments()` rồi cho rằng đã nắm hết mọi thông tin của các lớp lồng có generic.

## `Store<Integer>` không tự thay mọi `T` trong `Field`

Đọc `Store.class.getDeclaredField("current").getGenericType()` luôn mô tả khai báo trường `T`. Chỉ tạo `new Store<Integer>()` không làm metadata của `Field` đó tự đổi thành `Integer.class`.

Nếu lớp khác khai báo một trường `Store<Integer> store`, chữ ký của **trường đó** có thể chứa `Integer`. Hoặc một lớp con có thể công bố `extends Store<Integer>` trong chữ ký lớp cha. Để diễn giải `current` trong ngữ cảnh cụ thể ấy, cần lập ánh xạ từ biến kiểu `T` của `Store` sang đối số `Integer` rồi áp dụng ánh xạ trên cấu trúc kiểu.

Đọc chữ ký khai báo và phân giải biến kiểu theo ngữ cảnh là hai công việc khác nhau. Không xem cận `Number` là giá trị thay thế mặc định cho `T`, và không suy ra `Integer` chỉ từ dữ liệu tình cờ đang lưu trong trường.

## Tham số: kiểu generic khác tên tham số và annotation kiểu

Có thể đọc từng đối tượng `Parameter` bằng `method.getParameters()`, rồi gọi `getParameterizedType()` để lấy thông tin kiểu. Đây là một lối truy cập khác cho tham số, không biến kiểu tổng quát thành kiểu cụ thể. Xem [`Parameter.getParameterizedType()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Parameter.html#getParameterizedType()).

Không cần `-parameters` để ví dụ đọc được `List<? super T>` hoặc `T[]`. Tùy chọn đó liên quan đến việc lưu tên tham số cho reflection; tên như `target` và `input` không được dùng để xác định kiểu trong chương trình.

Annotation trên kiểu sử dụng là một lớp thông tin khác. Khi cần đọc những annotation đó, xét các API `getAnnotatedType`, `getAnnotatedParameterTypes` và `getAnnotatedReturnType`; chỉ đọc `Type` không phải cách lấy toàn bộ annotation kiểu.

## Lỗi thường gặp và kiểm tra cần thiết

- Ép mọi `getGenericType()` thành `ParameterizedType`: trường `T`, `T[]` hoặc `String` sẽ không phù hợp.
- Ép mọi đối số của `List<...>` thành `Class<?>`: đối số có thể là wildcard, biến kiểu hoặc kiểu có tham số khác.
- Tìm phương thức bằng kiểu chưa xóa hoặc kiểu được đoán từ một instance: có thể dẫn đến `NoSuchMethodException`.
- Xem chữ ký generic như sự kiểm chứng dữ liệu thực: metadata không tự ngăn dữ liệu sai bị đưa vào qua raw type hoặc một đường không an toàn.
- Dựa vào tên lớp triển khai của `Type`: hãy dùng các giao diện công khai và quy tắc cấu trúc.

Các API generic có thể báo lỗi khi chữ ký trong bytecode không hợp lệ hoặc tham chiếu kiểu không có mặt trong môi trường chạy. Với bộ đọc dùng cho thư viện ngoài, cần phân biệt lỗi metadata như `GenericSignatureFormatError`, `TypeNotPresentException` hoặc `MalformedParameterizedTypeException` với trường hợp kiểu đơn giản không có đối số generic.

## Thực hành đối chiếu

1. Đổi trường `names` từ `List<String>` thành `List<Integer>`. Kiểu raw vẫn là `java.util.List`, còn chữ ký và `names.argument` đổi sang `java.lang.Integer`.
2. Đổi `limits` thành `List<?>`; đọc đối số wildcard và xác nhận cận trên là `Object`, cận dưới là mảng rỗng.
3. Đổi `history` thành `String[]`. Dòng raw và generic đều biểu diễn `java.lang.String[]`, nhưng nhãn generic trở thành `Class`.
4. Thêm một biến kiểu của phương thức rồi so sánh `method.getTypeParameters()` với `Store.class.getTypeParameters()` để xác định nơi khai báo.
5. Đổi `T extends Number` thành `T extends CharSequence` và cập nhật phần tìm `group` dùng `CharSequence[].class`; nếu không cập nhật kiểu tham số tra cứu, chương trình không tìm được khai báo phương thức.

Sau bài học, cần chỉ ra được API nào đọc từng vị trí khai báo, vì sao kết quả là `Type` và ở bước nào cần phân giải thêm ngữ cảnh thay vì tự đoán một `Class` cụ thể.