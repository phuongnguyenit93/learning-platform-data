# Không nhầm `Method` object với kết quả gọi phương thức trong Java Reflection

## 1. Hai đối tượng khác nhau, hai vai trò khác nhau

Trong Java Reflection, `java.lang.reflect.Method` là **đối tượng mô tả một phương thức**: tên, kiểu trả về khai báo, danh sách kiểu tham số, modifier, annotation, class khai báo phương thức và các đặc tính liên quan. Bạn có thể lấy `Method` từ `Class.getMethod(...)` hoặc `Class.getDeclaredMethod(...)` mà **chưa hề chạy phần thân phương thức**.

Khi muốn thực sự thực thi phương thức mà `Method` mô tả, gọi:

~~~java
Object result = method.invoke(receiver, arguments);
~~~

`Method.invoke(...)` dùng đối tượng `Method` để thực hiện lời gọi, rồi trả về **giá trị mà phương thức đích trả về** dưới dạng `Object`. Nếu phương thức đích trả `void`, giá trị mà `invoke` trả về là `null`. Nếu phương thức đích trả primitive như `int`, Reflection sẽ boxing giá trị thành wrapper như `Integer`. Nếu phương thức đích vốn trả `null`, `invoke` cũng trả `null`.

Cần phân biệt:

| Biểu thức / biến | Nó đại diện cho cái gì? | Có thực thi phương thức đích chưa? |
| --- | --- | --- |
| `Method method = type.getMethod("run");` | Metadata cho phương thức `run()` | Chưa. |
| `method.getName()` | Tên phương thức dưới dạng `String` | Chưa. |
| `method.getReturnType()` | Đối tượng `Class<?>` cho kiểu trả về được khai báo | Chưa. |
| `Object value = method.invoke(target);` | Giá trị trả về từ một lần chạy `run()` | Rồi. |
| `Method another = method;` | Tham chiếu tới cùng đối tượng mô tả phương thức | Chưa chạy thêm lần nào. |

**Điểm mấu chốt:** `method` là **đối tượng công cụ dùng để gọi**; `value` là **kết quả của một lần gọi**. Hai giá trị chỉ có thể cùng kiểu `Method` trong trường hợp đặc biệt là **chính phương thức đích có kiểu trả về `Method`**. Không có quy tắc chung rằng `invoke()` trả về một `Method` khác.

## 2. Ví dụ Java 17+ chạy độc lập

