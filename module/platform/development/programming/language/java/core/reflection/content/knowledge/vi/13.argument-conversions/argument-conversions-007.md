# Varargs của phương thức đích được biểu diễn bằng một tham số mảng

## 1. Ý chính: `String...` là một tham số `String[]` ở runtime

Trong mã nguồn Java, khai báo **varargs** cho phép người gọi truyền số lượng đối số biến đổi ở vị trí cuối:

~~~java
void send(String channel, String... messages) {
    // messages có kiểu String[]
}
~~~

Trình biên dịch cho phép:

~~~java
send("news");
send("news", "A");
send("news", "A", "B");
send("news", new String[]{"A", "B"});
~~~

Đây là các đoạn minh họa bên trong lớp có phương thức `send`, chưa phải chương trình độc lập. Trong những lời gọi sử dụng số phần tử biến đổi, compiler **đóng gói phần cuối thành một mảng `String[]`** để truyền tới phương thức đích.

Tại runtime, chữ ký đã khai báo của `send` chỉ có **hai tham số**:

1. `String channel`.
2. `String[] messages`.

Varargs là **cú pháp hỗ trợ tại vị trí gọi trong mã Java**; nó không có nghĩa phương thức đích thực sự có bất kỳ số lượng tham số runtime nào. JVM dùng kiểu mảng ở cuối chữ ký và metadata đánh dấu phương thức nhận varargs.

**Đặc biệt với Reflection:** `Method.invoke` **không tự gom các đối số rời thành mảng cuối của phương thức đích**. Khi gọi qua Reflection, bạn phải chuẩn bị mảng cuối cùng đúng kiểu và đúng vị trí.

## 2. `getMethod` tìm chữ ký mảng, không tìm các phần tử rời

Cho phương thức public:

~~~java
public void send(String channel, String... messages) { }
~~~

Tra cứu:

~~~java
Method m = Messenger.class.getMethod(
        "send", String.class, String[].class);
~~~

Đây là đoạn minh họa, cần có lớp `Messenger`, import `java.lang.reflect.Method` và xử lý checked exception.

Không dùng:

~~~java
// Sai: tìm ba tham số String riêng biệt, không tồn tại.
Messenger.class.getMethod(
        "send", String.class, String.class, String.class);
~~~

Một phương thức khai báo `send(String, String...)` có đúng dạng tham số runtime `(String, String[])`. Vì vậy:

| Phép tra cứu | Kết quả |
| --- | --- |
| `getMethod("send", String.class, String[].class)` | Tìm thấy phương thức khai báo varargs. |
| `getMethod("send", String.class)` | Không tìm thấy overload này nếu lớp chỉ khai báo `(String, String[])`. |
| `getMethod("send", String.class, String.class)` | Không khớp vì tham số thứ hai yêu cầu `String[]`. |
| `getMethod("send", String.class, String.class, String.class)` | Không khớp vì số tham số không đúng. |

`getMethod` yêu cầu **kiểu tham số khai báo chính xác**; nó không làm overload resolution như trình biên dịch, không tự mở rộng hay gom varargs. Tra sai chữ ký dẫn tới `NoSuchMethodException`, chứ chưa tới bước `invoke`.

### Kiểm tra metadata bằng Reflection

~~~java
Method method = Messenger.class.getMethod(
        "send", String.class, String[].class);

System.out.println(method.isVarArgs());           // true
System.out.println(method.getParameterCount());   // 2
System.out.println(method.getParameterTypes()[1].isArray()); // true
System.out.println(method.getParameterTypes()[1].getComponentType()); // class java.lang.String
~~~

`isVarArgs()` cho biết phương thức **được khai báo** nhận số đối số biến đổi. `getParameterTypes()` vẫn trả mảng các **kiểu tham số hình thức**, và kiểu cuối là `String[].class`.

