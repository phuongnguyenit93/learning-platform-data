# Phương thức cầu nối khi kế thừa và ghi đè kiểu generic

## 1. Phương thức cầu nối giải quyết vấn đề gì?

Phương thức cầu nối (bridge method) là phương thức do trình biên dịch sinh để giữ đúng hành vi ghi đè sau khi xóa kiểu. Nó nhận lời gọi theo dạng kiểu mà lớp cha hoặc interface yêu cầu, rồi chuyển tiếp đến phương thức thực sự do lập trình viên viết.

Điểm xuất phát là sự khác nhau giữa:

- **Hợp đồng ở mã nguồn:** lớp con có thể kế thừa một lớp tổng quát với đối số kiểu cụ thể như `String`.
- **Descriptor trong bytecode:** biến kiểu của lớp cha có thể bị xóa thành `Object`, trong khi phương thức lớp con vẫn dùng `String`.

Ví dụ rút gọn:

```java
class Holder<T> {
    public void set(T value) {
    }
}

class TextHolder extends Holder<String> {
    @Override
    public void set(String value) {
    }
}
```

Ở mã nguồn, `TextHolder.set(String)` thực sự ghi đè phương thức được kế thừa qua `Holder<String>`. `@Override` được trình biên dịch chấp nhận.

Nhưng khi xem dạng thực thi:

| Nơi khai báo | Phương thức trong mã nguồn | Descriptor |
| --- | --- | --- |
| `Holder<T>` | `set(T)` | `(Ljava/lang/Object;)V` |
| `TextHolder` | `set(String)` | `(Ljava/lang/String;)V` |

Hai descriptor khác nhau. Trình biên dịch sinh thêm một `set(Object)` trong `TextHolder` để nối lời gọi theo hợp đồng đã xóa của lớp cha với `set(String)` do người viết khai báo.

Cơ chế này vẫn áp dụng trên Java hiện đại. Ví dụ hoàn chỉnh trong bài dùng Java 17+ và không cần sử dụng raw type.

## 2. Từ một lời gọi đa hình đến phương thức thật

Giả sử:

```java
Holder<String> holder = new TextHolder();
holder.set("Java");
```

Ở mã nguồn, biến `holder` cho phép truyền `String`. Khi biên dịch lời gọi theo lớp cha, phương thức đích có dạng đã xóa là `Holder.set(Object)`.

Khi chạy, đối tượng thực tế là `TextHolder`. Phương thức cầu nối trong lớp này tiếp nhận lời gọi và chuyển sang bản xử lý `String`.

```text
holder.set("Java") trong mã nguồn
        ↓
Lời gọi theo Holder.set(Object) trong bytecode
        ↓ phân phối động theo đối tượng thực tế
TextHolder.set(Object) do trình biên dịch sinh
        ↓ kiểm tra chuyển Object sang String
TextHolder.set(String) do lập trình viên viết
```

Có thể hình dung thân phương thức cầu nối như sau:

```java
// Mã giả giải thích thân bridge; không thêm vào TextHolder ở trên.
public void set(Object value) {
    set((String) value);
}
```

Phương thức này không chứa một bản sao của toàn bộ nghiệp vụ. Nó chuyển đối số về kiểu cần thiết rồi gọi phương thức thực sự.

Nếu tự thêm đoạn trên vào lớp tổng quát đã có quan hệ ghi đè, ta có thể gây lỗi xung đột tên sau xóa kiểu. Hãy để trình biên dịch sinh bridge và chỉ viết đúng phương thức cần ghi đè.

## 3. Cầu nối có thể thích nghi cả kiểu tham số lẫn kiểu trả về

### 3.1. Tham số: cần kiểm tra kiểu trước khi chuyển tiếp

Với `set(T)` và lớp con chốt `T = String`, bridge nhận `Object`, chuyển sang `String`, rồi gọi `set(String)`.

Đây là lý do một stack trace có thể trỏ tới `set` dù phương thức mà ta tự viết không có phép cast. Cast nằm trong phương thức do trình biên dịch sinh.

Theo cách sử dụng có kiểm tra kiểu thông thường, một `Holder<String>` không cho phép `set(123)`, nên giá trị sai kiểu bị chặn trước khi chạy. Nếu cơ chế động như reflection đưa một `Integer` vào bridge `set(Object)`, cast sang `String` thất bại với `ClassCastException`.

### 3.2. Kết quả: giữ descriptor trả về mà lớp cha yêu cầu

