# Overload và chữ ký cần dùng để tìm phương thức bằng Java Reflection

## 1. Vấn đề: một tên có thể chỉ nhiều phương thức

Trong Java, **method overloading (nạp chồng phương thức)** cho phép nhiều phương thức có cùng tên trong một lớp nếu **danh sách kiểu tham số khác nhau**. Khác nhau có thể ở số lượng, kiểu hoặc thứ tự tham số.

```java
class Example {
    void send(String text) { }
    void send(int number) { }
    void send(String text, int times) { }
    void send(int times, String text) { }
}
```

Đây là bốn phương thức khác nhau. Cả bốn cùng tên `send` nhưng có các danh sách kiểu tham số lần lượt là:

- `(String)`
- `(int)`
- `(String, int)`
- `(int, String)`

Với Reflection, **chỉ biết tên `send` là chưa đủ** để xác định một overload. Ta cần chính xác tên phương thức và **danh sách `Class<?>[]` mô tả kiểu tham số đã khai báo, đúng thứ tự**.

Khái niệm **method signature** trong Java Language Specification (§8.4.2) chủ yếu gồm tên phương thức và các tham số kiểu theo quy tắc ngôn ngữ; **kiểu trả về không dùng để overload**. Khi nói tới *khóa tra cứu* của `Class.getMethod`/`getDeclaredMethod`, điều cần truyền trực tiếp là **tên** và **`Class<?>...` của các tham số sau erasure**.

## 2. Tra cứu phương thức bằng API nào?

Hai lời gọi phổ biến:

```java
Class<?> type = Example.class;

// Tìm method public, kể cả method public được kế thừa.
java.lang.reflect.Method method1 =
        type.getMethod("send", String.class, int.class);

// Tìm method khai báo trực tiếp trong Example, không phụ thuộc modifier.
java.lang.reflect.Method method2 =
        type.getDeclaredMethod("send", String.class, int.class);
```

| API | Phạm vi | Cần truyền | Nếu không tìm thấy |
| --- | --- | --- | --- |
| `getMethod(String name, Class<?>... parameterTypes)` | Phương thức `public` trên lớp, interface liên quan và phương thức `public` kế thừa theo quy tắc API | Tên và danh sách kiểu tham số chính xác | `NoSuchMethodException` |
| `getDeclaredMethod(String name, Class<?>... parameterTypes)` | Phương thức khai báo trực tiếp trong lớp/interface đang xét, gồm `private`, `protected`, package-private và `public` | Tên và danh sách kiểu tham số chính xác | `NoSuchMethodException` |
| `getMethods()` | Mảng các `Method` `public` trong phạm vi tìm kiếm của API | Không nhận tên/chữ ký | Mảng có thể rỗng |
| `getDeclaredMethods()` | Mảng phương thức khai báo trực tiếp, không lọc modifier | Không nhận tên/chữ ký | Mảng có thể rỗng |

**Ví dụ:** Với `void send(String, int)`, tra cứu `getDeclaredMethod("send", String.class, int.class)` sẽ khớp; đảo thứ tự thành `(int.class, String.class)` là overload khác. Java **không tìm phương thức “gần giống nhất”** nếu danh sách `Class` không khớp.

Phương thức **không có tham số** được tra cứu bằng `getMethod("ping")` hoặc `getMethod("ping", new Class<?>[0])`. Không tự thêm `Object.class` để thay thế danh sách rỗng.

### `getMethod` khác `getDeclaredMethod` cả ở phạm vi kế thừa

Nếu `Child extends Parent` và chỉ `Parent` khai báo `public void action(Number value)`:

- `Child.class.getMethod("action", Number.class)` tìm được phương thức `public` kế thừa.
- `Child.class.getDeclaredMethod("action", Number.class)` ném `NoSuchMethodException` nếu `Child` không tự khai báo hoặc override phương thức đó.
- Nếu một overload là `private`, `getMethod` sẽ không tìm thấy overload đó, dù tên/phần tham số đúng. `getDeclaredMethod` trên **lớp khai báo** có thể tìm ra metadata của nó.

