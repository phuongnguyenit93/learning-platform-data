# Kiểm thử tra cứu primitive, wrapper, overload và generic erasure bằng Java Reflection

## 1. Mục tiêu: kiểm chứng hành vi thật thay vì suy đoán cách Reflection chọn method

Khi dùng `Class.getMethod(...)` hoặc `Class.getDeclaredMethod(...)`, lỗi thường đến từ việc nhầm quy tắc **tra cứu method theo chữ ký** với quy tắc **gọi method trong Java**. Java compiler có thể chọn overload nhờ autoboxing, unboxing, primitive widening và tham chiếu kiểu kế thừa; còn `getMethod(name, parameterTypes)` đòi hỏi danh sách kiểu tham số **khớp đúng** chữ ký đã khai báo. Reflection không tự tìm “overload gần đúng nhất”.

Phạm vi bài kiểm thử:

1. Phân biệt `int.class` và `Integer.class` khi tra cứu.
2. Chứng minh các overload `choose(int)`, `choose(Integer)`, `choose(Number)`, `choose(Object)` là những method độc lập.
3. Kiểm tra `Method.invoke` có thể unbox/widen một số đối số sau khi đã tìm ra method, nhưng không tự chọn overload.
4. Tìm method khai báo `List<String>` bằng `List.class` do **generic erasure**, đồng thời đọc metadata `ParameterizedType` còn lưu trong class file.
5. Nhận ra bridge method do compiler sinh khi override method generic.
6. Viết kiểm thử có assertion, chạy độc lập bằng JDK 17+, output ổn định và báo sai khác ngay lúc chạy.

**Điểm then chốt:** một method **được tìm thấy** hay không là một câu hỏi; một `Method` đã tìm được **nhận đối số nào lúc `invoke`** là câu hỏi khác.

## 2. Phân biệt ba lớp quy tắc

| Tình huống | Java compiler khi gọi trực tiếp | `getMethod(...)` khi tra cứu | `Method.invoke(...)` sau khi có `Method` |
| --- | --- | --- | --- |
| `choose(5)` với nhiều overload | Thực hiện overload resolution tại compile time; `int` thường được ưu tiên nếu khớp chính xác | Phải chỉ rõ `int.class` để tìm `choose(int)` | Nhận boxed `Integer` làm đối số cho tham số `int` qua unboxing |
| `choose(Integer.valueOf(5))` | Ưu tiên overload `Integer` nếu có | Phải chỉ rõ `Integer.class` | Đối số là `Integer` phù hợp với tham số `Integer` |
| `choose(Short.valueOf((short) 5))` | Có thể chọn overload theo quy tắc method invocation applicable/most-specific | Không tự tìm `choose(int)` khi truyền `short.class` | Nếu đã có `choose(int)`, có thể unbox `Short` thành `short` rồi widening thành `int` |
| `accept(new ArrayList<String>())` với tham số `List<String>` | Gọi được vì `ArrayList<String>` implements `List<String>` | Tra cứu theo kiểu **đã khai báo** `List.class`, không phải `ArrayList.class` | Một instance `ArrayList` phù hợp với tham số `List` |
| `accept(List<String>)` | Compiler dùng generic để kiểm tra kiểu phần tử | Kiểu tham số runtime đã xóa: `List.class` | Kiểm tra kiểu đối số runtime, không tự kiểm tra từng phần tử là `String` |

`getMethod`/`getDeclaredMethod` không có khái niệm “chọn method có tham số superclass của kiểu truyền vào”, không làm boxing `int.class` thành `Integer.class` và không chọn overload dựa trên return type.

Lưu ý về `Method.invoke`: đối số cho kiểu nguyên thủy phải là wrapper có thể unbox; API cho phép primitive widening khi hợp lệ, nhưng không cho phép primitive narrowing. `null` không thể chuyển thành primitive. Đối với kiểu tham chiếu, đối tượng phải có kiểu tương thích. `invoke` cũng có thể thất bại do receiver sai, access control, lỗi argument hoặc exception ném từ method đích (được bọc trong `InvocationTargetException`).

## 3. Tra cứu primitive và wrapper: phải chỉ rõ `Class` tương ứng

Giả sử có hai khai báo:

```java
public String choose(int value) { return "int"; }
public String choose(Integer value) { return "Integer"; }
```

