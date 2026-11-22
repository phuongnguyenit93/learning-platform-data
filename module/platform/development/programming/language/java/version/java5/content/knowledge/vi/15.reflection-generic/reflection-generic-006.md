# ParameterizedType và các đối số kiểu thực tế

## 1. ParameterizedType biểu diễn điều gì?

`List<String>` không chỉ là lớp/interface List: nó còn có một đối số kiểu là String. Trong reflection, `ParameterizedType` biểu diễn một kiểu sử dụng có thông tin tham số như vậy.

Ta cần mô hình này khi viết bộ đọc cấu hình, bộ ánh xạ dữ liệu hay công cụ phân tích API: biết một trường là Map chưa đủ nếu còn cần biết kiểu khóa và kiểu giá trị. Reflection đọc chữ ký kiểu được khai báo, không tự kiểm tra kiểu của từng phần tử dữ liệu đang nằm trong collection. [API ParameterizedType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/ParameterizedType.html)

Phân biệt:

- **Tham số kiểu (type parameter):** T trong khai báo `class Box<T>`.
- **Đối số kiểu (type argument):** String trong lần sử dụng `Box<String>`.
- **ParameterizedType:** đối tượng mô tả kiểu sử dụng như `Box<String>`; nó không phải một instance Box.

Ví dụ trong bài dùng Java 17 trở lên.

## 2. Ba thành phần cần đọc

| API | Với `Map<String, List<Integer>>` |
| --- | --- |
| `getRawType()` | Kiểu khai báo gốc `Map` |
| `getActualTypeArguments()` | Mảng gồm `String` và `List<Integer>` |
| `getOwnerType()` | `null`, vì Map là kiểu ở cấp cao nhất |

`getRawType()` trả `Type`; các đối tượng ParameterizedType từ core reflection trả Class ở thành phần này. Đừng nhầm “raw type” trong API với lời khuyên khai báo collection bằng kiểu thô. Nó là phần khai báo gốc mà đối tượng ParameterizedType đang mô tả. [Hợp đồng ParameterizedType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/ParameterizedType.html)

Các đối số được trả theo vị trí. Với Map<K, V>, vị trí 0 ứng với K và vị trí 1 ứng với V. Cần kiểm tra số phần tử trước khi đọc chỉ số trong một công cụ tổng quát.

### “Actual” không đồng nghĩa với “đã là một lớp cụ thể”

Trong `List<T>`, đối số thực tế của lần sử dụng List là T, nhưng T vẫn là biến kiểu. Trong `List<? extends Number>`, đối số là wildcard. Do đó không ép mọi phần tử của `getActualTypeArguments()` thành `Class<?>`.

```text
Map<String, List<Integer>>
├── kiểu gốc: Map
├── đối số 0: String
└── đối số 1: List<Integer>
    ├── kiểu gốc: List
    └── đối số 0: Integer
```

Đối số thứ hai là một ParameterizedType khác. Bộ đọc phải đi sâu vào cấu trúc nếu muốn biết Integer.

## 3. Lấy Type từ đâu?

Với trường:

```java
Type type = Model.class.getDeclaredField("values").getGenericType();
if (type instanceof ParameterizedType parameterized) {
    Type[] arguments = parameterized.getActualTypeArguments();
}
```

Đây là đoạn minh họa, cần khai báo Model và import các kiểu reflection. Chương trình đầy đủ ở phần sau.