## 3. Tra cứu dùng kiểu khai báo chính xác: không tự đổi kiểu

Giả sử lớp có:

```java
void calculate(int value) { }
void calculate(Integer value) { }
void calculate(Number value) { }
void calculate(Object value) { }
```

Các tham số `int`, `Integer`, `Number` và `Object` là bốn chữ ký khác nhau.

| Tra cứu | Có khớp overload tương ứng? | Lý do |
| --- | --- | --- |
| `getDeclaredMethod("calculate", int.class)` | Có | Kiểu khai báo `int` |
| `getDeclaredMethod("calculate", Integer.class)` | Có | Kiểu khai báo `Integer` |
| `getDeclaredMethod("calculate", Number.class)` | Có | Kiểu khai báo `Number` |
| `getDeclaredMethod("calculate", Object.class)` | Có | Kiểu khai báo `Object` |
| `getDeclaredMethod("calculate", short.class)` | Không | Không có overload `short`; không widening thành `int` |
| `getDeclaredMethod("calculate", Long.class)` | Không | Không có overload `Long`; không tự chọn `Number` |
| `getDeclaredMethod("calculate", String.class)` | Không | Không có overload `String`; không tự chọn `Object` |

Ở **bước tìm Method**, Reflection không áp dụng boxing/unboxing, widening primitive, chọn superclass/interface có thể gán được hay thuật toán overload resolution của trình biên dịch Java. Nói cách khác, `int.class != Integer.class`, và `String.class != Object.class`.

Ở **bước gọi Method đã tìm được** qua `Method.invoke`, cơ chế kiểm tra/chuyển đổi đối số lại khác. Ví dụ: đối tượng `Method` đại diện cho overload `calculate(int)` có thể nhận `Integer.valueOf(5)` rồi unbox khi gọi. Tuy nhiên, nó **vẫn gọi chính overload `(int)`**, không chuyển sang `(Integer)`.

## 4. Ví dụ hoàn chỉnh Java 17+: overload, kế thừa, varargs và generic

Lưu toàn bộ chương trình dưới tên `MethodOverloadLookupDemo.java`:

```java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;

public class MethodOverloadLookupDemo {
    static class Base {
        public String inherited(Number number) {
            return "Base:" + number;
        }
    }

    static class Handler extends Base {
        public String choose(Object value) {
            return "Object";
        }

        public String choose(String value) {
            return "String";
        }

        public String choose(int value) {
            return "int";
        }

        public String choose(Integer value) {
            return "Integer";
        }

        public String combine(String text, int count) {
            return text.repeat(count);
        }

        public String pack(String... values) {
            return "pack:" + Arrays.toString(values);
        }

        public <T extends Number> String accept(T number) {
            return "accept:" + number;
        }

        private String hidden(double value) {
            return "hidden:" + value;
        }
    }

    public static void main(String[] args) throws Exception {
        Handler handler = new Handler();

        Method objectVersion =
                Handler.class.getMethod("choose", Object.class);
        Method stringVersion =
                Handler.class.getMethod("choose", String.class);
        Method intVersion =
                Handler.class.getMethod("choose", int.class);
        Method integerVersion =
                Handler.class.getMethod("choose", Integer.class);

        System.out.println("choose(Object) with String: "
                + objectVersion.invoke(handler, "abc"));
        System.out.println("choose(String): "
                + stringVersion.invoke(handler, "abc"));
        System.out.println("choose(int): "
                + intVersion.invoke(handler, Integer.valueOf(5)));
        System.out.println("choose(Integer): "
                + integerVersion.invoke(handler, Integer.valueOf(5)));

        Method inherited =
                Handler.class.getMethod("inherited", Number.class);
        System.out.println("inherited owner: "
                + inherited.getDeclaringClass().getSimpleName());

        Method combine =
                Handler.class.getMethod("combine", String.class, int.class);
        System.out.println("combine: " + combine.invoke(handler, "Hi", 2));

        try {
            Handler.class.getMethod("combine", int.class, String.class);
        } catch (NoSuchMethodException e) {
            System.out.println("Wrong order: NoSuchMethodException");
        }

        try {
            Handler.class.getMethod("choose", StringBuilder.class);
        } catch (NoSuchMethodException e) {
            System.out.println("choose(StringBuilder): NoSuchMethodException");
        }

        try {
            Handler.class.getMethod("choose", short.class);
        } catch (NoSuchMethodException e) {
            System.out.println("choose(short): NoSuchMethodException");
        }

        Method varargs = Handler.class.getMethod("pack", String[].class);
        System.out.println("pack parameter: "
                + varargs.getParameterTypes()[0].getTypeName());
        System.out.println("pack varargs: " + varargs.isVarArgs());
        System.out.println("pack invoke: "
                + varargs.invoke(handler, (Object) new String[] {"a", "b"}));

        Method generic =
                Handler.class.getMethod("accept", Number.class);
        System.out.println("generic erased type: "
                + generic.getParameterTypes()[0].getTypeName());
        System.out.println("generic metadata: "
                + generic.getGenericParameterTypes()[0].getTypeName());

        try {
            Handler.class.getMethod("accept", Integer.class);
        } catch (NoSuchMethodException e) {
            System.out.println("accept(Integer): NoSuchMethodException");
        }

        Method hidden =
                Handler.class.getDeclaredMethod("hidden", double.class);
        System.out.println("hidden private: "
                + Modifier.isPrivate(hidden.getModifiers()));
    }
}
```

