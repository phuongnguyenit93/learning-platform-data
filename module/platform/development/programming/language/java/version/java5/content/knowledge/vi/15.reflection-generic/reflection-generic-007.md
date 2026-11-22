# TypeVariable và danh sách giới hạn

## Biến kiểu không phải một lớp cụ thể

Trong khai báo `Box<T extends Number>`, `T` là biến kiểu (type variable). Nó là một vị trí kiểu có tên, với điều kiện rằng đối số kiểu được dùng phải nằm trong giới hạn đã công bố.

Reflection biểu diễn biến kiểu bằng `TypeVariable`, không tự thay nó thành `Integer.class`, `Double.class` hay một lớp cụ thể khác. Một bộ đọc metadata cần giữ được tên, nơi khai báo và các cận của biến kiểu để không nhầm điều kiện của khai báo với kiểu đã được chọn trong một ngữ cảnh sử dụng.

Bài dùng thuật ngữ **cận trên (upper bound)** cho kiểu mà biến kiểu bị giới hạn bởi. `getBounds()` trả về danh sách các cận trên dưới dạng `Type[]`. Ví dụ dùng Java 17+ và chỉ các API reflection hiện hành.

## Lấy biến kiểu từ nơi khai báo

| Khai báo generic | API đọc các biến kiểu |
| --- | --- |
| Lớp hoặc interface | `SomeType.class.getTypeParameters()` |
| Phương thức | `method.getTypeParameters()` |
| Hàm tạo generic | `constructor.getTypeParameters()` |

Các đối tượng `Class`, `Method` và `Constructor` đều tham gia hợp đồng `GenericDeclaration`. Mảng trả về theo thứ tự khai báo; nếu không có biến kiểu do chính khai báo đó định nghĩa, mảng có độ dài bằng `0`. Xem [`GenericDeclaration`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/GenericDeclaration.html).

Không phải cứ có `T` trong kiểu trả về của một phương thức là phương thức ấy tự khai báo `T`. `T` có thể thuộc lớp bao ngoài. Muốn xác định nguồn, dùng `getGenericDeclaration()` trên chính `TypeVariable`.

## Các dạng cận cần hiểu

| Khai báo | Nội dung cận đọc được |
| --- | --- |
| `<U>` | `Object` vì không viết cận tường minh |
| `<T extends Number>` | `Number` |
| `<T extends Number & Comparable<T>>` | `Number` và `Comparable<T>` |
| `<V extends T>` | Biến kiểu `T` |
| `<E extends Comparable<E>>` | Kiểu có tham số `Comparable<E>`, tham chiếu lại `E` |

Cận giao như `Number & Comparable<T>` có nghĩa đối số kiểu phải thỏa **đồng thời** các ràng buộc, không phải được chọn một trong hai. Trong cú pháp khai báo cận, Java dùng `extends` cả với interface; không viết `T implements Comparable<T>`.