Đó là **hai chữ ký khác nhau**, vì `int` là primitive, còn `java.lang.Integer` là reference type. Các mệnh đề sau khác nhau:

- `int.class == Integer.TYPE` là `true`: trường `TYPE` trên wrapper mô tả primitive `int`.
- `int.class == Integer.class` là `false`: `int.class` và `Integer.class` là hai đối tượng `Class` cho **hai kiểu khác nhau**.
- `type.getMethod("choose", int.class)` tìm method tham số primitive `int`.
- `type.getMethod("choose", Integer.class)` tìm method tham số wrapper `Integer`.
- `type.getMethod("choose", Long.class)` ném `NoSuchMethodException` nếu không có overload chính xác `Long`, ngay cả khi class có method `choose(Number)` hoặc `choose(Object)`.

`Class.forName("int")` **không** tương đương `int.class`: tên `"int"` không phải tên binary của một class bình thường mà `Class.forName` tìm được. Với primitive, dùng literal `int.class` hoặc `Integer.TYPE`.

Không gọi `getClass()` trên một biến primitive: `int` không phải object. Nếu nó được autobox thành `Integer` trước khi gọi `getClass()`, kết quả phản ánh wrapper `Integer.class`, không phải `int.class`.

## 4. Overload: lookup chính xác khác áp dụng quy tắc ép kiểu

Cho các overload cùng tên:

```java
public String choose(int value) { return "int"; }
public String choose(Integer value) { return "Integer"; }
public String choose(Number value) { return "Number"; }
public String choose(Object value) { return "Object"; }
```

Các biểu thức `type.getMethod("choose", int.class)`, `getMethod("choose", Integer.class)`, `getMethod("choose", Number.class)` và `getMethod("choose", Object.class)` đều hợp lệ, trả **bốn đối tượng `Method` mô tả bốn khai báo khác nhau**.

Ngược lại, `getMethod("choose", Short.class)` và `getMethod("choose", short.class)` đều ném `NoSuchMethodException` nếu không có đúng hai chữ ký này. Reflection không suy luận chọn `Number` hay `int` theo sự phù hợp của `Short`.

Một khi đã lưu `Method chooseInt = type.getMethod("choose", int.class)`, `chooseInt.invoke(target, Integer.valueOf(5))` có thể trả `"int"` vì đối số boxed được unbox; điều này **không có nghĩa** `getMethod("choose", Integer.class)` trả `choose(int)`. Tương tự, `Short.valueOf((short) 5)` có thể unbox thành `short` rồi widening sang `int` khi `invoke`. Nhưng `chooseInt.invoke(target, Long.valueOf(5))` không hạ `long` về `int`: lời gọi không hợp lệ.

Thêm các tình huống nên kiểm thử:

- `null` được phép cho tham số tham chiếu như `Integer` (nếu method chấp nhận), nhưng không cho tham số primitive `int`.
- Khi `Method.invoke` gọi phương thức instance, cần receiver hợp lệ; với phương thức static, receiver không cần là instance.
- Với varargs, đối số truyền vào `invoke` ở mức reflection phải khớp tham số mảng đã biên dịch; đừng cho rằng nó luôn đóng gói các varargs như cú pháp lời gọi Java thông thường.
- Nếu method đích ném exception, `invoke` bọc nó trong `InvocationTargetException`; khác với `NoSuchMethodException` xảy ra khi tìm chữ ký.

## 5. Generic erasure: tra cứu theo kiểu tham số đã xóa

Xét khai báo:

```java
public int accept(java.util.List<String> values) {
    return values.size();
}
```

`List<String>` chỉ hỗ trợ kiểm tra generic tại compile time. Ở runtime, kiểu tham số method đã erasure thành `java.util.List`; vì vậy:

- `Sample.class.getMethod("accept", List.class)` — **tìm thấy**.
- `Sample.class.getMethod("accept", ArrayList.class)` — **không tìm thấy**: tham số method khai báo là `List`, không phải `ArrayList`, mặc dù có thể gọi method bằng instance `ArrayList`.
- `method.getParameterTypes()[0] == List.class` — `true`: API này trả `Class<?>` kiểu đã xóa.
- `method.getGenericParameterTypes()[0]` có thể là `ParameterizedType` mô tả `List<String>` nếu class file có `Signature` metadata đúng.
- Khi `method.invoke(target, new ArrayList<String>())`, Reflection kiểm tra tham số raw/runtime `List`; nó không quan sát riêng đối số generic `String` của từng instance.

