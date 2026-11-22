# Tra cứu phương thức static, virtual và constructor bằng MethodHandles.Lookup

## 1. Mục tiêu và ngữ cảnh

`java.lang.invoke.MethodHandle` là tham chiếu có kiểu tới một hành vi có thể gọi ở runtime. Trong Java hiện đại, cách thông dụng để tìm handle trỏ tới phương thức hoặc constructor là dùng `MethodHandles.Lookup`. Bài này tập trung vào đúng **ba phép tra cứu**:

- **`findStatic`**: tìm phương thức `static` — gọi mà không cần đối tượng nhận lời gọi.
- **`findVirtual`**: tìm phương thức instance — handle nhận thêm **receiver** ở đối số đầu tiên và dùng cơ chế phân phối phương thức động.
- **`findConstructor`**: tìm constructor — handle được gọi để tạo **đối tượng mới**.

Cả ba API có từ Java 7 và **tiếp tục được hỗ trợ trong Java 17+**. Nội dung và ví dụ ưu tiên Java 17, quyền truy cập của Java Platform Module System (JPMS) và quy tắc gọi có kiểu hiện hành.

**Khi nào cần dùng?** Khi framework, bộ ánh xạ, plug-in hoặc thành phần runtime phải chọn hành vi bằng metadata hoặc cấu hình đã kiểm tra. Với lời gọi biết sẵn lúc biên dịch, code Java trực tiếp, lambda hoặc method reference thường đơn giản hơn.

## 2. Ba mảnh ghép trước khi tra cứu

### 2.1. `MethodHandles.Lookup` — quyền tra cứu

~~~java
import java.lang.invoke.MethodHandles;

MethodHandles.Lookup lookup = MethodHandles.lookup();
~~~

`MethodHandles.lookup()` trả về một `Lookup` có quyền truy cập dựa trên **class nơi nó được gọi**. Nó không mặc nhiên được đọc/thi hành mọi thành viên private của mọi class. Các phép `find...` sử dụng quyền này để xác minh có thể truy cập đối tượng đích.

- `lookup()`: dùng khi tra cứu dựa trên ngữ cảnh class hiện tại.
- `publicLookup()`: dùng cho những thành viên public có thể truy cập công khai trong ngữ cảnh class/module phù hợp.
- `privateLookupIn(targetClass, callerLookup)`: dành cho trường hợp thật sự cần truy cập private khi có quyền phù hợp; trong môi trường module, package có thể cần `opens` theo quy tắc JPMS. Không dùng API này như cách bỏ qua ranh giới bảo mật.

### 2.2. `MethodType` — chữ ký của phương thức

~~~java
import java.lang.invoke.MethodType;

// Phương thức trả int, nhận hai int:
MethodType twoIntsToInt =
        MethodType.methodType(int.class, int.class, int.class);

// Phương thức trả String, nhận một String:
MethodType stringToString =
        MethodType.methodType(String.class, String.class);

// Không có đối số, trả String:
MethodType noArgsToString =
        MethodType.methodType(String.class);
~~~

Đây là **các đoạn đặt trong method Java**, không phải file Java độc lập. Công thức:

~~~text
MethodType.methodType(KIỂU_TRẢ_VỀ, KIỂU_THAM_SỐ_1, KIỂU_THAM_SỐ_2, ...)
~~~

Ví dụ `MethodType.methodType(int.class, int.class, int.class)` được in thành `(int,int)int`. Thứ tự và kiểu là chính xác: `int.class` khác `Integer.class`; `String.class` khác `Object.class`. `MethodType` không chứa **tên** method; tên được truyền riêng cho `findStatic` và `findVirtual`.

### 2.3. `MethodHandle` — hành vi đã tra cứu

~~~java
// Ví dụ minh họa sau khi tạo được handle:
MethodType actual = handle.type();
System.out.println(actual);
~~~

Mỗi handle có kiểu xác định và bất biến. Để gọi qua `invokeExact`, call site phải khớp **số đối số, từng kiểu tham số và kiểu trả về** của `handle.type()`. `invoke` cho phép một số chuyển đổi thông qua `asType`, nhưng không phải chuyển đổi bất kỳ. Những quy tắc này rất quan trọng khi đối chiếu ba loại handle bên dưới.

