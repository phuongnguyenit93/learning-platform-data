# Method, proxy instance và args trong InvocationHandler (Java Dynamic Proxy)

## Mục tiêu và bức tranh tổng thể

Với JDK dynamic proxy, khi người gọi gọi một phương thức trên đối tượng proxy, lớp proxy do JDK tạo chuyển lời gọi đến `InvocationHandler.invoke(Object proxy, Method method, Object[] args)`. Handler quyết định xử lý lời gọi bằng logic riêng, ủy quyền sang target, hoặc ném ngoại lệ. Muốn viết handler đúng, bạn phải phân biệt **proxy instance**, **metadata của phương thức** và **giá trị các đối số**.

~~~text
Caller: api.add(2, 5)
          |
          v
JDK proxy implements interface Calculator
          |
          v
InvocationHandler.invoke(proxy, method, args)
                         |       |       |
              chính proxy       |       +-- [Integer(2), Integer(5)]
                                +---------- Method: Calculator.add(int,int)
          |
          +--> xử lý trực tiếp / gọi method.invoke(target, args)
          |
          v
return Object (Integer(7)) -> proxy unbox -> caller nhận int 7
~~~

JDK dynamic proxy triển khai **interface**; bạn tạo proxy bằng `Proxy.newProxyInstance(classLoader, interfaces, handler)`. `target` không phải tham số mặc định của `InvocationHandler`: nếu muốn proxy làm việc như một decorator, bạn tự giữ target trong handler và tự gọi tiếp.

## 1. `invoke(proxy, method, args)` trả về dữ liệu gì?

Chữ ký trong `java.lang.reflect.InvocationHandler`:

~~~java
Object invoke(Object proxy, Method method, Object[] args) throws Throwable;
~~~

Đây là chữ ký API, không phải chương trình chạy độc lập.

| Tham số | Bản chất | Dùng để làm gì? |
| --- | --- | --- |
| `proxy` | Chính **đối tượng JDK proxy** mà caller đang gọi; nó thường khác đối tượng nghiệp vụ `target` | Kiểm tra identity, thực hiện quy tắc `equals/hashCode/toString`, chạy default method trên proxy |
| `method` | `java.lang.reflect.Method` đại diện cho phương thức được proxy xử lý | Đọc tên/chữ ký/annotation/kiểu trả về, chọn chính sách, ủy quyền cho receiver tương thích |
| `args` | `Object[]` chứa **giá trị đối số theo thứ tự**; bằng `null` nếu method không có tham số | Kiểm tra, log có kiểm soát, biến đổi, hoặc chuyển tiếp sang target |

### 1.1. `Method` là metadata của lời gọi, không nhất thiết là method trên target

Các API quan trọng:

- `getName()` trả tên phương thức. Khi có overload, phải so thêm `getParameterTypes()`; tên đơn lẻ chưa đủ phân biệt `find(int)` và `find(String)`.
- `getDeclaringClass()` thường trả interface khai báo phương thức (có thể là **superinterface**); với `equals(Object)`, `hashCode()` và `toString()`, nó trả `Object.class`.
- `getReturnType()` và `getParameterTypes()` mô tả kiểu runtime (sau type erasure); `getGenericReturnType()` và `getGenericParameterTypes()` đọc thông tin generic được lưu trong chữ ký khai báo.
- `getAnnotation(MyAnnotation.class)` đọc annotation runtime trên chính `Method` này. Nó **không tự tìm** annotation chỉ tồn tại trên method được triển khai bởi target.
- `isDefault()` nhận diện interface default method; `isVarArgs()` nhận diện tham số varargs; `getExceptionTypes()` cho biết checked exceptions trên chữ ký.

Nếu proxy triển khai nhiều interface khai báo phương thức **cùng tên và danh sách tham số**, `Method` đưa cho handler được lựa chọn dựa trên thứ tự interface trong lúc tạo proxy; nó không bắt buộc tương ứng với interface mà caller dùng để tham chiếu lời gọi. Với chữ ký trùng nhau, không suy diễn quá nhiều từ `getDeclaringClass()` hay chỉ từ annotation của một trong các interface.

### 1.2. `proxy` là proxy, không phải target

