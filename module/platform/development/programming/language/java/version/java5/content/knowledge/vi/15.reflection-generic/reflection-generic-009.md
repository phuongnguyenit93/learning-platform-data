# GenericArrayType và kiểu phần tử generic

## 1. Vì sao mảng cần một dạng Type riêng?

Một trường `String[] names` có lớp mảng cụ thể là `String[].class`. Nhưng trường `T[] values` trong một lớp generic còn chứa biến kiểu T. Nếu chỉ đọc lớp mảng sau xóa kiểu, ta mất thông tin rằng phần tử vốn được khai báo theo T.

`GenericArrayType` là một dạng của `Type`, dùng để biểu diễn kiểu mảng có thành phần generic như biến kiểu hoặc kiểu được tham số hóa. Phương thức chính là `getGenericComponentType()`, trả **Type của một tầng phần tử**, không nhất thiết là Class. [API GenericArrayType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/GenericArrayType.html)

Nó là mô tả kiểu trong chữ ký. Nó không phải một mảng dữ liệu và không cung cấp độ dài hay giá trị tại chỉ số.

## 2. Ba câu hỏi phải tách biệt

| Câu hỏi | API thường dùng |
| --- | --- |
| Trường được khai báo bằng kiểu generic nào? | `Field.getGenericType()` |
| Kiểu lớp của trường sau xóa kiểu là gì? | `Field.getType()` |
| Một đối tượng mảng hiện có mang lớp mảng nào? | `array.getClass()` |

Ví dụ với `class Box<T extends Number>` có trường `T[] values`:

- Chữ ký generic giữ T[].
- Lớp của trường sau xóa kiểu là Number[] vì cận của T trong ví dụ là Number.
- Lớp thực tế của một giá trị được gán vào trường còn phụ thuộc đối tượng mảng đã được tạo.

Không suy luận rằng mọi T[] đều xóa thành Object[]. Với T không có cận tường minh, Object là cận mặc định; với T có cận, quy tắc xóa kiểu cần xét cận tương ứng. [JLS: xóa kiểu](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.6)

## 3. Không phải mọi kiểu mảng đều là GenericArrayType

| Khai báo | Dạng Type bên ngoài khi đọc chữ ký |
| --- | --- |
| `String[]` | `Class<?>` |
| `int[]` | `Class<?>` |
| `T[]` | `GenericArrayType` |
| `T[][]` | `GenericArrayType`, phần tử một tầng còn là T[] |
| `List<String>[]` | `GenericArrayType`, phần tử là ParameterizedType |
| `List<?>[]` | `GenericArrayType`, phần tử là ParameterizedType |
| `List<T[]>` | `ParameterizedType`; mảng nằm bên trong đối số của List |

Đặc biệt, `List<T[]>` là **danh sách có đối số kiểu là mảng**, không phải một kiểu mảng ở tầng ngoài. Bộ đọc phải xét nút đang đứng trong cấu trúc Type.

Đừng dùng câu “có GenericArrayType thì không thể tạo mảng” làm quy tắc. `List<?>[]` chứa phần tử generic trong chữ ký nhưng ngôn ngữ cho phép biểu thức `new List<?>[2]`; lý do liên quan đến tính xác định được lúc chạy của kiểu phần tử. [JLS: kiểu có thể xác định lúc chạy](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.7)

## 4. Chương trình đọc chữ ký mảng

Lưu toàn bộ vào **GenericArrayTypeDemo.java**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.util.List;

public class GenericArrayTypeDemo {
    static class Model<T extends Number> {
        String[] names;
        int[] counts;
        T[] numbers;
        T[][] matrix;
        List<String>[] groups;
        List<?>[] unknownGroups;
        List<T[]> batches;
    }

    public static void main(String[] args) throws Exception {
        String[] fields = {
            "names", "counts", "numbers", "matrix",
            "groups", "unknownGroups"
        };

        for (String name : fields) {
            Field field = Model.class.getDeclaredField(name);
            Type generic = field.getGenericType();
            Type component = componentOf(generic);

            System.out.println(name
                    + ": generic=" + generic.getTypeName()
                    + ", node=" + kind(generic)
                    + ", erased=" + field.getType().getTypeName());
            System.out.println("  component="
                    + component.getTypeName()
                    + ", node=" + kind(component));
        }

        Type matrix = Model.class.getDeclaredField("matrix")
                .getGenericType();
        System.out.println("matrixDimensions="
                + dimensions(matrix));
        System.out.println("matrixLeaf="
                + leafComponent(matrix).getTypeName());

        Type batches = Model.class.getDeclaredField("batches")
                .getGenericType();
        System.out.println("batchesNode=" + kind(batches));
        if (batches instanceof ParameterizedType list) {
            Type argument = list.getActualTypeArguments()[0];
            System.out.println("batchArgument="
                    + argument.getTypeName()
                    + ", node=" + kind(argument));
        }
    }

    private static Type componentOf(Type type) {
        if (type instanceof GenericArrayType array) {
            return array.getGenericComponentType();
        }

        if (type instanceof Class<?> concrete
                && concrete.isArray()) {
            return concrete.getComponentType();
        }

        return null;
    }