Xét lớp cha có:

```java
public T get() {
    return value;
}
```

và lớp con chốt kiểu `String`, khai báo:

```java
@Override
public String get() {
    return super.get();
}
```

Dạng đã xóa của phương thức cha trả `Object`, còn phương thức lớp con trả `String`. Trong trường hợp này, trình biên dịch có thể sinh bridge:

```text
get():Object → gọi get():String → trả kết quả như Object
```

Không cần cast đầu vào vì không có tham số. Kết quả `String` dùng được như `Object`, nên bridge chỉ cần chuyển tiếp kết quả.

Ở cấp mã nguồn Java, không thể khai báo hai phương thức chỉ khác nhau về kiểu trả về. Ở cấp class file, descriptor của phương thức có bao gồm kiểu trả về; vì vậy có thể thấy cả `get():String` và `get():Object` trong lớp đã biên dịch.

Không nên viết hai phiên bản ấy bằng tay để mô phỏng class file.

## 4. Chương trình hoàn chỉnh: setter và getter đều có bridge

Lưu thành `BridgeDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;
import java.util.stream.Collectors;

public class BridgeDemo {
    static class Holder<T> {
        private T value;

        Holder(T value) {
            this.value = value;
        }

        public void set(T value) {
            this.value = value;
        }

        public T get() {
            return value;
        }
    }

    static class TextHolder extends Holder<String> {
        TextHolder(String value) {
            super(value);
        }

        @Override
        public void set(String value) {
            super.set(value.trim());
        }

        @Override
        public String get() {
            return super.get();
        }
    }

    private static String describe(Method method) {
        String parameters = Arrays.stream(method.getParameterTypes())
                .map(Class::getSimpleName)
                .collect(Collectors.joining(", "));

        return method.getName() + "(" + parameters + ") -> "
                + method.getReturnType().getSimpleName()
                + ", bridge=" + method.isBridge()
                + ", synthetic=" + method.isSynthetic();
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        TextHolder actual = new TextHolder("start");
        Holder<String> holder = actual;

        holder.set("  Java  ");
        System.out.println("value = " + holder.get());

        Arrays.stream(TextHolder.class.getDeclaredMethods())
                .filter(Method::isBridge)
                .sorted(Comparator.comparing(Method::getName))
                .map(BridgeDemo::describe)
                .forEach(System.out::println);

        Method bridgeSetter =
                TextHolder.class.getDeclaredMethod("set", Object.class);

        try {
            bridgeSetter.invoke(actual, 123);
        } catch (InvocationTargetException failure) {
            System.out.println("wrong input = "
                    + failure.getCause().getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```shell