- `Proxy.isProxyClass(proxy.getClass())` xác nhận class do API JDK proxy tạo ra; `Proxy.getInvocationHandler(proxy)` truy xuất handler từ proxy hợp lệ.
- Không dựa vào tên class sinh bởi JDK vì đó là chi tiết triển khai.
- **Không ủy quyền bằng `method.invoke(proxy, args)`** trong chính handler: khi gọi phương thức interface trên proxy một lần nữa, lời gọi đi vào cùng handler, có thể lặp đến `StackOverflowError`. Thông thường dùng `method.invoke(target, args)`, với target triển khai interface tương ứng.
- Ngay cả `System.out.println(proxy)` hoặc nối chuỗi với proxy cũng có thể gọi `proxy.toString()` rồi vào handler lần nữa. Dùng thông tin phương thức hoặc identity để log khi chưa có chính sách `toString` rõ ràng.

### 1.3. `args` chứa giá trị, với ba tình huống đặc biệt

**Không tham số:** `ping()` khiến `args == null`; không được truy cập `args.length` trước khi kiểm tra. Handler có thể chuẩn hóa thành `args == null ? new Object[0] : args` nếu thuật toán cần một mảng.

**Primitive và null:** `add(2,5)` có mảng `Object[]` gồm hai `Integer` (boxing). Ngược lại, `send(null)` có mảng **dài 1**, phần tử `args[0] == null`; khác với `args == null`.

**Varargs:** `join("a", "b")` của `join(String... parts)` nhận `args.length == 1` và `args[0]` là mảng `String[]{"a","b"}`. Varargs là một tham số mảng ở runtime. `join((String[]) null)` lại có mảng `args` một phần tử với `args[0] == null`.

## 2. Chương trình Java 17+ chạy được: quan sát cả ba tham số

Lưu toàn bộ thành **HandlerArgumentsDemo.java**. Chương trình có một target `CalculatorImpl`, method trả primitive, varargs, default method, `Object.toString` và `Object.equals`.

~~~java
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Arrays;

public class HandlerArgumentsDemo {
    public interface Calculator {
        int add(int left, int right);
        String join(String... parts);

        default String origin() {
            return "from default";
        }
    }

    static final class CalculatorImpl implements Calculator {
        @Override
        public int add(int left, int right) {
            return left + right;
        }

        @Override
        public String join(String... parts) {
            return String.join(":", parts);
        }
    }

