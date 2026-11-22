# 7.4. Ảnh hưởng của kiểu biến, phép cast kết quả, `null` và câu lệnh bỏ kết quả

Khi gọi `MethodHandle.invokeExact(...)` hoặc `MethodHandle.invoke(...)`, Java không đối xử với lời gọi như một phương thức thông thường có tham số cố định `Object...` và kiểu trả về `Object`. Đây là hai phương thức **signature-polymorphic**: compiler tạo *chữ ký tại vị trí gọi* (*call-site method descriptor*) từ **kiểu tĩnh của từng đối số** và **cách biểu thức kết quả được sử dụng**.

Hệ quả đáng nhớ: cùng một `MethodHandle`, cùng giá trị đầu vào, nhưng đổi kiểu biến từ `String` sang `Object`, thêm hoặc bỏ cast kết quả, viết `null` trực tiếp, hoặc bỏ hẳn kết quả thành một câu lệnh có thể làm lời gọi **thành công, chuyển đổi động hoặc ném `WrongMethodTypeException`**. Muốn chẩn đoán đúng, phải nhìn **chữ ký bytecode tại call site**, không chỉ nhìn giá trị runtime.

Bài này dùng Java 17+, so sánh `invokeExact` và `invoke`, giải thích trường hợp `null` và `void`, sau đó kiểm chứng bằng chương trình biên dịch/chạy độc lập.

## 1. Hai chữ ký quan trọng: kiểu của handle và kiểu của call site

Mỗi method handle có một kiểu bất biến về mặt giao diện gọi, biểu diễn bằng `MethodType`:

```java
MethodHandle greet = MethodHandles.constant(String.class, "hello");
System.out.println(greet.type()); // ()String
```

`()String` nghĩa là **không nhận tham số**, trả về `String`. Nếu một handle tham chiếu phương thức `String repeat(int n)` trên một instance chưa bind, kiểu của nó có thể là `(Owner,int)String`: receiver ở vị trí tham số đầu tiên; nếu đã `bindTo(owner)` thì có thể là `(int)String`. Muốn biết sự thật, đọc `handle.type()` và từng `parameterType(i)`/`returnType()` của `MethodType`.

Nhưng còn một kiểu thứ hai: **chữ ký mà compiler ghi vào instruction tại nơi gọi**. Với `invokeExact` và `invoke`, compiler không coi lời gọi là “mảng `Object[]` thực sự”; nó tạo descriptor chuyên biệt theo source Java.

Giả sử `greet.type()` là `()String`. Các lời gọi sau đều có **0 tham số**, nhưng **kiểu trả về kỳ vọng khác nhau**:

```java
String a = (String) greet.invokeExact(); // call site: ()String
Object b = (Object) greet.invokeExact(); // call site: ()Object
greet.invokeExact();                     // call site: ()void
```

Chỉ dòng đầu có descriptor khớp chính xác `()String`. Hai dòng sau **biên dịch được nhưng ném `WrongMethodTypeException` khi chạy**. Đây là điều gây bất ngờ nếu chỉ nhìn cả ba như “gọi cùng một handle không có đối số”.

`invokeExact` yêu cầu **chữ ký call site trùng hoàn toàn** `handle.type()`, gồm số lượng tham số, kiểu từng tham số **và kiểu trả về**. `invoke` cho phép thích ứng một số kiểu như `handle.asType(callSiteType)`, kể cả thích ứng kiểu trả về; nó không cam kết mọi chuyển đổi đều hợp lệ.

| Phương thức | Khi call-site type khác `handle.type()` | Khi chuyển đổi hợp lệ |
| --- | --- | --- |
| `invokeExact` | Ném `WrongMethodTypeException`; không tự chuyển đổi | Không áp dụng: chỉ được gọi đúng kiểu tuyệt đối |
| `invoke` | Thử thích ứng kiểu theo quy tắc `asType`; nếu không thể, thường ném `WrongMethodTypeException` | Có thể cast tham chiếu, boxing/unboxing, widening primitive, bỏ kết quả hoặc tạo giá trị mặc định cho kiểu trả về theo quy tắc phù hợp |
| `invokeWithArguments` | Không dùng kiểu call site đặc biệt như hai API trên; đối số đưa vào dưới dạng `Object`/danh sách | Được thiết kế cho trường hợp danh sách đối số động, có overhead và quy tắc chuyển đổi riêng |