Biên dịch/chạy từ thư mục chứa tệp với JDK 17 trở lên:

```bash
javac MethodOverloadLookupDemo.java
java MethodOverloadLookupDemo
```

Stdout:

```text
choose(Object) with String: Object
choose(String): String
choose(int): int
choose(Integer): Integer
inherited owner: Base
combine: HiHi
Wrong order: NoSuchMethodException
choose(StringBuilder): NoSuchMethodException
choose(short): NoSuchMethodException
pack parameter: java.lang.String[]
pack varargs: true
pack invoke: pack:[a, b]
generic erased type: java.lang.Number
generic metadata: T
accept(Integer): NoSuchMethodException
hidden private: true
```

Ý nghĩa từng phần:

1. `getMethod("choose", Object.class)` và `getMethod("choose", String.class)` lấy **hai đối tượng Method cho hai overload khác nhau**. Cùng truyền chuỗi `"abc"` lúc `invoke`, kết quả vẫn lần lượt là `Object` và `String`. **Không có chọn lại overload theo kiểu runtime của đối số**.
2. `int.class` và `Integer.class` tạo hai chữ ký độc lập. `Integer.valueOf(5)` có thể được unbox khi invoke overload `(int)`, nhưng không làm bước tra cứu nhập hai chữ ký thành một.
3. `getMethod("inherited", Number.class)` tìm phương thức công khai của `Base`; `getDeclaringClass()` xác định lớp **khai báo**.
4. Đảo `(String.class, int.class)` thành `(int.class, String.class)` gây `NoSuchMethodException` vì thứ tự tham số là một phần khóa tra cứu.
5. `StringBuilder.class` không được tự chuyển lên `Object.class`; `short.class` cũng không được tự chuyển sang `int.class`.
6. Varargs `String...` được lưu dưới dạng tham số mảng `String[]`, nên tìm bằng `String[].class`.
7. Generic `<T extends Number>` được **type erasure** thành `Number` trong kiểu tham số runtime. `getGenericParameterTypes()` vẫn có thể cung cấp thông tin biến kiểu `T`.
8. `getDeclaredMethod` cho phép tìm metadata của `private hidden(double)` trực tiếp, không có nghĩa mọi caller đều tự động được phép gọi phương thức `private`.

## 5. Varargs: biểu diễn trong chữ ký là kiểu mảng

