# WildcardType và giới hạn trên, giới hạn dưới

## Khái niệm và vị trí trong mô hình reflection

Trong mã generic, wildcard `?` biểu diễn một đối số kiểu chưa được chỉ rõ cụ thể. Có thể bổ sung giới hạn để ràng buộc kiểu đó:

- `?`: một kiểu chưa biết.
- `? extends Number`: một kiểu chưa biết, có giới hạn trên là `Number`.
- `? super Integer`: một kiểu chưa biết, có giới hạn dưới là `Integer`.

Khi đọc chữ ký generic bằng reflection, Java dùng interface `java.lang.reflect.WildcardType` để mô tả những biểu thức wildcard này.

`WildcardType` mở rộng `Type`. Nó không phải một lớp đối tượng nghiệp vụ và không chỉ ra trực tiếp lớp của từng phần tử đang có trong một collection. Nó mô tả **ràng buộc trong khai báo kiểu**.

API vẫn áp dụng trong Java hiện đại. Các ví dụ của bài chạy trên JDK 17 trở lên.

## Vì sao cần đọc giới hạn thay vì chỉ thấy dấu hỏi?

Ba khai báo sau đều chứa wildcard nhưng cung cấp các cam kết khác nhau:

```java
List<?> any;
List<? extends Number> producers;
List<? super Integer> consumers;
```

Đây là các khai báo field minh họa, chưa phải chương trình độc lập.

Nếu một công cụ phân tích chỉ thấy dấu `?` rồi gộp cả ba thành “không biết kiểu”, nó làm mất các ràng buộc quan trọng:

- `producers` cho phép xem phần tử đọc ra như `Number`.
- `consumers` cho phép truyền `Integer` vào thao tác thêm được phép.
- `any` không có cam kết kiểu cụ thể hơn `Object` để đọc.

Dù vậy, phản chiếu được các giới hạn không đồng nghĩa công cụ đã có quyền sửa collection hoặc đã kiểm tra toàn bộ dữ liệu trong nó. Cần giữ riêng câu hỏi về **chữ ký khai báo**, **khả năng thao tác của kiểu** và **hành vi thực tế của collection**.

Quy tắc wildcard của ngôn ngữ được mô tả tại [JLS §4.5.1](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.5.1).

## Hai API cốt lõi của WildcardType

```java
Type[] getUpperBounds();
Type[] getLowerBounds();
```

Cả hai trả mảng `Type`, không phải `Class<?>[]`.

- **Giới hạn trên** mô tả kiểu ở phía trên trong quan hệ kiểu của wildcard.
- **Giới hạn dưới** mô tả kiểu ở phía dưới trong quan hệ đó.

Bảng quan trọng:

| Biểu thức wildcard | getUpperBounds() | getLowerBounds() |
| --- | --- | --- |
| `?` | `[Object]` | `[]` |
| `? extends Number` | `[Number]` | `[]` |
| `? super Integer` | `[Object]` | `[Integer]` |

Các tên trong bảng được viết ngắn để dễ đọc; khi in bằng `getTypeName()`, các kiểu thường xuất hiện với tên đầy đủ như `java.lang.Object`.

### Giới hạn trên ngầm định là Object

Với `?` hoặc `? super Integer`, không có giới hạn trên tường minh trong cú pháp. Reflection trả `Object` làm giới hạn trên.

Điều này không biến `List<? super Integer>` thành `List<Object>`. Nó chỉ mô tả giới hạn trên của wildcard, trong khi giới hạn dưới `Integer` vẫn là một phần của thông tin cần giữ.

### Không có giới hạn dưới được biểu diễn bằng mảng rỗng

Với `?` và `? extends Number`, `getLowerBounds()` trả mảng độ dài 0.

API giải thích rằng khi không có giới hạn dưới tường minh, giới hạn dưới về mặt mô hình là kiểu của `null`, và trường hợp đó được biểu diễn bằng mảng rỗng. Không có một `Null.class` để đặt vào mảng.

