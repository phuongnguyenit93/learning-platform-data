# Phân biệt getType() với getGenericType()

## Một trường có nhiều góc nhìn về kiểu

Giả sử khai báo một trường `List<String> names`, nhưng giá trị hiện tại của nó là một `ArrayList`. Có ba thông tin khác nhau:

- Kiểu trường sau xóa kiểu: `List`.
- Chữ ký generic của khai báo: `List<String>`.
- Lớp thực của đối tượng hiện đang được lưu: `ArrayList`.

`Field.getType()` phục vụ góc nhìn thứ nhất; `Field.getGenericType()` phục vụ góc nhìn thứ hai. Muốn biết góc nhìn thứ ba, phải đọc giá trị rồi khảo sát chính đối tượng đó.

Bài dùng Java 17+ và tập trung vào trường (`Field`), giúp chọn đúng API mà không nhầm metadata của khai báo với dữ liệu lúc chạy.

## So sánh hợp đồng của hai phương thức

| Nội dung | `getType()` | `getGenericType()` |
| --- | --- | --- |
| Kiểu kết quả | `Class<?>` | `Type` |
| Mức thông tin | Kiểu trường sau xóa kiểu | Kiểu khai báo, gồm generic khi có chữ ký tương ứng |
| Với `List<String>` | `List.class` | `ParameterizedType` biểu diễn `List<String>` |
| Với `T extends Number`, trường `T` | `Number.class` | `TypeVariable` biểu diễn `T` |
| Với `String` | `String.class` | Cũng là `String.class`, dưới kiểu giao diện `Type` |
| Có tự đọc giá trị trường không? | Không | Không |