    public static void main(String[] args) {
        Calculator target = new CalculatorImpl();

        InvocationHandler handler = (proxy, method, callArgs) -> {
            String methodName = method.getDeclaringClass().getSimpleName()
                    + "." + method.getName();

            // Tránh gọi toString() trên proxy trong equals(proxy).
            String shownArgs = method.getDeclaringClass() == Object.class
                    && method.getName().equals("equals")
                    ? "[reference]"
                    : callArgs == null
                            ? "null"
                            : Arrays.deepToString(callArgs);

            System.out.println("invoke " + methodName
                    + " | isProxy=" + Proxy.isProxyClass(proxy.getClass())
                    + " | args=" + shownArgs);

            if (method.getDeclaringClass() == Object.class) {
                return switch (method.getName()) {
                    case "toString" -> "CalculatorProxy";
                    case "hashCode" -> System.identityHashCode(proxy);
                    case "equals" -> proxy == callArgs[0];
                    default -> throw new UnsupportedOperationException(
                            method.getName());
                };
            }

            if (method.isDefault()) {
                return InvocationHandler.invokeDefault(proxy, method, callArgs);
            }

            try {
                return method.invoke(target, callArgs);
            } catch (InvocationTargetException e) {
                throw e.getCause();
            }
        };

        Calculator calculator = (Calculator) Proxy.newProxyInstance(
                Calculator.class.getClassLoader(),
                new Class<?>[]{Calculator.class},
                handler);

        System.out.println("result=" + calculator.add(2, 5));
        System.out.println("join=" + calculator.join("a", "b"));
        System.out.println("origin=" + calculator.origin());
        System.out.println("toString=" + calculator.toString());
        System.out.println("same=" + calculator.equals(calculator));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac HandlerArgumentsDemo.java
java HandlerArgumentsDemo
~~~

Output:

~~~text
invoke Calculator.add | isProxy=true | args=[2, 5]
result=7
invoke Calculator.join | isProxy=true | args=[[a, b]]
join=a:b
invoke Calculator.origin | isProxy=true | args=null
origin=from default
invoke Object.toString | isProxy=true | args=null
toString=CalculatorProxy
invoke Object.equals | isProxy=true | args=[reference]
same=true
~~~

**Giải thích các điểm quan trọng:**

1. `method` trong lời gọi `add` là `Calculator.add(int,int)`; `callArgs` chứa `Integer(2)` và `Integer(5)`. Handler chuyển lời gọi tới `CalculatorImpl`; giá trị trả về qua reflection là `Integer(7)` và proxy unbox thành `int` cho caller.
2. `join` có `args` một phần tử mảng, nên `Arrays.deepToString(callArgs)` hiển thị `[[a, b]]`.
3. `origin()` không có tham số nên `callArgs == null`. Vì `method.isDefault()` là true, `invokeDefault` thực thi phần thân default method trên proxy.
4. Hai lời gọi `Object.toString` và `Object.equals` vẫn đi qua handler. Ví dụ dùng identity equality; không in chính proxy bên trong `equals` để tránh callback ngoài ý muốn vào `toString`.
5. `target` là object nghiệp vụ có sẵn; `calculator` là proxy do `Proxy.newProxyInstance` trả về. Handler **tự quyết định** gọi target.

## 3. Forward Method sang target và xử lý exception

Khi `target` thực sự triển khai interface khai báo `method`, handler có thể dùng:

~~~java
try {
    return method.invoke(target, args);
} catch (InvocationTargetException e) {
    throw e.getCause();
}
~~~

Đây là **đoạn trích bên trong handler**, không phải class biên dịch độc lập. Reflection yêu cầu receiver tương thích và quyền truy cập hợp lệ; truyền sai receiver/đối số có thể gây `IllegalArgumentException`, truy cập không được phép có thể gây `IllegalAccessException`. Nếu bản thân target ném lỗi, `Method.invoke` bọc lỗi trong `InvocationTargetException`. Handler thường nên ném lại `getCause()` để giữ exception gốc.

Mặc dù `InvocationHandler.invoke` khai báo `throws Throwable`, lời gọi **qua proxy** phải tuân thủ hợp đồng kiểu trả về và `throws` của phương thức interface:

| Handler thực hiện | Kết quả ở phía caller |
| --- | --- |
| Trả `Integer(7)` khi method trả `int` | Proxy unbox thành `int 7` |
| Trả `null` cho phương thức trả primitive | `NullPointerException` |
| Trả một object sai kiểu trả về | `ClassCastException` |
| Ném `RuntimeException` hoặc `Error` | Ngoại lệ/lỗi đi ra bình thường |
| Ném checked exception được chữ ký method cho phép | Truyền ra như khai báo |
| Ném checked exception **không được khai báo** ở method interface | Proxy ném `UndeclaredThrowableException` bọc ngoại lệ đó |

Đây là lý do không nên để `InvocationTargetException` lọt ra trực tiếp khi bạn muốn caller thấy checked exception mà method đã khai báo. Với nhiều interface có chữ ký trùng nhau, checked exception có thể cần tương thích với **tất cả** chữ ký tương ứng, không chỉ một `Method.getExceptionTypes()`.

## 4. Trường hợp đặc biệt của Method và proxy

### 4.1. `equals`, `hashCode`, `toString`

Ba phương thức public không final từ `Object` này được JDK proxy chuyển tới handler. Với chúng, `method.getDeclaringClass() == Object.class`, kể cả khi interface redeclare chữ ký tương ứng. `wait()`/`notify()` không nằm trong nhóm xử lý đặc biệt này.

Bạn phải chọn chính sách nhất quán. Ví dụ dùng `proxy == args[0]` cho `equals`, `System.identityHashCode(proxy)` cho `hashCode` và chuỗi cố định cho `toString`. Nếu định nghĩa equality theo đối tượng đích hay khóa nghiệp vụ, cả `equals` và `hashCode` phải tuân thủ cùng nguyên tắc.

### 4.2. Default method của interface

Lời gọi vào `default method` của interface **vẫn tới handler**. Với Java 16+, `InvocationHandler.invokeDefault(proxy, method, args)` gọi phần thân default method hợp lệ trên **proxy**, như lời gọi `Interface.super.method(...)`. Đối số có thể null khi không có tham số.

Ngược lại, `method.invoke(target, args)` chạy trên target theo dispatch bình thường. Nếu target đã override default method, phần override có thể được chọn. Hai cách này khác receiver và có thể cho kết quả khác nhau. `invokeDefault` chỉ nhận `Method` tương ứng với default method còn hợp lệ trong hệ interface của proxy; không dùng được cho bất kỳ method thường nào.

### 4.3. Method trùng chữ ký, overload và metadata generic

Với overload `work(String)` và `work(int)`, so thêm `method.getParameterTypes()`; overload không được phân biệt bằng nội dung `args` đơn thuần, nhất là khi giá trị là null. Với nhiều interface chứa cùng chữ ký, thứ tự interface lúc tạo proxy ảnh hưởng `Method` đưa tới handler. Với generic, `Method` giữ thông tin khai báo trong phạm vi metadata còn lưu; nó không tự thay biến kiểu qua toàn bộ cây kế thừa thành kiểu cụ thể của target.

Nếu logic cần annotation của method được implement ở target, phải chủ động tra cứu method tương ứng trên class target và xử lý bridge/override khi cần. Annotation trên interface method không tự được “chuyển” vào method triển khai.

## 5. Bảng kiểm nhanh cho args

| Ví dụ gọi method | Giá trị `args` | Lưu ý |
| --- | --- | --- |
| `ping()` | `null` | Không tự giả định mảng rỗng |
| `send(null)` | `[null]` | Mảng dài 1, phần tử null |
| `add(2,5)` | `[Integer(2),Integer(5)]` | Primitive đã boxing |
| `join("a","b")` với `String...` | Mảng dài 1, phần tử là `String[]` | Không trải phẳng mảng varargs |
| `send((String)null)` | `[null]` | Overload phải phân biệt bằng kiểu Method |
| `record(secret)` | Có thể chứa dữ liệu nhạy cảm | Không log toàn bộ token/password |

Khi chuyển `args` cho `method.invoke(target, args)`, phải giữ đúng **số lượng và cấu trúc tham số**. Truyền riêng `args[0]` cho method cần nhiều đối số, hoặc bọc thêm mảng ở sai tầng, sẽ làm thay đổi cách reflection nhận tham số; Java varargs ở đây không cho phép tự ý trải phẳng mảng.

## 6. Các lỗi phổ biến và cách tự kiểm tra

- **Đệ quy không kết thúc:** gọi `method.invoke(proxy, args)` trong handler. Dùng target tương thích hoặc xử lý đặc biệt `invokeDefault` khi muốn thực thi default body.
- **NPE do args:** truy cập `args.length` với method không tham số. Luôn kiểm tra null trước.
- **Nhầm mảng varargs:** xem `join("a","b")` là hai phần tử `args`. Thực tế chỉ có một phần tử kiểu `String[]`.
- **Nhầm metadata:** coi `method.getDeclaringClass()` là class của target hoặc tin annotation interface sẽ tự bao gồm annotation triển khai.
- **Sai kiểu trả về:** trả `null`/object không tương thích cho primitive hoặc reference return type.
- **Sai checked exception:** bỏ qua `InvocationTargetException.getCause()`, hoặc ném checked exception ngoài `throws` của interface.
- **Log gây side effect:** ép `toString()` trên proxy argument, hoặc ghi mật khẩu/token trong `args`.

Tự trả lời: (1) `proxy` khác `target` thế nào? (2) tại sao `ping()` cho `args == null` nhưng `send(null)` không? (3) tại sao `method.invoke(proxy, args)` có nguy cơ đệ quy? (4) vì sao `method.getDeclaringClass()` có thể là `Object.class`? (5) khi nào phải dùng `InvocationHandler.invokeDefault`? (6) phản xạ và proxy lần lượt bọc exception ra sao?

### Tài liệu chính thức

- Java SE 21 `InvocationHandler`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/InvocationHandler.html
- Java SE 21 `Proxy`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Proxy.html
- Java SE 21 `Method`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html
- Java SE 21 `UndeclaredThrowableException`: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/UndeclaredThrowableException.html