javac --release 17 -Xlint:all BridgeDemo.java
java BridgeDemo
```

Stdout chính xác khi biên dịch ví dụ bằng `javac`:

```text
value = Java
get() -> Object, bridge=true, synthetic=true
set(Object) -> void, bridge=true, synthetic=true
wrong input = ClassCastException
```

Ý nghĩa từng phần:

- `value = Java` chứng minh lời gọi qua biến lớp cha vẫn đến `TextHolder.set(String)`, nơi xử lý `trim()`.
- `get()` trả `Object` và `set(Object)` là hai bridge do trình biên dịch sinh; chúng không nằm trong mã nguồn của lớp con.
- Các bridge trong ví dụ được đánh dấu synthetic, nghĩa là thành viên được sinh trong quá trình biên dịch.
- Lời gọi reflection cố ý đưa sai kiểu vào phương thức có tham số thực thi là `Object`. Phép cast bên trong bridge làm phát sinh `ClassCastException`.
- `Method.invoke` bọc ngoại lệ do phương thức đích ném trong `InvocationTargetException`; chương trình in tên lớp của nguyên nhân bằng `getCause()`.

Phần reflection gây lỗi là thí nghiệm chẩn đoán. Trong mã sử dụng bình thường, hãy gọi qua hợp đồng `Holder<String>`, để trình biên dịch chặn dữ liệu không hợp lệ.

Danh sách phương thức được sắp xếp trước khi in vì reflection không cam kết thứ tự khai báo từ `getDeclaredMethods()`. Trong ví dụ, mỗi tên `get` và `set` chỉ có một bridge, nên sắp theo tên đủ để output ổn định.

## 5. Kiểm chứng trong bytecode bằng javap

Sau khi biên dịch, chạy:

```shell
javap -p -s 'BridgeDemo$Holder'
javap -p -c -v 'BridgeDemo$TextHolder'
javap -p -c BridgeDemo
```

Nháy đơn giữ nguyên ký tự `$` khi dùng PowerShell hoặc shell có mở rộng biến. Với Windows Command Prompt, dùng nháy kép quanh tên lớp thay thế.

Trong lớp cha, tìm:

```text
set: (Ljava/lang/Object;)V
get: ()Ljava/lang/Object;
```

Đây là cách ghi rút gọn các cặp tên–descriptor cần tìm, không phải toàn bộ stdout của `javap`.

Trong lớp con, có bốn phương thức liên quan:

| Phương thức trong class file | Nguồn gốc | Vai trò |
| --- | --- | --- |
| `set(String):void` | Người viết khai báo | Chuẩn hóa chuỗi rồi lưu |
| `get():String` | Người viết khai báo | Đọc giá trị theo hợp đồng `String` |
| `set(Object):void` | Trình biên dịch sinh | Chuyển đối số sang `String`, gọi setter thật |
| `get():Object` | Trình biên dịch sinh | Gọi getter thật và trả kết quả theo hợp đồng cha |

Với `-v`, hai phương thức được sinh có cờ `ACC_BRIDGE` và `ACC_SYNTHETIC`.

Luồng lệnh quan trọng của setter bridge:

```text
aload_0
aload_1
checkcast java/lang/String
invokevirtual TextHolder.set:(Ljava/lang/String;)V
return
```

Luồng lệnh quan trọng của getter bridge:

```text
aload_0
invokevirtual TextHolder.get:()Ljava/lang/String;
areturn
```

Hai khối trên đã bỏ offset, số hiệu constant pool và rút gọn tên lớp để tập trung vào cơ chế. Trong output thực, lớp lồng nhau có tên nhị phân `BridgeDemo$TextHolder`.

Trong bytecode của `BridgeDemo.main`, tìm lời gọi `Holder.set:(Ljava/lang/Object;)V`. Dù đối số ở mã nguồn là chuỗi và đối tượng thực tế là `TextHolder`, lời gọi vẫn được tạo theo hợp đồng đã xóa của kiểu lớp cha. Phân phối động đưa nó đến bridge thích hợp ở lớp con.

Cũng cần phân biệt hai cast có thể xuất hiện:

- Cast trong `TextHolder.set(Object)` thích nghi **đầu vào của phương thức ghi đè**.
- Cast tại nơi gọi `Holder.get()`, nếu cần `String`, thích nghi **kết quả đọc từ phương thức đã xóa kiểu**.

Chúng phục vụ các vị trí khác nhau; không phải mọi `checkcast` trong chương trình đều nằm trong bridge.

## 6. Quan hệ với implements và kiểu trả về hiệp biến

### 6.1. Cài đặt interface tổng quát cũng có thể cần bridge

```java
interface Converter<T> {
    T convert(T value);
}

class UpperCaseConverter implements Converter<String> {
    @Override
    public String convert(String value) {
        return value.toUpperCase(java.util.Locale.ROOT);
    }
}
```

Đây là đoạn độc lập minh họa quan hệ khai báo, không có `main`.

Hợp đồng của `Converter<T>` sau xóa kiểu là `convert(Object):Object`. Phương thức người viết cung cấp trong `UpperCaseConverter` là `convert(String):String`. Bridge thích nghi cả tham số lẫn kết quả để lời gọi thông qua `Converter<String>` vẫn dùng đúng cách cài đặt.

Cơ chế không chỉ dành cho từ khóa `extends`; vấn đề nằm ở việc giữ quan hệ ghi đè hoặc cài đặt phương thức qua dạng kiểu đã xóa.

### 6.2. Không phải mọi bridge đều do một lớp tổng quát trực tiếp gây ra

Java cho phép ghi đè với kiểu trả về hiệp biến (covariant return): phương thức lớp con có thể trả một kiểu con của kiểu trả về lớp cha.

```java
class Parent {
    public Object create() {
        return "parent";
    }
}

class Child extends Parent {
    @Override
    public String create() {
        return "child";
    }
}
```

`javac` cũng có thể sinh bridge cho `create():Object` để chuyển tiếp đến `create():String`, dù hai lớp này không khai báo tham số kiểu.

Ví dụ này giúp nhận diện đúng phạm vi của thuật ngữ: bridge phục vụ việc thích nghi phương thức ở cấp class file; xóa kiểu trong generics là một nguyên nhân quan trọng, nhưng không phải nguyên nhân duy nhất.

## 7. Những điều bridge không làm

### 7.1. Không tự sửa một phương thức ghi đè sai

```java
class WrongTextHolder extends Holder<String> {
    WrongTextHolder() {
        super("");
    }