Các lời gọi `invokeExact`/`invoke` được khai báo `throws Throwable`. Ví dụ độc lập trong bài dùng `main(String[] args) throws Throwable` để không làm loãng trọng tâm. Trong mã ứng dụng, phải quyết định cách xử lý ngoại lệ theo hợp đồng của method handle.

## 2. Kiểu biến của **đối số** quyết định tham số trong descriptor

Xét handle identity có kiểu `(String)String`:

```java
MethodHandle identity = MethodHandles.identity(String.class);
String text = "A";
Object sameObject = text;
```

Hai biến `text` và `sameObject` trỏ đến **cùng một đối tượng `String`**, nhưng kiểu compile-time khác nhau.

```java
String a = (String) identity.invokeExact(text);       // (String)String: OK
String b = (String) identity.invokeExact(sameObject); // (Object)String: lỗi
String c = (String) identity.invoke(sameObject);      // có thể thích ứng: OK
```

- `a`: tham số tĩnh `String`, kết quả cast trực tiếp `String` → khớp `(String)String`.
- `b`: tham số tĩnh `Object` dù giá trị thật là `String` → call site `(Object)String`, sai chữ ký exact, ném `WrongMethodTypeException` **trước khi method handle thực thi hành vi đích**.
- `c`: `invoke` có thể tạo adapter `(Object)String`, kiểm tra/cast đối tượng đầu vào thành `String`, nên thành công với giá trị đang là `String`. Nếu đối tượng thật không phải `String`, việc chuyển đổi tham chiếu có thể ném `ClassCastException`; đó khác với `WrongMethodTypeException` do descriptor không tương thích.

Có thể ép kiểu ở **đối số** để mô tả call site rõ ràng:

```java
String d = (String) identity.invokeExact((String) sameObject);
```

Phép `(String) sameObject` có thể gây `ClassCastException` *trước* khi method handle được gọi nếu giá trị không tương thích. Khi phép cast thành công, tham số tại call site có kiểu tĩnh `String`. Java không tự dùng kiểu runtime của `sameObject` để thay thế `Object` trong descriptor của `invokeExact`.

Điều này cũng đúng với primitive: một `int` và một `long` có thể cùng biểu diễn số `7`, nhưng `(int)int` và `(long)int` là hai descriptor khác nhau. `invokeExact` không tự widening, boxing hoặc unboxing; `invoke` có thể thích ứng những chuyển đổi mà `asType` hỗ trợ. Một handle nhận `int` không có nghĩa caller có thể truyền mọi kiểu số qua `invoke`.

**Quy tắc thực hành:** Khi lỗi exact, in `handle.type()` và ghi kiểu tĩnh của **từng biểu thức đối số tại source**. Đừng chỉ log `value.getClass()`, vì điều đó bỏ sót việc biến `Object` chứa `String` và không giúp cho primitive hoặc `null`.

## 3. Kiểu biến **nhận kết quả** không tự tạo descriptor trả về mong muốn

Đây là khác biệt tinh tế giữa hai hướng “kiểu biến”.

### 3.1. `String result = handle.invokeExact()` không có nghĩa call site trả `String`

Trong Java 17, nếu lời gọi signature-polymorphic **được dùng như biểu thức nhưng không có cast trực tiếp**, kiểu trả về được compiler chọn là `Object`. Gán kết quả cho biến `String` **không** tự biến call-site return thành `String`:

```java
MethodHandle greet = MethodHandles.constant(String.class, "hello");

// Không biên dịch: biểu thức invokeExact() không cast có kiểu Object.
// String wrong = greet.invokeExact();

Object alsoWrongAtRuntime = greet.invokeExact(); // compile OK, runtime WMT
String correct = (String) greet.invokeExact();    // call site ()String: OK
```

Dòng `Object alsoWrongAtRuntime = ...` biên dịch nhưng kỳ vọng `()Object`, nên `WrongMethodTypeException` nếu handle thực sự là `()String`.

Với `var`, suy luận kiểu biến cũng không cứu được descriptor:

```java
// var result = greet.invokeExact(); // var suy ra Object; runtime WMT
var result = (String) greet.invokeExact(); // var suy ra String; OK
```