Không truy cập `getLowerBounds()[0]` khi chưa kiểm tra độ dài.

Xem hợp đồng đầy đủ tại [WildcardType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/WildcardType.html).

## Tìm WildcardType trong cây generic

Với field:

```java
List<? extends Number> producers;
```

Kết quả của `field.getGenericType()` là một `ParameterizedType` mô tả toàn bộ `List<? extends Number>`.

Wildcard nằm trong đối số kiểu:

```text
ParameterizedType: List
└── WildcardType: ? extends Number
    └── upper bound: Class Number
```

Các bước đọc:

1. Lấy `Type` của field.
2. Xác nhận nút ngoài là `ParameterizedType`.
3. Lấy mảng `getActualTypeArguments()`.
4. Xác nhận đối số cần xét là `WildcardType`.
5. Đọc giới hạn trên và dưới.

Không ép trực tiếp toàn bộ kiểu field sang `WildcardType`. Cũng không ép mọi đối số của `ParameterizedType` sang wildcard: `List<Number>` có đối số là `Class` của `Number`, không phải wildcard.

Nếu dùng `field.getType()`, bạn chỉ nhận được `List.class`, không có cấu trúc wildcard bên trong. API về kiểu khai báo nằm tại [Field.getGenericType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html#getGenericType()).

## Ví dụ chạy đầy đủ

Chương trình đọc năm field theo tên cố định để thứ tự output rõ ràng. Nó không dựa vào thứ tự mà `getDeclaredFields()` trả về.

Lưu thành `WildcardBoundsDemo.java`:

```java
import java.lang.reflect.Field;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.WildcardType;
import java.util.ArrayList;
import java.util.List;
import java.util.StringJoiner;

public class WildcardBoundsDemo {
    static class Model {
        List<?> any;
        List<? extends Number> producers;
        List<? super Integer> consumers;
        List<? extends List<String>> nested;
        List<Number> concrete;
    }

    static String names(Type[] bounds) {
        StringJoiner result = new StringJoiner(", ", "[", "]");
        for (Type bound : bounds) {
            result.add(bound.getTypeName());
        }
        return result.toString();
    }

    static void inspect(String fieldName)
            throws NoSuchFieldException {
        Field field = Model.class.getDeclaredField(fieldName);
        Type type = field.getGenericType();
        if (!(type instanceof ParameterizedType parameterized)) {
            throw new IllegalArgumentException("Expected parameterized field");
        }

        Type argument = parameterized.getActualTypeArguments()[0];
        System.out.println("field=" + fieldName);
        System.out.println("argument=" + argument.getTypeName());
        if (argument instanceof WildcardType wildcard) {
            System.out.println("upper=" + names(wildcard.getUpperBounds()));
            System.out.println("lower=" + names(wildcard.getLowerBounds()));
        } else {
            System.out.println("wildcard=false");
        }
    }

    public static void main(String[] args)
            throws NoSuchFieldException {
        inspect("any");
        inspect("producers");
        inspect("consumers");
        inspect("nested");
        inspect("concrete");

        List<? extends Number> source = List.of(1, 2);
        Number first = source.get(0);
        List<? super Integer> destination = new ArrayList<Number>();
        destination.add(Integer.valueOf(7));
        Object item = destination.get(0);
        System.out.println("read.extends=" + first.intValue());
        System.out.println("read.super=" + item);
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 WildcardBoundsDemo.java
java WildcardBoundsDemo
```

Kết quả:

```text
field=any
argument=?
upper=[java.lang.Object]
lower=[]
field=producers
argument=? extends java.lang.Number
upper=[java.lang.Number]
lower=[]
field=consumers
argument=? super java.lang.Integer
upper=[java.lang.Object]
lower=[java.lang.Integer]
field=nested
argument=? extends java.util.List<java.lang.String>
upper=[java.util.List<java.lang.String>]
lower=[]
field=concrete
argument=java.lang.Number
wildcard=false
read.extends=1
read.super=7
```

## Giải thích cơ chế đọc trong chương trình

### Kiểm tra ParameterizedType trước

`inspect` lấy `Field`, rồi dùng `getGenericType()`. Nếu nút ngoài không phải `ParameterizedType`, hàm báo lỗi theo hợp đồng của chính ví dụ.

Năm field đều khai báo dạng `List<...>`, nên mỗi field có một đối số kiểu. Vì thế chương trình dùng phần tử `[0]`.

Một công cụ dùng chung cho `Map<K, V>`, kiểu lồng nhau và các khai báo khác phải xét đủ đối số theo cấu trúc cần xử lý. Không nên sao chép giả định “mọi kiểu chỉ có một đối số” từ ví dụ này sang đầu vào tùy ý.

### Phân biệt wildcard và đối số kiểu cụ thể

`argument instanceof WildcardType wildcard` xác định có cần đọc giới hạn hay không.

Với `concrete`, đối số là `Number`, nên in `wildcard=false`. Đây là một trường hợp hợp lệ, không phải lỗi thiếu thông tin.

`List<Number>` và `List<? extends Number>` có quan hệ và khả năng thao tác khác nhau. Mô hình reflection giữ lại sự khác biệt ấy.

### Duyệt mảng giới hạn

Hàm `names` duyệt toàn bộ mảng `Type[]` và không truy cập phần tử đầu tiên một cách vô điều kiện.

Cách này đọc đúng cả mảng rỗng của giới hạn dưới. API trả mảng và khuyến nghị mã sử dụng có khả năng làm việc với nhiều giới hạn, dù cú pháp wildcard hiện tại không cung cấp danh sách nhiều giới hạn như một khai báo biến kiểu có thể có.

Chuỗi do `getTypeName()` trả được dùng để hiển thị. Chương trình không phân tích chuỗi để suy ra cấu trúc.

## Giới hạn có thể là kiểu generic, không chỉ là Class

Field `nested` có khai báo:

```java
List<? extends List<String>> nested;
```

Cây kiểu:

```text
ParameterizedType: List
└── WildcardType
    └── upper bound: ParameterizedType List<String>
        └── Class String
```

Vì vậy, phần tử đầu của `getUpperBounds()` trong trường hợp này là `ParameterizedType`, không phải `Class`.

Nếu muốn lấy `String` bên trong, cần tiếp tục phân loại giới hạn, chuyển về `ParameterizedType` sau khi kiểm tra rồi đọc đối số kiểu của nó.

Một giới hạn cũng có thể tham chiếu biến kiểu. Ví dụ trong một lớp `Box<T extends Number>`, khai báo `List<? extends T>` sẽ có giới hạn trên là mô tả biến kiểu `T`, không tự đổi thành `Number`.

Định nghĩa về đối số và kiểu sở hữu nằm tại [ParameterizedType](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/ParameterizedType.html).

## Ý nghĩa đọc và ghi: liên hệ với extends và super

Reflection mô tả đúng cú pháp ràng buộc; để sử dụng các ràng buộc đó, cần giữ đúng ngữ nghĩa generic.

### ? extends Number: đọc theo Number

Một `List<? extends Number>` có thể trỏ tới danh sách với một kiểu phần tử cụ thể chưa biết, chẳng hạn `Integer` hoặc `Double`.

Khi đọc phần tử, có thể nhận bằng biến `Number`. Nhưng không thể thêm tùy ý một `Integer` hoặc `Double`, vì chưa biết kiểu phần tử thực sự mà danh sách cam kết nhận.

Ví dụ minh họa trong một phương thức:

```java
List<? extends Number> source = List.of(1, 2);
Number first = source.get(0);
// source.add(Integer.valueOf(3)); // Cố ý không hợp lệ về kiểu.
```

Không nên diễn đạt tuyệt đối là “không thể làm bất kỳ thay đổi nào” đối với danh sách có `extends`. Một số thao tác như xóa phần tử không cần thêm một giá trị mới theo kiểu phần tử. Khả năng thực hiện còn phụ thuộc hợp đồng của collection, chẳng hạn có hỗ trợ thay đổi hay không.

Về mặt kiểu, `null` có thể được truyền cho tham số kiểu tham chiếu trong những tình huống tương ứng, nhưng collection cụ thể vẫn có thể từ chối null hoặc từ chối mọi thay đổi. Không dùng điều đó để kết luận danh sách từ `List.of` là có thể sửa.

### ? super Integer: thêm Integer, đọc theo Object

Một `List<? super Integer>` có thể tham chiếu đến `List<Integer>`, `List<Number>` hoặc `List<Object>`.

Có thể thêm `Integer` vì giá trị đó phù hợp với mọi lựa chọn kể trên. Khi đọc, cam kết chung chỉ đủ để nhận `Object`.

Ví dụ:

```java
List<? super Integer> destination = new ArrayList<Number>();
destination.add(Integer.valueOf(7));
Object item = destination.get(0);
```

Không mặc nhiên gán kết quả `destination.get(0)` cho `Integer`: danh sách có thể là `List<Object>` với những phần tử khác đã tồn tại.

`getLowerBounds()` trả `Integer` không có nghĩa “mọi phần tử đang nằm trong collection đều là Integer hoặc kiểu con”. Nó mô tả giới hạn dưới của đối số kiểu, không phải một cuộc kiểm tra dữ liệu.

### ? không đồng nghĩa với Object

`List<?>` là một danh sách có kiểu phần tử chưa biết. `List<Object>` là danh sách được khai báo có thể chứa các giá trị tham chiếu dưới hợp đồng phần tử `Object`.

Bạn có thể gán `List<String>` cho biến `List<?>`, nhưng không thể gán nó trực tiếp cho `List<Object>`.

Dù wildcard `?` có giới hạn trên `Object`, không được thay toàn bộ kiểu `List<?>` bằng `List<Object>` rồi cho phép thêm bất kỳ đối tượng nào.

## WildcardType khác TypeVariable

| Đặc điểm | WildcardType | TypeVariable |
| --- | --- | --- |
| Biểu thức thường gặp | `?`, `? extends X`, `? super Y` | `T`, `E`, `K` |
| Có tên do người viết đặt | Không có một tên biến kiểu như T | Có |
| Có khai báo tạo biến kiểu riêng | Không theo cách TypeVariable có | Có thể truy về qua `getGenericDeclaration()` |
| API đọc giới hạn | Giới hạn trên và dưới | `getBounds()` cho giới hạn trên |
| Vai trò | Biểu thị đối số kiểu chưa biết ở một vị trí sử dụng | Định nghĩa một biến kiểu có thể được dùng lại trong khai báo |

Không biến `?` thành một biến tên `"?"` để áp dụng cơ chế ánh xạ giống `T`.

Một phương thức generic dùng cùng `T` ở nhiều vị trí có thể biểu diễn quan hệ giữa các vị trí đó. Các wildcard riêng biệt không tự khẳng định cùng một kiểu chưa biết.

Cơ chế capture conversion của trình biên dịch giúp kiểm tra các thao tác trên wildcard; `WildcardType` mô tả wildcard trong chữ ký, không phải một API để lấy “lớp cụ thể của kiểu capture” từ một collection đang chạy.

## Reflection đọc chữ ký, không xác thực toàn bộ dữ liệu

Nếu đọc `List<? extends Number>` từ một field, bạn biết field được khai báo với ràng buộc đó. Bạn chưa biết:

- Field hiện có giá trị hay là `null`.
- Danh sách có bao nhiêu phần tử.
- Mỗi phần tử có lớp thực tế nào.
- Danh sách có hỗ trợ thêm/xóa hay không.
- Có dữ liệu không an toàn đã được đưa vào qua mã dùng raw type hoặc unchecked operation hay không.

Không nên suy luận toàn bộ nội dung danh sách từ một mảng giới hạn trả về bởi reflection.

`value.getClass()` cũng không tự khôi phục wildcard của nơi biến `value` từng được khai báo. Thông tin khai báo cần được đọc từ `Field`, phương thức hoặc chữ ký phù hợp.

Nếu mục tiêu là kiểm tra dữ liệu đầu vào, cần có bước xác minh giá trị thực tế theo hợp đồng, bên cạnh bước đọc chữ ký.

## Nguyên tắc khi viết bộ phân tích WildcardType

1. Bắt đầu từ đúng phần tử khai báo có metadata generic.
2. Kiểm tra nút ngoài trước khi ép kiểu.
3. Duyệt đúng vị trí đối số; không giả định mọi kiểu đều là `List`.
4. Giữ cả giới hạn trên lẫn giới hạn dưới.
5. Phân loại từng giới hạn như một `Type` khác.
6. Chỉ dùng `getTypeName()` cho hiển thị, không dùng làm bộ phân tích cú pháp.
7. Không thay một wildcard bằng giới hạn của nó rồi coi hai kiểu là tương đương.

Nếu công cụ chủ động “rút gọn” một kiểu về một lớp để phục vụ mục tiêu riêng, cần ghi rõ đây là chính sách xấp xỉ và thông tin nào đã bị bỏ. Chẳng hạn, lấy `Object` từ giới hạn trên của `? super Integer` rồi bỏ giới hạn dưới sẽ làm mất thông tin quan trọng về đầu vào được nhận.

Đọc các giới hạn cũng có thể gặp `TypeNotPresentException` hoặc `MalformedParameterizedTypeException` nếu chữ ký tham chiếu kiểu không còn tồn tại hoặc không hợp lệ. Không tự thay dữ liệu lỗi bằng `Object` nếu cách làm đó che mất một ràng buộc mà công cụ phải tuân thủ.

## Lỗi phổ biến

| Hiện tượng hoặc hiểu nhầm | Cách kiểm tra |
| --- | --- |
| Ép kiểu field trực tiếp sang WildcardType | Đọc ParameterizedType rồi lấy đúng đối số kiểu |
| Ép giới hạn sang Class bị lỗi | Giới hạn có thể là ParameterizedType hoặc TypeVariable |
| Truy cập lowerBounds[0] gây lỗi | Mảng giới hạn dưới có thể rỗng |
| Coi upper Object là List<Object> | Giữ toàn bộ wildcard, kể cả giới hạn dưới |
| Coi super Integer là danh sách chỉ có Integer | Phân biệt ràng buộc kiểu với nội dung thực tế |
| Mọi đối số generic bị coi là wildcard | List<Number> dùng đối số kiểu cụ thể |
| Dùng getType rồi không thấy wildcard | Dùng API đọc kiểu generic của khai báo |
| Dựa vào chuỗi tên lớp triển khai nội bộ | Dùng các interface reflection công khai |

## Thực hành kiểm chứng

1. Chạy ví dụ và giải thích từng cặp `upper`/`lower`.
2. Thêm field `List<? extends CharSequence>`; đọc giới hạn và so sánh với `List<?>`.
3. Đổi `consumers` thành `List<? super Number>`; xác nhận giới hạn dưới đổi thành `Number`, giới hạn trên vẫn là `Object`.
4. Với field `nested`, dùng `instanceof ParameterizedType` trên giới hạn trên để lấy đối số `String` ở tầng trong.
5. Thêm một field `List<Number>` và một field `List<? extends Number>`, rồi giải thích vì sao chúng không tương đương dù cùng liên quan `Number`.
6. Trên một collection có thể sửa, thử các thao tác hợp lệ và các dòng cố ý không hợp lệ về kiểu trong những tệp thử riêng; tách lỗi biên dịch generic khỏi lỗi do collection không hỗ trợ thao tác.

Điều cần nắm là **wildcard mô tả một khoảng ràng buộc của đối số kiểu**. `WildcardType` giúp đọc khoảng đó theo cấu trúc; nó không tự chọn một lớp phần tử cụ thể hoặc biến chữ ký generic thành bằng chứng về toàn bộ dữ liệu lúc chạy.