    private static int dimensions(Type type) {
        int result = 0;
        Type current = type;

        while (true) {
            Type component = componentOf(current);
            if (component == null) {
                return result;
            }
            result++;
            current = component;
        }
    }

    private static Type leafComponent(Type type) {
        Type current = type;

        while (true) {
            Type component = componentOf(current);
            if (component == null) {
                return current;
            }
            current = component;
        }
    }

    private static String kind(Type type) {
        if (type instanceof GenericArrayType) {
            return "GenericArrayType";
        }
        if (type instanceof ParameterizedType) {
            return "ParameterizedType";
        }
        if (type instanceof TypeVariable<?>) {
            return "TypeVariable";
        }
        if (type instanceof Class<?>) {
            return "Class";
        }
        return "Other";
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 GenericArrayTypeDemo.java
java GenericArrayTypeDemo
```

Kết quả chuẩn:

```text
names: generic=java.lang.String[], node=Class, erased=java.lang.String[]
  component=java.lang.String, node=Class
counts: generic=int[], node=Class, erased=int[]
  component=int, node=Class
numbers: generic=T[], node=GenericArrayType, erased=java.lang.Number[]
  component=T, node=TypeVariable
matrix: generic=T[][], node=GenericArrayType, erased=java.lang.Number[][]
  component=T[], node=GenericArrayType
groups: generic=java.util.List<java.lang.String>[], node=GenericArrayType, erased=java.util.List[]
  component=java.util.List<java.lang.String>, node=ParameterizedType
unknownGroups: generic=java.util.List<?>[], node=GenericArrayType, erased=java.util.List[]
  component=java.util.List<?>, node=ParameterizedType
matrixDimensions=2
matrixLeaf=T
batchesNode=ParameterizedType
batchArgument=T[], node=GenericArrayType
```

Ví dụ chỉ đọc metadata của trường, không tạo Model và không lấy giá trị của các trường. Vì vậy việc các trường mặc định là `null` không ảnh hưởng kết quả chữ ký. [API Field.getGenericType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Field.html#getGenericType())

## 5. Đọc từng tầng, không nhảy thẳng về Class

Hàm `componentOf` xử lý hai nhánh:

- Với GenericArrayType, gọi `getGenericComponentType()`.
- Với Class biểu diễn mảng, gọi `getComponentType()`.

`Class.getComponentType()` chỉ dùng trên đối tượng Class; nó trả `null` khi Class không biểu diễn mảng. Không có lý do ép T[] thành Class để gọi phương thức này. [API Class.getComponentType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html#getComponentType())

Với T[][]:

```text
T[][]
  → một tầng phần tử: T[]
  → thêm một tầng:     T
```

Hàm `dimensions` đếm các tầng mảng trong mô tả kiểu. Nó không đếm chiều dài từng hàng của một mảng hai chiều. Hàm `leafComponent` dừng tại T vì T không còn là kiểu mảng.

Với `List<String>[]`, sau khi lấy một tầng phần tử, ta nhận ParameterizedType của List<String>. Muốn đọc String, cần dùng `getActualTypeArguments()` trên chính đối tượng ParameterizedType đó. Nếu cứ gọi phương thức lấy phần tử mảng, bộ đọc đã đi nhầm mô hình.

### Biến kiểu cần ngữ cảnh để được giải

Đọc T từ chữ ký không tự cho biết T là Integer hay Double. Nếu một công cụ biết ngữ cảnh T được gắn với Integer, nó có thể xây kết quả kiểu đã thay thế tương ứng; việc này là thuật toán giải biến kiểu, không phải tác dụng tự động của GenericArrayType.

Cận `T extends Number` không có nghĩa “T chính là Number”. Cận dùng để giới hạn kiểu hợp lệ và có vai trò trong xóa kiểu. Khi còn thiếu ngữ cảnh, hãy giữ TypeVariable cùng nơi khai báo thay vì khẳng định đã tìm thấy một kiểu cụ thể. [API TypeVariable](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/TypeVariable.html)

## 6. Đọc chữ ký khác với tạo mảng

Hai đoạn sau là **ví dụ cố ý không hợp lệ**, không nằm trong các chương trình chạy ở bài:

```java
// Inside a generic class with type parameter T:
T[] values = new T[3];

// With java.util.List imported:
List<String>[] groups = new List<String>[3];
```

Java không cho phép các biểu thức tạo mảng này vì kiểu phần tử tương ứng không xác định đầy đủ ở lúc chạy theo quy tắc ngôn ngữ. Tuy nhiên, khai báo trường `T[] values;` hoặc `List<String>[] groups;` vẫn hợp lệ. Đọc được chữ ký không cấp quyền tạo một mảng bằng cú pháp bị cấm. [JLS: biểu thức tạo mảng](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.10.1)

Nếu đã có Class của kiểu phần tử cụ thể, `Array.newInstance` có thể tạo mảng lúc chạy. Tham số của API này là Class, không phải Type tùy ý; không thể truyền trực tiếp GenericArrayType hay ParameterizedType vào đó. [API Array.newInstance](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Array.html#newInstance(java.lang.Class,int))

### Chương trình tạo mảng hợp lệ

Lưu thành **ArrayCreationDemo.java**:

```java
import java.lang.reflect.Array;
import java.util.List;

public class ArrayCreationDemo {
    public static void main(String[] args) {
        String[] names =
                (String[]) Array.newInstance(String.class, 2);
        names[0] = "Lan";

        System.out.println("namesType="
                + names.getClass().getTypeName());
        System.out.println("namesLength="
                + Array.getLength(names));
        System.out.println("firstName=" + names[0]);

        List<?>[] groups = new List<?>[2];
        groups[0] = List.of("x");
        groups[1] = List.of(7);

        System.out.println("groupsType="
                + groups.getClass().getTypeName());
        System.out.println("firstGroupElement="
                + groups[0].get(0).getClass().getSimpleName());
        System.out.println("secondGroupElement="
                + groups[1].get(0).getClass().getSimpleName());
    }
}
```

Chạy:

```shell
javac --release 17 -encoding UTF-8 ArrayCreationDemo.java
java ArrayCreationDemo
```

Kết quả:

```text
namesType=java.lang.String[]
namesLength=2
firstName=Lan
groupsType=java.util.List[]
firstGroupElement=String
secondGroupElement=Integer
```

Phép ép sang String[] có cơ sở vì lời gọi tạo mảng đã chỉ định String.class. Mảng List<?>[] cho phép mỗi phần tử là một List với đối số kiểu chưa xác định; hai danh sách chứa String và Integer đều phù hợp. Lớp mảng runtime chỉ biết thành phần List, không tạo một lớp mảng riêng cho từng đối số generic của các List.

Không dùng `Array.newInstance(List.class, n)` rồi ép thành List<String>[] như một cách “khôi phục String”: mảng tạo ra vẫn chỉ có lớp phần tử List, và phép ép không bổ sung kiểm tra nội dung generic.

## 7. Ứng dụng trong công cụ đọc kiểu

Khi xây mô hình dữ liệu hoặc bộ chuyển đổi, có thể chuẩn hóa bước đọc một tầng mảng bằng cách tương tự `componentOf`. Sau đó giao Type phần tử cho bộ đọc generic chung.

Cần giữ rõ:

1. **Cấu trúc khai báo:** có mấy tầng mảng, Type phần tử là gì?
2. **Ngữ cảnh biến kiểu:** T đã được liên kết với kiểu nào hay vẫn chưa biết?
3. **Lớp cấp phát:** đã có Class đủ dùng để tạo mảng hay chưa?
4. **Dữ liệu hiện tại:** giá trị có null không, độ dài bao nhiêu, chứa gì?

Không trộn bốn câu hỏi thành một phép ép kiểu. Nếu chưa có Class cụ thể cho nhu cầu cấp phát, công cụ phải chọn chiến lược phù hợp hoặc báo không hỗ trợ; không âm thầm dùng Object[] rồi khẳng định đó là đúng loại mảng yêu cầu.

Các lỗi truy cập metadata như `TypeNotPresentException` hoặc `MalformedParameterizedTypeException` cũng khác với việc một Type không phải mảng. Giữ ngữ cảnh kiểu/trường trong thông báo lỗi để người dùng công cụ phân biệt được hai tình huống. [Hợp đồng GenericArrayType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/GenericArrayType.html)

### Những lỗi thường gặp

- Ép kết quả `getGenericType()` thành Class mà không kiểm tra dạng Type.
- Bỏ qua GenericArrayType vì đã xử lý các Class có `isArray() == true`.
- Đọc một tầng của T[][] rồi nghĩ đã đến T.
- Coi `List<T[]>` là mảng ở tầng ngoài.
- Dùng cận Number để khẳng định T thực tế chính là Number.
- Đoán độ dài hoặc kiểu phần tử dữ liệu từ chữ ký.
- Cho rằng GenericArrayType luôn đồng nghĩa với biểu thức tạo mảng bị cấm.

### Tự thực hành

1. Bỏ cận `extends Number` ở Model: lớp mảng sau xóa kiểu của `numbers` và `matrix` thay đổi thế nào?
2. Thêm `T[][][] cube;`: xác nhận số tầng và kiểu cuối cùng.
3. Thêm `List<T>[] pending;`: sau một tầng mảng, còn cần đọc những nút Type nào?
4. So sánh `String[][]` với `T[][]`: cả hai có hai chiều, nhưng dạng Type ở từng tầng khác nhau ra sao?
5. Thêm một trường không phải mảng rồi gọi `componentOf`: phải xử lý `null` trước khi dùng kết quả. Vòng lặp chính hiện chỉ gọi với các trường đã biết là mảng.
6. Tạo mảng Integer bằng `Array.newInstance(Integer.class, 3)`, kiểm tra lớp runtime và phân biệt nó với việc chỉ đọc chữ ký T[].
