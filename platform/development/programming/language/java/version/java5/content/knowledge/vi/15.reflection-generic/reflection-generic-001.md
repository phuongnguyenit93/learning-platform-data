# Class<T> và quan hệ giữa Class với đối tượng

## Hai loại đối tượng cần phân biệt

Một đối tượng như chuỗi `"An"` chứa dữ liệu mà chương trình sử dụng. Đối tượng `String.class` lại mô tả kiểu `String`: tên kiểu, lớp cha, các phương thức, trường và thông tin reflection khác.

`Class<T>` là lớp tổng quát của Java dùng để biểu diễn thông tin kiểu lúc chạy. Trong `Class<String>`, đối số `String` cho biết đối tượng `Class` này mô tả kiểu `String`; bản thân nó không phải một chuỗi. Xem [vai trò của `Class<T>`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html).

Có thể hình dung quan hệ:

```text
biến name  ──tham chiếu──> đối tượng chuỗi "An"
                               │ getClass()
                               ▼
                         đối tượng String.class
                         có kiểu Class<String>
```

`String.class` cũng là một đối tượng Java. Nhưng việc lấy đối tượng mô tả kiểu không tạo thêm một đối tượng nghiệp vụ của kiểu đó.

Bài dùng Java 17+ để làm rõ quan hệ giữa kiểu khai báo, lớp thực và thông tin kiểu được truyền vào một API tổng quát.

## `.class` và `getClass()` trả lời hai câu hỏi

| Biểu thức | Ý nghĩa | Cần một đối tượng có sẵn? |
| --- | --- | --- |
| `Number.class` | Đối tượng mô tả kiểu `Number` đã chỉ rõ trong mã | Không |
| `value.getClass()` | Đối tượng mô tả lớp thực của đối tượng mà `value` đang tham chiếu | Có, và tham chiếu phải khác `null` |

Với `Number value = Integer.valueOf(7)`, kiểu khai báo của biến là `Number`, lớp thực của đối tượng là `Integer`. Vì vậy `value.getClass()` mô tả `Integer`, không mô tả `Number`.