**Phân biệt rõ:** kiểu tĩnh của **biểu thức đối số** quyết định từng *parameter type*; còn với **return type** của signature-polymorphic call, quy tắc đặc biệt là **cast trực tiếp, biểu thức thường hoặc câu lệnh**. Không áp dụng suy luận “biến nhận là String thì JVM tự coi lời gọi trả String”.

### 3.2. Cast trực tiếp vào lời gọi trở thành một phần chữ ký

Theo quy tắc Java Language Specification `15.12.3`, nếu toàn bộ lời gọi là **toán hạng trực tiếp của cast**, kiểu dùng để cast (sau erasure khi có generics) quyết định **return type của call-site descriptor**:

```java
String text = (String) greet.invokeExact(); // ()String
Object value = (Object) greet.invokeExact(); // ()Object
int number = (int) intHandle.invokeExact(); // ()int; giả sử intHandle.type() là ()int
```

Lưu ý `(Object) greet.invokeExact()` **không** phải “gọi xong lấy `String` rồi ép lên `Object`”. Với `invokeExact`, cast `Object` làm call site yêu cầu trực tiếp `()Object`; nếu handle trả `String`, lời gọi đã sai trước khi thu được giá trị nào.

Nếu muốn vừa gọi chính xác `()String` vừa gán kết quả vào `Object`, hãy để **cast trong cùng** xác định descriptor:

```java
Object upcast = (String) greet.invokeExact();          // descriptor ()String
Object alsoUpcast = (Object) (String) greet.invokeExact(); // vẫn ()String
```

Compiler sử dụng cast gần lời gọi nhất; việc mở rộng kết quả sau đó là chuyển kiểu của Java bên ngoài phương thức signature-polymorphic. Trái lại, `(String) (Object) greet.invokeExact()` làm cast `Object` gần lời gọi nhất và vẫn gây lỗi exact với `()String`.

### 3.3. Chuyển đổi kiểu phải là quyết định có chủ đích

Nếu thật sự muốn dùng descriptor `()Object` với `invokeExact`, chuyển **kiểu của method handle** một cách tường minh trước khi gọi:

```java
MethodHandle adapted =
        greet.asType(MethodType.methodType(Object.class)); // ()Object
Object result = (Object) adapted.invokeExact();             // OK
```

`asType` tạo handle tương thích kiểu mong đợi (nếu quy tắc chuyển đổi cho phép). Nó không tự chuyển mọi giá trị hoặc khắc phục mismatch về số lượng tham số. `greet` gốc vẫn có `()String`; việc tạo adapter không đổi chính handle ban đầu.

Đối với `invoke`, caller có thể viết `Object result = greet.invoke();` và để adapter tương ứng xử lý chuyển `String` sang `Object`. Đổi từ `invokeExact` sang `invoke` chỉ phù hợp khi **chủ đích** cho phép chuyển đổi, không phải để che khuất sai sót trong hợp đồng kiểu.

## 4. Vai trò của `null`: ba vị trí hoàn toàn khác nhau

### 4.1. `null` làm **đối số**: `null` không có kiểu `String`

Với một *null literal không cast* là đối số của `invokeExact`/`invoke`, compiler dùng kiểu ký hiệu **`java.lang.Void`** cho vị trí đó trong call-site descriptor. Đó là **class `Void`**, không phải kiểu trả về `void`.

```java
MethodHandle identity = MethodHandles.identity(String.class); // (String)String

String correct = (String) identity.invokeExact((String) null); // OK, null
String wrong = (String) identity.invokeExact(null);            // WMT
String accepted = (String) identity.invoke(null);              // OK, null
```

Mã minh họa ở trên cố tình chứa dòng `wrong` sẽ ném lỗi khi chạy; chương trình đầy đủ bên dưới bắt ngoại lệ đó.

- `(String) null`: tham số tại call site là `String`; khớp `(String)String`, kết quả `null` bình thường.
- `null` không cast: tham số tại call site là `Void`; `invokeExact` đòi khớp tuyệt đối nên ném `WrongMethodTypeException`.
- `invoke(null)`: với trường hợp tham số kiểu tham chiếu `String`, thích ứng theo `asType` có thể nhận giá trị `null`, nên lời gọi minh họa trả `null`. Không suy ra rằng mọi kiểu đích hoặc mọi chuyển đổi từ `null` đều hợp lệ.

