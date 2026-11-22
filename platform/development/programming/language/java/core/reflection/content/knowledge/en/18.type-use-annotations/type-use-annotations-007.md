# getAnnotatedReturnType, getAnnotatedExceptionTypes và receiver type trong Java Reflection

Khi học Java Reflection, việc đọc metadata của một phương thức không chỉ dừng ở `getReturnType()` hay `getExceptionTypes()`. Java còn cho phép gắn annotation trực tiếp lên **vị trí sử dụng kiểu** (*type use*), ví dụ annotation trên kiểu trả về, kiểu exception trong mệnh đề `throws`, hoặc kiểu `this` của một instance method.

Ba API quan trọng thuộc `java.lang.reflect.Executable` là:

- `getAnnotatedReturnType()`: đọc **lần sử dụng kiểu trả về** cùng type-use annotations của nó.
- `getAnnotatedExceptionTypes()`: đọc các **lần sử dụng kiểu exception trong `throws`**, giữ thứ tự khai báo và annotation tại từng vị trí.
- `getAnnotatedReceiverType()`: đọc **kiểu receiver** (kiểu của `this` theo quy tắc ngôn ngữ), bao gồm annotation trên *explicit receiver parameter* khi có; kết quả có thể là `null` nếu executable không thể có receiver parameter.

Cả ba đều làm việc với `AnnotatedType` hoặc mảng `AnnotatedType[]`; **không cần gọi phương thức đích** để lấy thông tin. Chúng mô tả metadata ở thời điểm khai báo, **không** tự thi hành kiểm tra nghiệp vụ nào đối với annotation.

## 1. Điều kiện để đọc type-use annotation tại runtime

Annotation nhắm đến vị trí **dùng một kiểu** phải cho phép `ElementType.TYPE_USE`. Để Reflection nhìn thấy tại runtime, cần thêm `RetentionPolicy.RUNTIME`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE_USE)
@Retention(RetentionPolicy.RUNTIME)
@interface Mark {
    String value();
}
```

Đoạn trên là **khai báo minh họa**; chương trình độc lập bên dưới sẽ khai báo annotation `Mark` trong class của chính nó.

`@Target(TYPE_USE)` cho phép các cú pháp như:

```java
public @Mark("result") String read() { return "ok"; }
public void save() throws @Mark("io") java.io.IOException {}
```

Hai dòng chỉ minh họa vị trí type-use, chưa phải chương trình chạy độc lập và method `save` không ném `IOException` mặc dù khai báo `throws`. Java cho phép khai báo một checked exception mà phần thân method không nhất thiết phải ném exception đó.

**Phân biệt:** annotation gắn trên **khai báo method** với `ElementType.METHOD` được đọc bằng `Method.getAnnotation` hoặc `getDeclaredAnnotations()`. Annotation gắn trên **kiểu trả về** cần `getAnnotatedReturnType()`. Tương tự, annotation trên một **khai báo tham số** khác với annotation trên **kiểu của tham số**. Không được suy rằng `Method.getAnnotations()` sẽ trả toàn bộ annotation bên trong generic return type hay mệnh đề `throws`.

## 2. Bức tranh tổng quát về các API của Executable

`Executable` là lớp cha của `Method` và `Constructor`. Nó cung cấp các API về danh sách tham số, ngoại lệ, receiver và annotated types.

| Câu hỏi | API | Kiểu trả về của Reflection |
| --- | --- | --- |
| Phương thức trả kiểu nào sau erasure? | `Method.getReturnType()` | `Class<?>` |
| Kiểu trả về có cấu trúc generic nào? | `Method.getGenericReturnType()` | `Type` |
| Type-use annotations nằm ở đâu trên kiểu trả về? | `Method.getAnnotatedReturnType()` | `AnnotatedType` |
| Có những kiểu exception nào trong `throws`? | `Executable.getExceptionTypes()` | `Class<?>[]` |
| Các exception types có khai báo generic nào? | `Executable.getGenericExceptionTypes()` | `Type[]` |
| Annotation trên từng kiểu exception trong `throws`? | `Executable.getAnnotatedExceptionTypes()` | `AnnotatedType[]` |
| Kiểu receiver có annotation nào? | `Executable.getAnnotatedReceiverType()` | `AnnotatedType` hoặc `null` |
| Type-use annotations trên kiểu của formal parameters? | `Executable.getAnnotatedParameterTypes()` | `AnnotatedType[]` |

Mỗi `AnnotatedType` biểu diễn một **nút trong cây sử dụng kiểu**. Phương thức `getType()` trả về `Type` nền, còn `getAnnotation(SomeAnnotation.class)` đọc annotation nằm **ngay tại nút đó**. Nếu annotation nằm trên type argument hoặc bound sâu hơn, cần đi vào các nút con bằng API chuyên biệt như `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()`.

Đây không phải một trình đánh giá giá trị lúc chạy: `getAnnotatedExceptionTypes()` không chờ method ném exception, và `getAnnotatedReturnType()` không chờ method trả về giá trị.

## 3. getAnnotatedReturnType(): annotation trên kiểu trả về

Giả sử một method khai báo:

```java
public @Mark("result") List<@Mark("element") String> read() {
    return List.of("ok");
}
```

Đây là đoạn minh họa trong ngữ cảnh có `List` và `Mark`.

- `method.getReturnType()` trả `List.class` (generic bị **erasure**).
- `method.getGenericReturnType()` biểu diễn `List<String>` với các tham số generic nhưng chưa cho biết trực tiếp annotation tại từng vị trí.
- `method.getAnnotatedReturnType()` biểu diễn **lần dùng `List<String>`**; trên nút ngoài có `@Mark("result")`.
- Vì kiểu ngoài là parameterized, có thể dùng `AnnotatedParameterizedType` và `getAnnotatedActualTypeArguments()[0]` để đến nút **`String`**; ở đó mới có `@Mark("element")`.

Ví dụ đường truy cập metadata:

```java
Method method = Service.class.getDeclaredMethod("read");
AnnotatedType returnUse = method.getAnnotatedReturnType();
Mark outer = returnUse.getAnnotation(Mark.class);