Xem hợp đồng của [`Field.getType()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Field.html#getType()) và [`Field.getGenericType()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Field.html#getGenericType()).

`Class` triển khai `Type`, nên việc `getGenericType()` trả `Type` không có nghĩa mọi kết quả phải là một đối tượng `ParameterizedType`. `Type` có thể biểu diễn lớp, kiểu có tham số, biến kiểu và các dạng khác. Xem [`Type`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Type.html).

## Ví dụ hoàn chỉnh với nhiều dạng trường

Lưu tệp `FieldTypeComparison.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.util.ArrayList;
import java.util.List;

public final class FieldTypeComparison {
    private FieldTypeComparison() {
    }

    static class Model<T extends Number> {
        String title;
        int count;
        List<String> names = new ArrayList<>();
        List<?> unknowns;
        T item;
        T[] items;
        String[] labels;
        List<String>[] groups;
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
        if (type instanceof GenericArrayType) {
            return "GenericArrayType";
        }
        throw new IllegalArgumentException("unsupported field type: " + type);
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        List<String> fieldNames = List.of(
                "title", "count", "names", "unknowns",
                "item", "items", "labels", "groups");
        for (String name : fieldNames) {
            Field field = Model.class.getDeclaredField(name);
            Class<?> erased = field.getType();
            Type generic = field.getGenericType();
            System.out.println(name + ": " + erased.getTypeName()
                    + " | " + kind(generic) + " | " + generic.getTypeName());
        }

        Field names = Model.class.getDeclaredField("names");
        Type namesType = names.getGenericType();
        if (namesType instanceof ParameterizedType parameterized) {
            System.out.println("names.argument: "
                    + parameterized.getActualTypeArguments()[0].getTypeName());
        }

        Field title = Model.class.getDeclaredField("title");
        System.out.println("title.sameType: "
                + title.getType().equals(title.getGenericType()));

        Model<Integer> model = new Model<>();
        Object value = names.get(model);
        System.out.println("names.valueClass: " + value.getClass().getTypeName());
        Field item = Model.class.getDeclaredField("item");
        System.out.println("item.inIntegerModel: " + item.getGenericType().getTypeName());
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp bằng JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror FieldTypeComparison.java
java FieldTypeComparison
```

Stdout chính xác:

```text
title: java.lang.String | Class | java.lang.String
count: int | Class | int
names: java.util.List | ParameterizedType | java.util.List<java.lang.String>
unknowns: java.util.List | ParameterizedType | java.util.List<?>
item: java.lang.Number | TypeVariable | T
items: java.lang.Number[] | GenericArrayType | T[]
labels: java.lang.String[] | Class | java.lang.String[]
groups: java.util.List[] | GenericArrayType | java.util.List<java.lang.String>[]
names.argument: java.lang.String
title.sameType: true
names.valueClass: java.util.ArrayList
item.inIntegerModel: T
```

Mỗi dòng trường lần lượt in: **tên trường | kết quả `getType()` | dạng của kết quả generic | tên kiểu generic**. Trong định dạng thực tế của chương trình, dấu hai chấm nằm sau tên trường và các phần dữ liệu còn lại ngăn bởi ` | `.

Các trường được lấy theo danh sách tên cố định để đầu ra có thứ tự xác định. Chương trình không dựa vào thứ tự trả về của một mảng liệt kê toàn bộ trường.

## Trường không dùng đối số kiểu: hai API có thể cùng mô tả một kiểu

`title` khai báo `String`, vì vậy cả hai API cùng biểu diễn `String.class`. Dòng `title.sameType: true` xác nhận điều đó bằng `equals`.

`count` là primitive `int`, nên metadata vẫn là đối tượng `Class` đại diện cho `int`, không phải `Integer.class`. Hai API không tự đóng hộp kiểu khai báo thành wrapper.

`labels` là `String[]`. Nó cũng có một đối tượng `Class` biểu diễn kiểu mảng hoàn chỉnh. Do vậy `getGenericType()` của trường này là `Class`, không phải `GenericArrayType`.

Việc tên phương thức có chữ “Generic” không bắt buộc kết quả phải chứa generic. Nó có kiểu kết quả đủ rộng để mô tả cả những trường không cần cấu trúc phức tạp.

## Trường có tham số kiểu: thông tin bị mất khi chỉ lấy `Class`

`names` có chữ ký `List<String>`. `getType()` chỉ cho `List.class`; kết quả đó không chứa một đối số `String` để tiếp tục đọc.

`getGenericType()` của trường này là `ParameterizedType`. Từ đó, `getActualTypeArguments()` cho các đối số kiểu. Trong ví dụ cố định, đối số đầu là `String.class` nên chương trình in `java.lang.String`.

`unknowns` khai báo `List<?>`, không phải một trường không có thông tin generic. Kết quả vẫn là `ParameterizedType`, nhưng đối số là wildcard, không phải một `Class` cụ thể. Nếu cần đi sâu, phải xử lý `WildcardType` và các cận của nó.

Không viết một phép ép mặc định như `(Class<?>) parameterized.getActualTypeArguments()[0]` trong bộ đọc dùng cho mọi trường. Đối số kiểu còn có thể là `T`, `List<String>` hoặc wildcard. Kiểm tra cấu trúc `Type` tại mỗi bước.

Với một trường `Map<String, List<Integer>>`, nguyên tắc này tiếp tục áp dụng ở nhiều cấp: đối số thứ hai là một kiểu có tham số khác, không phải chỉ `List.class`. Một bộ đọc schema hoặc công cụ hiển thị chữ ký cần giữ cây cấu trúc đó.

## Biến kiểu và xóa kiểu

`Model` khai báo `T extends Number`. Trường `item` dùng biến `T`, nên:

- `getType()` trả `Number.class`, tương ứng kiểu sau xóa kiểu của `T`.
- `getGenericType()` trả biến `T` để giữ mối quan hệ generic trong khai báo.

Đối với mảng `T[]`, xóa kiểu được áp dụng lên kiểu thành phần, nên `getType()` cho `Number[].class`; `getGenericType()` giữ cấu trúc `T[]` bằng `GenericArrayType`. Xem [quy tắc xóa kiểu trong JLS](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.6).

Không dùng cận `Number` để kết luận đối số kiểu thực tế đã được chọn. Nó là giới hạn khai báo, không phải một phép suy ra `Integer` hoặc `Double` từ một instance.

Ví dụ tạo `Model<Integer>` nhưng dòng cuối vẫn in `T`: đối tượng `Field` mô tả khai báo trong `Model`, không tự nhận thêm ngữ cảnh `Integer` từ biến `model`. Nếu muốn phân giải `T` theo một cách sử dụng cụ thể, cần metadata của ngữ cảnh và ánh xạ biến kiểu riêng.

## Hai loại mảng cần phân biệt

| Trường | `getType()` | `getGenericType()` |
| --- | --- | --- |
| `String[] labels` | `Class` của `String[]` | Cũng là `Class` của `String[]` |
| `T[] items` | `Class` của `Number[]` trong ví dụ | `GenericArrayType`, thành phần là biến `T` |
| `List<String>[] groups` | `Class` của `List[]` | `GenericArrayType`, thành phần là `List<String>` |

`groups` chỉ được khai báo để khảo sát metadata; ví dụ không tạo mảng bằng `new List<String>[...]`, vốn không hợp lệ. Một khai báo kiểu trường hợp lệ không có nghĩa mọi biểu thức tạo mảng với cùng cách viết đều được phép.

Khi đã nhận diện `GenericArrayType`, dùng `getGenericComponentType()` để đọc thành phần. Khi nhận được `Class<?>` và cần phân tích mảng, dùng `isArray()` cùng `getComponentType()` trên đối tượng `Class` đó.

## Không nhầm với giá trị trường

`names.get(model)` trong chương trình mới là thao tác đọc giá trị của trường trên một đối tượng. Giá trị đang là `ArrayList`, nên gọi `getClass()` trên kết quả cho `java.util.ArrayList`.

Điều này không làm `names.getType()` đổi từ `List` thành `ArrayList`, cũng không làm chữ ký generic đổi. Nếu thay dữ liệu lưu bằng một cách triển khai `List` khác, metadata khai báo vẫn mô tả `List<String>`.

Đọc metadata của khai báo không cần một instance; phần vòng lặp đầu tiên dùng `Model.class` là đủ. Đọc giá trị instance bằng `Field.get` lại cần một đối tượng phù hợp và phải tuân thủ kiểm tra truy cập. Ví dụ đặt mã khảo sát và lớp lồng trong cùng chương trình; không có thao tác thay đổi quyền truy cập.

Nếu trường tham chiếu đang là `null`, hai API metadata vẫn trả kiểu khai báo; chỉ chuỗi thao tác đọc giá trị rồi gọi `getClass()` mới thất bại vì giá trị `null`.

## Dùng API nào trong ứng dụng?

| Nhu cầu | Lựa chọn khởi đầu |
| --- | --- |
| Kiểm tra trường có kiểu primitive, enum, mảng hoặc có tương thích một lớp ở mức bị xóa không | `getType()` |
| Hiển thị khai báo như `List<String>` hoặc phân tích schema có đối số kiểu | `getGenericType()` |
| Xác định lớp thực của đối tượng đang nằm trong trường | Đọc giá trị rồi dùng `getClass()` nếu khác `null` |
| Đọc annotation trên kiểu sử dụng | `getAnnotatedType()` và các API `AnnotatedType` tương ứng |

Không dùng `getGenericType()` như một phép kiểm tra dữ liệu tự động. Có chữ ký `List<String>` không chứng minh mọi giá trị bên trong một đối tượng không an toàn đều là chuỗi; metadata mô tả khai báo chứ không duyệt phần tử.

Không phân tích generic bằng cách tách `getTypeName()` theo dấu phẩy hoặc ngoặc nhọn. Tên kiểu phù hợp để trình bày, còn thuật toán cần dùng `instanceof` với `Class`, `ParameterizedType`, `TypeVariable`, `WildcardType` và `GenericArrayType` theo cấu trúc gặp được.

## Chất lượng metadata và giới hạn nguồn đầu vào

Thông tin generic phụ thuộc chữ ký được lưu trong lớp đã biên dịch. Nếu một công cụ xử lý bytecode loại bỏ chữ ký generic, reflection không thể tự dựng lại chính xác mọi đối số kiểu từ dữ liệu hiện tại.

Đọc metadata generic từ lớp được sinh hoặc thư viện bên ngoài cũng có thể phát hiện chữ ký không hợp lệ hay kiểu tham chiếu không có mặt. Các lỗi như `GenericSignatureFormatError`, `TypeNotPresentException` hoặc `MalformedParameterizedTypeException` không đồng nghĩa với một trường thông thường không có đối số generic.

Các công cụ đọc metadata nên phân biệt: kiểu đơn giản hợp lệ, cấu trúc generic chưa được hỗ trợ và metadata bị lỗi. Không đổi cả ba trường hợp thành một kết quả “Object” để tiếp tục âm thầm.

## Thực hành kiểm chứng

1. Đổi trường `names` từ `List<String>` thành `List<Integer>`. `getType()` vẫn cho `List`; phần generic và đối số đầu đổi thành `Integer`.
2. Đổi `T extends Number` thành `T extends CharSequence` và đổi instance thử thành `Model<String>`. `item` sau xóa kiểu trở thành `CharSequence`, nhưng phần generic vẫn là `T`.
3. Bỏ phần khởi tạo `names = new ArrayList<>()`, chỉ giữ khai báo. Các dòng metadata giữ nguyên; cần kiểm tra `null` trước khi in lớp thực của giá trị.
4. Đổi `labels` sang `Integer[]`. Hai API tiếp tục nhận diện kiểu mảng cụ thể bằng `Class`, với thành phần mới.
5. Lấy đối số của `unknowns` và kiểm tra nó là `WildcardType`; đừng ép trực tiếp thành `Class`.

Để giải thích một kết quả, hãy nêu rõ mình đang đọc kiểu sau xóa kiểu, cấu trúc generic của khai báo hay lớp thực của dữ liệu. Ba câu trả lời có thể khác nhau mà đều đúng.