Một biến có kiểu cụ thể giữ kiểu đó dù giá trị đang là `null`:

```java
String s = null;
String value = (String) identity.invokeExact(s); // OK: (String)String
```

Vì thế `(String) null` và `String s = null` hữu ích khi muốn khai báo rõ chữ ký gọi; `null` trần trong `invokeExact` có thể tạo descriptor không như mong muốn.

### 4.2. `null` làm **kết quả thực tế**: descriptor vẫn phải khớp

Xét handle `()String` trả về `null`:

```java
MethodHandle nullResult = MethodHandles.constant(String.class, null);
String value = (String) nullResult.invokeExact(); // OK, value == null
Object mismatch = (Object) nullResult.invokeExact(); // WrongMethodTypeException
```

Giá trị `null` **không** khiến JVM bỏ qua kiểm tra chữ ký. Trong dòng thứ hai, `()Object` vẫn khác `()String`, nên lỗi phát sinh ngay ở kiểm tra kiểu, dù nếu được gọi thành công thì giá trị là `null`. Nếu cần `Object`, dùng `invoke` hoặc `asType`.

### 4.3. Chính **biến MethodHandle** là `null`

```java
MethodHandle absent = null;
String value = (String) absent.invokeExact(); // NullPointerException
```

Đây là lỗi dereference receiver `null`, khác cả `WrongMethodTypeException` (chữ ký mismatch) lẫn `null` làm đối số/kết quả. Khi chẩn đoán, xác minh handle đã được lookup/khởi tạo trước khi bàn tới `handle.type()`.

### 4.4. `null` và unboxing primitive

`invoke` có thể thêm chuyển đổi từ wrapper sang primitive. Nếu **kết quả wrapper là `null`**, việc unboxing thất bại:

```java
MethodHandle nullableInt = MethodHandles.constant(Integer.class, null);
int count = (int) nullableInt.invoke(); // NullPointerException khi unboxing
```

Lỗi ở đây liên quan **giá trị được chuyển đổi**, không phải “`null` tự gây WrongMethodTypeException”. Để giữ giá trị nullable, yêu cầu `Integer` và kiểm tra `null` trước khi unbox.

## 5. Bỏ kết quả: gọi như một câu lệnh mang return type `void`

Ở một lời gọi đứng một mình thành **expression statement**:

```java
greet.invokeExact();
greet.invoke();
```

Compiler xác định **return type tại call site là `void`**. Điều này ảnh hưởng trực tiếp tới kiểm tra chữ ký:

- Với handle `()String`, `greet.invokeExact();` tạo call site `()void` → **`WrongMethodTypeException`** (handle trả `String`, không khớp kiểu trả `void`).
- Với cùng handle, `greet.invoke();` có thể thích ứng kiểu trả về từ `String` sang `void` bằng cách **bỏ giá trị trả về**; lời gọi được thực thi, kết quả không được dùng.
- Với handle thật sự `()void`, `voidHandle.invokeExact();` mới khớp chính xác. Nếu caller `invoke` yêu cầu `Object` từ handle `()void`, adapter `asType` có thể tạo kết quả tham chiếu mặc định **`null`**, theo quy tắc chuyển đổi từ `void`.

Ví dụ:

```java
MethodHandle noResult =
        MethodHandles.empty(MethodType.methodType(void.class));

noResult.invokeExact();       // OK: ()void
Object value = noResult.invoke(); // OK: ()Object, value == null
```

**Không nhầm “bỏ qua biến nhận kết quả” với “bỏ kết quả bằng câu lệnh”.**

```java
Object ignored = greet.invoke(); // call site ()Object: nhận Object
greet.invoke();                  // call site ()void: bỏ kết quả
```

Cả hai có thể thành công với `invoke` nhưng tạo **hai descriptor khác nhau**. Với `invokeExact`, `Object ignored = greet.invokeExact()` (một biểu thức) cũng khác `greet.invokeExact();` (câu lệnh); cả hai sai với `greet.type() == ()String` vì lần lượt muốn `Object` và `void`.

Nếu một target có side effect nhưng trả giá trị, việc gọi `invoke()` dưới dạng câu lệnh vẫn chạy target và bỏ giá trị khi adaptation hợp lệ. Với `invokeExact()` bị `WrongMethodTypeException` vì return mismatch, target chưa được gọi, nên không thể coi đây là một cách “gọi rồi bỏ kết quả”.

