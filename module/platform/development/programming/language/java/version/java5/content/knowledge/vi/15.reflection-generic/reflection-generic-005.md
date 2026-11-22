# Vai trò của Type trong mô hình reflection

## Khái niệm: vì sao Class<?> chưa đủ?

`Class<?>` rất phù hợp để biểu diễn một lớp, interface, kiểu mảng cụ thể hoặc kiểu nguyên thủy tại lúc chạy. Tuy nhiên, một khai báo Java còn có thể chứa các hình thức kiểu như:

- `List<String>`: kiểu được gắn tham số kiểu.
- `T`: biến kiểu.
- `? extends Number`: wildcard có giới hạn.
- `T[]`: mảng có kiểu thành phần là biến kiểu.

Không thể biểu diễn tất cả các cấu trúc đó bằng một `Class<?>` duy nhất mà vẫn giữ nguyên thông tin generic.

`java.lang.reflect.Type` là interface chung cho mô hình mô tả kiểu trong reflection. `Class` là một cách triển khai `Type`; bên cạnh đó còn có các interface dành cho những dạng kiểu generic khác.

Vai trò quan trọng của `Type` là cho phép API trả về **một mô tả kiểu tổng quát**, sau đó người đọc phân biệt cấu trúc cụ thể để lấy thông tin cần dùng.

Đây là API vẫn áp dụng trong Java hiện đại. Chương trình trong bài chạy trên JDK 17 trở lên và không cần thư viện ngoài.

## Từ một lớp đến một biểu thức kiểu có cấu trúc

So sánh hai câu hỏi về field:

```java
List<String> labels;
```

Đây là một khai báo minh họa, chưa phải chương trình độc lập.

- “Field này dùng lớp hoặc interface nào sau xóa kiểu?” → `List`.
- “Field này được khai báo với thông tin generic nào?” → `List<String>`.

Với đối tượng `Field` tương ứng:

| API | Kiểu kết quả | Thông tin |
| --- | --- | --- |
| `getType()` | `Class<?>` | Kiểu của field ở mức lớp sau xóa kiểu |
| `getGenericType()` | `Type` | Kiểu khai báo, có thể giữ cấu trúc generic |

Vì vậy, `getGenericType()` không hứa rằng kết quả luôn là `Class`. Trong ví dụ này, kết quả là một `ParameterizedType`.

Nếu người viết ép mọi `Type` về `Class<?>`, mã có thể chạy với field kiểu `String`, rồi thất bại khi gặp `List<String>` hoặc `T`.