Kiểu của phần tử trong mảng cận là `Type`, vì cận có thể là `Class`, `ParameterizedType` hoặc `TypeVariable`. Không ép mọi cận sang `Class<?>`. Xem [`TypeVariable.getBounds()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/TypeVariable.html#getBounds()).

## Ví dụ hoàn chỉnh

Lưu tệp `TypeVariableBoundsDemo.java`:

```java
import java.io.Serializable;
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.lang.reflect.TypeVariable;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;
import java.util.stream.Collectors;

public final class TypeVariableBoundsDemo {
    private TypeVariableBoundsDemo() {
    }

    static class Box<T extends Number & Comparable<T>, U, V extends T> {
        T value;

        public <T extends CharSequence & Serializable> T echo(T text) {
            return text;
        }
    }

    private static String names(Type[] types) {
        return Arrays.stream(types).map(Type::getTypeName)
                .collect(Collectors.joining(" & "));
    }

    private static void walk(Type type, String indent, Set<TypeVariable<?>> path) {
        if (type instanceof TypeVariable<?> variable) {
            if (!path.add(variable)) {
                System.out.println(indent + variable.getName() + " (cycle)");
                return;
            }
            System.out.println(indent + "variable " + variable.getName());
            for (Type bound : variable.getBounds()) {
                walk(bound, indent + "  ", path);
            }
            path.remove(variable);
        } else if (type instanceof ParameterizedType parameterized) {
            System.out.println(indent + "parameterized " + type.getTypeName());
            for (Type argument : parameterized.getActualTypeArguments()) {
                walk(argument, indent + "  ", path);
            }
        } else if (type instanceof Class<?> concrete) {
            System.out.println(indent + "class " + concrete.getTypeName());
        } else {
            throw new IllegalArgumentException("unsupported bound shape: " + type);
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        TypeVariable<?>[] variables = Box.class.getTypeParameters();
        for (TypeVariable<?> variable : variables) {
            System.out.println(variable.getName() + ".bounds: "
                    + names(variable.getBounds()));
        }

        TypeVariable<?> classT = variables[0];
        System.out.println("classT.owner: "
                + ((Class<?>) classT.getGenericDeclaration()).getSimpleName());
        System.out.println("value.erased: "
                + Box.class.getDeclaredField("value").getType().getTypeName());

        Method echo = Box.class.getDeclaredMethod("echo", CharSequence.class);
        TypeVariable<Method> methodT = echo.getTypeParameters()[0];
        System.out.println("methodT.bounds: " + names(methodT.getBounds()));
        System.out.println("methodT.owner: " + methodT.getGenericDeclaration().getName());
        System.out.println("sameName: " + classT.getName().equals(methodT.getName()));
        System.out.println("sameVariable: " + classT.equals(methodT));

        Type secondBound = classT.getBounds()[1];
        System.out.println("secondBoundParameterized: "
                + (secondBound instanceof ParameterizedType));
        ParameterizedType comparable = (ParameterizedType) secondBound;
        System.out.println("selfArgumentEqualsT: "
                + comparable.getActualTypeArguments()[0].equals(classT));

        System.out.println("walk:");
        walk(classT, "", new HashSet<>());
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp bằng JDK 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all -Werror TypeVariableBoundsDemo.java
java TypeVariableBoundsDemo
```

Stdout chính xác:

```text
T.bounds: java.lang.Number & java.lang.Comparable<T>
U.bounds: java.lang.Object
V.bounds: T
classT.owner: Box
value.erased: java.lang.Number
methodT.bounds: java.lang.CharSequence & java.io.Serializable
methodT.owner: echo
sameName: true
sameVariable: false
secondBoundParameterized: true
selfArgumentEqualsT: true
walk:
variable T
  class java.lang.Number
  parameterized java.lang.Comparable<T>
    T (cycle)
```

Hàm `names` nối các tên cận bằng ` & ` để trình bày; không dùng chuỗi này làm thuật toán suy luận kiểu. Phần đọc và duyệt cấu trúc vẫn làm việc với `Type`.

## Đọc từng kết quả từ danh sách cận

### `T`: hai cận có hai dạng metadata

Cận đầu của `T` là `Number`, được biểu diễn bởi `Class<?>`. Cận thứ hai là `Comparable<T>`, được biểu diễn bởi `ParameterizedType`.

`getActualTypeArguments()[0]` trên cận `Comparable<T>` trả lại một `TypeVariable` biểu diễn cùng biến `T`. Dòng `selfArgumentEqualsT` xác nhận điều đó bằng `equals`, không bằng so sánh địa chỉ đối tượng. Xem [`ParameterizedType`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/ParameterizedType.html).

Thứ tự cận trong khai báo cần được giữ lại. Với `T extends Number & Comparable<T>`, kiểu sau xóa kiểu của `T` là `Number`, được thể hiện ở trường `value`. Không bỏ mọi cận trừ cận đầu chỉ vì kiểu sau xóa kiểu sử dụng cận đầu: các interface còn lại vẫn là một phần ràng buộc generic.

### `U`: không có cận viết ra vẫn có cận mặc định

`U` không viết `extends`, nhưng `getBounds()` không trả mảng rỗng cho khai báo này: nó có cận `Object`. Điều này cho phép một bộ đọc trình bày hoặc xử lý ràng buộc mặc định một cách nhất quán.

Đừng hiểu `Object` là đối số kiểu thực tế đã được chọn cho `U`. Nó là cận trên của biến kiểu chưa bị ràng buộc cụ thể hơn trong khai báo.

### `V`: cận là một biến kiểu khác

`V extends T` có cận trực tiếp là `T`, nên đầu ra in `V.bounds: T`. `getBounds()` không tự thay phần tử đó thành toàn bộ hai cận của `T` và trả một danh sách đã làm phẳng.

Nếu mục tiêu cần phân tích các ràng buộc gián tiếp, bộ đọc phải đi tiếp qua biến `T`. Ngược lại, nếu mục tiêu là tái hiện cấu trúc khai báo, giữ `V extends T` giúp bảo toàn mối quan hệ mà tác giả đã viết.

## Hai biến cùng tên ở hai phạm vi

`Box` khai báo `T extends Number & Comparable<T>`. Phương thức `echo` lại khai báo một `T` riêng, có cận `CharSequence & Serializable`. `T` của phương thức che tên `T` của lớp trong phạm vi tương ứng.

Vì vậy hai tên đều là `"T"`, nhưng `classT.equals(methodT)` là `false`. Cận khác nhau giúp nhận ra ví dụ, song điều quyết định danh tính biến kiểu không phải chỉ chuỗi tên hoặc danh sách cận mà còn nơi khai báo.

`classT.getGenericDeclaration()` là `Class` mô tả `Box`; `methodT.getGenericDeclaration()` là `Method` mô tả `echo`. Khi xây dựng ánh xạ thay thế biến kiểu, dùng chính `TypeVariable<?>` làm khóa thay vì chỉ dùng tên `"T"`.

API có thể tạo nhiều đối tượng biểu diễn cùng một biến kiểu, và chúng phải bình đẳng với nhau. Không dựa vào `==` để nhận diện mọi lần gặp cùng biến kiểu. Xem [hợp đồng của `TypeVariable`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/TypeVariable.html).

## Danh sách cận tạo thành đồ thị, có thể có chu trình

Với `T extends Comparable<T>`, việc đi từ `T` tới cận `Comparable<T>`, rồi tới đối số kiểu `T`, đưa bộ đọc trở về điểm xuất phát. Đây là kiểu tự tham chiếu hợp lệ, không phải chữ ký hỏng.

Nếu luôn mở mọi cận đệ quy mà không kiểm soát, bộ đọc có thể chạy không dừng hoặc gây `StackOverflowError`. Hàm `walk` trong ví dụ dùng tập `path` chứa những biến đang nằm trên đường duyệt hiện tại:

1. Gặp biến chưa có trong `path`: thêm vào, in và đi tiếp qua các cận.
2. Gặp lại biến đang có trong `path`: in `(cycle)` rồi dừng nhánh đó.
3. Sau khi xử lý xong các cận: bỏ biến khỏi `path` để những nhánh độc lập vẫn được duyệt.

`HashSet<TypeVariable<?>>` sử dụng `equals` và `hashCode`, phù hợp với hợp đồng nhận diện biến kiểu. Tập theo đường duyệt cũng khác một tập đã thăm toàn cục: một cận được chia sẻ ở nhánh khác không nhất thiết phải bị bỏ qua hoàn toàn.

Hàm `walk` chỉ hỗ trợ các dạng xuất hiện trong ví dụ và duyệt đối số kiểu của `ParameterizedType`. Nó chưa phải bộ phân tích mọi `Type`: wildcard lồng, mảng generic và thông tin kiểu chủ của lớp thành viên cần nhánh xử lý bổ sung nếu mở rộng phạm vi. Nhánh cuối báo rõ khi gặp cấu trúc chưa hỗ trợ.

## Quy tắc khai báo liên quan đến thứ tự và giới hạn

Trong cận giao có một lớp cụ thể, lớp đó phải đứng đầu; các thành phần bổ sung là interface. `T extends Number & Serializable` có thể hợp lệ, còn đưa `Number` vào vị trí sau một interface không đúng cú pháp ràng buộc này.

Kiểu sau xóa kiểu của một biến kiểu dựa trên cận trái nhất. Nếu không có cận tường minh, cận mặc định là `Object`. Điều này giải thích vì sao tra cứu một phương thức dùng tham số `T` phải xét chữ ký đã xóa, không chỉ tên biến generic. Xem [JLS về biến kiểu và xóa kiểu](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.4).

Các cận bổ sung còn chịu những hạn chế của hệ thống kiểu, chẳng hạn không được tạo các supertype có tham số xung đột. Một danh sách cận hợp lệ là kết quả của kiểm tra khi biên dịch; reflection đọc lại cấu trúc đó chứ không tự làm một phép lựa chọn interface cho ứng dụng.

Biến kiểu của Java khai báo các cận trên bằng `extends`; không có cú pháp khai báo `T super Integer`. Cận dưới như `? super Integer` thuộc wildcard, được biểu diễn bằng `WildcardType`, không phải `TypeVariable`.

## Cận không thay thế đối số kiểu thực tế

Với một lần sử dụng `Box<Integer, String, Integer>`, đối số `Integer` thỏa cận số và tự so sánh của `T`. Nhưng `Box.class.getTypeParameters()[0]` vẫn là biến kiểu `T` của khai báo, có cận `Number & Comparable<T>`.

Tạo instance không khiến mọi `TypeVariable` của lớp tự biến thành `Integer.class`. Muốn diễn giải thành viên trong một ngữ cảnh có đối số cụ thể, cần lấy metadata của ngữ cảnh đó và lập ánh xạ biến kiểu → đối số kiểu.

Không dùng `getBounds()[0]` như cách đoán “kiểu thật của T”. Ví dụ, thay `T` bằng `Number` sẽ làm mất ràng buộc `Comparable<T>` và không xác định được lớp cụ thể mà bên gọi đã chọn.

Khi cần kiểm tra dữ liệu lúc chạy, cận generic cũng không tự xác minh mọi thành phần của một cấu trúc dữ liệu bị xóa kiểu. Việc đọc metadata và kiểm tra giá trị thực là hai nhiệm vụ riêng.

## Annotation trên cận và các lỗi metadata

`getBounds()` trả thông tin kiểu. Nếu cận có annotation trên kiểu sử dụng và ứng dụng cần đọc chúng, dùng `getAnnotatedBounds()` để có `AnnotatedType[]`; không chờ `getBounds()` trả về các annotation dưới dạng tên chuỗi.

Ngoài ra, annotation đặt trên khai báo tham số kiểu và annotation đặt trên **cận** của nó là những vị trí khác nhau. Hãy xác định vị trí cần đọc trước khi chọn API.

Với lớp do công cụ khác sinh hoặc thư viện bên ngoài cung cấp, đọc cận có thể gặp `TypeNotPresentException` hoặc `MalformedParameterizedTypeException` nếu metadata tham chiếu kiểu không khả dụng hoặc không hợp lệ. Không thay tất cả lỗi đó bằng một danh sách cận rỗng, vì sẽ làm mất thông tin về nguyên nhân.

## Thực hành kiểm chứng

1. Đổi `<U>` thành `<U extends CharSequence>` rồi biên dịch lại. Dòng `U.bounds` đổi từ `Object` sang `CharSequence`.
2. Bỏ `Comparable<T>` khỏi cận `T`. Chỉ còn cận `Number`; đồng thời phải bỏ hoặc sửa đoạn ví dụ truy cập cận tại chỉ số `1`, vì cấu trúc khai báo đã thay đổi.
3. Đổi tên biến kiểu của `echo` từ `T` thành `E` và sửa kiểu tham số/trả về theo tên mới. `sameName` thành `false`, còn hai biến vẫn không bình đẳng.
4. Đổi `V extends T` thành `V extends Number`. Dòng `V.bounds` trở thành `java.lang.Number`, không còn liên kết trực tiếp tới biến `T`.
5. Thử một khai báo sai với lớp đứng sau interface trong tệp riêng để quan sát lỗi biên dịch; không đưa nó vào ví dụ chạy chính.

Người học cần giải thích được `TypeVariable` thuộc nơi khai báo nào, vì sao mảng cận chứa `Type`, vì sao cận giao là điều kiện đồng thời và vì sao một bộ duyệt generic phải xử lý được chu trình.