## 6. Primitive, boxing và widening cho kết quả

Với handle trả `int`:

```java
MethodHandle number = MethodHandles.constant(int.class, 7); // ()int

int exact = (int) number.invokeExact(); // OK, ()int
Object boxed = number.invoke();         // OK, ()Object: boxing
long widened = (long) number.invoke();  // OK, ()long: widening
number.invoke();                        // OK, ()void: bỏ kết quả
number.invokeExact();                   // WMT: ()void khác ()int
```

Dòng `number.invokeExact();` cuối cố tình thể hiện lỗi, cần bắt `WrongMethodTypeException` nếu đưa vào chương trình. Các conversion của `invoke` chịu quy tắc `asType`, **không phải bộ chuyển đổi tổng quát**: không tự parse `String` thành số, không mặc nhiên narrowing primitive, không nhận sai arity tùy ý.

Khi thay đổi cast, `invokeExact` không “tự boxing return” để phù hợp:

```java
Object x = (Object) number.invokeExact(); // ()Object, sai với ()int
int y = (int) number.invokeExact();       // ()int, đúng
Object z = (Integer) number.invoke();     // có thể boxing int thành Integer
```

Chẳng hạn khi muốn exact `()Object`, cần chuẩn bị một handle đã `asType(methodType(Object.class))`. Khi chỉ muốn dùng kết quả như `Object`, có thể viết `Object x = (String) greet.invokeExact();` nếu handle trả `String`: cast gần lời gọi xác định descriptor `()String`, còn assignment widening sau đó hợp lệ.

## 7. Ví dụ hoàn chỉnh chạy trên Java 17+

Lưu toàn bộ chương trình dưới tên **`MethodHandleCallSiteDemo.java`**. Ví dụ dùng `MethodHandles.constant` và `identity` để tách rõ vấn đề call site khỏi việc lookup quyền truy cập; từng lỗi mong đợi được bắt riêng.

```java
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.invoke.WrongMethodTypeException;

public class MethodHandleCallSiteDemo {
    public static void main(String[] args) throws Throwable {
        MethodHandle greet = MethodHandles.constant(String.class, "hello");
        System.out.println("type=" + greet.type());

        String exact = (String) greet.invokeExact();
        System.out.println("exact=" + exact);

        try {
            Object wrong = (Object) greet.invokeExact();
        } catch (WrongMethodTypeException e) {
            System.out.println("exactObject=" + e.getClass().getSimpleName());
        }

        try {
            greet.invokeExact();
        } catch (WrongMethodTypeException e) {
            System.out.println("exactStatement=" + e.getClass().getSimpleName());
        }

        Object adapted = greet.invoke();
        System.out.println("invokeObject=" + adapted);
        greet.invoke();
        System.out.println("invokeStatement=ok");

        MethodHandle identity = MethodHandles.identity(String.class);
        String stringArg = "A";
        Object objectArg = stringArg;
        System.out.println("argExact=" + (String) identity.invokeExact(stringArg));

        try {
            String badArg = (String) identity.invokeExact(objectArg);
        } catch (WrongMethodTypeException e) {
            System.out.println("argObjectExact=" + e.getClass().getSimpleName());
        }

        System.out.println("argAdapt=" + (String) identity.invoke(objectArg));
        String typedNull = (String) identity.invokeExact((String) null);
        System.out.println("typedNull=" + (typedNull == null));

        try {
            String wrongNull = (String) identity.invokeExact(null);
        } catch (WrongMethodTypeException e) {
            System.out.println("untypedNullExact=" + e.getClass().getSimpleName());
        }

        String looseNull = (String) identity.invoke(null);
        System.out.println("untypedNullInvoke=" + (looseNull == null));

        MethodHandle nullResult = MethodHandles.constant(String.class, null);
        String actualNull = (String) nullResult.invokeExact();
        System.out.println("returnNull=" + (actualNull == null));

        try {
            Object wrongReturn = (Object) nullResult.invokeExact();
        } catch (WrongMethodTypeException e) {
            System.out.println("returnNullAsObjectExact="
                    + e.getClass().getSimpleName());
        }

        MethodHandle missing = null;
        try {
            String value = (String) missing.invokeExact();
        } catch (NullPointerException e) {
            System.out.println("handleNull=" + e.getClass().getSimpleName());
        }

        MethodHandle number = MethodHandles.constant(int.class, 7);
        int n = (int) number.invokeExact();
        Object boxed = number.invoke();
        long widened = (long) number.invoke();
        number.invoke();
        System.out.println("number=" + n + "," + boxed + "," + widened);

        try {
            number.invokeExact();
        } catch (WrongMethodTypeException e) {
            System.out.println("numberStatementExact="
                    + e.getClass().getSimpleName());
        }

        MethodHandle noResult =
                MethodHandles.empty(MethodType.methodType(void.class));
        noResult.invokeExact();
        System.out.println("voidExact=ok");
        Object fromVoid = noResult.invoke();
        System.out.println("voidInvokeObject=" + fromVoid);

        MethodHandle nullableInt =
                MethodHandles.constant(Integer.class, null);
        try {
            int primitive = (int) nullableInt.invoke();
        } catch (NullPointerException e) {
            System.out.println("nullUnbox=" + e.getClass().getSimpleName());
        }

        MethodHandle asObject =
                greet.asType(MethodType.methodType(Object.class));
        Object exactObject = (Object) asObject.invokeExact();
        System.out.println("adaptExactObject=" + exactObject);
    }
}
```