    // @Override // Nếu bật annotation này, trình biên dịch báo lỗi.
    public void set(Integer value) {
    }
}
```

Trong ngữ cảnh các lớp của ví dụ chính, `set(Integer)` không ghi đè `set(String)` mà `WrongTextHolder` kế thừa từ `Holder<String>`. Đây là một phương thức khác. Bridge không biến một kiểu tham số tùy ý thành phương thức ghi đè hợp lệ.

Hãy dùng `@Override` cho phương thức dự định ghi đè; annotation giúp phát hiện sai sót ở mã nguồn. Nó không phải một nút bật việc sinh bridge.

### 7.2. Không được sinh chỉ vì “có generics”

Nếu lớp con giữ nguyên `T` và ghi đè một phương thức có cùng dạng đã xóa:

```java
class ForwardingHolder<T> extends Holder<T> {
    ForwardingHolder(T value) {
        super(value);
    }

    @Override
    public void set(T value) {
        super.set(value);
    }
}
```

thì phương thức setter của lớp cha và lớp con đều có descriptor `set(Object):void` khi `T` không có cận khác. Với trường hợp này, không cần một bridge bổ sung chỉ để chuyển từ `Object` sang một kiểu cụ thể.

Tương tự, lớp con chỉ kế thừa phương thức mà không khai báo ghi đè không nhất thiết có thêm bridge trong chính lớp đó. Đừng dự đoán số bridge chỉ từ số dấu `<...>` trong mã nguồn.

### 7.3. Không phải cơ chế nạp chồng thông thường

Ở mã nguồn, `set(String)` trong `TextHolder` là ghi đè sau khi áp dụng đối số kiểu `String` cho lớp cha. Phương thức `set(Object)` xuất hiện thêm là sản phẩm biên dịch.

Đừng giải thích kết quả đa hình chỉ bằng quy tắc chọn overload tại thời điểm biên dịch. Cần tách việc chọn phương thức theo kiểu tĩnh của biểu thức khỏi việc phân phối động theo đối tượng khi chạy.

### 7.4. Không phải mọi thành viên synthetic đều là bridge

`isSynthetic()` cho biết thành viên được sinh; `isBridge()` nhận diện riêng phương thức cầu nối. Một công cụ liệt kê thành viên không nên xem mọi phương thức synthetic là bridge.

Nếu viết công cụ tạo tài liệu hoặc kiểm tra phương thức, có thể dùng `isBridge()` để nhận diện bản thích nghi và tìm phương thức khai báo tương ứng. Không nên xóa bỏ chúng khỏi mọi phân tích một cách máy móc: chúng vẫn là những phương thức thực trong class file và có thể tham gia lời gọi, reflection hoặc stack trace.

## 8. Cách đọc một lỗi liên quan đến bridge

Khi stack trace hoặc reflection hiển thị một phương thức mà mã nguồn không có:

1. Xác định lớp cha/interface và đối số kiểu mà lớp con sử dụng.
2. Tìm phương thức dự định ghi đè, kiểm tra `@Override`.
3. Tính dạng xóa của phương thức cha và descriptor phương thức lớp con.
4. Dùng `javap -p -c -v` hoặc `Method.isBridge()` xác nhận phương thức được sinh.
5. Nếu có lỗi chuyển kiểu, lần theo giá trị đã vào bridge bằng đường nào; phân biệt ngoại lệ thật với lớp bọc của reflection.

Không nên sửa bằng cách thêm một overload `Object` hoặc bỏ generics. Trước hết hãy khôi phục cách truyền dữ liệu đúng với hợp đồng kiểu của phương thức.

## Tài liệu đối chiếu

- [Oracle — Effects of Type Erasure and Bridge Methods](https://docs.oracle.com/javase/tutorial/java/generics/bridgeMethods.html): cơ chế chuyển tiếp sau xóa kiểu.
- [JLS §8.4.8.3 — Requirements in Overriding and Hiding](https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.8.3): hợp đồng ghi đè và các ràng buộc liên quan.
- [Java Method API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/reflect/Method.html): `isBridge()`, `isSynthetic()` và cách reflection biểu diễn phương thức.
