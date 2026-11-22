# Mẫu type token và anonymous subclass trong Java Reflection

## 1. Vì sao cần type token?

Trong Java, kiểu generic giúp trình biên dịch kiểm tra tính an toàn kiểu nhưng phần lớn tham số kiểu bị **type erasure** khi chạy. Chẳng hạn, cả `List<String>` và `List<Integer>` cùng có raw class là `java.util.List`. Biểu thức `List<String>.class` không hợp lệ; `List.class` chỉ biểu diễn raw type.

Tuy vậy, Java có thể lưu **chữ ký generic được khai báo** trong metadata của lớp, field, method hoặc superclass. Reflection có thể đọc chữ ký đó dưới dạng `java.lang.reflect.Type`. Mẫu **type token** sử dụng một đối tượng đại diện cho mô tả kiểu, để truyền kiểu phức tạp như `List<String>` hoặc `Map<String, List<Integer>>` tới một API cần thông tin kiểu.

Phân biệt hai trường hợp:

- **Class token**: `String.class`, `List.class` hoặc `Class<T>` phù hợp khi chỉ cần danh tính lớp/raw type.
- **Generic type token**: `Type` mô tả cả cấu trúc generic được khai báo, ví dụ `List<String>`, kiểu lồng nhau, wildcard hoặc mảng generic. Không phải mọi `Type` đều là `Class<?>`.

Type token **không đảo ngược type erasure của một đối tượng bất kỳ**. Nó đọc thông tin generic còn được lưu ở một vị trí khai báo cụ thể.

## 2. Anonymous subclass giúp giữ đối số generic như thế nào?

Đây là cách dùng thường gặp:

~~~java
Type type = new TypeRef<List<String>>() {}.type();
~~~

Dấu `{}` tạo ra **anonymous subclass** của `TypeRef<List<String>>`. Trình biên dịch lưu chữ ký generic của superclass trên lớp ẩn danh. Khi đối tượng được tạo:

1. `getClass()` trả về `Class` của anonymous subclass, **không phải** chính `TypeRef.class`.
2. `getClass().getGenericSuperclass()` đọc kiểu superclass đã khai báo, tức `TypeRef<List<String>>`.
3. Giá trị nhận được là một `ParameterizedType`; `getActualTypeArguments()[0]` chính là `List<String>`, vẫn ở dạng `Type`.
4. Có thể giữ `Type` này để đưa cho thư viện xử lý dữ liệu hoặc để phân tích tiếp bằng Reflection.

Cú pháp `new TypeRef<List<String>>()` **không có** `{}` sẽ không tạo được đối tượng trong ví dụ bên dưới vì `TypeRef` là lớp `abstract`. Quan trọng hơn, anonymous subclass là nơi có **chữ ký generic cụ thể** để đọc. Mẫu này đôi khi được gọi là *super type token*.

## 3. Tự xây dựng một TypeRef đơn giản, chạy được trên Java 17+

Lưu mã sau thành `TypeTokenDemo.java`:

~~~java
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.List;
import java.util.Map;

public class TypeTokenDemo {
    static abstract class TypeRef<T> {
        private final Type type;

        protected TypeRef() {
            Type parent = getClass().getGenericSuperclass();
            if (!(parent instanceof ParameterizedType parameterized)
                    || parameterized.getRawType() != TypeRef.class) {
                throw new IllegalStateException(
                        "Phải kế thừa TypeRef<T> với đối số kiểu cụ thể");
            }
            type = parameterized.getActualTypeArguments()[0];
        }

        public final Type type() {
            return type;
        }
    }

    static final class Example {
        List<String> names;
    }