Phương thức:

```java
public void log(String... messages) { }
```

về danh sách kiểu tham số trên `Method` tương đương khai báo `log(String[] messages)`. Hai cách khai báo không thể dùng làm hai overload riêng biệt trong một lớp.

```java
// Trong ngữ cảnh lớp có method public void log(String... messages).
Method logMethod = Example.class.getMethod("log", String[].class);
boolean isVarargs = logMethod.isVarArgs(); // true
```

Không tra bằng `getMethod("log", String.class)` chỉ vì lời gọi Java `log("a")` hợp lệ. Cũng không tra bằng `getMethod("log", String.class, String.class)` chỉ vì có thể gọi `log("a", "b")`. Tại bước Reflection lookup, số tham số của method varargs này vẫn là **một**.

Khi dùng `Method.invoke(Object receiver, Object... args)` trong Java, đối số cuối là varargs **của chính API invoke**. Muốn truyền một mảng `String[]` thành **một tham số** của target method, dùng:

```java
logMethod.invoke(instance, (Object) new String[] {"a", "b"});
```

Đoạn trên là mã minh họa trong ngữ cảnh đã có `logMethod` và `instance`. Cast `(Object)` khiến Java không trải mảng làm danh sách đối số của `Method.invoke`. Bản thân `Method.invoke` không tự đóng gói các chuỗi rời thành mảng cho target method varargs.

## 6. Generic: tra cứu dựa trên kiểu **sau erasure**

Ví dụ:

```java
public <T extends Number> void process(T value) { }
```

Đối với Reflection:

```java
// Ví dụ nằm trong phạm vi lớp có phương thức process như trên.
Method method = Example.class.getMethod("process", Number.class);
System.out.println(method.getParameterTypes()[0]); // class java.lang.Number
```

`T` có bound là `Number` nên kiểu tham số sau erasure là `Number`. Nếu `T` không có bound thì erasure thường là `Object` (có quy tắc riêng khi nhiều bound). Truyền `Integer.class` **không** thay thế `Number.class` để tra cứu phương thức generic đó.

Tương tự, tham số `List<String>` và `List<Integer>` đều có raw type runtime là `java.util.List`. Khi tra cứu:

```java
// Ví dụ nằm trong ngữ cảnh lớp có phương thức:
// public void consume(java.util.List<String> values) { ... }
Method method = Example.class.getMethod("consume", java.util.List.class);
```

Trong cùng một lớp, **không thể overload** chỉ dựa trên `List<String>` so với `List<Integer>`, vì hai khai báo xung đột do cùng erasure. `getGenericParameterTypes()` và `getTypeParameters()` có thể giúp khám phá metadata generic sau khi tra cứu được `Method`, nhưng tham số truyền vào `getMethod` vẫn là `Class<?>...`, không phải `ParameterizedType`.

## 7. Kiểu trả về có giúp chọn overload không?

Không. Hai khai báo trong **cùng một lớp Java** như sau không hợp lệ:

```java
// MINH HỌA MÃ KHÔNG BIÊN DỊCH ĐƯỢC: chỉ khác return type.
int parse(String source) { return 1; }
long parse(String source) { return 2L; }
```

Mỗi method trên cùng tên và cùng tham số `(String)`; kiểu trả về `int` hay `long` không tạo overload hợp lệ. Vì vậy không có API `getMethod(name, returnType, parameterTypes)`.

Cần phân biệt với phương thức tổng hợp (*synthetic*), phương thức cầu nối (*bridge method*) và quy tắc covariant return: compiler/JVM có thể lưu nhiều method có **cùng tên và cùng parameter types** nhưng **khác return type** trong bytecode. Khi đó, `Class.getMethod`/`getDeclaredMethod` áp dụng quy tắc lựa chọn của API (ưu tiên kiểu trả về đặc thù hơn khi các kiểu cho phép so sánh; một số trường hợp còn phụ thuộc quy tắc của API), chứ không nhận return type từ người gọi. Nếu đang kiểm tra bytecode tạo tự động, có thể duyệt `getDeclaredMethods()`, rồi xem `isBridge()`, `isSynthetic()`, `getReturnType()` và `getDeclaringClass()` để phân biệt các `Method`.