## 3. Bảng so sánh ba phép tra cứu

| API | Hành vi đích | `MethodType` truyền lúc tra cứu | Kiểu `MethodHandle` thu được |
| --- | --- | --- | --- |
| `lookup.findStatic(C.class, "m", type)` | `static R m(P...)` | `(P...)R` | `(P...)R`; không có receiver |
| `lookup.findVirtual(C.class, "m", type)` | `R m(P...)` của instance | `(P...)R`; **không ghi receiver** | `(C,P...)R`; receiver được thêm ở đầu |
| `lookup.findConstructor(C.class, ctorType)` | `new C(P...)` | `(P...)void` | `(P...)C`; trả đối tượng mới |

`C` là class được tra cứu; `P...` là các kiểu tham số được khai báo và `R` là kiểu trả về. Bảng thể hiện trường hợp điển hình, không có biến thể varargs. Một method/constructor khai báo varargs có thể cho ra handle dạng **variable arity** theo quy tắc riêng; khi cần gọi cố định, xem `asFixedArity()`.

Ba điểm thường nhầm:

1. **`findVirtual` thêm receiver vào *handle kết quả*, không thêm vào `MethodType` dùng tìm kiếm.**
2. **`findConstructor` nhận `void.class` làm kiểu trả về khi tìm**, nhưng handle được gọi sẽ trả về đối tượng class `C`.
3. **`findStatic` không có receiver**; không dùng `findVirtual` để tìm phương thức được khai báo `static`.

## 4. Tra cứu phương thức static: `findStatic`

Chữ ký API:

~~~java
MethodHandle findStatic(
        Class<?> refc, String name, MethodType type)
        throws NoSuchMethodException, IllegalAccessException;
~~~

Ví dụ class có phương thức:

~~~java
public static int add(int a, int b) {
    return a + b;
}
~~~

Tra cứu:

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
MethodHandle addHandle = lookup.findStatic(
        Example.class,
        "add",
        MethodType.methodType(int.class, int.class, int.class));
~~~

Đoạn trên minh họa **bên trong ứng dụng đã có class `Example`** chứa phương thức `public static int add(int,int)`. Nếu class/kiểu không khớp hoặc quyền truy cập không hợp lệ, tra cứu thất bại; đoạn này chưa phải chương trình chạy độc lập.

`addHandle.type()` là `(int,int)int`. Gọi handle:

~~~java
int answer = (int) addHandle.invokeExact(4, 5);
System.out.println(answer); // 9
~~~

Lời gọi `invokeExact` cần một ngữ cảnh `throws Throwable` hoặc `catch` tương ứng, vì lời gọi handle có thể truyền ngoại lệ của target. Cast `(int)` trong biểu thức giúp compiler tạo call site có **kiểu trả về int**, trùng kiểu của handle.

### Tìm đúng overload

Giả sử class có:

~~~java
public static int combine(int x, int y) {
    return x + y;
}

public static String combine(String x, String y) {
    return x + y;
}
~~~

`findStatic` không chọn overload dựa vào đối số truyền ở lần gọi sau; nó tìm theo **tên + `MethodType` chính xác**. Ví dụ:

~~~java
MethodHandle numbers = lookup.findStatic(
        Example.class, "combine",
        MethodType.methodType(int.class, int.class, int.class));

MethodHandle strings = lookup.findStatic(
        Example.class, "combine",
        MethodType.methodType(
                String.class, String.class, String.class));
~~~

Hai đoạn này vẫn giả định `Example` và `lookup` đã được khai báo đúng scope. Nếu khai báo `Integer.class` thay cho `int.class` đối với method nguyên thủy, tra cứu không khớp chữ ký. Nếu muốn đổi kiểu sau khi đã tìm đúng handle, cân nhắc adapter `asType(...)` hoặc dùng `invoke(...)` theo quy tắc chuyển đổi cho phép.

**Static không có phân phối override động:** một phương thức static không được override theo nghĩa virtual dispatch. Khi cần đa hình phụ thuộc **đối tượng thực tế**, dùng method instance qua `findVirtual`.

## 5. Tra cứu phương thức instance: `findVirtual`

Chữ ký API:

~~~java
MethodHandle findVirtual(
        Class<?> refc, String name, MethodType type)
        throws NoSuchMethodException, IllegalAccessException;
~~~

Ví dụ tra cứu `String.substring(int)`:

~~~java
MethodHandle substring = MethodHandles.lookup().findVirtual(
        String.class,
        "substring",
        MethodType.methodType(String.class, int.class));
~~~

`MethodType` khi tìm là `(int)String` vì `substring` là method instance có một đối số `int`, trả `String`. Nhưng handle nhận được có kiểu **`(String,int)String`**: tham số đầu tiên là receiver — chuỗi cần gọi method.

~~~java
String piece = (String) substring.invokeExact("abcdef", 2);
System.out.println(piece); // cdef
~~~

Ví dụ này phải được đặt trong method `throws Throwable` hoặc xử lý lỗi; nó không phải file Java độc lập. Truyền `String` nhận lời gọi trước đối số `int`. Nếu bỏ receiver hoặc dùng một `Object` chứa chuỗi mà không chỉnh kiểu call site tương ứng, `invokeExact` không khớp kiểu.

### Phân phối phương thức động (virtual dispatch)

Giả sử:

~~~java
class Message {
    public String say(String name) {
        return "Hello " + name;
    }
}
class LoudMessage extends Message {
    @Override
    public String say(String name) {
        return "HEY " + name;
    }
}
~~~

Khi tìm `Message.say(String)` bằng `findVirtual(Message.class, ...)`, handle có loại `(Message,String)String`. Lúc thực thi, nếu receiver thực tế là `new LoudMessage()`, JVM sẽ gọi bản `say` đã override trong `LoudMessage`. Kiểu **tham số receiver ở call site** vẫn cần khớp `Message` nếu dùng `invokeExact`.

Đây là khác biệt quan trọng so với `findStatic`: target instance method có thể được dispatch theo class thực của đối tượng, theo quy tắc Java về override và giao diện. Với lời gọi `super` đặc biệt, private method hoặc invocation semantics khác, không tự coi `findVirtual` là thay thế của `findSpecial`.

### Cố định receiver khi cần

~~~java
// virtualSay có kiểu (Message,String)String;
// created là một đối tượng Message đã có.
MethodHandle fixed = virtualSay.bindTo(created);

// fixed có kiểu (String)String:
String result = (String) fixed.invokeExact("Lan");
~~~

`bindTo` tạo một handle mới, cố định đối số tham chiếu đầu tiên (ở đây là receiver). Nó không gọi target ngay lập tức. Những biến `virtualSay` và `created` trong fragment được khai báo ở chương trình đầy đủ phần 7.

## 6. Tra cứu constructor: `findConstructor`

Chữ ký API:

~~~java
MethodHandle findConstructor(Class<?> refc, MethodType type)
        throws NoSuchMethodException, IllegalAccessException;
~~~

Giả sử class:

~~~java
public class Message {
    public Message(String prefix) {
        // Gán trạng thái đối tượng.
    }
}
~~~

Tìm constructor nhận `String`:

~~~java
MethodHandle ctor = MethodHandles.lookup().findConstructor(
        Message.class,
        MethodType.methodType(void.class, String.class));
~~~

**Vì sao `void.class`?** Kiểu tra cứu mô tả chữ ký *của constructor* trong JVM: `(String)void`. Nhưng handle **kết quả** thực hiện thao tác *tạo đối tượng* và có kiểu **`(String)Message`**. Do đó:

~~~java
Message message = (Message) ctor.invokeExact("Hello");
~~~

Đây là các fragment minh họa phải đặt trong đúng scope với class `Message` và method `throws Throwable`. Khác `findVirtual`, constructor **không nhận instance làm receiver**; nó tạo instance mới. Java constructor không được kế thừa như instance method.

Một số điểm thực hành:

- Constructor có `0` tham số: dùng `MethodType.methodType(void.class)` để tìm; handle có kiểu `()C`.
- Constructor quá tải: cần đúng các loại tham số trong `MethodType`; không tự chọn overload theo giá trị truyền ở lần gọi.
- Kiểm tra quyền truy cập constructor và class trước khi tra cứu; constructor private không thể được tìm tùy ý bằng `publicLookup()`.
- Không thể tạo instance bằng cách tra cứu constructor của interface hoặc abstract class như với class cụ thể có thể khởi tạo.
- Khi cần phân phối đa hình giữa các class đã tạo sẵn, giải pháp là method instance/`findVirtual`; constructor luôn gắn với class được tra cứu cụ thể.