if (returnUse instanceof AnnotatedParameterizedType pt) {
    AnnotatedType stringUse =
            pt.getAnnotatedActualTypeArguments()[0];
    Mark inner = stringUse.getAnnotation(Mark.class);
}
```

Đoạn này cần imports `java.lang.reflect.*`, class `Service` và `Mark` đã khai báo, đồng thời xử lý `NoSuchMethodException`; ví dụ chạy đầy đủ có ở mục 6.

**Cần nhớ:** `getAnnotatedReturnType()` vẫn trả một `AnnotatedType` với method không có annotation trên return type. Mảng `getAnnotations()` rỗng chỉ có nghĩa nút hiện tại không mang annotation được phản chiếu, không có nghĩa không tồn tại return type.

Với phương thức `void ping()`, kiểu trả về vẫn được biểu diễn bằng `void.class`; `getAnnotatedReturnType().getType()` biểu diễn `void`. Nó **không phải** `null` hay `Void.class`.

`Executable.getAnnotatedReturnType()` cũng áp dụng cho **constructor**, nhưng ngữ nghĩa khác: đối tượng `AnnotatedType` biểu diễn **kiểu đối tượng được xây dựng**, không phải một kiểu return được khai báo như method. Không nên gọi `getReturnType()` trên `Constructor`, vì phương thức đó thuộc `Method`, không phải `Constructor`.

## 4. getAnnotatedExceptionTypes(): annotation trong throws

Ví dụ một phương thức khai báo:

```java
public void load()
        throws @Mark("io") IOException,
               @Mark("state") IllegalStateException {
}
```

Đoạn này minh họa khai báo method, giả định import `IOException` và `Mark`. Dù thân phương thức trống, hai kiểu xuất hiện trong mệnh đề `throws` vẫn là metadata có thể đọc.

`method.getAnnotatedExceptionTypes()` trả về **`AnnotatedType[]` theo đúng thứ tự các exception types được liệt kê trong mệnh đề `throws`**:

| Chỉ số | `getType()` của phần tử | Annotation tại phần tử |
| --- | --- | --- |
| `0` | `java.io.IOException` | `@Mark("io")` |
| `1` | `java.lang.IllegalStateException` | `@Mark("state")` |

Tương phản:

- `getExceptionTypes()` trả `Class<?>[]`, cho biết các lớp exception được khai báo nhưng không mang thông tin type-use annotations ngay trong phần tử `Class`.
- `getGenericExceptionTypes()` trả `Type[]` khi cần thông tin kiểu tổng quát, chẳng hạn một type variable kiểu `E extends Exception` trong `throws E`.
- `getAnnotatedExceptionTypes()` trả `AnnotatedType[]`, cho phép đọc annotation trên lần dùng từng exception type, và với trường hợp phù hợp có thể duyệt các dạng `AnnotatedTypeVariable`.

**Giới hạn rất quan trọng:** Mảng này chứa các exception types **được khai báo trong `throws`**, không phải danh sách tất cả lỗi thực tế có thể phát sinh khi method chạy. Một method có `throws IOException` nhưng chưa từng ném nó vẫn trả metadata; ngược lại, method không khai báo `throws` vẫn có thể ném `RuntimeException` hoặc `Error`. Nếu không có kiểu exception nào trong `throws`, mảng kết quả dài **0**, không phải `null`.

Mảng `AnnotatedType[]` của exception types giữ **thứ tự khai báo**, khác với một số API Reflection trả mảng method/field mà thứ tự không được bảo đảm như thứ tự source.

## 5. Receiver type là gì? Vì sao khác với parameter thông thường?

Với instance method, **receiver** là đối tượng mà method sẽ thực thi trên đó, thường được nhắc đến bằng `this`. Java cho phép viết một **explicit receiver parameter** nhằm gắn type-use annotation lên kiểu receiver:

```java
class Service {
    public void action(@Mark("receiver") Service this) {
        // this là đối tượng nhận lời gọi action().
    }
}
```

Đây là đoạn minh họa trong ngữ cảnh `Mark` đã khai báo. Receiver parameter có cú pháp giống một tham số ở chữ ký, nhưng **không** phải formal parameter mang giá trị độc lập được truyền bằng lời gọi. Trong ví dụ:

- `action()` vẫn được gọi bằng `service.action()`, **không truyền thêm một đối số** cho `this`.
- `Method.getParameterCount()` của `action` vẫn bằng **0**.
- `Method.getParameterTypes()` và `getAnnotatedParameterTypes()` không thêm một phần tử cho explicit receiver.
- `getAnnotatedReceiverType()` cung cấp `AnnotatedType` có thể chứa `@Mark("receiver")`.
- Việc thêm receiver parameter không thay đổi overload signature của method và không cho phép gọi static method bằng receiver.

Với method `read(@Mark("receiver") Service this)` có annotation, ta có thể đọc:

```java
AnnotatedType receiverUse = method.getAnnotatedReceiverType();
Mark tag = receiverUse.getAnnotation(Mark.class);
```

**Các trường hợp cần phân biệt** theo hợp đồng JDK 21:

| Loại executable | `getAnnotatedReceiverType()` |
| --- | --- |
| Instance method có explicit receiver annotation | Một `AnnotatedType` chứa annotation trên kiểu receiver |
| Instance method không viết receiver parameter (hoặc receiver không mang annotation) | Vẫn là `AnnotatedType`, nhưng **không có annotation** tại receiver |
| Static method | `null` vì không thể có receiver parameter |
| Constructor của top-level class hoặc static member class | `null` |
| Constructor của non-static inner member class | Có thể trả `AnnotatedType` biểu diễn **enclosing receiver type**, kể cả không ghi explicit receiver annotation |
| Constructor của local/anonymous class | `null` theo hợp đồng API |

Vì vậy, **`getAnnotatedReceiverType() == null` không đồng nghĩa “không viết annotation”**. Một instance method không viết explicit receiver vẫn trả `AnnotatedType` *không có annotation*; còn static method trả `null` vì không có receiver theo loại executable. Ngược lại, một `AnnotatedType` không có annotation không chứng minh trong source đã khai báo một explicit receiver parameter.

Với inner-class constructor, quy tắc ngữ pháp receiver khác instance method thông thường (receiver gắn với enclosing instance), nên không thể máy móc dùng kiểu `Inner this` như với method. Hãy xem JLS nếu cần phân tích chi tiết receiver của constructor.

**Receiver type không phải kiểu runtime của object cụ thể:** `getAnnotatedReceiverType()` mô tả kiểu receiver theo khai báo, không kiểm tra `receiver.getClass()` của object khi chạy, cũng không thay đổi dynamic dispatch.

## 6. Ví dụ Java 17+ đầy đủ, chạy được

Tạo tệp `AnnotatedExecutableDemo.java`:

```java
import java.io.IOException;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedParameterizedType;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Method;
import java.util.List;