Nếu một phương thức khai báo `send(String, String[])` (viết mảng trực tiếp) thay vì `send(String, String...)`, chữ ký kiểu runtime vẫn là `(String, String[])` nhưng `isVarArgs()` sẽ trả `false`. Không thể khai báo cả hai dạng này như hai overload khác nhau trong cùng lớp, vì chúng có cùng chữ ký sau khi biên dịch.

## 3. Hai tầng varargs rất dễ nhầm

Với Reflection, có **hai dấu `...` với hai ý nghĩa khác nhau**:

~~~java
// Phương thức đích:
void send(String channel, String... messages);

// API Reflection:
Object Method.invoke(Object receiver, Object... args);
~~~

Tầng thứ nhất: `messages` là **tham số thứ hai của `send`**, kiểu `String[]`.  
Tầng thứ hai: `args` là **mảng `Object[]` chứa toàn bộ đối số của lời gọi `send`**, ngoại trừ receiver của instance method.

Một lời gọi đúng có cấu trúc:

~~~text
Method.invoke(
    receiver,                               <-- instance gọi method
    new Object[]{
        "news",                              <-- tham số #1: String
        new String[]{"A", "B"}               <-- tham số #2: String[]
    }
)
~~~

Số lượng phần tử của `Object[]` là **2**, không phải 3. Mảng `String[]` có thể chứa 0, 1, 2 hoặc nhiều phần tử, nhưng vẫn là **một phần tử** trong mảng các đối số của Reflection.

Do đó:

~~~java
method.invoke(receiver, "news",
        (Object) new String[]{"A", "B"});

method.invoke(receiver,
        new Object[]{"news", new String[]{"A", "B"}});
~~~

Hai dạng trên đều gọi `send` với đúng hai tham số. Dạng thứ hai chỉ rõ toàn bộ mảng đối số Reflection. Dạng thứ nhất dùng `(Object)` để khẳng định mảng `String[]` là **một đối số** của `Method.invoke`, đặc biệt hữu ích với phương thức đích chỉ có một tham số mảng.

## 4. Chương trình Java 17+ chạy đầy đủ

Tạo file **`ReflectVarargsLesson.java`**:

~~~java
import java.lang.reflect.Method;
import java.util.Arrays;

public class ReflectVarargsLesson {
    public static class Messenger {
        public void send(String channel, String... messages) {
            System.out.println(channel + " -> " + Arrays.toString(messages));
        }

        public void only(String... messages) {
            System.out.println("only -> " + Arrays.toString(messages));
        }

        public static void launch(String... args) {
            System.out.println("launch -> " + Arrays.toString(args));
        }
    }

