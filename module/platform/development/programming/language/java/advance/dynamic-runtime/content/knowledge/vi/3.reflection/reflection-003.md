# 3.3. Tìm phương thức theo tên và kiểu tham số; giới hạn của việc chọn overload lúc chạy

## Mục tiêu

Sau bài này, bạn có thể:

- Phân biệt **chọn overload lúc biên dịch**, **tìm chính xác một phương thức qua Reflection**, và **điều phối override lúc chạy**.
- Sử dụng đúng **Class.getMethod**, **Class.getDeclaredMethod**, **Method.invoke** với tên phương thức và danh sách kiểu tham số.
- Giải thích vì sao lấy **arg.getClass()** rồi tra cứu thường thất bại với kiểu cha, primitive, null, varargs hoặc generic.
- Biết khi nào cần tự quy định thuật toán chọn overload, cách xử lý trường hợp mơ hồ và giới hạn quyền truy cập.
- Nhận biết lỗi tra cứu khác với lỗi gọi phương thức; tránh nhầm việc gọi Reflection với “trình biên dịch tự chọn overload tốt nhất”.

## 1. Ba quyết định khác nhau

Java cho phép nhiều phương thức **cùng tên nhưng khác danh sách kiểu tham số** (overloading). Chẳng hạn:

~~~java
public String format(Object value)  { return "Object"; }
public String format(Number value)  { return "Number"; }
public String format(Integer value) { return "Integer"; }
public String format(int value)     { return "int"; }
~~~

Bốn phương thức trên là bốn **overload**; Java phải xác định đang nói tới phương thức nào.

| Cơ chế | Điều quyết định | Thời điểm chính | Ví dụ |
| --- | --- | --- | --- |
| **Overload resolution của trình biên dịch** | Chữ ký thích hợp nhất dựa trên **kiểu biểu thức tại thời điểm biên dịch**, tập overload có thể áp dụng và luật Java | Compile-time | **service.format(value)** |
| **Reflection lookup** | Tên và **danh sách Class<?> của tham số được chỉ định chính xác**; không tự suy luận overload tốt nhất từ giá trị đối số | Runtime, khi gọi API tra cứu | **type.getMethod("format", Number.class)** |
| **Dynamic dispatch của override** | Sau khi biết chữ ký cần gọi, lựa chọn implementation được override theo **lớp thực tế của receiver** đối với instance method ảo | Runtime, khi gọi | Đối tượng lớp con override **format(Object)** |

Hai từ “động” dễ gây nhầm lẫn: Reflection cho phép **chọn chữ ký theo thông tin runtime** nếu chính chương trình cung cấp tên và loại tham số, nhưng **không có nghĩa** **getMethod** đang chạy lại đầy đủ các quy tắc overload resolution của trình biên dịch Java.

Cần phân biệt hai câu hỏi:

1. **Chữ ký nào được chọn?** Ví dụ **format(Number)** hay **format(Integer)**.
2. **Implementation nào thực thi chữ ký đó?** Ví dụ **Base.format(Number)** hay **Derived.format(Number)** nếu lớp con override.

Việc Reflection trả về một đối tượng **Method** chính là đã chốt chữ ký được tìm. Lệnh **Method.invoke** gọi phương thức đó; nó không duyệt tất cả overload cùng tên để chọn lại.

## 2. Tìm theo tên và kiểu tham số chính xác

### 2.1. Class.getMethod và Class.getDeclaredMethod

Hai API phổ biến:

~~~java
// Tìm phương thức public được công bố bởi lớp hoặc thừa kế.
Method publicMethod =
        SomeType.class.getMethod("execute", String.class, int.class);

// Tìm phương thức khai báo TRỰC TIẾP trong SomeType, bất kể visibility.
Method declaredMethod =
        SomeType.class.getDeclaredMethod("execute", String.class, int.class);
~~~

Đoạn trên là **minh họa API**, giả định **SomeType** có phương thức tương ứng; không phải chương trình độc lập.