public class AnnotatedExecutableDemo {
    @Target(ElementType.TYPE_USE)
    @Retention(RetentionPolicy.RUNTIME)
    public @interface Mark {
        String value();
    }

    public static class Service {
        public @Mark("result") List<@Mark("element") String> read(
                @Mark("receiver") Service this)
                throws @Mark("io") IOException,
                       @Mark("state") IllegalStateException {
            return List.of("ok");
        }

        public String plain() {
            return "plain";
        }

        public static void ping() {}

        public void noThrows() {}

        public Service() {}
    }

    private static String mark(AnnotatedType type) {
        if (type == null) {
            return "null";
        }
        Mark ann = type.getAnnotation(Mark.class);
        return ann == null ? "none" : ann.value();
    }

    public static void main(String[] args) throws Exception {
        Method read = Service.class.getDeclaredMethod("read");

        AnnotatedType ret = read.getAnnotatedReturnType();
        System.out.println(
                "return.raw=" + read.getReturnType().getTypeName()
        );
        System.out.println("return.tag=" + mark(ret));

        AnnotatedType elem =
                ((AnnotatedParameterizedType) ret)
                .getAnnotatedActualTypeArguments()[0];
        System.out.println(
                "return.argument="
                + elem.getType().getTypeName() + ":" + mark(elem)
        );

        AnnotatedType[] exceptions =
                read.getAnnotatedExceptionTypes();
        System.out.println("exceptions=" + exceptions.length);

        for (int i = 0; i < exceptions.length; i++) {
            System.out.println(
                    "throws[" + i + "]="
                    + exceptions[i].getType().getTypeName()
                    + ":" + mark(exceptions[i])
            );
        }

        AnnotatedType receiver = read.getAnnotatedReceiverType();
        System.out.println("receiver.tag=" + mark(receiver));
        System.out.println(
                "receiver.type="
                + ((Class<?>) receiver.getType()).getSimpleName()
        );
        System.out.println(
                "receiver.isFormalParameter=" + read.getParameterCount()
        );

        Method plain = Service.class.getDeclaredMethod("plain");
        System.out.println(
                "plain.receiver.tag="
                + mark(plain.getAnnotatedReceiverType())
        );

        Method ping = Service.class.getDeclaredMethod("ping");
        System.out.println(
                "static.receiver=" + mark(ping.getAnnotatedReceiverType())
        );
        System.out.println(
                "static.return.type="
                + ping.getAnnotatedReturnType().getType().getTypeName()
        );

        Method noThrows = Service.class.getDeclaredMethod("noThrows");
        System.out.println(
                "noThrows=" + noThrows.getAnnotatedExceptionTypes().length
        );

        System.out.println(
                "constructor.receiver="
                + mark(Service.class.getDeclaredConstructor()
                        .getAnnotatedReceiverType())
        );
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac AnnotatedExecutableDemo.java
java AnnotatedExecutableDemo
```

Kết quả mong đợi trên Java 17+:

```text
return.raw=java.util.List
return.tag=result
return.argument=java.lang.String:element
exceptions=2
throws[0]=java.io.IOException:io
throws[1]=java.lang.IllegalStateException:state
receiver.tag=receiver
receiver.type=Service
receiver.isFormalParameter=0
plain.receiver.tag=none
static.receiver=null
static.return.type=void
noThrows=0
constructor.receiver=null
```

Giải thích:

1. `getReturnType()` cho `List.class` sau erasure. `getAnnotatedReturnType()` giữ `@Mark("result")` tại nút ngoài của kiểu trả về.
2. `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[0]` đi xuống `String` để tìm `@Mark("element")`, thay vì trộn annotation của container và element.
3. `getAnnotatedExceptionTypes()` trả hai kiểu `IOException` và `IllegalStateException` theo thứ tự khai báo, với giá trị `io` và `state` tương ứng.
4. `getAnnotatedReceiverType()` của `read` giữ annotation `receiver` trên `Service this`. Class cơ sở của receiver có simple name `Service`.
5. `getParameterCount() == 0` chứng minh receiver khai báo tường minh **không** phải formal parameter mà người gọi phải truyền vào.
6. `plain()` là instance method, không viết explicit receiver: API vẫn trả một `AnnotatedType` nhưng không có annotation `Mark`, nên nhãn là `none`.
7. `ping()` là static method: receiver type là `null`; return type là `void`.
8. `noThrows()` không có `throws`: mảng `getAnnotatedExceptionTypes()` rỗng.
9. Constructor `Service()` thuộc **static member class**, nên không có receiver kiểu enclosing instance và `getAnnotatedReceiverType()` trả `null`.

Chương trình chỉ đọc metadata; không gọi `read()` hay `plain()`, không cần tạo một đối tượng `Service`. Mỗi method được tìm bằng tên cụ thể, nên không phụ thuộc thứ tự của `getDeclaredMethods()`.

## 7. Nếu kiểu trả về/exception là generic hoặc phức hợp

`AnnotatedType` là một họ interface. Đọc annotation của **nút ngoài** bằng `getAnnotation` chưa đủ nếu annotation ở các thành phần bên trong.

Với một return type có đối số generic:

```java
public List<@Mark("item") String> items() {
    return List.of();
}
```

Cần kiểm tra `getAnnotatedReturnType() instanceof AnnotatedParameterizedType`, sau đó duyệt `getAnnotatedActualTypeArguments()` để lấy annotation tại `String`.

Khi return type là mảng, wildcard hay type variable, các nhánh khác của họ `AnnotatedType` cần xử lý riêng:

| Loại nút | API duyệt thông tin con |
| --- | --- |
| `AnnotatedParameterizedType` | `getAnnotatedActualTypeArguments()` và khi phù hợp `getAnnotatedOwnerType()` |
| `AnnotatedArrayType` | `getAnnotatedGenericComponentType()` |
| `AnnotatedWildcardType` | `getAnnotatedUpperBounds()`, `getAnnotatedLowerBounds()` |
| `AnnotatedTypeVariable` | `getAnnotatedBounds()` |

Ví dụ method generic:

```java
public <E extends Exception> void call() throws E {}
```

Đây là đoạn minh họa, không phải chương trình độc lập. `getGenericExceptionTypes()` có thể trả một `TypeVariable` đại diện cho `E`, còn `getAnnotatedExceptionTypes()` biểu diễn **lần sử dụng `E` trong `throws`** dưới dạng `AnnotatedType`, có thể là `AnnotatedTypeVariable`. Annotation đặt trên **bound** `E extends Exception` là thông tin ở **vị trí bound** khác với annotation đặt trên **lần dùng `E` trong `throws`**.

Nếu viết bộ duyệt metadata đệ quy trên các bounds, cần chú ý chu trình type variable (ví dụ `T extends Comparable<T>`) và có cơ chế visited-set phù hợp. Đừng ép kiểu mọi `AnnotatedType` thành `AnnotatedParameterizedType`.

## 8. Ba loại annotation dễ bị đọc nhầm

Một framework kiểm tra annotation trên method nên tách ít nhất ba câu hỏi:

| Vị trí cần đọc | API phù hợp | Ví dụ minh họa |
| --- | --- | --- |
| Annotation trên **khai báo method** | `method.getAnnotation(DeclarationAnnotation.class)` | `@Deprecated` ngay trước khai báo method |
| Annotation trên **kiểu trả về** | `method.getAnnotatedReturnType().getAnnotation(TypeUseAnnotation.class)` | `@Mark("result") List<String> read()` |
| Annotation trên **đối số của kiểu trả về** | `AnnotatedParameterizedType.getAnnotatedActualTypeArguments()[i]` | `List<@Mark("item") String>` |
| Annotation trên **kiểu exception** | `method.getAnnotatedExceptionTypes()[i].getAnnotation(...)` | `throws @Mark("io") IOException` |
| Annotation trên **kiểu receiver** | `method.getAnnotatedReceiverType().getAnnotation(...)` (nếu khác `null`) | `method(@Mark("this") C this)` |
| Annotation trên **kiểu formal parameter** | `method.getAnnotatedParameterTypes()[i]` | `save(@Mark("argument") String s)` |

Ở hàng receiver, `C` tượng trưng cho declaring class của instance method; mã minh họa chỉ thể hiện cú pháp, không dùng làm class Java độc lập.

Nếu annotation được khai báo với **nhiều target** (`METHOD`, `PARAMETER`, `TYPE_USE`...), cần kiểm tra vị trí cú pháp và quy tắc ghi metadata của compiler, thay vì mặc định nó được lưu ở một API duy nhất. Nếu không có `@Retention(RUNTIME)`, việc không nhìn thấy annotation qua Reflection runtime chưa chứng minh annotation vắng mặt trong source hoặc class file.

## 9. Lỗi phổ biến và cách khắc phục

**Lỗi 1 — Dùng `getReturnType()` để đọc annotation trong `List<@Mark String>`.** `getReturnType()` chỉ trả `Class<?> = List.class`; dùng `getAnnotatedReturnType()` rồi duyệt đến generic argument.

**Lỗi 2 — Đọc `getExceptionTypes()` rồi cho rằng đã có annotation trên `throws`.** Kết quả chỉ là `Class<?>[]`; dùng `getAnnotatedExceptionTypes()` để có `AnnotatedType[]`.

**Lỗi 3 — Tưởng `getAnnotatedExceptionTypes()` liệt kê lỗi sẽ xảy ra lúc chạy.** Nó chỉ phản ánh **`throws` clause**; không chạy phương thức, không quan sát exception phát sinh thực tế.

**Lỗi 4 — Đồng nhất `getAnnotatedReceiverType() == null` với receiver không được annotation.** Instance method có thể trả `AnnotatedType` không có annotation; `null` được dùng khi executable **không thể có receiver parameter**, ví dụ static method.

**Lỗi 5 — Nghĩ explicit receiver là một tham số bình thường.** `Service this` không làm tăng `getParameterCount()` và không buộc người gọi truyền thêm `this`.

**Lỗi 6 — Tưởng receiver type phản ánh runtime subclass.** Metadata ghi kiểu receiver theo khai báo; object khi chạy có thể thuộc lớp con, còn dynamic dispatch là vấn đề riêng.

**Lỗi 7 — Không xử lý mảng rỗng hoặc `null`.** `getAnnotatedExceptionTypes()` có thể trả mảng rỗng; `getAnnotatedReceiverType()` có thể trả `null`. Kiểm tra trước khi lấy `[0]` hoặc `getAnnotation`.

**Lỗi 8 — Nhầm annotation khai báo method với annotation trên kiểu trả về.** `Method.getAnnotations()` không tự bao gồm annotation tại tất cả các type-use positions.

**Lỗi 9 — Bỏ qua `RetentionPolicy.RUNTIME`.** `TYPE_USE` chỉ cho phép đặt annotation; không bảo đảm annotation xuất hiện qua Reflection nếu retention không phù hợp.

**Lỗi 10 — Xem `AnnotatedType` luôn là một kiểu đơn giản.** Return type có thể parameterized, array, wildcard hoặc type variable; phải đi đúng cấu trúc cây kiểu, không cast bừa.

## 10. Tự kiểm tra

1. Phương thức có kiểu trả về `@Mark("top") List<@Mark("item") String>`. Đọc `top` ở đâu? **Tại `getAnnotatedReturnType()`**; đọc `item` ở **nút type argument thứ nhất**.
2. `throws @Mark("io") IOException` có `getExceptionTypes()[0]` trả annotation không? **Không**, phần tử là `Class`; cần `getAnnotatedExceptionTypes()[0]`.
3. Method không khai báo `throws` thì `getAnnotatedExceptionTypes()` trả gì? **Mảng rỗng**, không phải `null`.
4. Static method có receiver type không? **Không**, `getAnnotatedReceiverType()` trả `null`.
5. Instance method không có explicit receiver annotation thì receiver type có bắt buộc `null` không? **Không**; API trả `AnnotatedType` không có annotation trên receiver.
6. `void act(@Mark("x") C this)` khai báo bao nhiêu **formal parameters**? **0**; receiver không tính là formal parameter thông thường.
7. `getAnnotatedReceiverType()` có phải kiểu runtime chính xác của đối tượng đang gọi không? **Không**; nó là metadata trên kiểu receiver theo khai báo.
8. `getAnnotatedReturnType()` có chạy phương thức và xem đối tượng được trả về không? **Không**; chỉ đọc cấu trúc khai báo.
9. Với method `<E extends Exception> void call() throws E`, nên xem API nào để thấy cấu trúc kiểu generic ở `throws`? **`getGenericExceptionTypes()`**, và dùng **`getAnnotatedExceptionTypes()`** khi cần annotation trên lần dùng kiểu.
10. Vì sao annotation `@Target(TYPE_USE)` nhưng không `@Retention(RUNTIME)` có thể không đọc được bằng Reflection? **Vì quyền đặt annotation và khả năng giữ annotation đến runtime là hai thuộc tính độc lập.**

## 11. Tài liệu chính thức

- [Oracle Java SE 21 — `Executable`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Executable.html): các hợp đồng `getAnnotatedReturnType()`, `getAnnotatedExceptionTypes()`, `getAnnotatedReceiverType()`, kiểu receiver của method và constructor.
- [Oracle Java SE 21 — `Method`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html): thông tin method, return type, generic return type và annotation.
- [Oracle Java SE 21 — `AnnotatedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedType.html): `getType()`, annotation tại mỗi type-use node.
- [Oracle Java SE 21 — `AnnotatedParameterizedType`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/AnnotatedParameterizedType.html): annotation trên các đối số generic.
- [Java Language Specification SE 21 — §8.4.1 Formal Parameters](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.4.1): receiver parameters của instance methods.
- [Java Language Specification SE 21 — §9.7 Annotations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.7): annotation tại vị trí type use.

**Ghi nhớ:** `getAnnotatedReturnType()` nhìn vào **kiểu trả về**; `getAnnotatedExceptionTypes()` nhìn vào **những kiểu ghi trong `throws`**; `getAnnotatedReceiverType()` nhìn vào **kiểu của receiver `this`**. Cả ba đọc *annotation trên vị trí dùng kiểu*, không phải cùng một nhóm annotation của khai báo method, và luôn phải xét đúng nút `AnnotatedType` cũng như khả năng trả mảng rỗng hoặc `null`.