**Không được nhầm:** “type erasure” **không** đồng nghĩa mọi metadata generic bị loại khỏi `.class`. Generic `Signature` của **khai báo** có thể được compiler lưu và Reflection đọc qua `getGenericParameterTypes()`, `getGenericReturnType()` hoặc `getGenericSuperclass()`. Metadata có thể thiếu hoặc hỏng sau khi xử lý bytecode, do đó công cụ không nên mặc định mọi file `.class` luôn chứa signature đầy đủ.

Hai overload chỉ khác đối số generic như `accept(List<String>)` và `accept(List<Integer>)` **không thể cùng khai báo trong một class** vì chữ ký sau erasure trùng `accept(List)`: compiler báo name clash.

## 6. Bridge method: lưu ý khi đếm và lựa chọn method

Một trường hợp tinh tế của generic erasure xuất hiện khi override:

```java
class Parent<T> {
    public T echo(T value) { return value; }
}

class Child extends Parent<String> {
    @Override
    public String echo(String value) { return value.toUpperCase(); }
}
```

Ở `Parent`, method `echo(T)` có tham số erased `Object`. Ở `Child`, method do người viết khai báo nhận `String`. Để bảo đảm lời gọi đa hình trên một tham chiếu `Parent` sau erasure vẫn đi đến `Child.echo(String)`, compiler Java thông thường sinh **bridge method** nhận `Object` rồi chuyển sang method nhận `String`.

Vì vậy khi duyệt `Child.class.getDeclaredMethods()`, có thể gặp cả:

- Method `echo(String)` do tác giả khai báo: `isBridge() == false`.
- Method `echo(Object)` do compiler sinh: `isBridge() == true` và thường `isSynthetic() == true`.

Bridge method là phương thức thực trong bytecode, có thể được Reflection liệt kê hoặc tìm theo tham số erased. Công cụ annotation/dispatcher cần quyết định có bỏ qua bridge/synthetic để tránh xử lý trùng hay cần mapping bridge về method gốc; không nên mặc định số method phản chiếu bằng số method lập trình viên nhìn thấy trong file `.java`.

Bridge còn xuất hiện trong các trường hợp override có return type hiệp biến hoặc sau khi xóa generic theo quy tắc tương thích nhị phân. Việc xác định cụ thể method nào được sinh phụ thuộc cấu trúc kế thừa và compiler; hãy kiểm tra bằng `javap -p -v` nếu thiết kế công cụ chuyên sâu.

## 7. Chương trình kiểm thử Java 17+ độc lập, có assertion

Tạo tệp `ReflectionLookupTests.java`. Các kiểm thử dùng `check(label, condition)`; nếu sai, chương trình ném `AssertionError` và kết thúc bất thường, không phụ thuộc cờ JVM `-ea`.