Trong lập trình ứng dụng thông thường, nên xác định đúng **tên + danh sách kiểu tham số** trước; chỉ kiểm tra kiểu trả về và metadata sau khi có đối tượng `Method`.

## 8. Tra cứu overload động: vì sao không thể chỉ dùng `arg.getClass()`?

Một lỗi phổ biến:

```java
// Mã minh họa có chủ đích: không phải bộ phân giải overload tổng quát.
Object arg = Integer.valueOf(7);
Method selected = Handler.class.getMethod("choose", arg.getClass());
```

Lệnh trên chọn `choose(Integer)` nếu có. Nhưng nếu API cần gọi `choose(int)`, `arg.getClass()` trả `Integer.class` nên **không tìm đúng chữ ký**. Với `arg == null` thì `arg.getClass()` còn gây `NullPointerException`. Nếu lớp chỉ có `choose(Number)`, `getMethod("choose", Integer.class)` vẫn thất bại mặc dù một `Integer` có thể gán cho tham số `Number` khi gọi.

Khi cần gọi một method có chữ ký đã được thiết kế, cách đúng và đơn giản nhất là lấy thông tin chữ ký từ **hợp đồng API**:

```java
// Ví dụ ngắn; Handler và instance xuất hiện trong chương trình đầy đủ ở trên.
Method method = Handler.class.getMethod("choose", int.class);
Object result = method.invoke(instance, Integer.valueOf(7));
```

Đoạn này không độc lập; `instance` là đối tượng `Handler` đã tạo và caller cần xử lý checked exceptions. `invoke` chạy đúng overload `(int)`; đối số `Integer` có thể được unbox tại bước gọi.

Nếu thật sự cần **lựa chọn overload từ dữ liệu runtime chưa biết trước chữ ký**, phải định nghĩa riêng chiến lược: thu thập các candidate theo tên/số lượng tham số; đánh giá assignability, boxing/unboxing, primitive widening, null, varargs và mức độ đặc hiệu; phát hiện trường hợp mơ hồ. Đó là **bài toán resolution riêng**, không phải tính năng của `getMethod`. Ưu tiên tránh tự mô phỏng overload resolution của `javac` nếu có thể xác định chữ ký từ interface hoặc giao ước từ trước.

## 9. Quy trình truy vấn Method an toàn trong dự án

1. **Xác định tên và danh sách kiểu khai báo** từ interface, tài liệu, annotation, schema hoặc contract; đừng phỏng đoán từ một tập đối số runtime.
2. **Chọn phạm vi tìm kiếm:** `getMethod` cho `public` kể cả kế thừa; `getDeclaredMethod` cho member khai báo trực tiếp, gồm không công khai.
3. **Truyền chính xác từng `Class` theo thứ tự:** primitive dùng `int.class`, wrapper dùng `Integer.class`, array dùng `String[].class`, generic dùng erasure như `List.class`.
4. **Kiểm tra metadata nhận được** bằng `getParameterTypes()`, `getDeclaringClass()`, `getReturnType()`, `isVarArgs()`, `isBridge()` khi cần.
5. **Tách giai đoạn gọi thực thi:** `Method.invoke` còn kiểm tra receiver/đối số/quyền truy cập; checked exception hoặc exception bọc nguyên nhân target xảy ra ở bước này.

Ví dụ logic để đối chiếu signature sau khi liệt kê:

```java
// Mã minh họa trong phương thức đã import java.lang.reflect.Method và java.util.Arrays.
Class<?>[] expected = {String.class, int.class};
for (Method method : Handler.class.getDeclaredMethods()) {
    if (method.getName().equals("combine")
            && java.util.Arrays.equals(method.getParameterTypes(), expected)) {
        System.out.println(method.getName()); // combine
    }
}
```