`Field.getType()` cho kiểu lớp sau xóa kiểu; `Field.getGenericType()` cho mô hình Type của khai báo trường. [API Field.getGenericType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Field.html#getGenericType())

Có thể gặp ParameterizedType từ lớp cha generic, giao diện generic, kiểu trả về hay kiểu tham số phương thức. Dù lấy từ nguồn nào, vẫn cần kiểm tra dạng Type trước khi ép kiểu.

## 4. Chương trình đầy đủ với các dạng đối số

Lưu toàn bộ mã vào **ParameterizedTypeDemo.java**:

```java
import java.lang.reflect.Field;
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.lang.reflect.WildcardType;
import java.util.List;
import java.util.Map;

public class ParameterizedTypeDemo {
    static class Outer<A> {
        class Inner<B> {
        }

        class Plain {
        }
    }

    static class Model<T> {
        Map<String, List<Integer>> values;
        List<T> pending;
        List<? extends Number> numbers;
        List<String>[] rows;
        Outer<String>.Inner<Integer> member;
        Outer<String>.Plain plainMember;
        String label;
    }

    public static void main(String[] args) throws Exception {
        Field field = Model.class.getDeclaredField("values");
        System.out.println("fieldClass="
                + field.getType().getSimpleName());

        ParameterizedType map = requireParameterized(
                field.getGenericType());
        System.out.println("mapRaw=" + rawName(map));
        System.out.println("mapOwnerIsNull="
                + (map.getOwnerType() == null));

        Type[] mapArguments = map.getActualTypeArguments();
        System.out.println("key="
                + mapArguments[0].getTypeName());

        ParameterizedType list = requireParameterized(
                mapArguments[1]);
        System.out.println("valueRaw=" + rawName(list));
        System.out.println("listElement="
                + list.getActualTypeArguments()[0].getTypeName());

        ParameterizedType pending = parameterizedField("pending");
        Type pendingArgument =
                pending.getActualTypeArguments()[0];
        System.out.println("pendingVariable="
                + (pendingArgument instanceof TypeVariable<?>));
        System.out.println("pendingArgument="
                + pendingArgument.getTypeName());

        ParameterizedType numbers = parameterizedField("numbers");
        Type numberArgument =
                numbers.getActualTypeArguments()[0];
        if (numberArgument instanceof WildcardType wildcard) {
            System.out.println("numberUpper="
                    + wildcard.getUpperBounds()[0].getTypeName());
            System.out.println("numberLowerCount="
                    + wildcard.getLowerBounds().length);
        }

        Type rows = Model.class.getDeclaredField("rows")
                .getGenericType();
        System.out.println("rowsGenericArray="
                + (rows instanceof GenericArrayType));
        if (rows instanceof GenericArrayType array) {
            ParameterizedType component =
                    requireParameterized(
                        array.getGenericComponentType());
            System.out.println("rowElement="
                    + component.getActualTypeArguments()[0]
                        .getTypeName());
        }

        ParameterizedType member = parameterizedField("member");
        System.out.println("memberRaw=" + rawName(member));
        System.out.println("memberArgument="
                + member.getActualTypeArguments()[0].getTypeName());

        ParameterizedType owner =
                requireParameterized(member.getOwnerType());
        System.out.println("ownerRaw=" + rawName(owner));
        System.out.println("ownerArgument="
                + owner.getActualTypeArguments()[0].getTypeName());

        ParameterizedType plain =
                parameterizedField("plainMember");
        System.out.println("plainArgumentCount="
                + plain.getActualTypeArguments().length);
        System.out.println("plainOwnerParameterized="
                + (plain.getOwnerType() instanceof ParameterizedType));

        Type label = Model.class.getDeclaredField("label")
                .getGenericType();
        System.out.println("labelParameterized="
                + (label instanceof ParameterizedType));

        Type again = Model.class.getDeclaredField("values")
                .getGenericType();
        System.out.println("sameType=" + map.equals(again));
    }

    private static ParameterizedType parameterizedField(
            String name) throws NoSuchFieldException {
        return requireParameterized(
                Model.class.getDeclaredField(name).getGenericType());
    }

    private static ParameterizedType requireParameterized(
            Type type) {
        if (type instanceof ParameterizedType parameterized) {
            return parameterized;
        }
        throw new IllegalArgumentException(
                "Expected ParameterizedType: " + type);
    }

    private static String rawName(ParameterizedType type) {
        Type raw = type.getRawType();
        if (raw instanceof Class<?> rawClass) {
            return rawClass.getSimpleName();
        }
        return raw.getTypeName();
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ParameterizedTypeDemo.java
java ParameterizedTypeDemo
```

Kết quả chuẩn:

```text
fieldClass=Map
mapRaw=Map
mapOwnerIsNull=true
key=java.lang.String
valueRaw=List
listElement=java.lang.Integer
pendingVariable=true
pendingArgument=T
numberUpper=java.lang.Number
numberLowerCount=0
rowsGenericArray=true
rowElement=java.lang.String
memberRaw=Inner
memberArgument=java.lang.Integer
ownerRaw=Outer
ownerArgument=java.lang.String
plainArgumentCount=0
plainOwnerParameterized=true
labelParameterized=false
sameType=true
```

## 5. Giải thích các trường hợp quan trọng

### Generic lồng nhau phải đọc nhiều cấp

Trường `values` có kiểu Map với hai đối số. Muốn tìm Integer, đi từ đối số 1 của Map sang ParameterizedType của List rồi lấy đối số 0. Lấy đối số đầu tiên của Map sẽ cho String, không phải “kiểu phần tử chung” của toàn bộ cấu trúc.

Mã không tạo Model hay đọc giá trị trường: `getGenericType()` chỉ đọc khai báo. Trường đang mang `null` cũng không làm mất chữ ký generic.

### TypeVariable giữ phần chưa biết

Trường `pending` khai báo `List<T>`. Đọc từ `Model.class` cho TypeVariable T, không phải Object và cũng không tự biết String chỉ vì ở nơi khác có biến `Model<String>`.

Muốn biết T trong một ngữ cảnh cụ thể, phải có thông tin liên kết tham số với đối số từ ngữ cảnh đó rồi thay thế. Cận của biến kiểu chỉ mô tả giới hạn, không phải lúc nào cũng là đối số đã chọn. Hai nơi khai báo đều dùng tên T vẫn có thể là hai biến kiểu khác nhau. [API TypeVariable](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/TypeVariable.html)

### Wildcard là phạm vi, không phải một lựa chọn duy nhất

`? extends Number` cho cận trên Number và không có cận dưới được khai báo. Nó không nói kiểu cụ thể của danh sách là chính Number. Tương tự, `? super Integer` cần đọc cận dưới; cận trên của nó vẫn là Object.

Các phương thức bounds trả mảng Type. Một công cụ tổng quát nên duyệt mảng thay vì mặc định mọi tình huống chỉ có một phần tử; chương trình trên dùng phần tử đầu vì đã biết chính xác khai báo thử nghiệm. [API WildcardType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/WildcardType.html)

### Mảng generic không phải ParameterizedType ở nút ngoài

Trường `rows` là `List<String>[]`: nút ngoài là GenericArrayType, còn kiểu thành phần là ParameterizedType của List<String>. Nếu ép ngay toàn bộ `rows` thành ParameterizedType thì sai.

`String[]` không phải cùng trường hợp này: đó là kiểu mảng có thể được biểu diễn bằng Class. Việc khai báo `List<String>[] rows;` hợp lệ không có nghĩa Java cho phép tạo trực tiếp `new List<String>[10]`. [API GenericArrayType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/GenericArrayType.html), [JLS: kiểu có thể xác định lúc chạy](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.7)

## 6. Owner giữ đối số của lớp bao ngoài

Trong `Outer<String>.Inner<Integer>`:

- Đối số riêng của Inner là Integer.
- Đối số String thuộc Outer được giữ ở `getOwnerType()`.
- Không gộp hai đối số thành một mảng rồi coi vị trí đầu luôn là của Inner.

Trường `plainMember` còn cho thấy một tình huống dễ bỏ sót: Plain không tự khai báo tham số kiểu, nên mảng đối số của nó rỗng, nhưng nó vẫn được biểu diễn bằng ParameterizedType vì nằm trong kiểu bao ngoài đã tham số hóa.

Vì vậy, “là ParameterizedType” không bảo đảm `getActualTypeArguments()[0]` hợp lệ. Luôn xét `length` và owner theo đúng cấu trúc. Kiểu ở cấp cao nhất có owner `null`; đừng áp dụng kết luận đó cho mọi kiểu thành viên. [ParameterizedType: owner và mảng đối số](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/ParameterizedType.html)

## 7. Đọc cấu trúc thay vì phân tích chuỗi

`getTypeName()` phù hợp để hiển thị kết quả như trong bài. Không nên tách chuỗi theo dấu phẩy hay dấu ngoặc nhọn để xây thuật toán: generic lồng nhau, owner và tên lớp có thể làm cách tách đơn giản sai.

Một bộ đọc Type có thể phân nhánh:

```text
Type
├── Class              → kiểu cụ thể hoặc mảng Class
├── ParameterizedType  → raw type + owner + các đối số
├── TypeVariable       → nơi khai báo + tên + cận
├── WildcardType       → các cận
└── GenericArrayType   → kiểu thành phần
```

Nếu duyệt sâu cả cận biến kiểu, cần đề phòng cấu trúc tham chiếu vòng. Ví dụ `T extends Comparable<T>` đưa việc đọc cận quay về T. Bộ duyệt phải có cơ chế nhận biết đã gặp kiểu hoặc giới hạn mục tiêu xử lý.

So sánh các kiểu phản chiếu bằng `equals` theo hợp đồng, không giả định hai lần đọc sẽ luôn trả cùng tham chiếu `==`. `sameType=true` trong chương trình kiểm tra tính bằng nhau về kiểu, không kiểm tra danh tính đối tượng.

Không phụ thuộc một lớp triển khai nội bộ của JDK để nhận biết ParameterizedType; dùng chính giao diện công khai.

## 8. Giới hạn và cách áp dụng

ParameterizedType mô tả kiểu, không thay thế Class ở mọi API và không tự cung cấp hàm tạo để tạo instance `List<String>`. Muốn tạo một collection hoặc ánh xạ dữ liệu, công cụ phải có chính sách chọn kiểu triển khai và đọc/kiểm tra dữ liệu riêng.

Xóa kiểu vẫn có hiệu lực: `new ArrayList<String>()` và `new ArrayList<Integer>()` không tạo hai lớp runtime khác nhau. Có thể đọc thông tin generic được lưu trong khai báo trường như ví dụ, nhưng không suy ra mọi đối số của một instance bất kỳ từ `getClass()`. [JLS: xóa kiểu](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.6)

Khi viết công cụ tổng quát, cần tách ba kết quả:

1. Đã xác định một lớp cụ thể.
2. Có cấu trúc generic nhưng còn biến kiểu/wildcard.
3. Không có đủ metadata cho mục tiêu cần giải.

Đừng biến trường hợp chưa biết thành Object rồi báo rằng kiểu đã được giải hoàn toàn. Việc truy cập metadata cũng có thể gặp lỗi khi chữ ký sai hay kiểu được tham chiếu không tồn tại; hãy báo ngữ cảnh trường/kiểu thay vì thay bằng kết quả rỗng. [API Field.getGenericType](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Field.html#getGenericType())

### Tự thực hành

1. Đổi `values` thành `Map<String, Integer>`. Phần đối số thứ hai còn là ParameterizedType không? Sửa bộ đọc để xử lý được cả hai dạng.
2. Đổi `numbers` thành `List<? super Integer>`: in cả cận trên và cận dưới, rồi giải thích chúng.
3. Đổi `pending` thành `List<List<T>>`: phải đi bao nhiêu tầng trước khi gặp TypeVariable?
4. Với `plainMember`, thử truy cập đối số tại chỉ số 0 để hiểu vì sao cần kiểm tra độ dài; sau đó giữ lại cách kiểm tra an toàn.
5. Thêm trường `String[] names;` và đối chiếu dạng Type với trường `rows`.
6. So sánh `getType()` và `getGenericType()` trên cùng trường Map. Thông tin nào chỉ API generic giữ lại?