```java
import java.lang.reflect.Method;
import java.lang.reflect.ParameterizedType;
import java.lang.reflect.Type;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class ReflectionLookupTests {
    public static class Sample {
        public String choose(int value) { return "int"; }
        public String choose(Integer value) { return "Integer"; }
        public String choose(Number value) { return "Number"; }
        public String choose(Object value) { return "Object"; }

        public int accept(List<String> values) {
            return values.size();
        }
    }

    public static class Parent<T> {
        public T echo(T value) { return value; }
    }

    public static class Child extends Parent<String> {
        @Override
        public String echo(String value) {
            return value.toUpperCase(Locale.ROOT);
        }
    }

    static void check(String label, boolean condition) {
        if (!condition) {
            throw new AssertionError(label);
        }
        System.out.println("PASS " + label);
    }

    static boolean lookupMissing(Class<?> type, String name,
            Class<?> parameter) {
        try {
            type.getMethod(name, parameter);
            return false;
        } catch (NoSuchMethodException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        Class<Sample> type = Sample.class;
        Sample target = new Sample();

        Method primitive = type.getMethod("choose", int.class);
        Method wrapper = type.getMethod("choose", Integer.class);
        Method number = type.getMethod("choose", Number.class);
        Method object = type.getMethod("choose", Object.class);

        check("primitive != wrapper", int.class != Integer.class);
        check("Integer.TYPE == int.class", Integer.TYPE == int.class);
        check("four exact signatures",
                primitive.getParameterTypes()[0] == int.class
                && wrapper.getParameterTypes()[0] == Integer.class
                && number.getParameterTypes()[0] == Number.class
                && object.getParameterTypes()[0] == Object.class);

        check("missing Long overload",
                lookupMissing(type, "choose", Long.class));
        check("missing short overload",
                lookupMissing(type, "choose", short.class));

        check("invoke unboxes Integer",
                "int".equals(primitive.invoke(target, Integer.valueOf(7))));
        check("invoke widens short to int",
                "int".equals(primitive.invoke(target,
                        Short.valueOf((short) 7))));
        check("invoke wrapper exact",
                "Integer".equals(wrapper.invoke(target, Integer.valueOf(7))));
        check("invoke Number accepts Integer",
                "Number".equals(number.invoke(target, Integer.valueOf(7))));

        boolean narrowingRejected = false;
        try {
            primitive.invoke(target, Long.valueOf(7L));
        } catch (IllegalArgumentException expected) {
            narrowingRejected = true;
        }
        check("long to int rejected", narrowingRejected);

        Method accept = type.getMethod("accept", List.class);
        check("List erased parameter",
                accept.getParameterTypes()[0] == List.class);
        check("ArrayList not declared",
                lookupMissing(type, "accept", ArrayList.class));
        check("ArrayList argument accepted",
                Integer.valueOf(2).equals(accept.invoke(target,
                        new ArrayList<>(List.of("a", "b")))));

        Type generic = accept.getGenericParameterTypes()[0];
        check("generic signature retained",
                generic instanceof ParameterizedType
                && ((ParameterizedType) generic)
                        .getActualTypeArguments()[0] == String.class);

        Method declared = Child.class.getDeclaredMethod("echo", String.class);
        Method bridge = Child.class.getDeclaredMethod("echo", Object.class);
        check("source method not bridge", !declared.isBridge());
        check("generated bridge method", bridge.isBridge()
                && bridge.isSynthetic());
        check("bridge dispatch",
                "HELLO".equals(bridge.invoke(new Child(), "hello")));

        boolean primitiveNameMissing = false;
        try {
            Class.forName("int");
        } catch (ClassNotFoundException expected) {
            primitiveNameMissing = true;
        }
        check("Class.forName int not primitive", primitiveNameMissing);
    }
}
```

Lệnh biên dịch và chạy:

```bash
javac -encoding UTF-8 ReflectionLookupTests.java
java ReflectionLookupTests
```

Output chuẩn:

```text
PASS primitive != wrapper
PASS Integer.TYPE == int.class
PASS four exact signatures
PASS missing Long overload
PASS missing short overload
PASS invoke unboxes Integer
PASS invoke widens short to int
PASS invoke wrapper exact
PASS invoke Number accepts Integer
PASS long to int rejected
PASS List erased parameter
PASS ArrayList not declared
PASS ArrayList argument accepted
PASS generic signature retained
PASS source method not bridge
PASS generated bridge method
PASS bridge dispatch
PASS Class.forName int not primitive
```

Chương trình bảo đảm những điểm sau:

- Tên các overload giống nhau nhưng `Method.getParameterTypes()` cho thấy **chữ ký riêng**; không có autoboxing ở bước `getMethod`.
- Nhánh `lookupMissing(...)` xác minh trực tiếp `NoSuchMethodException` thay vì coi “không tìm thấy” là lỗi không mong đợi.
- Các phép `invoke` minh họa rõ **unboxing + primitive widening** so với primitive narrowing bị từ chối.
- Khi truyền `ArrayList<String>` vào method khai báo `List<String>`, invocation thành công do `ArrayList` phù hợp với raw `List` runtime, nhưng lookup bằng `ArrayList.class` vẫn thất bại.
- `getGenericParameterTypes()` đọc khai báo `List<String>` đã được `javac` giữ trong `Signature`. Bước này kiểm tra metadata thực tế của class file biên dịch bởi bài thử; không phải một đảm bảo cho mọi bytecode bên ngoài.
- `Child` có bridge method theo kết quả biên dịch Java 17; invocation qua bridge gọi bản override và trả `HELLO`.
- `Class.forName("int")` xác nhận literal primitive phải lấy bằng `int.class` hoặc `Integer.TYPE`.