Biên dịch và chạy trong thư mục chứa file:

```bash
javac --release 17 MethodHandleCallSiteDemo.java
java MethodHandleCallSiteDemo
```

Kết quả **`stdout` chính xác**:

```text
type=()String
exact=hello
exactObject=WrongMethodTypeException
exactStatement=WrongMethodTypeException
invokeObject=hello
invokeStatement=ok
argExact=A
argObjectExact=WrongMethodTypeException
argAdapt=A
typedNull=true
untypedNullExact=WrongMethodTypeException
untypedNullInvoke=true
returnNull=true
returnNullAsObjectExact=WrongMethodTypeException
handleNull=NullPointerException
number=7,7,7
numberStatementExact=WrongMethodTypeException
voidExact=ok
voidInvokeObject=null
nullUnbox=NullPointerException
adaptExactObject=hello
```

**Tại sao các nhóm kết quả như vậy?**

1. `type=()String` là kiểu thật của `greet`. Cast `(String)` cho phép `invokeExact` khớp; cast `(Object)` hoặc gọi như câu lệnh tạo return type khác và ném `WrongMethodTypeException`.
2. `invokeObject` và `invokeStatement` cho thấy `invoke` thích ứng cả trả `Object` lẫn bỏ kết quả `void` từ cùng handle `()String`.
3. `argExact` và `argObjectExact` chứng minh kiểu biến truyền vào quyết định descriptor: cùng giá trị `"A"`, nhưng `String` khác `Object` ở compile time.
4. `typedNull` thành công vì `(String) null` khớp handle `(String)String`; `untypedNullExact` thất bại với `Void`; `untypedNullInvoke` thành công vì kiểu tham chiếu có thể thích ứng trong trường hợp này.
5. `returnNull` và `returnNullAsObjectExact` cho thấy **giá trị kết quả `null` không miễn kiểm tra return descriptor**. `handleNull` là lỗi receiver `null`, còn `nullUnbox` xuất hiện ở conversion sang primitive.
6. `number` chứng minh `invoke` có thể boxing `int` thành `Object`, widening sang `long` và bỏ kết quả; `invokeExact` ở vị trí câu lệnh vẫn đòi `()void` nên thất bại.
7. `voidExact` là lời gọi exact tới handle thật sự trả `void`. `voidInvokeObject=null` là kết quả thích ứng `void` → `Object`. `adaptExactObject` thể hiện cách chủ động thay type của handle trước khi gọi exact `()Object`.

Chương trình **không** minh họa việc mọi handle đều có thể được adapt sang mọi kiểu; khả năng thích ứng phụ thuộc `MethodType`, arity và quy tắc `asType` cụ thể.

## 8. Chẩn đoán `WrongMethodTypeException` theo call site

Khi thấy `WrongMethodTypeException`, hãy kiểm tra theo thứ tự:

1. **Có handle chưa?** Nếu biến handle là `null`, bạn sẽ gặp `NullPointerException` trước khi có thể kiểm tra chữ ký.
2. **Handle yêu cầu type nào?** In `handle.type()`. Kiểm tra arity, parameter types, return type, và adapter đã được áp dụng hay chưa.
3. **Caller đang tạo descriptor nào?** Xem kiểu tĩnh của **từng biểu thức đối số** (bao gồm receiver chưa bind) và cách biểu thức kết quả được sử dụng. Đặc biệt tìm các biến `Object` chứa `String`, `null` không cast, primitive/wrapper và `invokeExact()` đứng một mình.
4. **Có cast trực tiếp vào lời gọi không?** `Object v = handle.invokeExact()` yêu cầu return `Object`; `Object v = (String)handle.invokeExact()` yêu cầu return `String` rồi mới gán lên `Object`.
5. **Mục tiêu thực sự cần exact hay conversion?** Nếu hợp đồng cho phép chuyển đổi, cân nhắc `invoke` hoặc `asType` một cách có chủ đích. Nếu contract đòi exact, sửa đúng cast và kiểu biểu thức ở call site.
6. **Phân biệt WMT với lỗi dữ liệu:** `ClassCastException` có thể xảy ra khi adapter của `invoke` thực hiện cast tham chiếu, `NullPointerException` có thể xảy ra khi unbox `null`, và target có thể ném ngoại lệ nghiệp vụ. Các lỗi này không đồng nhất với sai descriptor.

Bảng đối chiếu cho `MethodHandle h` có `h.type() == ()String`:

| Source Java | Return type tại call site | `invokeExact` | `invoke` |
| --- | --- | --- | --- |
| `String v = (String) h.invokeX();` | `String` | Thành công | Thành công |
| `Object v = (Object) h.invokeX();` | `Object` | `WrongMethodTypeException` | Thành công qua widening reference |
| `Object v = h.invokeX();` | `Object` | `WrongMethodTypeException` | Thành công qua widening reference |
| `h.invokeX();` | `void` | `WrongMethodTypeException` | Thành công, bỏ kết quả |
| `Object v = (String) h.invokeX();` | `String` | Thành công | Thành công |

Trong bảng, `invokeX()` là **ký hiệu minh họa**, thay lần lượt bằng `invokeExact()` và `invoke()` để đọc cột tương ứng; `invokeX` **không phải** tên phương thức có thật của Java.

Với code generic, cast như `(List<String>) h.invokeExact()` (nếu source cho phép unchecked cast) tạo return descriptor theo kiểu **đã erasure**, tức `List`, không mã hóa tham số `String`. Method handle không tự xác minh phần tử của collection. Vì vậy một generic type trong source cũng không đảm bảo an toàn dữ liệu ở runtime.

## 9. Lỗi phổ biến và cách sửa

| Lỗi thường gặp | Hiện tượng | Cách khắc phục |
| --- | --- | --- |
| Chỉ nhìn kiểu runtime của argument | `String` thực tế nhưng biến được khai báo `Object` khiến exact sai | Dùng biến/cast tĩnh đúng kiểu handle cần; hoặc chọn `invoke` nếu cho phép adaptation |
| Cho rằng biến nhận `String` định ra return type | `String x = h.invokeExact()` không biên dịch | Cast **ngay vào invocation**: `String x = (String) h.invokeExact()` |
| Cast kết quả lên `Object` tưởng chỉ là widening sau gọi | `(Object) h.invokeExact()` tạo `()Object` | Dùng `Object x = (String) h.invokeExact()` hoặc adapt handle sang `()Object` |
| Dùng `null` trần trong `invokeExact` | Compiler ghi tham số `Void`, gây WMT với handle đòi `String` | Dùng `(String) null` hoặc biến kiểu `String` đang là `null` |
| Bỏ kết quả của handle có return khác `void` bằng `invokeExact()` | Call site `()void` không khớp | Gọi `invoke()` nếu muốn bỏ kết quả và adapter hỗ trợ, hoặc giữ kết quả bằng cast đúng type |
| Dùng `invoke` rồi tin mọi lỗi sẽ biến mất | Adapter không thể chuyển kiểu hoặc dữ liệu sai loại | Kiểm tra `asType`, arity, primitive conversion và kiểu runtime |
| Thấy `null` rồi kết luận descriptor có thể bỏ qua | `null` result vẫn khiến `()Object` khác `()String` khi exact | Match type trước, xử lý nullable value sau |
| Cho rằng `invokeExact` bao ngoại lệ target như reflection | Code bắt nhầm `InvocationTargetException` | `invokeExact`/`invoke` truyền `Throwable` từ target trực tiếp theo contract; xử lý cause đúng nguồn |
| Dùng `System.out.println(h.invokeExact())` để debug | Lời gọi bên trong không có cast, result descriptor `Object` | In `h.type()` trước; nếu cần in value thì cast trực tiếp đúng return type |

