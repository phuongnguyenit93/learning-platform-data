# RecordComponent: tên, kiểu, generic type và accessor

## 1. RecordComponent mô tả điều gì?

Phần đầu một khai báo record liệt kê các **thành phần (record component)**:

~~~java
record Position(int x, int y) {
}
~~~

Ở đây có hai thành phần tên `x` và `y`, cùng kiểu `int`. Java tạo các trường lưu trữ và các phương thức truy cập tương ứng, nhưng bản thân **thành phần record**, **trường** và **phương thức** là những khái niệm khác nhau.

`java.lang.reflect.RecordComponent` cung cấp metadata của một thành phần được khai báo trong phần đầu record. Từ metadata đó, ta có thể biết:

- Tên thành phần.
- Kiểu biểu diễn bằng `Class<?>`.
- Cấu trúc kiểu generic biểu diễn bằng `Type`.
- Phương thức truy cập, gọi là **accessor**, của thành phần.
- Lớp record khai báo thành phần đó.

Điều này hữu ích cho công cụ sinh tài liệu, khảo sát mô hình dữ liệu hoặc đọc các thành phần theo thứ tự khai báo. Thay vì đoán từ mọi trường và phương thức của một lớp, công cụ có thể bắt đầu từ danh sách thành phần record.

API `RecordComponent` có từ Java 16. Các chương trình trong bài dùng Java 17 trở lên và không cần tính năng preview.

## 2. Đi từ Class đến danh sách thành phần

Điểm vào là `Class.getRecordComponents()`:

~~~java
RecordComponent[] components = Position.class.getRecordComponents();
~~~

Đoạn trên là minh họa; cần import `java.lang.reflect.RecordComponent` và khai báo `Position` khi đặt trong chương trình.

Có ba trường hợp phải phân biệt:

| Token lớp | `isRecord()` | `getRecordComponents()` |
| --- | --- | --- |
| Lớp record có thành phần | `true` | Mảng khác `null`, chứa các thành phần |
| Lớp record không có thành phần, như `record Empty() {}` | `true` | Mảng rỗng |
| Lớp không phải record | `false` | `null` |

Các thành phần được trả về **theo đúng thứ tự khai báo trong phần đầu record**. Đây là hợp đồng của [Class.getRecordComponents](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getRecordComponents()).

Ví dụ `record Position(int x, int y)` có thứ tự `x`, rồi `y`. Không nên suy ra thứ tự này bằng cách duyệt `getDeclaredFields()` hoặc `getDeclaredMethods()`, vì các API đó không bảo đảm thứ tự khai báo.

Các trường `static` bổ sung hoặc phương thức tiện ích trong thân record cũng không tự trở thành thành phần record.

## 3. Bốn nhóm thông tin chính

| API trên `RecordComponent` | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `getName()` | `String` | Tên thành phần được khai báo |
| `getType()` | `Class<?>` | Token kiểu; với generic, đây là kiểu sau xóa kiểu |
| `getGenericType()` | `Type` | Kiểu khai báo, có thể giữ cấu trúc tham số hóa hoặc biến kiểu |
| `getAccessor()` | `Method` | Phương thức truy cập tương ứng |
| `getDeclaringRecord()` | `Class<?>` | Record khai báo thành phần |

Tài liệu [RecordComponent](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/RecordComponent.html) mô tả các API này.

`RecordComponent` không phải là `Field`. Không có thao tác `component.get(record)` hoặc `component.set(record, value)` tương tự thao tác đọc/ghi trường. Muốn đọc giá trị thông qua accessor, lấy `Method` rồi gọi nó trên một đối tượng record.

## 4. Chương trình đầy đủ: tên, kiểu, generic và giá trị

Ví dụ sau có bốn dạng thành phần:

- `String code`: kiểu lớp thông thường.
- `int priority`: kiểu nguyên thủy.
- `T weight`, với `T extends Number`: biến kiểu có cận.
- `List<String> tags`: kiểu tham số hóa.

Lưu vào `RecordComponentDemo.java`:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.RecordComponent;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.util.Arrays;
import java.util.List;