**Nếu kiểm thử báo FAIL hoặc ném exception**, xem vị trí đầu tiên để phân biệt lookup failure, invocation conversion, metadata generic và compiler bridge. Không sửa assertion chỉ để biến kiểm thử thành PASS.

## 8. Thiết kế test matrix cho công cụ sử dụng Reflection

Khi xây mapper, serializer, DI container, RPC dispatcher hoặc test framework, nên kiểm tra một **ma trận** thay vì chỉ vài “happy path”:

| Nhóm | Ca thử | Kết quả dự kiến |
| --- | --- | --- |
| Primitive lookup | `getMethod("choose", int.class)` | Tìm đúng `choose(int)` |
| Wrapper lookup | `getMethod("choose", Integer.class)` | Tìm đúng `choose(Integer)` |
| Missing overload | `getMethod("choose", Long.class)` | `NoSuchMethodException`, dù có `choose(Number)` |
| Widening invocation | Gọi `choose(int)` với `Short` | Có thể unbox rồi widen `short → int` |
| Narrowing invocation | Gọi `choose(int)` với `Long` | `IllegalArgumentException` |
| Reference invocation | Gọi `choose(Number)` với `Integer` | Hợp lệ vì tham chiếu kiểu con có thể gán cho `Number` |
| Generic erased lookup | Tìm `accept(List<String>)` qua `List.class` | Tìm được `accept(List)` |
| Generic concrete lookup | Tìm `accept(ArrayList.class)` | Không có chữ ký chính xác, thất bại |
| Generic signature | `getGenericParameterTypes()` | Có thể cho `List<String>` khi `Signature` được giữ |
| Bridge method | `getDeclaredMethods()` trên subclass override generic | Có thể thấy method bridge/synthetic |
| Inherited public | `getMethod` so với `getDeclaredMethod` | `getMethod` có thể tìm inherited public; `getDeclaredMethod` chỉ tìm method khai báo trực tiếp |
| Access control | Tìm private method bằng `getDeclaredMethod` | Có thể thấy metadata, nhưng invoke còn chịu access/module rules |
| Negative path | Tên sai, tham số null, sai receiver, checked target exception | Kiểm tra đúng ngoại lệ ở **giai đoạn** phù hợp |

Với test dựa vào Reflection, nên tách rõ ba loại assertion:

1. **Lookup contract:** phương thức được định vị theo tên và danh sách kiểu tham số chính xác; thiếu chữ ký gây `NoSuchMethodException`.
2. **Invocation contract:** receiver và actual arguments tương thích với declared parameter types; method đích hoạt động/đẩy exception như mong đợi.
3. **Metadata contract:** generic `Type`, annotation, bridge/synthetic flags còn tồn tại trong class file đang dùng; những thông tin ấy có thể bị thay đổi bởi compiler hoặc công cụ xử lý bytecode.

Nếu kiểm tra bytecode do framework tạo động hoặc proxy class, đừng áp kỳ vọng giống hệt `javac` với các method sinh ra tự động: hãy quan sát cấu trúc bytecode thật và chọn quy tắc phù hợp.

## 9. Những bẫy phổ biến khi kiểm thử

### Dựa vào `getDeclaredMethods()` để chọn overload “đầu tiên”

Thứ tự các method trả về từ `getDeclaredMethods()`/`getMethods()` **không được bảo đảm ổn định** theo mã nguồn. Không dùng `methods[0]` để suy ra overload ưu tiên, cũng không dùng thứ tự reflection thay thế overload resolution của compiler. Hãy lọc theo tên, exact parameter types, visibility và chính sách chọn rõ ràng.

### Dùng `getMethod` rồi tưởng nó tự gọi method

`getMethod` chỉ trả `Method`; không thực thi body. Khi gọi `invoke`, có thể gặp `IllegalAccessException` hoặc `InvocationTargetException`; với method static, receiver có thể là `null`, nhưng với method instance cần object thích hợp. Hãy test riêng “lookup đúng” và “gọi đúng”.

### So sánh kiểu wrapper với primitive bằng tên đơn giản

`int.class.getSimpleName()` là `"int"`, `Integer.class.getSimpleName()` là `"Integer"`; dùng chuỗi để suy luận convertibility là cách dễ vỡ. Nên dùng `Class<?>` và bảng chuyển đổi primitive rõ ràng nếu framework thật sự cần chọn overload động.