    public static void main(String[] args) throws NoSuchFieldException {
        Type a = new TypeRef<List<String>>() {}.type();
        Type b = new TypeRef<Map<String, List<Integer>>>() {}.type();
        Type c = new TypeRef<List<Integer>>() {}.type();

        System.out.println(a.getTypeName());
        System.out.println(b.getTypeName());
        System.out.println(a.equals(c));

        if (b instanceof ParameterizedType p) {
            System.out.println(p.getRawType().getTypeName());
            for (Type arg : p.getActualTypeArguments()) {
                System.out.println(arg.getTypeName());
            }
        }

        Type fieldType = Example.class.getDeclaredField("names")
                .getGenericType();
        System.out.println(a.equals(fieldType));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 TypeTokenDemo.java
java TypeTokenDemo
~~~

Stdout:

~~~text
java.util.List<java.lang.String>
java.util.Map<java.lang.String, java.util.List<java.lang.Integer>>
false
java.util.Map
java.lang.String
java.util.List<java.lang.Integer>
true
~~~

Giải thích các kết quả:

- `a` và `c` có raw type giống nhau (`List`) nhưng đối số generic khác nhau (`String` và `Integer`), nên phép so sánh `Type.equals` cho kết quả `false`.
- `b` là `ParameterizedType` cho `Map<String, List<Integer>>`. `getRawType()` trả về `Map.class`; hai phần tử `getActualTypeArguments()` lần lượt là `String.class` và một `ParameterizedType` cho `List<Integer>`.
- Field `names` khai báo trực tiếp `List<String>` nên `Field.getGenericType()` cho một mô tả kiểu tương đương `a`; kết quả so sánh là `true`. Không cần tạo instance của `Example` để đọc khai báo field.
- Constructor của `TypeRef` chặn trường hợp kế thừa trực tiếp bằng raw type hoặc không khai báo `TypeRef<T>` dưới dạng superclass được tham số hóa. Triển khai đơn giản này **chỉ hỗ trợ lớp kế thừa trực tiếp `TypeRef<...>`**, không tự lần theo nhiều tầng kế thừa.

Chữ ký generic được đọc từ cấu trúc lớp đã biên dịch; thao tác này **không kiểm tra nội dung thực tế** của một `List` tại runtime. Mẫu `TypeRef` cũng không tự giải mã JSON, chuyển đổi dữ liệu hay xác minh từng phần tử.

## 4. Đọc cây Type đúng cách

`Type` là một interface chung. Kết quả đọc được có thể thuộc các loại sau:

| Loại Reflection | Ví dụ | Ý nghĩa và API chính |
| --- | --- | --- |
| `Class<?>` | `String.class`, `List.class`, `String[].class` | Lớp hoặc mảng có kiểu thành phần reifiable; `getTypeName()` |
| `ParameterizedType` | `List<String>`, `Map<String, Integer>` | Raw type, owner type và đối số kiểu; `getRawType()`, `getOwnerType()`, `getActualTypeArguments()` |
| `TypeVariable<?>` | `T` trong `class Box<T>` | Biến kiểu từ khai báo; `getName()`, `getBounds()`, `getGenericDeclaration()` |
| `WildcardType` | `? extends Number`, `? super Integer` | Cận trên/dưới; `getUpperBounds()`, `getLowerBounds()` |
| `GenericArrayType` | `List<String>[]`, `T[]` | Mảng có kiểu thành phần không reifiable; `getGenericComponentType()` |

Ví dụ `new TypeRef<List<? extends Number>>() {}.type()` có nút ngoài là `ParameterizedType` cho `List`; đối số kiểu của nút này là `WildcardType`. Với `new TypeRef<List<String>[]>() {}.type()`, nút ngoài thường là `GenericArrayType` có component là `ParameterizedType` cho `List<String>`.

Muốn phân tích chính xác generic lồng nhau, cần duyệt đệ quy theo **loại nút**; không ép tất cả kết quả về `Class<?>`. Ví dụ kiểm tra một `Type` trước khi xử lý:

~~~java
if (type instanceof ParameterizedType p) {
    Type raw = p.getRawType();
    Type[] args = p.getActualTypeArguments();
    // Tiếp tục kiểm tra loại của từng phần tử args.
} else if (type instanceof Class<?> cls) {
    // Kiểu lớp, primitive hoặc mảng reifiable.
} else if (type instanceof TypeVariable<?> tv) {
    // Tên và bounds của biến kiểu; chưa chắc đã là kiểu cụ thể.
}
~~~

Đoạn trên là **mảnh mã minh họa** với biến `type` đã có sẵn; phần chương trình hoàn chỉnh ở mục 3 có thể chạy độc lập.

Các nguồn Reflection khác cũng cung cấp `Type`: `Field.getGenericType()`, `Method.getGenericReturnType()`, `Method.getGenericParameterTypes()`, `Class.getGenericInterfaces()` và `Class.getGenericSuperclass()`. Nếu dùng các phiên bản **không có “Generic”**, như `Field.getType()` hoặc `Method.getReturnType()`, kết quả chỉ là `Class<?>` sau erasure.

## 5. Áp dụng khi thiết kế API

Khi một hàm cần biết cấu trúc kiểu đích để phân tích dữ liệu, nên để nó nhận `Type` (hoặc một abstraction tương đương), thay vì chỉ nhận `Class<?>`. Cách gọi phía client có thể là:

~~~java
Type listOfNames = new TypeRef<List<String>>() {}.type();
Type index = new TypeRef<Map<String, List<Integer>>>() {}.type();
~~~

Hai biến trên là mô tả kiểu, thích hợp làm đầu vào cho API **có hỗ trợ `Type`**. API đó phải tự định nghĩa cách dùng `ParameterizedType`, wildcard và các kiểu lồng nhau; `TypeRef` chỉ làm nhiệm vụ giữ và cung cấp thông tin kiểu.

Đối với type đơn giản, `String.class` thường đủ và gọn hơn. Đối với kiểu khai báo trong một class cụ thể, đọc từ field/method bằng Reflection có thể phù hợp hơn việc tạo anonymous subclass mới. Nhiều thư viện có sẵn loại tương tự (chẳng hạn `TypeToken` hoặc `TypeReference`); tên API, khả năng hỗ trợ biến kiểu và cách tạo token có thể khác nhau giữa thư viện.

## 6. Những giới hạn và lỗi dễ gặp

### 6.1. Không thể suy ra generic của đối tượng thường

~~~java
List<String> names = new java.util.ArrayList<>();
System.out.println(names.getClass() == java.util.ArrayList.class);
~~~

Kết quả là `true`. Runtime class của instance là `ArrayList`, không mang riêng đối số `String` của biến `names`. `names.getClass().getGenericSuperclass()` cho biết khai báo superclass generic của **lớp ArrayList**, không chứng minh list đó có các phần tử `String`.

Không thể dùng `new TypeRef<>(...)` để “đọc ngược” kiểu generic đã mất từ một instance tùy ý nếu không có metadata khai báo bổ sung.

### 6.2. Bắt được biến kiểu chưa chắc bắt được kiểu cụ thể

Trong một phương thức generic:

~~~java
static <T> Type captureInGenericMethod() {
    return new TypeRef<List<T>>() {}.type();
}
~~~

`Type` tạo ra mô tả `List<T>`, trong đó `T` là một `TypeVariable` của khai báo phương thức. Dù gọi từ ngữ cảnh có đối số là `String`, không thể tự suy ra `List<String>` chỉ từ token này. Muốn kiểu cụ thể, hãy truyền vào một `Type` đã được xác định hoặc có cơ chế giải quyết biến kiểu từ ngữ cảnh phù hợp. Đoạn trên giả định `TypeRef` của mục 3 và import `Type`; đây là minh họa, không phải chương trình độc lập.

### 6.3. Nhầm `ParameterizedType` với `Class`

Ép kiểu `(Class<?>) new TypeRef<List<String>>() {}.type()` sẽ gây `ClassCastException` vì nút ngoài là `ParameterizedType`. Hãy kiểm tra bằng `instanceof` và chỉ lấy `getRawType()` khi thực sự cần raw type.

### 6.4. Raw type và lớp kế thừa nhiều tầng

Viết `new TypeRef() {}` làm mất đối số kiểu và bị constructor ví dụ phát hiện. Với `class Mid<T> extends TypeRef<T>` rồi `class Final extends Mid<String>`, `Final.class.getGenericSuperclass()` là `Mid<String>`, không trực tiếp là `TypeRef<String>`; triển khai mục 3 sẽ từ chối. Một phiên bản tổng quát muốn hỗ trợ phân cấp nhiều tầng phải lần theo hierarchy và giải quyết ánh xạ `TypeVariable` qua từng cấp, thay vì chỉ đọc `getActualTypeArguments()[0]` ở cấp đầu.

### 6.5. Đừng nhầm metadata với bảo đảm an toàn runtime

Token `List<String>` mô tả ý định kiểu. Nó không ngăn raw-type code thêm phần tử sai kiểu vào list và không biến kiểm tra `instanceof List<String>` thành hợp lệ. Việc validate/deserialize dữ liệu cần xử lý riêng, bao gồm kiểu con, null, wildcard và sai định dạng.

## 7. Ghi nhớ khi dùng Reflection generic

- Khi cần đối số generic **được khai báo trên superclass**, dùng `getGenericSuperclass()` và kiểm tra `ParameterizedType`.
- Với một type token cụ thể, dùng `new TypeRef<KiểuĐích>() {}`; cặp `{}` là phần tạo subclass có chữ ký để Reflection đọc.
- Sau khi lấy `Type`, duyệt các loại `Class`, `ParameterizedType`, `WildcardType`, `TypeVariable` và `GenericArrayType` theo nhu cầu. Không giả định mọi nút đều có class trực tiếp.
- Phân biệt **kiểu được khai báo** với **kiểu của dữ liệu khi đang chạy**; type erasure vẫn áp dụng.
- Chỉ sử dụng token với API hiểu `Type`. Kiểm thử riêng các trường hợp nested generic, wildcard, generic method và raw type nếu framework của bạn hỗ trợ chúng.

Bản chất của mẫu này là **đưa một biểu thức generic cụ thể vào chữ ký superclass của một anonymous subclass**, rồi lấy lại mô tả đó qua Reflection. Đây là cách truyền thông tin kiểu giàu cấu trúc cho API mà vẫn tuân theo cơ chế type erasure của Java.