public class RecordComponentDemo {
    public record Parcel<T extends Number>(
            String code, int priority, T weight, List<String> tags) {
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
        return "Other";
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        Parcel<Integer> parcel =
                new Parcel<>("P-7", 2, 3, List.of("fragile"));

        RecordComponent[] components = Parcel.class.getRecordComponents();

        System.out.println("components: "
                + Arrays.stream(components)
                        .map(RecordComponent::getName)
                        .toList());

        for (RecordComponent component : components) {
            Method accessor = component.getAccessor();
            System.out.println(component.getName()
                    + " | type=" + component.getType().getTypeName()
                    + " | generic=" + component.getGenericType().getTypeName()
                    + " | kind=" + kind(component.getGenericType()));
            System.out.println("accessor=" + accessor.getName()
                    + "; parameters=" + accessor.getParameterCount()
                    + "; genericReturn="
                    + accessor.getGenericReturnType().getTypeName());
            System.out.println("value=" + accessor.invoke(parcel));
        }

        Object priority = components[1].getAccessor().invoke(parcel);
        System.out.println("boxed priority: "
                + priority.getClass().getSimpleName());

        TypeVariable<?> weightType =
                (TypeVariable<?>) components[2].getGenericType();
        System.out.println("weight bounds: "
                + Arrays.stream(weightType.getBounds())
                        .map(Type::getTypeName)
                        .toList());

        ParameterizedType tagsType =
                (ParameterizedType) components[3].getGenericType();
        System.out.println("tags arguments: "
                + Arrays.stream(tagsType.getActualTypeArguments())
                        .map(Type::getTypeName)
                        .toList());

        System.out.println("declaring record: "
                + (components[0].getDeclaringRecord() == Parcel.class));

        Parcel<Double> other =
                new Parcel<>("P-8", 1, 2.5, List.of("local"));
        System.out.println("same runtime class: "
                + parcel.getClass().equals(other.getClass()));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 RecordComponentDemo.java
java RecordComponentDemo
~~~

Kết quả chính xác:

~~~text
components: [code, priority, weight, tags]
code | type=java.lang.String | generic=java.lang.String | kind=Class
accessor=code; parameters=0; genericReturn=java.lang.String
value=P-7
priority | type=int | generic=int | kind=Class
accessor=priority; parameters=0; genericReturn=int
value=2
weight | type=java.lang.Number | generic=T | kind=TypeVariable
accessor=weight; parameters=0; genericReturn=T
value=3
tags | type=java.util.List | generic=java.util.List<java.lang.String> | kind=ParameterizedType
accessor=tags; parameters=0; genericReturn=java.util.List<java.lang.String>
value=[fragile]
boxed priority: Integer
weight bounds: [java.lang.Number]
tags arguments: [java.lang.String]
declaring record: true
same runtime class: true
~~~

Chương trình kiểm tra loại `Type` qua các interface công khai như `ParameterizedType` và `TypeVariable`. Nó không in tên lớp triển khai nội bộ của JDK để suy luận loại generic.

### 4.1. Tên thành phần là tên trong khai báo

`getName()` cho `code`, `priority`, `weight` và `tags`, đúng theo phần đầu của `Parcel`.

Tên này không phải:

- Giá trị chuỗi đang lưu trong thành phần, như `P-7`.
- Tên của lớp triển khai một giá trị.
- Tên getter theo quy ước JavaBeans.

Accessor record dùng tên thành phần: `code()`, `priority()`, `weight()`, `tags()`. Không mặc định chúng có dạng `getCode()` hoặc `getWeight()`.

Không cần tùy chọn `javac -parameters` để `RecordComponent.getName()` biết tên thành phần. Đây là metadata thành phần record, không phải việc đoán tên tham số của một phương thức tùy ý.

### 4.2. getType cho token Class

Với `code`, token là `String.class`. Với `priority`, token là `int.class`.

Với thành phần `weight` được khai báo là `T`, mà `T extends Number`, kiểu sau xóa kiểu là `Number`; vì vậy `getType()` cho `Number.class`.

Với `tags`, token là `List.class`. Không có một class literal `List<String>.class` để trả về.

Điểm này giúp chọn công cụ đúng: dùng `getType()` khi cần token lớp để đối chiếu hoặc tìm chữ ký Reflection; dùng `getGenericType()` khi cần hiểu cấu trúc kiểu khai báo đầy đủ hơn.

### 4.3. getGenericType giữ thông tin của khai báo

Các kết quả trong chương trình:

| Thành phần | `getType()` | `getGenericType()` |
| --- | --- | --- |
| `code` | `String.class` | Một `Class` biểu diễn `String` |
| `priority` | `int.class` | Một `Class` biểu diễn `int` |
| `weight` | `Number.class` | `TypeVariable` tên `T` |
| `tags` | `List.class` | `ParameterizedType` biểu diễn `List<String>` |

Vì `Class` cũng triển khai `Type`, kết quả `getGenericType()` không phải lúc nào cũng là `ParameterizedType`. Ép mọi kết quả sang `ParameterizedType` sẽ làm chương trình lỗi với các thành phần như `code` và `priority`.

Trong thí nghiệm, biến kiểu `T` có cận `Number`, đọc được bằng `TypeVariable.getBounds()`. Kiểu tham số hóa của `tags` có đối số `String`, đọc được bằng `ParameterizedType.getActualTypeArguments()`.

### 4.4. Metadata T không tự đổi thành Integer theo đối tượng

Đối tượng `parcel` được tạo qua khai báo `Parcel<Integer>`, nhưng metadata của thành phần `weight` vẫn là `T`, không tự trở thành `Integer`.

Cuối chương trình, đối tượng `Parcel<Double>` và đối tượng `Parcel<Integer>` có cùng lớp thực tế. `RecordComponent` được lấy từ lớp khai báo `Parcel`, nên không lưu riêng đối số generic của từng biến bên ngoài.

Nếu công cụ có ngữ cảnh bổ sung, chẳng hạn một trường được khai báo là `Parcel<Integer>`, nó có thể phân tích `Type` của ngữ cảnh đó và xây dựng ánh xạ `T -> Integer`. Đó là bước phân giải generic riêng; `component.getGenericType()` tự nó không làm bước này chỉ từ một instance.

Cũng không suy luận rằng nhìn thấy giá trị `3` chứng minh mọi giá trị của `T` là `Integer`. Giá trị đang đọc và kiểu khai báo là hai loại thông tin khác nhau.

## 5. Type có cấu trúc, không chỉ là một chuỗi để in

`getTypeName()` hữu ích khi trình bày kết quả cho người đọc. Nếu công cụ cần xử lý kiểu, hãy dùng các interface của `Type` để đi theo cấu trúc.

Một số trường hợp có thể gặp:

| Kiểu thành phần trong khai báo | Kiểu sau xóa kiểu, với `T extends Number` nếu có | Dạng `Type` thường cần xử lý |
| --- | --- | --- |
| `String` | `String` | `Class` |
| `int` | `int` | `Class` của kiểu nguyên thủy |
| `String[]` | `String[]` | `Class` của mảng |
| `List<String>` | `List` | `ParameterizedType` |
| `T` | `Number` | `TypeVariable` |
| `T[]` | `Number[]` | `GenericArrayType` |

Với một thành phần như `List<? extends Number>`, đối tượng ở cấp ngoài cùng là `ParameterizedType`; đối số kiểu bên trong là một `WildcardType`. Nếu công cụ khảo sát generic đầy đủ, cần xử lý lồng nhau thay vì chỉ kiểm tra một cấp.

Không nên phân tích chuỗi `getTypeName()` bằng cách tách dấu phẩy và dấu ngoặc nhọn để thay cho các API cấu trúc. Kiểu generic có thể lồng nhiều cấp, có wildcard, biến kiểu và mảng generic.

`getGenericSignature()` cung cấp biểu diễn chữ ký generic ở dạng chuỗi metadata. Nếu mục đích là hiểu kiểu khai báo, `getGenericType()` thường là điểm bắt đầu rõ ràng hơn.

Generic metadata cũng không thay thế việc kiểm tra dữ liệu. Việc đọc được khai báo `List<String>` không tự duyệt và xác minh mọi phần tử trong một danh sách đang chạy.

## 6. Accessor nối metadata với một đối tượng cụ thể

`getAccessor()` trả về `java.lang.reflect.Method`. Với record Java hợp lệ, đó là phương thức truy cập tương ứng, có tên thành phần, không nhận tham số và trả về kiểu của thành phần.

Ví dụ trong chương trình:

~~~java
Method accessor = component.getAccessor();
Object value = accessor.invoke(parcel);
~~~

Đoạn này phân tách hai việc:

1. `getAccessor()` lấy metadata phương thức.
2. `invoke(parcel)` thực thi phương thức trên đối tượng `parcel`.

`RecordComponent` tự nó không chứa giá trị của một instance. Hai đối tượng cùng lớp record dùng chung mô tả thành phần nhưng có thể có các giá trị khác nhau.

### Kiểu nguyên thủy được đóng hộp khi đi qua Object

Trong ví dụ, `priority()` trả về `int`. Tuy nhiên `Method.invoke(...)` trả về `Object`, nên kết quả số nguyên được đóng hộp thành `Integer`.

Vì vậy:

- `component.getType()` của `priority` vẫn là `int.class`.
- Đối tượng nhận được từ `invoke(...)` có lớp `Integer`.
- Đây không phải việc metadata của thành phần bị đổi từ `int` sang `Integer`.

Nếu thành phần có kiểu tham chiếu và accessor trả về `null`, kết quả Reflection cũng có thể là `null`. Không gọi `getClass()` trên giá trị vừa đọc khi chưa xét trường hợp đó.

### Điều kiện và lỗi khi gọi accessor

| Tình huống | Kết quả cần chú ý |
| --- | --- |
| Truyền một instance không phù hợp với lớp khai báo phương thức | Có thể ném `IllegalArgumentException` |
| Truyền `null` thay đối tượng nhận cho accessor instance | Ném `NullPointerException` |
| Gọi phương thức không truy cập được từ mã hiện tại | Có thể ném `IllegalAccessException` |
| Accessor tự ném ngoại lệ khi thực thi | Ngoại lệ được bọc trong `InvocationTargetException` |

Accessor là `public` không có nghĩa một lớp record không truy cập được hoặc một ranh giới module tự động bị bỏ qua. Ví dụ hoàn chỉnh dùng record lồng `public` trong lớp `public`, nên không cần mở truy cập bằng `setAccessible(true)`.

## 7. Accessor có thể do người viết định nghĩa

Không mặc định rằng gọi accessor luôn tương đương với lấy nguyên tham chiếu đang lưu trong trường private. Record có thể khai báo accessor tường minh có phần thân riêng.

Ví dụ sau sử dụng sao chép bảo vệ cho thành phần mảng:

- Constructor sao chép mảng đầu vào.
- Accessor trả về một bản sao.
- Reflection gọi accessor đó như một lời gọi phương thức bình thường.

Lưu vào `RecordAccessorDemo.java`:

~~~java
import java.lang.reflect.RecordComponent;
import java.util.Arrays;

public class RecordAccessorDemo {
    public record Packet(byte[] bytes) {
        public Packet {
            bytes = bytes.clone();
        }

        @Override
        public byte[] bytes() {
            return bytes.clone();
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        byte[] original = {1, 2};
        Packet packet = new Packet(original);
        RecordComponent component =
                Packet.class.getRecordComponents()[0];

        byte[] first =
                (byte[]) component.getAccessor().invoke(packet);
        System.out.println("accessor: "
                + component.getAccessor().getName());
        System.out.println("return type: "
                + component.getType().getTypeName());
        System.out.println("first read: " + Arrays.toString(first));
        System.out.println("same as original: " + (first == original));

        first[0] = 9;
        byte[] second =
                (byte[]) component.getAccessor().invoke(packet);
        System.out.println("after changing result: "
                + Arrays.toString(second));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 RecordAccessorDemo.java
java RecordAccessorDemo
~~~

Kết quả:

~~~text
accessor: bytes
return type: byte[]
first read: [1, 2]
same as original: false
after changing result: [1, 2]
~~~

Sau khi sửa mảng nhận được ở lần đọc đầu, lần đọc sau vẫn cho `[1, 2]`. `getAccessor().invoke(packet)` đã thực thi mã `bytes.clone()`, không trả trực tiếp trường lưu trữ.

Ví dụ này không có nghĩa mọi record đều tự sao chép mảng hoặc tập hợp. Record không tự bảo đảm bất biến sâu cho dữ liệu tham chiếu. Hành vi sao chép trong chương trình đến từ constructor và accessor được viết tường minh.

Khi xây dựng công cụ đọc record, việc chọn accessor hay đọc trực tiếp trường là một quyết định về hành vi quan sát. Accessor là giao diện phương thức của record và có thể có logic; đọc trường là thao tác khác, thường còn cần xử lý truy cập private.

## 8. Chọn dữ liệu đầu ra: lược đồ thành phần và giá trị runtime

Khi thiết kế công cụ khảo sát record, nên tách hai sản phẩm có mục đích khác nhau:

| Đầu ra | Nguồn dữ liệu | Ví dụ với `Parcel<T>` |
| --- | --- | --- |
| Lược đồ (*schema*) | `getName()`, `getType()`, `getGenericType()` | Thành phần `weight` khai báo kiểu `T extends Number` |
| Giá trị của một instance | `getAccessor().invoke(instance)` | `weight` đang có giá trị `3` |

Lược đồ có thể được lập một lần từ `Parcel.class`; để đọc giá trị phải có một instance phù hợp. Nếu dùng `LinkedHashMap` ghép tên thành phần với giá trị accessor, hãy duyệt mảng `RecordComponent[]` theo thứ tự header. Đối tượng kết quả chỉ là ảnh chụp các giá trị mà accessor trả về; nó không tự sao chép sâu danh sách hoặc những đối tượng mutable trong record.

Việc xây một bộ đọc giá trị hoàn chỉnh phải quyết định thêm cách xử lý `null`, lỗi truy cập và `InvocationTargetException`. Metadata generic không thay thế các kiểm tra dữ liệu đó.

## 9. Những lỗi thường gặp

**Đồng nhất RecordComponent với Field.** Thành phần record có quan hệ với trường lưu trữ và accessor, nhưng là một loại metadata riêng. Muốn có trường theo tên phải dùng API trường; muốn đọc qua accessor phải gọi `getAccessor()`.

**Dùng getType để kết luận mọi thông tin generic đã biến mất.** `getType()` cho token sau xóa kiểu; `getGenericType()` có thể giữ biến kiểu và cấu trúc tham số hóa của khai báo.

**Ép mọi Type sang ParameterizedType.** Thành phần `int`, `String` hoặc `T` không có cùng dạng `Type` với `List<String>`.

**Cho rằng có `Parcel<Integer>` thì metadata weight phải là `Integer`.** Metadata thành phần thuộc lớp khai báo generic; muốn thay `T` bằng đối số cụ thể cần ngữ cảnh phân giải bổ sung.

**Tự tạo tên getter getX theo JavaBeans.** Accessor record dùng tên thành phần. Lấy trực tiếp `getAccessor()` tránh phụ thuộc quy tắc đặt tên sai.

**Quên rằng invoke thực thi mã.** Accessor tường minh có thể sao chép dữ liệu, kiểm tra điều kiện hoặc ném ngoại lệ.

**Dùng null như thể record không có thành phần.** `getRecordComponents() == null` nghĩa là lớp không phải record; record không có thành phần cho mảng rỗng.

**Dựa vào thứ tự các field hoặc method.** Cần thứ tự thành phần thì lấy chính danh sách `RecordComponent`.

## 10. Tự kiểm tra

1. Với `record Position(int x, int y)`, accessor của `x` tên là `x` hay `getX`?
2. Trong ví dụ `Parcel<T extends Number>`, vì sao `weight.getType()` là `Number.class` còn `weight.getGenericType()` biểu diễn `T`?
3. `getGenericType()` của `List<String> tags` có thể ép sang `Class<?>` để lấy `List<String>.class` không?
4. Kết quả `getRecordComponents()` của một lớp thường khác record không có thành phần như thế nào?
5. Vì sao giá trị đọc qua accessor của `int priority` lại là một `Integer` khi được chứa trong `Object`?
6. Nếu accessor tự sao chép một mảng, Reflection gọi accessor có tự bỏ qua logic sao chép đó không?
7. `RecordComponent` có tự cho biết giá trị của thành phần nếu chưa có một đối tượng record không?
8. Vì sao hàm `readComponents` dùng `LinkedHashMap` thay vì dựa vào thứ tự lặp tùy ý của một map khác?

Đáp án:

1. Tên là `x`, và lời gọi trong mã Java là `position.x()`.
2. `getType()` dùng kiểu sau xóa kiểu; biến `T` có cận `Number`. `getGenericType()` mô tả biến kiểu của khai báo.
3. Không. Đây là `ParameterizedType`; không có class literal cho một kiểu tham số hóa như vậy.
4. Lớp thường cho `null`; record không có thành phần cho mảng rỗng.
5. `Method.invoke` trả về `Object`, nên kết quả nguyên thủy được đóng hộp.
6. Không. Reflection thực thi chính phương thức accessor đó.
7. Không. Nó mô tả khai báo; muốn đọc giá trị qua accessor phải cung cấp một instance phù hợp.
8. Để giữ đúng thứ tự thành phần được `getRecordComponents()` cung cấp.