| API | Phạm vi tìm | Có thấy private được khai báo trong lớp? | Có tìm public method thừa kế? |
| --- | --- | --- | --- |
| **getMethod(name, parameterTypes...)** | Public methods của lớp và các thành viên public được thừa kế | Không | Có |
| **getDeclaredMethod(name, parameterTypes...)** | Các methods khai báo trong chính lớp, kể cả private/protected/package-private | Có | Không |
| **getMethods()** | Mảng các public methods nhìn thấy từ lớp, kể cả thừa kế | Không | Có |
| **getDeclaredMethods()** | Mảng methods khai báo trong chính lớp | Có | Không |

**getDeclaredMethod** tìm thấy một private method **không đồng nghĩa** với có quyền gọi nó. Quyền truy cập được kiểm tra khi Reflection sử dụng phương thức; quy tắc package, module và khả năng mở truy cập vẫn áp dụng.

Thứ tự các phần tử trong **getMethods() / getDeclaredMethods()** không được bảo đảm. Đừng chọn “phương thức cùng tên đầu tiên” rồi cho rằng nó là overload phù hợp nhất.

### 2.2. Tham số của phương thức tra cứu là Class, không phải giá trị

Chữ ký tra cứu quan trọng:

~~~java
Class<?>.getMethod(String name, Class<?>... parameterTypes)
Class<?>.getDeclaredMethod(String name, Class<?>... parameterTypes)
~~~

**parameterTypes** là các **kiểu tham số hình thức**, theo đúng thứ tự, sau type erasure nếu có generic. Trình biên dịch Java thường tạo được lớp mô tả kiểu bằng **String.class**, **Number.class**, **int.class**, **String[].class**, v.v.

Ví dụ:

| Phương thức được khai báo | Cách tra cứu đúng | Cách tra cứu dễ sai |
| --- | --- | --- |
| **send(String value)** | **getMethod("send", String.class)** | **getMethod("send", Object.class)** |
| **send(Number value)** | **getMethod("send", Number.class)** | **getMethod("send", Integer.class)** |
| **send(int value)** | **getMethod("send", int.class)** | **getMethod("send", Integer.class)** |
| **send(String... values)** | **getMethod("send", String[].class)** | **getMethod("send", String.class)** |
| **send(int[] values)** | **getMethod("send", int[].class)** | **getMethod("send", Integer[].class)** |
| **send(List<String> values)** | **getMethod("send", List.class)** | **getMethod("send", ArrayList.class)** |

Trong bảng, giả định mỗi hàng xét độc lập và kiểu **List** đến từ **java.util.List**.

Java Reflection yêu cầu **kiểu tham số phải trùng chính xác**, không dùng quan hệ cha–con, autoboxing, primitive widening hay luật varargs để **tìm** phương thức. Vì vậy, **getMethod("send", Integer.class)** không trả về **send(Number)**, dù đối tượng Integer có thể được truyền vào **send(Number)** khi đã có đối tượng Method tương ứng.

Định nghĩa tham số rỗng được biểu thị bằng **getMethod("run")** (không cung cấp kiểu tham số). Với trường hợp có nhiều overload, phải truyền đúng số lượng và thứ tự kiểu.

### 2.3. Tên + tham số; không chọn bằng kiểu trả về

Trong Java source, không thể khai báo hai overload chỉ khác kiểu trả về. Hai dòng dưới đây không thể cùng tồn tại như hai khai báo method thông thường:

~~~java
// Hai khai báo cùng chữ ký sẽ gây lỗi biên dịch:
String read(int id);
Integer read(int id);
~~~

Đoạn code này **cố tình không biên dịch**, dùng để minh họa lỗi “method is already defined”, không phải chương trình chạy.

Các overload được phân biệt bằng tên và danh sách kiểu tham số; **getMethod** không nhận kiểu trả về để chọn. Tuy nhiên, JVM bytecode và các **bridge method** do compiler sinh có thể tạo tình huống Reflection nhìn thấy các Method trùng tên và tham số nhưng khác kiểu trả về. Nếu quét toàn bộ **getDeclaredMethods**, cần chú ý **Method.isBridge()**, **isSynthetic()**, và **getReturnType()**; không nên giả định mảng luôn là tập các overload do lập trình viên viết trực tiếp.