`getClass()` là phương thức `final` của `Object`. Kiểu kết quả khi dùng trong mã được điều chỉnh theo kiểu tĩnh của biểu thức; với biến `Number`, có thể nhận vào `Class<? extends Number>`. Xem [`Object.getClass()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Object.html#getClass()).

Không gọi `getClass()` trên `null`: nó sẽ gây `NullPointerException`. Nếu đã biết tên kiểu tại thời điểm viết mã, dùng `.class` không cần tạo một instance chỉ để lấy metadata.

## Ví dụ hoàn chỉnh: đối tượng và lớp thực

Lưu tệp `ClassObjectDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public final class ClassObjectDemo {
    private ClassObjectDemo() {
    }

    public static void main(String[] args) {
        String name = "An";
        Class<String> literal = String.class;
        Class<? extends String> runtimeString = name.getClass();
        System.out.println("sameStringType: " + (literal == runtimeString));

        Number value = Integer.valueOf(7);
        Class<? extends Number> runtimeNumber = value.getClass();
        System.out.println("declaredType: " + Number.class.getSimpleName());
        System.out.println("runtimeType: " + runtimeNumber.getSimpleName());
        System.out.println("isInteger: " + (runtimeNumber == Integer.class));

        Object first = new Object();
        Object second = new Object();
        System.out.println("sameObject: " + (first == second));
        System.out.println("sameClass: " + (first.getClass() == second.getClass()));

        Class<?> unknown = Integer.class;
        Class<? extends Number> numberType = unknown.asSubclass(Number.class);
        System.out.println("narrowedType: " + numberType.getSimpleName());

        Object input = Integer.valueOf(9);
        Number number = Number.class.cast(input);
        System.out.println("castValue: " + number.intValue());
        System.out.println("isNumberInstance: " + Number.class.isInstance(input));
        System.out.println("integerAssignableToNumber: "
                + Number.class.isAssignableFrom(Integer.class));

        List<String> words = new ArrayList<>();
        List<Integer> numbers = new ArrayList<>();
        System.out.println("sameErasedClass: " + (words.getClass() == numbers.getClass()));
        System.out.println("isListInterface: " + List.class.isInterface());

        Class<Integer> primitive = int.class;
        Class<Integer> wrapper = Integer.class;
        System.out.println("samePrimitiveAndWrapper: " + (primitive == wrapper));
        System.out.println("primitiveFlag: " + primitive.isPrimitive());
        System.out.println("primitiveAcceptsBoxed: " + primitive.isInstance(1));

        Class<String[]> arrayType = String[].class;
        System.out.println("arrayComponent: "
                + arrayType.getComponentType().getSimpleName());
    }
}
```

Chạy tại thư mục chứa tệp bằng JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror ClassObjectDemo.java
java ClassObjectDemo
```

Stdout chính xác:

```text
sameStringType: true
declaredType: Number
runtimeType: Integer
isInteger: true
sameObject: false
sameClass: true
narrowedType: Integer
castValue: 9
isNumberInstance: true
integerAssignableToNumber: true
sameErasedClass: true
isListInterface: true
samePrimitiveAndWrapper: false
primitiveFlag: true
primitiveAcceptsBoxed: false
arrayComponent: String
```

`first` và `second` trỏ tới hai đối tượng khác nhau, nhưng chúng có cùng lớp thực `Object`. Các instance cùng lớp không cần một đối tượng `Class` riêng cho từng instance.

## `Class<T>` mang lại ràng buộc kiểu gì?

| Dạng | Cách hiểu |
| --- | --- |
| `Class<String>` | Mô tả đúng kiểu `String` trong hợp đồng tổng quát |
| `Class<?>` | Có một kiểu được mô tả nhưng mã hiện tại chưa biết cụ thể là kiểu nào |
| `Class<? extends Number>` | Mô tả một kiểu trong giới hạn `Number`, có thể là `Number` hoặc kiểu con |
| `Class<Object>` | Mô tả kiểu `Object`; không phải biến chứa mọi đối tượng `Class` |

Generics không tự có quan hệ mở rộng theo đối số kiểu. Vì `String` là kiểu con của `Object`, không có nghĩa `Class<String>` là kiểu con của `Class<Object>`. Nếu muốn chứa `String.class`, `Integer.class` và nhiều kiểu khác trong cùng một biến, hãy dùng `Class<?>`.

Đoạn sau minh họa khai báo hợp lệ và một dòng **cố ý không biên dịch**; không chép nguyên khối này vào chương trình chạy:

```java
Class<String> stringType = String.class;
Class<?> anyType = stringType;
Class<? extends CharSequence> textType = stringType;
// Class<Object> objectType = stringType; // Không tương thích kiểu.
```

`Class<T>` thường được gọi là thẻ kiểu (type token): một đối tượng mô tả kiểu được truyền vào API để liên kết thông tin lúc chạy với đối số kiểu ở lúc biên dịch.

Ví dụ phương thức tổng quát sau có thể đặt trong một lớp:

```java
static <T> T readAs(Class<T> expectedType, Object value) {
    return expectedType.cast(value);
}
```

Lời gọi `String text = readAs(String.class, "hello")` nhận được `String` mà không cần phép ép kiểu không được kiểm tra. Tuy nhiên, lời gọi `readAs(String.class, Integer.valueOf(1))` vẫn biên dịch vì tham số thứ hai là `Object`; kiểm tra kiểu diễn ra khi `cast` chạy và ném `ClassCastException` nếu giá trị không phù hợp.

Thẻ kiểu không làm mọi dữ liệu đầu vào trở nên đúng. Nó cho API một kiểu đích rõ ràng để kiểm tra và cung cấp kiểu kết quả tương ứng.

## `cast`, `asSubclass`, `isInstance` và `isAssignableFrom`

Bốn API này liên quan nhưng làm các công việc khác nhau:

| API | Đối tượng được kiểm tra | Ý nghĩa |
| --- | --- | --- |
| `Number.class.cast(value)` | Một giá trị đối tượng | Kiểm tra và trả lại chính giá trị dưới kiểu `Number`; không chuyển chuỗi thành số |
| `unknown.asSubclass(Number.class)` | Kiểu được `unknown` mô tả | Kiểm tra nó có thể được thu hẹp thành `Class<? extends Number>` không |
| `Number.class.isInstance(value)` | Một giá trị đối tượng | Trả boolean tương tự kiểm tra `instanceof Number` |
| `Number.class.isAssignableFrom(Integer.class)` | Hai kiểu | Hỏi giá trị có kiểu `Integer` có thể gán vào nơi nhận `Number` không |

Trong ví dụ, `cast` trả lại đối tượng `Integer` đang có dưới kiểu tĩnh `Number`; `asSubclass` trả lại đối tượng `Class` đang mô tả `Integer` dưới giới hạn kiểu chặt hơn. Không thao tác nào tạo instance nghiệp vụ mới.

`String.class.asSubclass(Number.class)` ném `ClassCastException`. Với `cast`, đầu vào `null` được trả lại là `null`; với `isInstance`, đầu vào `null` cho `false`. Khi dùng `isAssignableFrom`, đọc đúng chiều từ kiểu nhận tới kiểu cung cấp. Xem [các phương thức của `Class`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Class.html).

## Lớp thực không khôi phục mọi đối số generic

`words` và `numbers` đều được tạo bằng `new ArrayList<>()`. Dù kiểu khai báo lần lượt là `List<String>` và `List<Integer>`, `getClass()` của cả hai đều mô tả `ArrayList` sau xóa kiểu. Kết quả không chứa một `Class` riêng cho `ArrayList<String>` và `ArrayList<Integer>`.

Không có biểu thức hợp lệ `List<String>.class` hay `T.class` cho biến kiểu generic `T`. Cách lấy class literal phụ thuộc các kiểu được Java cho phép biểu diễn tại vị trí đó. Xem [class literal trong JLS](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.8.2).

`List.class` biểu diễn giao diện `List` ở mức lớp lúc chạy. `List.class.cast(value)` chỉ kiểm tra một đối tượng có phù hợp với `List` hay không; nó không kiểm tra mọi phần tử là `String`. Vì vậy không dùng `Class` đơn thuần để chứng minh một dữ liệu bất kỳ là `List<String>`.

Reflection vẫn có thể đọc thông tin generic được ghi trong **khai báo** của trường, phương thức hoặc lớp cha bằng các API liên quan đến `Type`. Điều đó khác với việc khôi phục đối số kiểu của mọi instance từ `getClass()`. Xem [xóa kiểu và kiểu còn biểu diễn được lúc chạy](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.7).

## Primitive, wrapper, interface và mảng

`Class` không chỉ mô tả lớp có thể khởi tạo. Nó còn có đối tượng đại diện cho interface, kiểu mảng, kiểu nguyên thủy và `void`.

Ví dụ cho thấy `int.class` và `Integer.class` đều có thể nhận vào biến `Class<Integer>`, nhưng chúng là hai đối tượng mô tả **hai kiểu khác nhau**. `int.class.isPrimitive()` là `true`, còn `Integer.class.isPrimitive()` là `false`.

`primitive.isInstance(1)` trong chương trình là `false`: đối số `1` được đóng hộp thành `Integer` để truyền vào tham số `Object`, trong khi kiểu nguyên thủy `int` không có instance đối tượng. Không suy ra rằng kiểm tra bằng `Class` tự áp dụng các chuyển đổi số hoặc đóng/mở hộp như một phép gán trong mã nguồn.

`String[].class` mô tả kiểu mảng, và `getComponentType()` cho `String.class`. Các mảng cùng kiểu phần tử và số chiều dùng cùng một đối tượng `Class`; mảng không đồng nghĩa với `Class` của phần tử.

`void.class` có kiểu `Class<Void>` nhưng không phải `Void.class`. Việc có đối tượng `Class` cho một kiểu không chứng minh có thể tạo một instance của kiểu đó.

## Lấy metadata không đồng nghĩa với tạo đối tượng

Không viết `new Class<String>()`; `Class` không có hàm tạo công khai để tự dựng mô tả một kiểu tùy ý. Các đối tượng `Class` được JVM cung cấp theo cơ chế nạp/định nghĩa kiểu.

Nếu cần tạo instance từ metadata, một API hiện hành là `type.getDeclaredConstructor().newInstance()`, nhưng còn phải thỏa điều kiện về hàm tạo, tính cụ thể của kiểu và khả năng truy cập. Đây là thao tác riêng với việc lấy `type`.

Ví dụ `List.class` là metadata hợp lệ của một interface, song không thể dùng nó như một lớp cụ thể có hàm tạo không tham số. Với một lớp đã biết trực tiếp trong mã, `new` thường rõ ràng hơn việc khởi tạo bằng reflection.

## Danh tính kiểu trong môi trường có nhiều bộ nạp lớp

Trong ví dụ đơn giản, `name.getClass() == String.class` cho `true`. So sánh trực tiếp các đối tượng `Class` dùng danh tính kiểu thật trong JVM; không cần chuyển chúng thành tên chuỗi để so sánh.

Trong hệ thống có nhiều class loader, tên nhị phân giống nhau chưa đủ để kết luận là cùng một kiểu. Kiểu lớp/interface được xác định cùng với bộ nạp định nghĩa nó; hai plugin có thể nạp các kiểu cùng tên nhưng không tương thích. Xem [quy tắc cùng kiểu trong JLS](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.3.4).

`Class.forName(...)` là một cách lấy metadata từ tên tại lúc chạy, nhưng cần chọn đúng tên và môi trường nạp lớp; nó không tạo đối tượng nghiệp vụ. Nếu chỉ cần kiểu đã biết tại lúc viết mã, `.class` tránh phải dựa vào một chuỗi tên.

## Thực hành kiểm chứng

1. Đổi giá trị của biến `Number value` thành `Double.valueOf(7.5)`. Kiểu khai báo vẫn là `Number`, nhưng `runtimeType` thành `Double` và `isInteger` thành `false`.
2. Đổi `unknown` thành `String.class`. `asSubclass(Number.class)` phải ném `ClassCastException`; việc dùng `Class<?>` không bỏ qua kiểm tra lúc chạy.
3. Đổi `input` thành chuỗi `"9"`. `Number.class.cast(input)` không phân tích chuỗi mà ném `ClassCastException`.
4. Đổi `String[].class` thành `Integer[].class` và cập nhật kiểu biến tương ứng. `getComponentType()` phải biểu diễn `Integer`.
5. Viết `Class<Object> wrong = String.class` trong một tệp thử riêng rồi biên dịch để thấy vì sao cần `Class<?>` khi kiểu được mô tả chưa biết.

Sau bài học, cần phân biệt được đối tượng dữ liệu, biến tham chiếu, kiểu khai báo và đối tượng `Class` mô tả lớp thực; đồng thời giải thích được `Class<T>` liên kết thông tin kiểu ở hai thời điểm như thế nào mà không khôi phục mọi đối số generic đã bị xóa.