### Nhầm method signature với kiểu thực của đối số

`List.class` là declared parameter class sau erasure của `accept(List<String>)`. Việc truyền `new ArrayList<>()` vào `invoke` là câu chuyện compatibility runtime; không làm chữ ký method đổi thành `ArrayList`.

### Suy luận generic từ object

`new ArrayList<String>().getClass()` không mang đối số `String` của riêng instance. `Field.getGenericType()` hoặc `Method.getGenericParameterTypes()` mô tả **khai báo** được lưu trong class file; `TypeToken` hoặc explicit schema/token phù hợp hơn khi API phải nhận type argument tại runtime.

### Bỏ qua bridge/synthetic

Nếu framework lặp qua `getDeclaredMethods()` để tự động đăng ký handler, bridge method có thể khiến đăng ký trùng. Dùng `isBridge()`/`isSynthetic()` khi cần, nhưng cũng phải nhớ bridge có chức năng dispatch thật nên không nên xóa bừa khỏi những công cụ phân tích runtime.

### Kết luận “Java reflection hỏng” từ `NoSuchMethodException`

Trước khi kết luận lỗi API, hãy in có kiểm soát danh sách `method.getParameterTypes()`, `method.isBridge()`, `getDeclaringClass()` và kiểm tra `getMethod` (public, có kế thừa) so với `getDeclaredMethod` (khai báo trực tiếp, cả private). Đặc biệt phân biệt `int.class` với `Integer.class` và `List.class` với `ArrayList.class`.

## 10. Bài tập tự kiểm tra

**Câu 1.** Class chỉ có `run(int)`. `getMethod("run", Integer.class)` có thành công vì autoboxing không?

**Đáp án:** Không. Lookup đòi chữ ký chính xác `int.class`; autoboxing/unboxing thuộc giai đoạn chuyển đổi đối số khi gọi, không áp dụng cho tìm method.

**Câu 2.** Đã có `Method` cho `run(int)`. Truyền `Short.valueOf((short) 3)` qua `invoke` có được không?

**Đáp án:** Có thể: unboxing `Short → short` rồi primitive widening `short → int`. Truyền `Long` vào tham số `int` không hợp lệ vì cần narrowing.

**Câu 3.** Vì sao `getMethod("accept", List.class)` đúng cho `accept(List<String>)`, trong khi `getMethod("accept", ArrayList.class)` sai?

**Đáp án:** Chữ ký sau erasure là `accept(List)`. `ArrayList` là kiểu implementation có thể dùng làm actual argument, không phải kiểu tham số đã khai báo.

**Câu 4.** Trong cùng class có thể overload `process(List<String>)` và `process(List<Integer>)` không?

**Đáp án:** Không. Cả hai erasure thành `process(List)`, gây name clash.

**Câu 5.** `getGenericParameterTypes()` nói `List<String>` có chứng minh một instance `ArrayList` hiện có chỉ chứa `String` không?

**Đáp án:** Không. Nó mô tả metadata của khai báo method; generic erasure không bảo đảm kiểm tra phần tử collection theo `String` tại runtime.

**Câu 6.** Vì sao subclass override `echo(String)` có thể xuất hiện thêm `echo(Object)` khi xem method bằng reflection?

**Đáp án:** Compiler sinh bridge để duy trì dispatch đa hình của method generic sau erasure. Dùng `isBridge()` và `isSynthetic()` để nhận diện.

**Câu 7.** Nếu framework cần chọn overload theo actual argument ở runtime, chỉ gọi `getMethod(name, arg.getClass())` đã đủ chưa?

**Đáp án:** Chưa. Primitive, `null`, subtype/interface, boxing/unboxing, widening, varargs và độ ưu tiên giữa các overload cần một thuật toán chọn method được thiết kế rõ; Java Reflection API `getMethod` không làm toàn bộ overload resolution thay cho framework.

**Kết luận:** Hãy test thành ba lớp **tra cứu chữ ký chính xác → gọi với chuyển đổi đối số phù hợp → kiểm tra generic/bridge metadata**. Primitive và wrapper là hai kiểu khác nhau, overload không được Reflection tự lựa chọn, còn generic erasure quyết định chữ ký runtime dù class file vẫn có thể chứa metadata generic phục vụ introspection.