## 3. Ví dụ đầy đủ: tra cứu exact signature khác với chọn overload

Lưu file **OverloadLookupDemo.java**:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

public class OverloadLookupDemo {
    public static class Formatter {
        public String format(Object value) {
            return "Object";
        }

        public String format(Number value) {
            return "Number";
        }

        public String format(Integer value) {
            return "Integer";
        }

        public String format(int value) {
            return "int(" + value + ")";
        }

        public String format(String... values) {
            return "String...:" + String.join(",", values);
        }

        public String onlyNumber(Number value) {
            return "onlyNumber";
        }

        private String hidden(String value) {
            return "hidden:" + value;
        }
    }

    public static void main(String[] args) throws Exception {
        Formatter formatter = new Formatter();

        // Kiểu tĩnh là Object, dù đối tượng thực sự là Integer.
        Object payload = Integer.valueOf(7);
        System.out.println("normal=" + formatter.format(payload));
        System.out.println("runtimeClass="
                + payload.getClass().getSimpleName());

        // Reflection chọn CHÍNH XÁC chữ ký được chỉ rõ.
        Method integerMethod =
                Formatter.class.getMethod("format", Integer.class);
        Method numberMethod =
                Formatter.class.getMethod("format", Number.class);
        Method intMethod =
                Formatter.class.getMethod("format", int.class);

        System.out.println("exactReference="
                + integerMethod.invoke(formatter, payload));
        System.out.println("explicitSuper="
                + numberMethod.invoke(formatter, payload));
        System.out.println("primitive="
                + intMethod.invoke(formatter, Integer.valueOf(7)));
        System.out.println("widening="
                + intMethod.invoke(formatter, Short.valueOf((short) 8)));

        // Tham số Java String... được lưu dưới dạng String[].
        Method arrayMethod =
                Formatter.class.getMethod("format", String[].class);
        System.out.println("varargs="
                + arrayMethod.invoke(
                        formatter, (Object) new String[]{"a", "b"}));

        try {
            Formatter.class.getMethod("format", Long.class);
        } catch (NoSuchMethodException e) {
            System.out.println("Long=not-found");
        }

        // getClass() không phải thuật toán chọn overload theo kiểu cha.
        try {
            Formatter.class.getMethod("onlyNumber", payload.getClass());
        } catch (NoSuchMethodException e) {
            System.out.println("runtimeOnlyNumber=not-found");
        }

        try {
            Formatter.class.getMethod("hidden", String.class);
        } catch (NoSuchMethodException e) {
            System.out.println("public-hidden=not-found");
        }

        Method declared =
                Formatter.class.getDeclaredMethod("hidden", String.class);
        System.out.println("declared-private="
                + Modifier.isPrivate(declared.getModifiers()));
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac -encoding UTF-8 OverloadLookupDemo.java
java OverloadLookupDemo
~~~

Stdout chính xác:

~~~text
normal=Object
runtimeClass=Integer
exactReference=Integer
explicitSuper=Number
primitive=int(7)
widening=int(8)
varargs=String...:a,b
Long=not-found
runtimeOnlyNumber=not-found
public-hidden=not-found
declared-private=true
~~~

### Giải thích từng phần

**normal=Object:** Biểu thức **payload** có **kiểu khai báo Object**. Java compiler chọn overload **format(Object)**, dù ở runtime **payload.getClass()** là **Integer**. Một receiver có thể dùng dynamic dispatch để chọn override của **format(Object)** nhưng không đổi chữ ký thành **format(Integer)** chỉ vì runtime argument là Integer.

**exactReference=Integer:** Chương trình chủ động yêu cầu **getMethod("format", Integer.class)**, nên Method đã đại diện cho overload Integer. Khi truyền payload thực tế là Integer, lời gọi hợp lệ.

**explicitSuper=Number:** Không có hành động “tự chọn Number” nào ở đây. Chương trình **đã chỉ định** overload **Number.class**, rồi chuyển object Integer vào tham số Number theo quan hệ subtype.

**primitive=int(7) và widening=int(8):** Lookup yêu cầu chính xác **int.class**. Sau khi đã tìm đúng Method, **Method.invoke** có thể nhận wrapper tương ứng (Integer) hoặc wrapper của primitive nhỏ hơn phù hợp (Short) rồi **unbox và primitive-widen** cho tham số int. Chuyển đổi đối số ở bước invoke **khác với** luật exact match ở bước lookup. Nếu thay lookup thành **getMethod("format", short.class)**, API không tự tìm **format(int)**.

**varargs=String...:a,b:** Khai báo **String...** trở thành tham số **String[]**. **Method.invoke** cũng có dạng varargs **Object...**, nên ép kiểu **(Object) new String[]{"a", "b"}** giúp chuyển **cả mảng String[] thành một đối số duy nhất** cho method được gọi. Reflection không tự gom nhiều đối số String rời thành String[] theo cách compiler xử lý lời gọi varargs thông thường.

**Long=not-found:** Không có overload có tham số **Long** chính xác. **format(Number)** và **format(Object)** có thể nhận một giá trị Long khi gọi đúng chữ ký, nhưng không phải kết quả của lookup **Long.class**.

**runtimeOnlyNumber=not-found:** **onlyNumber** chỉ có chữ ký **(Number)**; **payload.getClass()** trả về **Integer.class**, nên lookup thất bại mặc dù bản thân **onlyNumber(Number)** có thể nhận Integer.

**public-hidden=not-found / declared-private=true:** **getMethod** chỉ tìm public method. **getDeclaredMethod** cho phép tìm private method khai báo trong Formatter, nhưng việc lấy metadata không tự cấp quyền gọi.

## 4. Overload resolution và override dispatch là hai tầng độc lập

Ví dụ sau có hai overload **call(Object)** và **call(String)**. Lớp con **chỉ override call(Object)**.

Lưu file **OverrideDispatchDemo.java**:

~~~java
import java.lang.reflect.Method;

public class OverrideDispatchDemo {
    public static class Parent {
        public String call(Object value) {
            return "Parent/Object";
        }

        public String call(String value) {
            return "Parent/String";
        }
    }

    public static class Child extends Parent {
        @Override
        public String call(Object value) {
            return "Child/Object";
        }
    }

    public static void main(String[] args) throws Exception {
        Parent receiver = new Child();
        Object value = "hello";

        // Chữ ký Object được chọn theo kiểu tĩnh của value.
        System.out.println("java=" + receiver.call(value));

        // Reflection chốt chữ ký Object; override chạy ở Child.
        Method objectOverload =
                Parent.class.getMethod("call", Object.class);
        System.out.println("reflectObject="
                + objectOverload.invoke(receiver, value));

        // Reflection chốt chữ ký String; Child không override nó.
        Method stringOverload =
                Parent.class.getMethod("call", String.class);
        System.out.println("reflectString="
                + stringOverload.invoke(receiver, value));
    }
}
~~~

~~~bash
javac -encoding UTF-8 OverrideDispatchDemo.java
java OverrideDispatchDemo
~~~

Stdout:

~~~text
java=Child/Object
reflectObject=Child/Object
reflectString=Parent/String
~~~

**Vì sao?** Với lời gọi Java thường, compiler đã chọn chữ ký **call(Object)** vì biến value có kiểu tĩnh Object; khi runtime gọi trên Child, JVM sử dụng override **Child.call(Object)**. Reflection cũng có thể gọi override đó khi Method đại diện cho **call(Object)** của Parent. Nhưng **getMethod("call", String.class)** chỉ rõ chữ ký String, và Child không override chữ ký này nên implementation thừa kế là **Parent.call(String)** được thực thi. Chuỗi thực tế **"hello"** không tự khiến overload chuyển đổi qua lại.

**Quy tắc nhớ:** **Overloading** là chọn giữa các *chữ ký khác nhau*; **overriding** là chọn *implementation khác nhau của cùng chữ ký* (đối với lời gọi ảo).

## 5. Vì sao arg.getClass() không phải bộ giải overload tổng quát?

Một cách viết thường gặp:

~~~java
// Minh họa ý tưởng KHÔNG AN TOÀN để tìm overload tổng quát:
Class<?>[] types = new Class<?>[args.length];
for (int i = 0; i < args.length; i++) {
    types[i] = args[i].getClass();
}
Method method = target.getClass().getMethod(methodName, types);
~~~

Đây là **fragment minh họa** giả định có biến **args**, **target** và **methodName**, không phải chương trình độc lập. Nó chỉ có thể hoạt động khi mọi phần tử khác null **và** các runtime class tình cờ trùng **chính xác** với tham số phương thức đích.

Những phản ví dụ quan trọng:

| Dữ liệu và phương thức có sẵn | Kiểu trả về từ arg.getClass() | Tại sao tra cứu có thể sai? |
| --- | --- | --- |
| Đối số **Integer(7)**, phương thức **run(Number)** | Integer.class | Exact lookup không tìm supertype Number |
| Đối số **Integer(7)**, phương thức **run(int)** | Integer.class | int.class khác Integer.class |
| Đối số **Short(7)**, phương thức **run(int)** | Short.class | Có thể unbox+widen lúc invoke, nhưng lookup không widen |
| Đối số **null**, phương thức **run(String)** | Không có | **null.getClass()** ném NullPointerException; null không chỉ ra kiểu hình thức |
| Hai phương thức **run(String)** và **run(Integer)**, đối số null | Không có | Dùng null không xác định duy nhất overload; lời gọi Java **run(null)** cũng mơ hồ ở compile-time nếu hai overload không liên quan |
| Phương thức **run(String... xs)**, gọi với chuỗi riêng lẻ | String.class | Chữ ký runtime nhận String[] |
| Phương thức **run(List<String> xs)**, truyền ArrayList | ArrayList.class | Tham số runtime sau erasure là List.class |
| Phương thức **run(Serializable)** và **run(Cloneable)**, đối số ArrayList | ArrayList.class | Nhiều kiểu cha/interface có thể cùng phù hợp; cần chính sách giải mơ hồ |

Với kiểu tham số **List<String>**, Reflection tra cứu kiểu hình thức là **List.class**, không phải **List<String>.class** vì Java không có class literal cho tham số hóa generic. Không thể khai báo hai overload **run(List<String>)** và **run(List<Integer>)** trong cùng lớp chỉ khác type argument, vì hai chữ ký có cùng erasure.

Kể cả khi có thể tự duyệt toàn bộ method, **Class.isAssignableFrom(...)** chỉ giải quyết một phần quan hệ kiểu tham chiếu; riêng nó không giải quyết đầy đủ primitive, autoboxing, widening, varargs, null, độ đặc hiệu hay ưu tiên các pha chọn overload.

## 6. Nếu muốn chọn overload theo giá trị runtime thì phải đặt ra chính sách

Không có API Reflection chuẩn nào tương đương hoàn toàn với “hãy tự gọi phương thức overload tốt nhất như javac sẽ chọn nếu nó thấy dữ liệu runtime của tôi”. Ứng dụng phải chọn một **hợp đồng gọi**. Ba cách thường dùng:

### Cách A: hợp đồng chỉ rõ chữ ký

Dùng khi cấu hình, RPC, message handler hoặc plugin đã có schema xác định rõ đối số kiểu gì. Ví dụ lệnh **createInvoice** chỉ nhận **(String, int)**; chương trình lấy Method bằng hai Class tương ứng. Mỗi hành vi được cấu hình bằng **tên + danh sách kiểu**, chứ không đoán từ giá trị runtime.

Ưu điểm: dự đoán được, dễ validate, dễ audit và tránh mơ hồ. Thích hợp nếu source dữ liệu đến từ JSON hoặc cấu hình có schema.

### Cách B: đăng ký các Method được phép gọi

Chỉ expose những hành vi nghiệp vụ được duyệt, ánh xạ tên lệnh thành Method đã tra cứu sẵn. Ví dụ **action=showNumeric** ánh xạ duy nhất đến **format(Number)**. Lựa chọn overload là **quy tắc do ứng dụng quản lý**, không dựa vào thứ tự **getMethods()**.

Mẫu fragment sau áp dụng cho lớp **Formatter** trong ví dụ đầu:

~~~java
// Fragment nằm trong ngữ cảnh có biến Formatter formatter.
java.util.Map<String, Method> commands = java.util.Map.of(
        "number", Formatter.class.getMethod("format", Number.class),
        "integer", Formatter.class.getMethod("format", Integer.class)
);
Method chosen = commands.get("number");
Object result = chosen.invoke(formatter, Integer.valueOf(7));
// result là chuỗi "Number".
~~~

Đoạn trên **không độc lập**; cần lớp Formatter, đối tượng formatter và xử lý checked exception như trong chương trình trước. Ứng dụng thực tế phải kiểm tra key không có trong allowlist trước khi gọi.

### Cách C: tự viết bộ phân giải overload (khi thật sự cần)

Nếu API nhận các argument runtime rồi phải tự chọn method trong nhiều overload, cần quy định rõ:

1. **Tập ứng viên:** tên, số tham số, public/declared, static/instance, visibility và receiver; cân nhắc lọc bridge/synthetic.
2. **Tính áp dụng:** các kiểu tham số có nhận được đối số không, bao gồm null cho kiểu tham chiếu, quan hệ kế thừa, primitive conversion, boxing/unboxing và varargs.
3. **Mức độ ưu tiên:** chọn method đặc hiệu hơn theo quy tắc đã định; nếu cần hành vi giống lời gọi Java, phải mô hình hóa các pha overload resolution trong JLS, thay vì chấm điểm đơn giản.
4. **Mơ hồ:** nếu không có ứng viên hoặc nhiều ứng viên ngang mức thì **báo lỗi rõ ràng**, không lấy method đầu tiên.
5. **Thực thi:** kiểm tra quyền truy cập, chuẩn hóa gói đối số varargs và bắt lỗi từ Method.invoke.

Cách C rất dễ phức tạp vì Java có các trường hợp biên như interface không liên quan, method generic, boxing cùng widening, varargs, lambda, null và luật most-specific. **Tái hiện javac hoàn chỉnh từ các object runtime cũng không có đủ thông tin**, vì trình biên dịch dùng **kiểu tĩnh của biểu thức** và target typing mà object thuần không giữ lại. Nếu yêu cầu nghiệp vụ cho phép, ưu tiên cách A hoặc B.

## 7. Những giới hạn thường bị bỏ sót

### 7.1. Primitive khác wrapper, và lookup khác invocation conversion

**int.class != Integer.class**. **getMethod("process", int.class)** chỉ khớp formal type int, còn **getMethod("process", Integer.class)** chỉ khớp formal type Integer.

Sau khi Method đã được chọn, **Method.invoke** có thể unbox wrapper thành primitive và thực hiện **primitive widening** hợp lệ. Ví dụ **Short** có thể truyền vào method có formal type int qua unboxing và widening. Không có conversion tùy ý: không thể lấy **String** rồi tự parse thành int, cũng không thể narrowing int xuống short nếu vượt hợp đồng invocation. Với tham số tham chiếu, đối số phải tương thích theo assignment reference; **Method.invoke** không biến kiểu đối số tham chiếu thành kiểu khác chỉ vì cùng có tên overload.

### 7.2. Null không có “runtime class” để suy ra

Với **print(String)** và **print(Integer)**, null tương thích với cả hai về mặt giá trị; chương trình phải chọn chữ ký bằng thông tin bổ sung (schema, khai báo, cast hoặc policy). **getMethod("print", String.class)** là lựa chọn rõ ràng; **null.getClass()** là lỗi. Với formal primitive, null không thể được unbox để gọi method.

Khi gọi bằng Reflection, cần đóng gói null đúng dạng đối số của **invoke**, ví dụ **method.invoke(receiver, new Object[]{null})** để truyền **một đối số null**. Tránh nhầm nó với **(Object[]) null**, cách viết có ý nghĩa như mảng tham số của invoke không được cung cấp.

### 7.3. Varargs là array tại runtime

**void log(String... lines)** có formal type **String[]**. Reflection lookup sử dụng **String[].class**. Bản thân **Method.invoke(Object receiver, Object... args)** cũng là varargs, nên:

~~~java
// Fragment minh họa, giả sử logMethod nhận đúng một String[]:
logMethod.invoke(receiver, (Object) new String[]{"a", "b"});
// Hoặc:
logMethod.invoke(receiver, new Object[]{new String[]{"a", "b"}});
~~~

Đừng trông chờ **logMethod.invoke(receiver, "a", "b")** tự gom hai String thành một String[]. Ở cấp độ Method.invoke, đó là **hai** argument riêng lẻ, trong khi method đích chỉ có **một** formal parameter kiểu String[].

### 7.4. Generics bị xóa kiểu; bridge methods có thể xuất hiện

Phương thức khai báo **void consume(List<String> items)** có formal parameter runtime là **java.util.List.class**. Những thông tin generic có thể xem qua **Method.getGenericParameterTypes()** nhưng **getMethod** vẫn tra cứu bằng Class<?> của kiểu sau erasure.

Khi kế thừa generic hoặc override có kiểu trả về covariant, compiler có thể sinh **bridge method** để giữ tương thích dispatch. Vì vậy khi liệt kê methods bằng Reflection, có thể gặp phương thức synthetic/bridge. Kiểm tra **isBridge()**, **isSynthetic()**, **getDeclaringClass()**, **getParameterTypes()**, **getReturnType()** nếu đang tự viết resolver hoặc trình phân tích API. Đừng coi tất cả các Method đó là những lựa chọn overload nghiệp vụ độc lập.

### 7.5. Public, declared và quyền truy cập là các tầng khác nhau

- **getMethod** tìm public method, kể cả có thể được kế thừa.
- **getDeclaredMethod** tìm method trên chính lớp, kể cả private; không tự tìm private method của superclass.
- **Method.invoke** vẫn phải kiểm tra quyền truy cập khi cần.
- **setAccessible(true)** hoặc **trySetAccessible()** có thể bị giới hạn bởi Java Platform Module System và strong encapsulation; không thể giả định luôn mở được private member của module khác.
- Với static method, đối tượng receiver của invoke được bỏ qua (có thể dùng null). Với instance method, receiver phải tương thích với declaring class.

Reflection có thể tìm ra Method nhưng vẫn không đủ quyền gọi; lỗi tra cứu và lỗi truy cập là hai loại sự cố khác nhau.

### 7.6. Reflection có overhead và lỗi được phát hiện lúc chạy

Lookup theo tên có thể thất bại khi triển khai khác phiên bản, thay đổi chữ ký hoặc bị thiếu quyền module. Các lỗi chỉ lộ ra lúc chạy, trong khi lời gọi Java tĩnh được compiler kiểm tra nhiều hơn. Nếu gọi cùng một method liên tục, có thể cache **Method** sau khi kiểm tra đúng class loader/version và chữ ký; không nên scan methods cho từng request nếu không cần. Chỉ tối ưu khi đo được chi phí thực tế.

## 8. Xử lý lỗi đúng giai đoạn

| Giai đoạn | Lỗi thường gặp | Hành động phù hợp |
| --- | --- | --- |
| Tra cứu bằng **getMethod / getDeclaredMethod** | **NoSuchMethodException** | Kiểm tra tên, số lượng, thứ tự và Class<?> của formal parameters; public vs declared; class loader |
| Gọi bằng **invoke** | **IllegalArgumentException** | Kiểm tra receiver, số lượng/kiểu argument và conversion hợp lệ |
| Gọi bằng **invoke** | **IllegalAccessException** | Kiểm tra visibility, quyền mở module và access context |
| Bản thân method được gọi ném lỗi | **InvocationTargetException** | Đọc **getCause()** hoặc **getTargetException()** để xử lý ngoại lệ thật từ method |
| Đối tượng/kiểu liên quan không hợp lệ | **NullPointerException**, **LinkageError** hoặc lỗi runtime khác theo ngữ cảnh | Xác định null nằm ở receiver/đối số hay vấn đề nạp/liên kết lớp; không gom mọi lỗi thành “method không tồn tại” |

Ví dụ, khi method nghiệp vụ ném **IllegalStateException**, **Method.invoke** thường báo **InvocationTargetException** bao bọc lỗi đó; không nên bắt rồi ghi “NoSuchMethodException” hoặc bỏ mất cause. **getMethod** thành công cũng không bảo đảm **invoke** sẽ thành công trên mọi đối số.

Đối với hệ thống nhận tên method từ JSON, HTTP hoặc plugin, hãy dùng **allowlist chữ ký**, kiểm tra số đối số và kiểu sau parse, từ chối tên không được phép, giới hạn surface Reflection. Không nên cho đầu vào không đáng tin tự do gọi bất kỳ method public nào của một object.

## 9. Câu hỏi tự kiểm tra

**1.** Một biến khai báo **Number n = Integer.valueOf(9)**. Lớp có hai overload **f(Number)** và **f(Integer)**. Lời gọi Java thường **f(n)** chọn overload nào?

**Đáp án:** **f(Number)** vì kiểu tĩnh của biểu thức n là Number. Object thực tế Integer không làm compiler chọn lại overload lúc chạy.

**2.** Có duy nhất **f(Number)**. **getMethod("f", Integer.class)** có tìm được không?

**Đáp án:** Không. Lookup cần đúng **Number.class**; **Integer.class** không được tự “nới” thành kiểu cha.

**3.** Nếu đã có Method của **f(int)**, có thể invoke với **Integer.valueOf(9)** không?

**Đáp án:** Có, khi các điều kiện gọi khác đều hợp lệ. Reflection có thể unbox Integer thành int ở bước **invoke**. Nhưng lookup **getMethod("f", Integer.class)** vẫn không tìm ra **f(int)**.

**4.** **f(String... values)** được tra cứu bằng **String.class** hay **String[].class**?

**Đáp án:** **String[].class**, vì varargs là array ở mức formal parameter của method.

**5.** **getDeclaredMethod("secret", String.class)** đã tìm được private method. Điều này có bảo đảm **invoke** thành công từ module bất kỳ?

**Đáp án:** Không. Lookup và access check là hai bước riêng; module/visibility có thể ngăn truy cập.

**6.** **Parent.call(Object)** bị **Child** override. Dùng Method của **Parent.call(Object)** và receiver Child thì luôn chạy Parent không?

**Đáp án:** Không. Với instance virtual method, **Method.invoke** thực hiện dynamic method dispatch, nên override của Child có thể được gọi.

**7.** Tại sao quét **getMethods()**, lọc cùng tên và lấy phần tử đầu tiên lại sai?

**Đáp án:** Không có thứ tự được bảo đảm, nhiều overload có thể cùng tên; còn có vấn đề phạm vi, inheritance, bridge/synthetic methods. Việc chọn overload cần chữ ký/policy rõ ràng.

## Ghi nhớ

- **getMethod / getDeclaredMethod** tìm bằng **tên + Class<?> của các formal parameters theo đúng thứ tự**. Đây là **exact signature lookup**.
- **Method.invoke** thực thi **Method đã chọn**; nó có một số chuyển đổi đối số hợp lệ nhưng **không giải lại overload**.
- **Overload resolution** của Java compiler dựa trên **kiểu tĩnh**, còn **override dispatch** của instance method có thể dựa trên lớp thực tế của receiver.
- **arg.getClass()** không phải bộ giải overload: nó bỏ qua null, kiểu cha/interface, primitive, varargs, generic erasure và trường hợp mơ hồ.
- Khi phải chọn method từ dữ liệu runtime, ưu tiên **hợp đồng chữ ký explicit hoặc registry Method cho phép**; nếu phải tự phân giải, cần định nghĩa chính sách áp dụng/độ đặc hiệu/lỗi mơ hồ một cách kiểm chứng được.

## Tài liệu tra cứu

- Java SE 17, **java.lang.Class** (getMethod, getDeclaredMethod, getMethods, getDeclaredMethods): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- Java SE 17, **java.lang.reflect.Method** (invoke, isVarArgs, isBridge, getParameterTypes): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html
- Java Language Specification, **15.12 Method Invocation Expressions**, đặc biệt **15.12.2 Compile-Time Step 2: Determine Method Signature**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.2
- Java Language Specification, **8.4 Method Declarations**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4