## 7. Ví dụ Java 17+ chạy đầy đủ

Ví dụ sau sử dụng ba phép tra cứu, in kiểu handle, chứng minh virtual dispatch, gọi constructor và minh họa sai kiểu của `invokeExact`. Chỉ cần **JDK 17+**, không có dependency bên ngoài.

Tạo file **`LookupMethodsDemo.java`**:

~~~java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class LookupMethodsDemo {
    public static int add(int a, int b) {
        return a + b;
    }

    public static class Message {
        private final String prefix;

        public Message(String prefix) {
            this.prefix = prefix;
        }

        public String say(String name) {
            return prefix + " " + name;
        }
    }

    public static class LoudMessage extends Message {
        public LoudMessage() {
            super("unused");
        }

        @Override
        public String say(String name) {
            return "HEY " + name;
        }
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();

        // Static: đúng tên và chữ ký (int,int)int.
        MethodHandle staticAdd = lookup.findStatic(
                LookupMethodsDemo.class, "add",
                MethodType.methodType(
                        int.class, int.class, int.class));
        System.out.println("static type: " + staticAdd.type());
        System.out.println(
                "static call: " + (int) staticAdd.invokeExact(4, 5));

        // Virtual: kiểu tìm (String)String;
        // kiểu handle kết quả (Message,String)String.
        MethodHandle virtualSay = lookup.findVirtual(
                Message.class, "say",
                MethodType.methodType(String.class, String.class));

        System.out.println("virtual type correct: " +
                virtualSay.type().equals(MethodType.methodType(
                        String.class, Message.class, String.class)));

        Message normal = new Message("Hello");
        Message loud = new LoudMessage();

        System.out.println("virtual normal: " +
                (String) virtualSay.invokeExact(normal, "Lan"));
        System.out.println("virtual override: " +
                (String) virtualSay.invokeExact(loud, "Lan"));

        // Constructor: kiểu tìm (String)void;
        // kiểu handle kết quả (String)Message.
        MethodHandle construct = lookup.findConstructor(
                Message.class,
                MethodType.methodType(void.class, String.class));

        System.out.println("constructor type correct: " +
                construct.type().equals(MethodType.methodType(
                        Message.class, String.class)));

        Message created = (Message) construct.invokeExact("Hi");
        System.out.println("constructor: " + created.say("Minh"));

        // bindTo cố định receiver của virtual handle:
        // (Message,String)String -> (String)String.
        MethodHandle boundSay = virtualSay.bindTo(created);
        System.out.println("bound type: " + boundSay.type());
        System.out.println("bound call: " +
                (String) boundSay.invokeExact("An"));

        // invokeExact đòi kiểu trả về cũng khớp.
        try {
            Object wrong = staticAdd.invokeExact(4, 5);
            System.out.println(wrong);
        } catch (WrongMethodTypeException ex) {
            System.out.println("wrong type: " +
                    ex.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa file:

~~~bash
javac --release 17 LookupMethodsDemo.java
java LookupMethodsDemo
~~~

`stdout`:

~~~text
static type: (int,int)int
static call: 9
virtual type correct: true
virtual normal: Hello Lan
virtual override: HEY Lan
constructor type correct: true
constructor: Hi Minh
bound type: (String)String
bound call: Hi An
wrong type: WrongMethodTypeException
~~~

Giải thích từng nhóm:

1. `findStatic` tìm `add(int,int)`; handle giữ đúng `(int,int)int` và gọi nhận `9`.
2. `findVirtual` tìm `Message.say(String)` với kiểu **không chứa receiver** lúc tra cứu. Phép `type().equals(...)` chứng minh handle đã thêm `Message` ở đầu.
3. `normal` và `loud` đều được khai báo bằng kiểu `Message` để lời gọi `invokeExact` khớp receiver. Receiver `loud` có runtime class `LoudMessage`, do đó lời gọi lấy bản `say` override, in `HEY Lan`.
4. `findConstructor` nhận `(String)void` nhưng handle trả `Message`. Kết quả `created` dùng như một đối tượng Java bình thường.
5. `bindTo(created)` cố định receiver và làm loại handle đổi thành `(String)String`.
6. `Object wrong = staticAdd.invokeExact(4, 5)` yêu cầu call-site return `Object`; handle lại trả `int`. JVM ném `WrongMethodTypeException`; ví dụ bắt có chủ ý để in thông điệp rõ ràng.

Đoạn `main` dùng `throws Throwable` cho minh họa vì `invokeExact` khai báo có thể truyền mọi ngoại lệ từ target. Trong code sản xuất, cân nhắc xử lý lỗi đúng biên ứng dụng và ghi nhận nguyên nhân cụ thể.

## 8. Những lỗi hay gặp khi tra cứu

| Hiện tượng | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| `NoSuchMethodException` từ `findStatic` | Tên sai, kiểu sai, method không phải static hoặc overload không khớp | Kiểm tra method thật và `MethodType`, dùng đúng `findStatic` |
| `NoSuchMethodException` từ `findVirtual` | Tên/chữ ký không khớp hoặc method static | Chỉ truyền các tham số khai báo vào `MethodType`; không thêm receiver tại đây |
| `NoSuchMethodException` từ `findConstructor` | Không tồn tại constructor có danh sách tham số đúng; nhầm return type | Dùng `void.class` khi tạo kiểu lookup, tìm đúng overload |
| `IllegalAccessException` trong lookup | Class, method hoặc constructor không truy cập được theo quyền Lookup/module | Kiểm tra public/private, package, `exports`/`opens` và ngữ cảnh tạo Lookup |
| `WrongMethodTypeException` tại `invokeExact` | Sai arity, receiver, kiểu tham số **hoặc kiểu trả về** | In `handle.type()` và khớp chính xác call-site descriptor |
| `ClassCastException` hoặc lỗi kiểu khi dùng `invoke` | Có adapter nhưng giá trị runtime không tương thích | Kiểm tra quy tắc `asType`/boxing/unboxing/reference casting |
| Class con override nhưng không được gọi như kỳ vọng | Tra cứu nhầm `static` hoặc dùng invocation semantics khác | Dùng `findVirtual` với instance method và receiver runtime phù hợp |
| Truyền sai class receiver cho `invokeExact` | Handle yêu cầu kiểu receiver của class lookup, call-site lại dùng kiểu khác | Khai báo biến receiver theo kiểu `handle.type()`; dùng `asType` khi cần adapter phù hợp |
| Constructor tìm đúng nhưng gọi trả về `Object` | `invokeExact` không tự nới kiểu trả về từ `C` sang `Object` | Cast trực tiếp `(C) ctor.invokeExact(...)` hoặc dùng `invoke`/adapter có kiểm soát |
| `publicLookup()` không đọc được member trong module | Thành viên không public hoặc package không được export đúng cách | Thiết kế API public hợp lệ hoặc cấp quyền qua cơ chế module theo chủ đích |

**Phân biệt thời điểm lỗi:** nhiều lỗi về tên, chữ ký, quyền phát sinh **khi tra cứu handle**; lỗi kiểu call-site phát sinh **khi gọi handle**. Không nên chỉ bắt `Exception` rồi trả `null` vì sẽ che nguyên nhân; chọn cách báo lỗi có đủ thông tin class, tên method và `MethodType` (không để lộ dữ liệu nhạy cảm).

## 9. Lookup, quyền truy cập và thiết kế hiện đại

### Quyền truy cập không tự động được nâng lên

`Lookup` có thể được xem là một capability: nó mang quyền xem/tìm thành viên dựa trên ngữ cảnh. `MethodHandle` trỏ tới member private được tạo hợp lệ có thể dùng về sau kể cả khi code giữ handle không có khả năng tra cứu member ấy. Do đó:

- Đừng phát tán `Lookup` có quyền rộng hoặc handle tới method nhạy cảm cho thành phần không đáng tin.
- Không xây cơ chế nhận tùy ý tên class, method và kiểu từ user input rồi tìm/call mà thiếu danh sách cho phép và kiểm tra ủy quyền.
- Với ứng dụng có module (`module-info.java`), cân nhắc quan hệ module, package `exports` và `opens`; bảo đảm API công khai là ranh giới chủ đích.
- Lưu/caching handle không thay cho đánh giá security policy tại thời điểm sử dụng; quyền nghiệp vụ vẫn phải được kiểm tra riêng.

### Dùng trong framework mà vẫn dễ bảo trì

Một hướng triển khai phổ biến:

~~~text
Metadata đã được xác thực
  -> Xác định class, loại thao tác, tên và MethodType
  -> Lookup.findStatic / findVirtual / findConstructor
  -> Kiểm tra handle.type() và hợp đồng caller
  -> Cache handle theo key đủ đặc trưng khi phù hợp
  -> Gọi trong phạm vi được phép và xử lý lỗi rõ ràng
~~~

Không đoán hiệu năng: MethodHandle có thể được JVM tối ưu tốt tại call site ổn định, nhưng lookup, adaptation, boxing, type checking và mẫu gọi động vẫn có chi phí. Nếu cần tối ưu một hot path, đo bằng benchmark tin cậy trước khi kết luận nó nhanh hơn reflection hoặc lời gọi trực tiếp.

`MethodHandle` là tham chiếu có kiểu, không phải API để liệt kê mọi method hoặc đọc annotation. Khi cần khám phá cấu trúc class, `Class` và `java.lang.reflect` vẫn phù hợp; từ một `Method` đã chọn và được phép truy cập có thể dùng `Lookup.unreflect` nếu cần chuyển sang dạng handle.

### Giới hạn của bài

`findSpecial` phục vụ invocation semantics khác với virtual dispatch thông thường; `findGetter`/`findSetter` phục vụ field, và `VarHandle` dành cho các access mode biến/atomic thích hợp. Đây là những API liên quan nhưng không phải ba phép tra cứu phương thức/constructor đang học. Không coi `findVirtual` là tên chung cho mọi hoạt động gọi method.

## 10. Checklist khi dùng ba API

1. Phân loại hành vi: **static**, **instance virtual** hay **constructor**.
2. Dùng đúng `Lookup` dựa trên quyền thực tế của caller/module; không tự ý vượt quyền.
3. Ghi rõ tên member và `MethodType` chính xác theo chữ ký; phân biệt `int` với `Integer`, class khai báo và overload.
4. Với `findStatic`: không đưa receiver vào kiểu hoặc danh sách tham số gọi.
5. Với `findVirtual`: **kiểu lúc tìm không có receiver**, nhưng lúc gọi handle phải truyền receiver đầu tiên; override dựa vào class runtime của receiver.
6. Với `findConstructor`: **`void.class` trong kiểu lúc tra cứu**, nhưng handle trả object của class được xây.
7. Kiểm tra `handle.type()` trước khi dùng `invokeExact`; khớp cả **kiểu trả về tại call site**.
8. Xử lý tách bạch lỗi **tra cứu** (`NoSuchMethodException`, `IllegalAccessException`) và lỗi **lời gọi** (`WrongMethodTypeException`, exception của target).
9. Không chia sẻ capability nhạy cảm tùy ý; validate metadata động và chính sách truy cập của người gọi.
10. Ưu tiên code Java thông thường khi không cần chọn hành vi ở runtime; đo hiệu năng trước khi thêm cache và adapter phức tạp.

**Ghi nhớ:**

~~~text
findStatic:      (P...)R    -> (P...)R
findVirtual:     (P...)R    -> (C,P...)R
findConstructor: (P...)void -> (P...)C
~~~

Trong cột trái là `MethodType` truyền khi tìm; bên phải là kiểu handle nhận được. Đây là công thức quan trọng nhất để không nhầm receiver và kiểu trả về constructor.

## Tài liệu tham khảo hiện hành

- [Java SE 17 — MethodHandles.Lookup](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findStatic`, `findVirtual`, `findConstructor` và quyền truy cập.
- [Java SE 17 — MethodHandle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `type()`, `invokeExact`, `invoke`, `bindTo` và chuyển kiểu.
- [Java SE 17 — MethodType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): kiểu tham số và kiểu trả về.
- [Java SE 17 — MethodHandles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.html): tạo `Lookup` và phương pháp kết hợp handle.