Tạo file `MethodObjectDemo.java`:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public class MethodObjectDemo {
    public static class Counter {
        private int value;

        public Counter(int initial) {
            this.value = initial;
        }

        public int add(int delta) {
            value += delta;
            return value;
        }

        public int current() {
            return value;
        }

        public void reset() {
            value = 0;
        }

        public static String label() {
            return "counter";
        }

        public int fail() {
            throw new IllegalStateException("boom");
        }
    }

    public static void main(String[] args) throws Exception {
        Counter counter = new Counter(10);
        Method add = Counter.class.getMethod("add", int.class);

        System.out.println("method name: " + add.getName());
        System.out.println("return type: " + add.getReturnType().getSimpleName());
        System.out.println("after lookup: " + counter.current());

        Object firstResult = add.invoke(counter, 5);
        System.out.println("result: " + firstResult);
        System.out.println("result type: " + firstResult.getClass().getSimpleName());
        System.out.println("counter value: " + counter.current());

        Method reset = Counter.class.getMethod("reset");
        Object voidResult = reset.invoke(counter);
        System.out.println("void result is null: " + (voidResult == null));
        System.out.println("after reset: " + counter.current());

        Method label = Counter.class.getMethod("label");
        System.out.println("static result: " + label.invoke(null));

        Method fail = Counter.class.getMethod("fail");
        try {
            fail.invoke(counter);
        } catch (InvocationTargetException ex) {
            System.out.println("cause: " + ex.getCause().getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 MethodObjectDemo.java
java MethodObjectDemo
~~~

Stdout đã xác nhận khi biên dịch ở mức Java 17 và chạy trên JDK 24:

~~~text
method name: add
return type: int
after lookup: 10
result: 15
result type: Integer
counter value: 15
void result is null: true
after reset: 0
static result: counter
cause: IllegalStateException
~~~

Giải thích các mốc:

1. `Counter.class.getMethod("add", int.class)` **chỉ tìm Method** cho tên `add` và đúng một tham số kiểu nguyên thủy `int`. Nó không cộng số nào; `counter.current()` vẫn là `10`. `int.class` trong truy vấn là kiểu tham số, không phải dữ liệu truyền vào.
2. `add.getName()` và `add.getReturnType()` đọc **metadata**. Vì phương thức nguồn khai báo `int add(int)`, `getReturnType()` là `int.class`. Chúng không chạy `add`.
3. `add.invoke(counter, 5)` **thực thi** `counter.add(5)`. Biến `firstResult` nhận giá trị `15` được boxing thành `Integer`, nhưng kiểu compile-time của biến vẫn là `Object`. Đồng thời trạng thái `counter.value` thay đổi từ `10` thành `15`.
4. `reset.invoke(counter)` gọi `void reset()`. Trạng thái được đặt về `0`, còn `voidResult` nhận `null`. Không có “đối tượng void” nào được trả ra.
5. `label.invoke(null)` dùng `null` làm receiver vì `label()` là `static`. Kết quả của lời gọi là `String "counter"`.
6. Phương thức `fail()` ném `IllegalStateException`; `Method.invoke()` bọc ngoại lệ phát sinh từ **phần thân method đích** trong `InvocationTargetException`. Gọi `getCause()` để truy ra ngoại lệ thực.

## 3. Ba thời điểm cần nhận diện trong quá trình Reflection

Có thể hình dung đường đi:

~~~text
Class<?> type = Counter.class
          |
          | getMethod("add", int.class)  [tra cứu metadata]
          v
Method add                        [chưa gọi add()]
          |
          | getName()/getReturnType()  [đọc metadata]
          |
          | invoke(counter, 5)       [thực thi add(5)]
          v
Object firstResult                 [Integer(15), kết quả lần gọi]
          |
          | ép kiểu/chuyển kiểu theo contract
          v
int value = (Integer) firstResult  [giá trị int 15]
~~~

Đường đi này không làm `Method` biến thành `Integer`: biến `add` vẫn đại diện cho **cùng metadata phương thức** trước và sau `invoke()`; chỉ có thêm đối tượng giá trị `firstResult` và các tác động phụ từ phương thức nguồn.

Một `Method` có thể được dùng để gọi **nhiều lần**, trên **nhiều instance tương thích**:

~~~java
Method method = Counter.class.getMethod("add", int.class);

Counter a = new Counter(1);
Counter b = new Counter(100);

Object resultA = method.invoke(a, 2); // Integer(3)
Object resultB = method.invoke(b, 2); // Integer(102)
~~~

Đây là đoạn bổ sung sử dụng class `Counter` đã định nghĩa ở phần 2, **không phải file Java độc lập**. Hai kết quả khác nhau vì receiver khác nhau; bản thân `method` không chứa trạng thái `value` của `a` hay `b`.

## 4. Vì sao `invoke()` trả `Object` và cách dùng đúng kiểu?

Chữ ký tổng quát:

~~~java
public Object invoke(Object obj, Object... args)
        throws IllegalAccessException, InvocationTargetException
~~~

- `obj` là **receiver** của một phương thức instance; phải là object có kiểu tương thích với class khai báo method. Với phương thức `static`, receiver bị bỏ qua, thường truyền `null`.
- `args` là các **giá trị tham số khi gọi**, theo đúng thứ tự và số lượng cần thiết. Không nhầm `int.class` (metadata tra cứu) với `5` (đối số thực thi).
- Kiểu khai báo của `Method.invoke()` là `Object` vì nó có thể gọi những phương thức có kiểu trả về rất khác nhau. Giá trị trả về thực được boxing nếu là primitive; với `void` thì `null`.
- Việc ép kiểu phải phù hợp với **giá trị runtime và hợp đồng của method đích**. Một method trả `String` cần ép về `String` nếu muốn dùng API của `String`; method trả `int` thường được nhận qua `Integer` khi invoke.

Ví dụ bổ sung sau dùng `Counter` và `add` trong phần 2:

~~~java
Object raw = add.invoke(counter, 7);
int number = (Integer) raw;
System.out.println(number);
~~~

Chú ý kết quả cuối cùng phụ thuộc giá trị hiện có của `counter` khi chạy đoạn này. Đây là đoạn minh họa **không có stdout cố định** trừ khi biết trạng thái trước đó; nó không phải một file standalone. Việc cast `(Integer)` phù hợp vì `add` trả primitive `int`.

**Phân biệt kiểu khai báo và kiểu của kết quả:**

~~~java
Class<?> declaredReturnType = add.getReturnType(); // int.class
Object actualReturnValue = add.invoke(counter, 1); // boxed Integer, ví dụ 1 lần gọi
Class<?> actualValueType = actualReturnValue.getClass(); // Integer.class
~~~

`declaredReturnType` có kiểu `Class<?>` và mô tả signature; `actualReturnValue` chứa dữ liệu của **một lần chạy**. Nếu method khai báo trả `Number` nhưng runtime trả `Integer`, `getReturnType()` vẫn là `Number.class`. Nếu method trả `null`, không thể gọi `getClass()` trực tiếp trên kết quả.

## 5. Từ metadata tới kết quả: chọn đúng thao tác

| Câu hỏi | API / giá trị cần dùng |
| --- | --- |
| Phương thức nào tồn tại? | `Class.getMethod(name, parameterTypes...)` cho public, kể cả inherited; `getDeclaredMethod(...)` cho khai báo trực tiếp |
| Phương thức trả kiểu gì theo chữ ký? | `method.getReturnType()` trả `Class<?>`; không chạy thân phương thức |
| Muốn thực thi và lấy kết quả? | `Object result = method.invoke(receiver, args...)` |
| Vì sao `result == null`? | Xét `getReturnType() == void.class` hoặc phương thức tham chiếu thực sự trả `null` |

**Tra cứu khác thực thi:** khi tìm overload, dùng chính xác tham số formal như `int.class`, `String[].class`; khi gọi, truyền **giá trị** như `5`, `new String[]{...}`. `invoke` không chọn lại overload. Instance method cần receiver tương thích, static method có thể dùng `null`. Nếu target nhận một mảng, truyền thành **một** đối số, ví dụ `method.invoke(receiver, (Object) names)`.

**Kết quả khác metadata:** với `int add(int)`, `getReturnType()` vẫn là `int.class` nhưng `invoke` trả `Integer`. Với `void reset()`, `invoke` trả `null` dù reset đã thay đổi trạng thái; method tham chiếu cũng có thể trả `null`.

**Lỗi khác kết quả:** không tìm được chữ ký → `NoSuchMethodException`; không được phép gọi → `IllegalAccessException`; receiver/args không hợp lệ → `IllegalArgumentException` hoặc `NullPointerException`; thân method ném lỗi → `InvocationTargetException`, đọc `getCause()`. Không dùng `result == null` để suy ra lời gọi thất bại.

## 6. Các tình huống sử dụng và lỗi thường gặp

**Tình huống 1 — Kiểm tra metadata trước khi gọi.** Framework dùng `getDeclaredMethods()` và `getAnnotation(...)` để tìm những handler thỏa điều kiện. Các object `Method` thu được chỉ là mô tả. Handler chỉ chạy tại thời điểm framework gọi `invoke(...)` (hoặc một cơ chế gọi tương đương).

**Tình huống 2 — Lấy dữ liệu do handler trả ra.** Một method như `String buildName()` sẽ cho kết quả `String` từ `invoke()`. Biến chứa `Method` không phải chuỗi tên được tạo. Muốn xử lý như chuỗi, lấy kết quả gọi, kiểm tra kiểu hoặc ép kiểu phù hợp.

**Tình huống 3 — Method thay đổi trạng thái hoặc thực hiện I/O.** Không thể quyết định phương thức đã hoàn thành công việc chỉ bằng việc lấy `Method`. Phải thực thi nó, xử lý ngoại lệ, và hiểu side effect. Với `void`, kết quả từ Reflection là `null` nhưng side effect vẫn có thể có.

Những sai lầm nên tránh:

1. **“`getMethod()` gọi luôn phương thức.”** Sai: đây chỉ là tra cứu metadata.
2. **“Biến `Method` chính là giá trị method trả về.”** Sai: chỉ `invoke()` chạy method, và phải lưu giá trị trả về riêng nếu cần.
3. **“Kết quả luôn có kiểu `Method`.”** Sai: kết quả tùy chữ ký method đích; API `invoke` khai báo trả `Object`.
4. **“Khi method trả primitive thì `result.getClass()` là `int.class`.”** Sai: nếu giá trị khác `null`, Reflection boxing `int` thành `Integer`.
5. **“`result == null` nghĩa là lời gọi không chạy.”** Sai: method `void` hoặc method reference-returning trả `null` đều cho giá trị `null`.
6. **“Chỉ cần `getReturnType()` là biết giá trị trả về thực tế.”** Sai: đó là **kiểu khai báo**. Chưa chạy method và chưa có kết quả.
7. **“Exception từ method đích sẽ luôn ném thẳng ra ngoài `invoke()`.”** Sai: nó thường được bọc trong `InvocationTargetException`; cần xét `getCause()`.
8. **“Đã lấy được `Method` thì chắc chắn gọi được.”** Sai: caller còn phải đáp ứng các quy tắc visibility, JPMS, receiver và đối số.
9. **“Gọi cùng một `Method` lúc nào cũng ra cùng kết quả.”** Sai: kết quả phụ thuộc receiver, input, trạng thái và side effect tại thời điểm gọi.

## 7. Tự kiểm tra hiểu bài

1. `Method m = Counter.class.getMethod("add", int.class);` có làm thay đổi trạng thái `Counter` không? Tại sao?
2. Với `Counter c = new Counter(7);`, `m.invoke(c, 3)` trả object kiểu runtime nào và giá trị bao nhiêu? Nếu gọi lại `m.invoke(c, 3)` thì kết quả còn giống ban đầu không?
3. Vì sao `reset.invoke(c) == null` không khẳng định `reset()` thất bại?
4. Tại sao `m.getReturnType() == int.class` trong khi `m.invoke(c, 1).getClass() == Integer.class`?
5. Nếu method đích ném `IllegalStateException`, nên quan sát `InvocationTargetException` ở đâu để lấy exception gốc?
6. Khi Reflection gọi một phương thức `static` không có tham số, giá trị truyền làm receiver có thể là gì?

**Ghi nhớ:** `Method` là **đối tượng biểu diễn một phương thức**; `Method.invoke(...)` là **hành động gọi phương thức đó**; kết quả `invoke(...)` là **giá trị trả về của lần gọi**, không phải bản thân `Method`.

## Tài liệu chuẩn

- [Java SE 17 — `java.lang.reflect.Method`, đặc biệt `invoke(...)`, `getReturnType()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [Java SE 17 — `java.lang.Class`, `getMethod(...)` và `getDeclaredMethod(...)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html)
- [Java SE 17 — `InvocationTargetException`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/InvocationTargetException.html)