    public static void main(String[] args) throws Exception {
        Messenger receiver = new Messenger();

        // 1. Java compiler tự đóng gói varargs ở lời gọi trực tiếp.
        receiver.send("direct", "A", "B");

        // 2. Reflection thấy chữ ký gồm String và String[].
        Method method = Messenger.class.getMethod(
                "send", String.class, String[].class);
        System.out.println("isVarArgs=" + method.isVarArgs());
        System.out.println("parameterCount=" + method.getParameterCount());
        System.out.println("second="
                + method.getParameterTypes()[1].getTypeName());
        System.out.println("component="
                + method.getParameterTypes()[1].getComponentType().getTypeName());

        // 3. Hai đối số của phương thức đích: String và String[].
        method.invoke(receiver, "reflect",
                (Object) new String[]{"C", "D"});
        method.invoke(receiver,
                new Object[]{"packed", new String[]{"E", "F"}});

        // 4. Mảng rỗng khác mảng null.
        method.invoke(receiver, "empty", (Object) new String[0]);
        method.invoke(receiver, "null", (Object) null);

        // 5. Reflection không tự gom chuỗi rời thành String[].
        try {
            method.invoke(receiver, "wrong", "G", "H");
        } catch (IllegalArgumentException e) {
            System.out.println("expanded: IllegalArgumentException");
        }

        // 6. Phương thức đích chỉ có một tham số String[].
        Method only = Messenger.class.getMethod("only", String[].class);
        only.invoke(receiver, (Object) new String[]{"x", "y"});

        try {
            // Cố ý trải mảng thành 2 args của Method.invoke.
            only.invoke(receiver, (Object[]) new String[]{"x", "y"});
        } catch (IllegalArgumentException e) {
            System.out.println("array spread: IllegalArgumentException");
        }

        // 7. Method static: receiver là null.
        Method launch = Messenger.class.getMethod(
                "launch", String[].class);
        launch.invoke(null, (Object) new String[]{"one", "two"});
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ReflectVarargsLesson.java
java ReflectVarargsLesson
~~~

Stdout được kiểm chứng:

~~~text
direct -> [A, B]
isVarArgs=true
parameterCount=2
second=java.lang.String[]
component=java.lang.String
reflect -> [C, D]
packed -> [E, F]
empty -> []
null -> null
expanded: IllegalArgumentException
only -> [x, y]
array spread: IllegalArgumentException
launch -> [one, two]
~~~

### Đọc kết quả đúng cách

- `direct` là lời gọi Java bình thường: compiler tự dựng `String[]`.
- `isVarArgs=true` và `parameterCount=2` xác nhận varargs là một tham số mảng trong chữ ký runtime.
- `reflect` và `packed` cho cùng kiểu lời gọi đích dù hai cách chuẩn bị `Object[]` khác nhau.
- `empty` truyền **mảng độ dài 0**; `null` truyền **tham chiếu mảng null**. Phương thức đích nhận hai giá trị khác nhau; ở đây `Arrays.toString(String[])` hiển thị `[]` và `null`.
- `expanded` đưa ba đối số `String` vào lời gọi đích có hai tham số hình thức; `Method.invoke` không tự gộp `"G", "H"` thành mảng.
- `array spread` cố ý đưa một `String[]` làm **Object[] đối số của API Reflection**, tức hai chuỗi rời. Kết quả không khớp phương thức `only(String[])`.
- `launch` chứng minh quy tắc tương tự áp dụng cho phương thức `static`; receiver truyền vào `Method.invoke` là `null`.

## 5. `main(String[])` và các phương thức static varargs

Khai báo:

~~~java
public static void main(String... args) {
    System.out.println(java.util.Arrays.toString(args));
}
~~~

có tham số runtime duy nhất là `String[]`, giống dạng `main(String[])`. Muốn gọi bằng Reflection:

~~~java
Method main = App.class.getMethod("main", String[].class);
main.invoke(null, (Object) new String[]{"first", "second"});
~~~

Đây là ví dụ minh họa trong chương trình có lớp `App` và xử lý ngoại lệ Reflection. Vì phương thức static không cần receiver, `invoke` truyền `null` ở đối số đầu tiên. `(Object)` giữ **toàn bộ `String[]` làm một đối số của phương thức đích**, tránh việc các chuỗi bị diễn giải thành nhiều phần tử của `Object... args`.

Nếu bạn tạo hệ thống chạy plugin, CLI launcher hoặc test runner gọi `main` động, đây là cách truyền args rõ ràng.

## 6. Cách viết tiện ích gọi phương thức varargs động

Nếu đầu vào đến từ mảng giá trị riêng lẻ, **hãy tự dựng mảng cuối theo `componentType`** của tham số varargs. Không phải mọi varargs đều là `String...`; có thể là `int...`, `Number...`, `Object...` hoặc mảng nhiều chiều.

Giả sử đã tìm đúng `Method` có `isVarArgs() == true` và biết `fixedCount = method.getParameterCount() - 1`. Một thuật toán chuẩn bị đối số (mức mô tả) gồm:

1. Xác thực số lượng giá trị đầu vào đủ cho các tham số cố định.
2. Giữ nguyên các đối số tương ứng `parameterTypes[0..fixedCount-1]`, kiểm tra tính tương thích.
3. Lấy kiểu mảng cuối bằng `parameterTypes[fixedCount]`, kiểu phần tử bằng `getComponentType()`.
4. Dùng `java.lang.reflect.Array.newInstance(componentType, extraCount)` để tạo mảng đúng kiểu, gán từng giá trị dư qua `Array.set` nếu chuyển đổi hợp lệ.
5. Xây `Object[] invocationArgs` có đúng `method.getParameterCount()` phần tử, vị trí cuối là mảng vừa tạo.
6. Gọi `method.invoke(receiver, invocationArgs)`.

Ví dụ minh họa khâu đóng gói mảng `String[]`:

~~~java
String[] trailing = new String[]{"alpha", "beta"};
Object[] invocationArgs = new Object[]{"news", trailing};
method.invoke(receiver, invocationArgs);
~~~

Đây là đoạn code trong ngữ cảnh có `method` và `receiver` tương thích; `invocationArgs` có hai phần tử. Với `int...`, mảng cuối phải là `int[]`, **không phải** `Integer[]`. `Array.set` xử lý các phép chuyển đổi thích hợp hoặc báo lỗi khi giá trị không tương thích; ứng dụng cần kiểm tra dữ liệu trước khi gọi.

Với thư viện nhận đầu vào động, phải quy định cả trường hợp đã được cung cấp sẵn mảng cuối: lựa chọn **giữ mảng như một đối số** hay **đóng gói phần tử vào mảng mới** tùy thuộc hợp đồng API. Đừng vừa giữ mảng vừa đóng gói lần nữa vô ý.

## 7. Câu hỏi tự kiểm tra

**Câu 1.** `void log(int level, String... parts)` có bao nhiêu tham số trong `getParameterTypes()`?  
**Hai:** `int.class` và `String[].class`.

**Câu 2.** `logMethod.invoke(receiver, 2, "a", "b")` có tự đóng `"a", "b"` thành một `String[]`?  
**Không.** Phải truyền `logMethod.invoke(receiver, 2, (Object) new String[]{"a", "b"})` hoặc `new Object[]{2, new String[]{"a","b"}}`.

**Câu 3.** Phương thức `void print(String[] values)` (không `...`) có cần một đối số mảng khi gọi qua Reflection?  
**Có.** Cách gọi qua Reflection xét danh sách tham số runtime; mảng vẫn là một tham số. `isVarArgs()` chỉ khác về metadata khai báo.

**Câu 4.** Mã nguồn khai báo `int...` thì `getMethod` truyền `int.class`, `Integer[].class`, hay `int[].class`?  
**`int[].class`**, vì chữ ký có một tham số mảng nguyên thủy.

**Câu 5.** `Method.invoke(receiver, (Object) new String[]{"x", "y"})` truyền bao nhiêu đối số cho phương thức đích?  
**Một**, là toàn bộ mảng `String[]`.

**Câu 6.** Một phương thức static khai báo `String... args`; receiver của `invoke` nên là gì?  
**`null`**; đối số của phương thức đích vẫn là một `String[]`.

**Ghi nhớ:** có **hai lớp varargs**: compiler đóng gói varargs ở lời gọi Java bình thường; còn `Method.invoke(Object, Object...)` chỉ đóng gói các đối số của **chính Reflection API**. Phương thức đích khai báo `T...` vẫn có đúng một tham số `T[]`, và bạn phải truyền mảng đó đúng vị trí.

### Tài liệu chính thức

- [JDK 17 — `Method.invoke`, `getParameterTypes`, `isVarArgs`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [Oracle Java Tutorials — Invoking Methods with a Variable Number of Arguments](https://docs.oracle.com/javase/tutorial/reflect/member/methodInvocation.html)
- [Dev.java — Invoking Methods](https://dev.java/learn/api/reflection-method-handles/reflection/methods/)
- [Java Language Specification §8.4.1 — Formal Parameters](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.1)
- [Java Language Specification §15.12.4.2 — Evaluate Arguments](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.4.2)