Lưu ý: `getDeclaredMethods()` **không đảm bảo thứ tự**, và mảng có thể chứa bridge/synthetic method. Không chọn `methods[0]` theo giả định overload đầu tiên là overload cần dùng.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân chính | Cách sửa |
| --- | --- | --- |
| `NoSuchMethodException: choose(java.lang.Integer)` dù có `choose(int)` | Tra cứu dùng wrapper thay primitive | Dùng `int.class` |
| Có `choose(Object)` nhưng tra `choose(StringBuilder)` thất bại | Lookup yêu cầu đúng kiểu khai báo | Dùng `Object.class` nếu đó là chữ ký contract |
| Có `combine(String,int)` nhưng không tìm được | Đảo thứ tự `Class` | Giữ đúng `String.class, int.class` |
| Có `log(String...)` nhưng tra bằng `String.class` | Varargs khai báo thành `String[]` | Dùng `String[].class` |
| Có `accept(T extends Number)` nhưng tra bằng `Integer.class` | Sau erasure, `T` là `Number` | Dùng `Number.class` |
| `getDeclaredMethod` không thấy phương thức `public` của cha | Phương thức không được khai báo trực tiếp trên lớp con | Dùng `getMethod` hoặc chuyển sang lớp khai báo |
| `getMethod` không thấy phương thức `private` | API chỉ tra `public` | Dùng `getDeclaredMethod` đúng lớp, rồi kiểm tra quyền |
| `Method.invoke` lỗi `IllegalArgumentException` | Sai receiver, số lượng hoặc kiểu đối số khi gọi | Kiểm tra `getParameterTypes()` và cách truyền varargs |
| `Method.invoke` ném `InvocationTargetException` | Chính target method ném exception khi chạy | Xem `getCause()` để biết lỗi do phương thức đích |
| Kết quả overload khác lời gọi Java thông thường | `invoke` dùng Method đã chọn, không chọn lại theo argument runtime | Chọn đúng chữ ký trước khi gọi |

## 11. Tự kiểm tra

**Câu 1:** Lớp khai báo `void send(int count)` và `void send(Integer count)`. Hai lời gọi `getDeclaredMethod("send", int.class)` và `getDeclaredMethod("send", Integer.class)` có trả cùng một overload không?

**Đáp án:** Không. Đây là hai đối tượng `Method` cho hai khai báo có chữ ký tham số khác nhau.

**Câu 2:** Lớp có `void send(String[] values)`. Có thể tra bằng `getMethod("send", String.class, String.class)` để gọi với hai chuỗi không?

**Đáp án:** Không. Kiểu tham số đã khai báo là `String[]`, phải dùng `String[].class`. `send(String[])` có thể tương ứng với cú pháp Java `String...` nếu khai báo varargs.

**Câu 3:** Lớp có `void test(Number value)`. `getMethod("test", Integer.class)` có tìm thấy chỉ vì `Integer extends Number` không?

**Đáp án:** Không. Phải truyền `Number.class` để tra cứu chính xác.

**Câu 4:** Một phương thức `public` khai báo ở superclass có thể tìm qua `Child.class.getMethod(...)` không?

**Đáp án:** Có, khi phương thức đó thuộc tập member công khai được kế thừa/tra cứu theo quy tắc của `getMethod`. `getDeclaredMethod` trên con chỉ thấy phương thức con khai báo trực tiếp.

**Ghi nhớ:** Khi dùng Reflection tìm overload, truyền **đúng tên + đúng số lượng, thứ tự, kiểu `Class` của các tham số đã khai báo**. Kiểu trả về không dùng chọn overload, Java conversions không diễn ra trong bước lookup, và `Method.invoke` chỉ thực thi phương thức đã được chọn.

Tài liệu tham khảo: [Java SE 17 `Class.getMethod` / `getDeclaredMethod`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html), [Java SE 17 `Method`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html), [JLS §8.4.2 — Method Signature](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.2).