## 10. Bài tập tự kiểm tra

Giả sử:

```java
MethodHandle a = MethodHandles.constant(String.class, "x"); // ()String
MethodHandle b = MethodHandles.identity(String.class);       // (String)String
MethodHandle c = MethodHandles.empty(MethodType.methodType(void.class)); // ()void
```

Các câu sau **độc lập** với nhau, có thể chạy riêng bằng một phương thức khai báo `throws Throwable`:

1. `Object result = (Object) a.invokeExact();` — có thành công không?
2. `Object result = (String) a.invokeExact();` — có thành công không?
3. `a.invokeExact();` và `a.invoke();` — dòng nào phù hợp để bỏ kết quả?
4. `String s = (String) b.invokeExact(null);` — điều gì xảy ra? Nếu thay `null` bằng `(String) null` thì sao?
5. `Object x = c.invoke();` — nhận được gì?
6. `Object raw = "x"; String s = (String) b.invokeExact(raw);` — raw có giá trị `String` thì có đủ không?
7. Nếu `a` trả `null` thay vì `"x"` thì câu 1 có trở thành hợp lệ không?
8. Vì sao `String value = a.invokeExact();` không thể dùng để “bắt” return type `String` cho call site?

**Đáp án:**

1. **Không**: cast trực tiếp `Object` tạo `()Object`; `a.type()` là `()String`, nên exact ném `WrongMethodTypeException`.
2. **Có**: cast gần lời gọi là `String` → descriptor `()String`. Assignment sau đó mở rộng `String` lên `Object` hợp lệ.
3. `a.invokeExact();` đòi `()void` nên ném `WrongMethodTypeException`; `a.invoke();` có thể thích ứng bỏ return và chạy thành công.
4. `null` không cast được xem là tham số `Void`, không khớp `(String)String` nên WMT; `(String) null` khớp và trả `null`.
5. `invoke` thích ứng `void` → `Object`; nhận `null`.
6. Không: kiểu **tĩnh** của `raw` là `Object`, nên exact sai; phải cast đối số `(String)raw` hoặc dùng `invoke` nếu muốn chuyển đổi.
7. Không. `null` làm kết quả không thay đổi `()String` của handle hay `()Object` của call site.
8. Vì lời gọi signature-polymorphic không có cast trực tiếp được compiler coi có result `Object`; không thể gán ngầm `Object` cho `String`. Viết `String value = (String) a.invokeExact();`.

## 11. Nguồn đối chiếu

- [Oracle Javadoc — MethodHandle, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): `type()`, `invokeExact`, `invoke`, chữ ký tại call site, trường hợp `null` không cast, `void` trong statement, `WrongMethodTypeException`.
- [Java Language Specification SE 17, `15.12.3 — Type of a Method Invocation](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.12.3): quy tắc tính compile-time argument types và result type đối với signature-polymorphic method.
- [Oracle Javadoc — MethodType, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): tham số và kiểu kết quả của handle.
- [Oracle Javadoc — MethodHandle.asType, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html#asType(java.lang.invoke.MethodType)): các conversion thích ứng call-site type.

**Ghi nhớ:** `invokeExact` chỉ chạy khi **toàn bộ** descriptor của vị trí gọi, kể cả kiểu trả về, trùng `handle.type()`. Với đối số, **kiểu tĩnh của biểu thức** là quyết định; với kết quả, **cast trực tiếp** có thể đổi return descriptor, **biểu thức không cast** thường trả `Object` và **câu lệnh bỏ kết quả** trả `void`. `null` trần ở đối số mang kiểu `Void`; `null` làm kết quả không miễn kiểm tra kiểu. `invoke` có thể thích ứng qua `asType`, nhưng chỉ khi conversion hợp lệ.