Đọc định nghĩa chung tại [Type](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Type.html) và API field tại [Field.getGenericType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html#getGenericType()).

## Các dạng chính trong mô hình Type

```text
Type
├── Class
├── ParameterizedType
├── TypeVariable
├── WildcardType
└── GenericArrayType
```

Sơ đồ thể hiện các dạng chính mà mã reflection cần nhận diện. `Class` là lớp triển khai, còn bốn tên còn lại là các interface mở rộng `Type`.

| Dạng | Ví dụ khai báo được mô tả | Câu hỏi để đọc tiếp |
| --- | --- | --- |
| `Class<?>` | `String`, `int`, `String[]`, hoặc `List` không kèm đối số kiểu | Lớp/interface nào? Có phải mảng không? |
| `ParameterizedType` | `List<String>`, `Map<String, List<Integer>>` | Kiểu gốc, đối số kiểu và kiểu sở hữu là gì? |
| `TypeVariable<?>` | `T` trong `Box<T>` | Biến kiểu do khai báo nào tạo ra? Giới hạn là gì? |
| `WildcardType` | `?`, `? extends Number`, `? super Integer` | Giới hạn trên/dưới là gì? |
| `GenericArrayType` | `T[]`, `List<String>[]` | Kiểu thành phần generic là gì? |

Wildcard thường xuất hiện bên trong danh sách đối số kiểu của một `ParameterizedType`; không nên trông chờ mọi field có wildcard sẽ trả trực tiếp `WildcardType` ở nút ngoài cùng.

Ví dụ, `List<? extends Number>` có nút ngoài là `ParameterizedType`; đối số thứ nhất mới là `WildcardType`.

## 1. Class cũng là Type

Khi khai báo chỉ cần một kiểu lớp cụ thể, kết quả `Type` có thể chính là `Class<?> `.

Ví dụ:

- `String` → `String.class`.
- `String[]` → đối tượng `Class` của kiểu mảng `String[]`.
- `int` → `int.class`.

Không phải mọi kiểu mảng đều là `GenericArrayType`. Mảng `String[]` có kiểu thành phần cụ thể nên được mô tả bằng `Class`.

Một biến có kiểu tĩnh `Type` vẫn có thể chứa `String.class`. Tuy nhiên, muốn gọi các API riêng của `Class`, như `isAssignableFrom` hoặc `getDeclaredMethods`, cần kiểm tra dạng thực tế trước.

`Type` không cung cấp một phép `cast` đối tượng tương đương `Class.cast`. Nó chủ yếu mô tả cấu trúc kiểu; các phép thao tác theo lớp thuộc API `Class`.

## 2. ParameterizedType: kiểu được gắn đối số kiểu

Với `List<String>`:

- `getRawType()` trả kiểu khai báo gốc, ở đây tương ứng `List.class`.
- `getActualTypeArguments()` trả các đối số kiểu, ở đây có một phần tử tương ứng `String.class`.
- `getOwnerType()` cung cấp kiểu sở hữu nếu đây là một kiểu thành viên của kiểu khác; với kiểu ở mức cao nhất như `List`, kết quả là `null`.

Tên “actual type arguments” không có nghĩa mỗi phần tử luôn là một lớp cụ thể. Với `List<T>`, đối số là `TypeVariable`; với `List<? extends Number>`, đối số là `WildcardType`.

Với `Map<String, List<Integer>>`, cấu trúc cần được đọc nhiều cấp:

```text
ParameterizedType: Map
├── Class: String
└── ParameterizedType: List
    └── Class: Integer
```

Nếu viết bộ đọc dùng chung, không nên chỉ lấy đối số đầu rồi ép thẳng sang `Class`.

Đối với kiểu lồng nhau có generic, thông tin kiểu có thể còn nằm ở `getOwnerType()`. Một công cụ chỉ đọc `getActualTypeArguments()` mà bỏ kiểu sở hữu có thể làm mất ngữ cảnh. Xem [ParameterizedType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/ParameterizedType.html).

## 3. TypeVariable: ký hiệu kiểu chưa được thay thế theo ngữ cảnh

Giả sử:

```java
class Box<T extends Number> {
    T value;
}
```

Đây là khai báo minh họa.

`value` được khai báo bằng biến kiểu `T`. Đọc `getGenericType()` của field này trả một `TypeVariable`, không tự đổi thành `Number.class`.

Các thông tin chính:

- `getName()`: tên biến kiểu, ở đây là `T`.
- `getBounds()`: các giới hạn trên, ở đây có `Number`.
- `getGenericDeclaration()`: lớp, phương thức hoặc constructor đã khai báo biến kiểu.

`T extends Number` không có nghĩa `T` chính là `Number`. Giới hạn cho biết một ràng buộc, không xác định một lựa chọn cụ thể.

Nếu không viết giới hạn trên tường minh, giới hạn mặc định là `Object`. Nếu có nhiều giới hạn như `T extends Number & Comparable<T>`, mảng giới hạn cần được đọc đầy đủ.

Hai biến kiểu cùng được đặt tên `T` ở hai khai báo khác nhau không tự trở thành cùng một biến kiểu. Khi ánh xạ biến kiểu, phải dùng danh tính khai báo của chúng, không dùng riêng chuỗi `"T"` làm khóa toàn cục.

Xem [TypeVariable](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/TypeVariable.html).

## 4. WildcardType: mô tả khoảng ràng buộc của đối số kiểu

Trong `List<? extends Number>`, wildcard nói rằng kiểu phần tử có một giới hạn trên phù hợp với `Number`. Nó không hứa rằng mọi phần tử có lớp thực tế đúng bằng `Number`.

Các API chính:

- `getUpperBounds()`: giới hạn trên.
- `getLowerBounds()`: giới hạn dưới.

Ví dụ:

| Wildcard | Giới hạn trên | Giới hạn dưới |
| --- | --- | --- |
| `?` | `Object` | Mảng rỗng |
| `? extends Number` | `Number` | Mảng rỗng |
| `? super Integer` | `Object` | `Integer` |

Không nên thay mọi wildcard bằng giới hạn trên rồi coi như đã giữ nguyên ý nghĩa. `List<? super Integer>` không đồng nghĩa với `List<Object>`, dù giới hạn trên được phản chiếu là `Object`.

Các giới hạn là mô tả ràng buộc kiểu. API không tự sinh đối tượng thỏa mãn ràng buộc và không tự kiểm tra toàn bộ phần tử trong danh sách. Xem [WildcardType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/WildcardType.html).

## 5. GenericArrayType: giữ thông tin thành phần generic

`GenericArrayType` mô tả mảng có kiểu thành phần là biến kiểu hoặc kiểu được gắn tham số generic.

- `T[]`: thành phần là biến kiểu `T`.
- `List<String>[]`: thành phần là `ParameterizedType` mô tả `List<String>`.

Dùng `getGenericComponentType()` để đọc thành phần dưới dạng `Type`, rồi tiếp tục phân loại.

Việc reflection mô tả được một khai báo như `List<String>[]` không có nghĩa Java cho phép biểu thức tạo mảng trực tiếp `new List<String>[10]`. Khả năng khai báo một dạng kiểu và quy tắc tạo giá trị cho kiểu đó là hai vấn đề riêng.

Xem [GenericArrayType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/GenericArrayType.html).

## Chương trình đầy đủ: đối chiếu Type với kiểu sau xóa kiểu

Lưu thành `TypeModelDemo.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.GenericArrayType;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.lang.reflect.WildcardType;
import java.util.List;

public class TypeModelDemo {
    static class Box<T extends Number> {
        String name;
        List<String> labels;
        T value;
        List<? extends Number> numbers;
        T[] values;
        String[] names;

        List<T> items() {
            return List.of();
        }
    }

    static class IntegerBox extends Box<Integer> {
    }

    static String kind(Type type) {
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
        return "other";
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        String[] fieldNames = {
                "name", "labels", "value", "numbers", "values", "names"
        };
        for (String fieldName : fieldNames) {
            Field field = Box.class.getDeclaredField(fieldName);
            Type genericType = field.getGenericType();
            System.out.println(fieldName + ":kind=" + kind(genericType)
                    + ",type=" + genericType.getTypeName()
                    + ",raw=" + field.getType().getTypeName());
        }

        ParameterizedType listType = (ParameterizedType)
                Box.class.getDeclaredField("numbers").getGenericType();
        Type argument = listType.getActualTypeArguments()[0];
        WildcardType wildcard = (WildcardType) argument;
        System.out.println("argument.kind=" + kind(argument));
        System.out.println("wildcard.upper="
                + wildcard.getUpperBounds()[0].getTypeName());

        TypeVariable<?> variable = Box.class.getTypeParameters()[0];
        System.out.println("T.bound="
                + variable.getBounds()[0].getTypeName());
        System.out.println("return="
                + Box.class.getDeclaredMethod("items")
                        .getGenericReturnType().getTypeName());

        ParameterizedType parent = (ParameterizedType)
                IntegerBox.class.getGenericSuperclass();
        System.out.println("parent.argument="
                + parent.getActualTypeArguments()[0].getTypeName());
        System.out.println("inherited.field="
                + IntegerBox.class.getSuperclass().getDeclaredField("value")
                        .getGenericType().getTypeName());
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 TypeModelDemo.java
java TypeModelDemo
```

Kết quả:

```text
name:kind=Class,type=java.lang.String,raw=java.lang.String
labels:kind=ParameterizedType,type=java.util.List<java.lang.String>,raw=java.util.List
value:kind=TypeVariable,type=T,raw=java.lang.Number
numbers:kind=ParameterizedType,type=java.util.List<? extends java.lang.Number>,raw=java.util.List
values:kind=GenericArrayType,type=T[],raw=java.lang.Number[]
names:kind=Class,type=java.lang.String[],raw=java.lang.String[]
argument.kind=WildcardType
wildcard.upper=java.lang.Number
T.bound=java.lang.Number
return=java.util.List<T>
parent.argument=java.lang.Integer
inherited.field=T
```

### Vì sao chương trình phân loại trước?

Hàm `kind` dùng `instanceof` với các interface/lớp công khai của mô hình reflection. Nó không phụ thuộc vào tên lớp triển khai nội bộ của JDK.

Ví dụ, một đối tượng triển khai `ParameterizedType` có thể được JDK biểu diễn bằng một lớp nội bộ. Tên lớp nội bộ đó không phải giao diện mà ứng dụng nên dùng để phân nhánh.

Những phép ép kiểu bên dưới phần in danh sách field dựa trên các khai báo đã cố định trong chính chương trình: `numbers` là `List<? extends Number>`, nên nút ngoài là `ParameterizedType` và đối số là `WildcardType`. Với đầu vào tùy ý, cần kiểm tra dạng trước khi ép.

### Ý nghĩa của hai cột type và raw

Trong output:

- `type` đến từ `getGenericType()`.
- `raw` là nhãn do ví dụ chọn để in kết quả `getType()`.

`T` có giới hạn `Number`, nên kiểu sau xóa kiểu của field `value` là `Number`. Mô tả generic vẫn là biến `T`.

Tương tự, field `values` có mô tả `T[]`, còn kiểu sau xóa kiểu là `Number[]`.

Field `names` được khai báo là `String[]`, nên cả hai cách đọc cùng mô tả một kiểu mảng cụ thể và nút kết quả là `Class`.

Mã chỉ đọc khai báo; nó không đọc giá trị field, không tạo đối tượng `Box` và không cần mở quyền truy cập bằng `setAccessible`.

## Các cửa vào mô hình Type

Ngoài field, reflection cung cấp mô tả kiểu generic ở nhiều vị trí:

| Phần tử | API tiêu biểu | Nội dung |
| --- | --- | --- |
| Field | `Field.getGenericType()` | Kiểu khai báo của field |
| Kiểu trả về | `Method.getGenericReturnType()` | Kiểu trả về có thông tin generic |
| Tham số | `Executable.getGenericParameterTypes()` | Các kiểu tham số theo thứ tự |
| Ngoại lệ | `Executable.getGenericExceptionTypes()` | Các kiểu ngoại lệ khai báo |
| Lớp cha | `Class.getGenericSuperclass()` | Kiểu lớp cha cùng đối số generic nếu có |
| Interface | `Class.getGenericInterfaces()` | Các kiểu interface cùng đối số generic nếu có |
| Tham số kiểu được khai báo | `getTypeParameters()` trên khai báo phù hợp | Các `TypeVariable` do khai báo đó tạo ra |

`getTypeParameters()` không đồng nghĩa `getActualTypeArguments()`:

- Khai báo `Box<T>` tạo ra tham số kiểu `T`.
- Việc dùng `Box<Integer>` cung cấp đối số kiểu `Integer`.

Đây là hai phía của quan hệ generic, tương tự phân biệt tham số và đối số của một lời gọi hàm.

## Thông tin generic có thể được giữ lại dù Java dùng xóa kiểu

Xóa kiểu (type erasure) không có nghĩa mọi dấu vết generic trong class file đều biến mất.

Các khai báo generic có thể được lưu trong metadata chữ ký của tệp class. Reflection đọc phần mô tả đó thông qua các API generic, trong khi các API trả `Class` phản ánh kiểu sau xóa kiểu.

Nhưng reflection không khôi phục một cách tổng quát các đối số generic từ mọi đối tượng:

```java
// Mảnh minh họa:
Object value = new java.util.ArrayList<String>();
Class<?> runtimeClass = value.getClass();
```

`runtimeClass` cho biết lớp `ArrayList`; nó không tự trở thành một token riêng mô tả `ArrayList<String>` của biểu thức tạo đối tượng.

Cũng không có class literal hợp lệ `List<String>.class`. `Type` mô tả thông tin kiểu lấy từ khai báo hoặc ngữ cảnh được lưu, không tạo ra một lớp lúc chạy riêng cho mọi tổ hợp generic.

Nền tảng của xóa kiểu nằm tại [JLS §4.6](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.6).

## TypeVariable cần được phân giải theo ngữ cảnh

Trong ví dụ:

```java
static class IntegerBox extends Box<Integer> {
}
```

Mô tả lớp cha cho biết `Box` được dùng với đối số `Integer`. Vì vậy, output có `parent.argument=java.lang.Integer`.

Tuy nhiên, field `value` được khai báo tại `Box` bằng `T`. Khi lấy đúng field đó qua lớp cha, `field.getGenericType()` vẫn trả `T`, nên dòng cuối là `inherited.field=T`.

Muốn kết luận “kiểu field trong ngữ cảnh `IntegerBox` là `Integer`”, một công cụ cần kết hợp:

1. Khai báo biến kiểu `T` của `Box`.
2. Quan hệ `IntegerBox extends Box<Integer>`.
3. Phép thay thế `T → Integer`.
4. Việc áp dụng phép thay thế vào kiểu field.

Nếu có nhiều cấp kế thừa hoặc các kiểu generic lồng nhau, cần tiếp tục truyền ánh xạ qua các cấp. API trả `Type` cung cấp dữ liệu để làm việc đó, không tự thực hiện mọi phép phân giải theo ngữ cảnh.

Trong mã, dùng `IntegerBox.class.getSuperclass().getDeclaredField("value")` để lấy field của `Box`. Gọi trực tiếp `IntegerBox.class.getDeclaredField("value")` sẽ không đúng vì `getDeclaredField` chỉ tìm field khai báo tại chính lớp đó.

## Cấu trúc Type có thể lồng nhau và có vòng tham chiếu

Một bộ duyệt dùng chung phải biết đi vào các nút con:

- Đối số và kiểu sở hữu của `ParameterizedType`.
- Các giới hạn của `TypeVariable`.
- Giới hạn trên/dưới của `WildcardType`.
- Kiểu thành phần của `GenericArrayType`.
- Kiểu thành phần của `Class` nếu đó là mảng cụ thể.

Nhưng không nên triển khai đệ quy vô hạn. Ví dụ:

```java
// Khai báo minh họa:
class Item<T extends Comparable<T>> {
}
```

Đọc giới hạn của `T` dẫn đến `Comparable<T>`, rồi gặp lại `T`. Nếu cứ mở rộng tất cả giới hạn, bộ duyệt có thể lặp không dừng.

Công cụ thực tế cần ghi nhận các nút đã xét hoặc có quy tắc dừng phù hợp. Dùng quan hệ `equals` của các mô tả kiểu khi cần so sánh; không dựa vào việc mọi lần đọc đều trả đúng cùng một đối tượng theo `==`. Đặc biệt, API `TypeVariable` không yêu cầu người dùng dựa vào danh tính đối tượng triển khai.

Hàm `kind` trong ví dụ chỉ phân loại, không mở rộng đệ quy các giới hạn, nên không vướng vấn đề đó.

## getTypeName để hiển thị, API cấu trúc để xử lý

`Type.getTypeName()` hữu ích cho log, bảng kiểm tra và giải thích như output của bài. Nó trả chuỗi mô tả kiểu.

Không nên xây bộ phân tích generic bằng cách tách chuỗi theo dấu `<`, `>` hoặc dấu phẩy. Kiểu có thể lồng sâu, có wildcard, mảng và kiểu sở hữu.

Nếu cần xử lý chính xác, hãy dùng các interface cấu trúc. Ví dụ, lấy đối số của `List<Map<String, Integer>>` bằng `getActualTypeArguments()`, không tìm dấu phẩy đầu tiên trong chuỗi.

Cũng không dùng tên kiểu hiển thị như một định danh duy nhất trong môi trường nhiều bộ nạp lớp. Hai kiểu cùng tên có thể thuộc các ngữ cảnh nạp khác nhau.

## Type và AnnotatedType phục vụ các câu hỏi khác nhau

`Type` mô tả cấu trúc kiểu generic. Nếu khai báo có annotation trên vị trí sử dụng kiểu, chẳng hạn `List<@Marker String>`, việc đọc các annotation đó cần mô hình `AnnotatedType` và các API `getAnnotated...` phù hợp.

Không coi việc có `Type` là đã tự thu thập tất cả annotation trong cây khai báo. Ngược lại, annotation của chính field cũng không phải annotation của mọi nút kiểu nằm bên trong field đó.

Khi xây công cụ đọc mô hình, cần xác định đang muốn:

- Kiểu khai báo.
- Annotation của phần tử khai báo.
- Annotation tại các vị trí sử dụng kiểu.

Ba nguồn này liên quan nhau nhưng không thể thay thế nhau bằng một lệnh gọi duy nhất.

## Lỗi thường gặp và giới hạn

| Hiểu nhầm | Cách đọc đúng |
| --- | --- |
| Mọi `Type` đều ép được sang `Class` | Phân loại dạng trước khi dùng API riêng |
| `getGenericType` luôn trả `ParameterizedType` | Kiểu không generic có thể trả `Class`; biến kiểu trả `TypeVariable` |
| `T extends Number` nghĩa là `T = Number` | Giới hạn chỉ là ràng buộc |
| Đối số của `ParameterizedType` luôn là lớp cụ thể | Đối số có thể là biến kiểu, wildcard hoặc kiểu lồng |
| Mọi mảng đều là `GenericArrayType` | `String[]` được mô tả bằng `Class` |
| `getClass()` trả đối số generic của đối tượng | Nó trả lớp lúc chạy, không tự giữ mọi cách gắn generic |
| Lấy field qua lớp con là tự thay `T` | Cần phân giải biến kiểu theo ngữ cảnh |
| Đọc chữ ký là đã kiểm chứng nội dung đối tượng | Cần kiểm tra dữ liệu thực tế nếu đó là yêu cầu |

Metadata chữ ký cũng có thể không hợp lệ hoặc tham chiếu kiểu không còn tồn tại trong đầu ra trộn phiên bản. Các API generic có thể phát sinh những lỗi như `GenericSignatureFormatError`, `TypeNotPresentException` hoặc `MalformedParameterizedTypeException`, tùy thao tác. Đừng bắt tất cả rồi tự coi kiểu là `Object` nếu việc đó làm mất một ràng buộc bắt buộc của công cụ.

## Thực hành kiểm chứng

1. Chạy chương trình, phân biệt sáu field theo dạng `Type` và kiểu sau xóa kiểu.
2. Đổi `List<String> labels` thành `List<Integer> labels`. Cấu trúc đối số thay đổi nhưng `getType()` vẫn là `List`.
3. Đổi giới hạn thành `T extends CharSequence`, đồng thời thay lớp con bằng kiểu phù hợp như `Box<String>`. Kiểm tra thay đổi ở `raw` của `value` và `values`.
4. Đổi wildcard sang `? super Integer`, rồi đọc cả mảng giới hạn trên và dưới bằng API tương ứng.
5. Thêm field `List<List<String>>`; mô tả cây kiểu mà không ép mọi nút về `Class`.
6. Giải thích vì sao `parent.argument=Integer` và `inherited.field=T` có thể cùng đúng trong một chương trình.

Điều cần nắm là vai trò của `Type` như **ngôn ngữ mô tả cấu trúc kiểu trong reflection**. Nó cung cấp dữ liệu cho việc phân tích chữ ký, ánh xạ kiểu và công cụ generic; nó không tự kiểm chứng nội dung đối tượng hoặc giải quyết mọi biến kiểu theo ngữ cảnh.
