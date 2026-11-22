# Đối chiếu chữ ký thực tế với biểu thức pointcut

## 1. Mục tiêu và bản chất của việc đối chiếu

Khi một advice không chạy, chạy sai phương thức hoặc chạy quá rộng, câu hỏi đầu tiên không phải “advice viết đúng chưa?” mà là **join point đang xảy ra có thật sự khớp với pointcut hay không?** Muốn trả lời, phải đối chiếu ba thành phần độc lập:

1. **Join point cần bắt:** sự kiện đang xét là *gọi phương thức* (`call`), *thực thi phương thức* (`execution`), đọc/ghi trường hay sự kiện khác?
2. **Chữ ký thực tế:** tên phương thức, kiểu khai báo, kiểu trả về, danh sách kiểu tham số, visibility, `static` và những chi tiết khác mà bộ dệt (weaver) thực sự nhìn thấy.
3. **Biểu thức pointcut:** mẫu chữ ký, điều kiện về vị trí mã, đối tượng/đối số lúc chạy, annotation và tổ hợp điều kiện.

Một phương thức có thể tồn tại, được gọi thành công và vẫn **không** khớp một pointcut. Ngược lại, pointcut dùng ký tự đại diện quá rộng có thể khớp hàng trăm vị trí không mong muốn. Đây là vấn đề chẩn đoán AOP nói chung; các ví dụ dùng **cú pháp pointcut của AspectJ** để có quy tắc cụ thể và khả năng kiểm chứng. Không nên suy rộng nguyên xi cú pháp đó sang mọi công cụ AOP: mỗi hệ thống chỉ hỗ trợ tập join point và cơ chế weaving mà nó định nghĩa.

### Những dấu hiệu hay gặp

- Không xuất hiện log của `before()` dù code trong phương thức đã chạy.
- Pointcut dự kiến bắt một overload nhưng lại bắt nhiều overload, hoặc bỏ sót overload.
- Pointcut `call(...)` và `execution(...)` cho số sự kiện khác nhau.
- Một phương thức khi gọi qua kiểu interface, lớp con hoặc qua đường gọi nội bộ cho kết quả khó hiểu.
- Biểu thức đúng về mặt cú pháp nhưng không có join point tương ứng trong tập class được dệt.

**Nguyên tắc điều tra:** quan sát chữ ký thực tế và loại join point trước; đối chiếu từng phần của mẫu; cuối cùng kiểm tra phạm vi weaving và điều kiện động. Không dùng kết quả của một chuỗi log duy nhất để suy ra mọi nguyên nhân.

## 2. Chữ ký Java, chữ ký join point và vị trí xảy ra sự kiện

Xét đoạn Java:

```java
package demo;

public class OrderService {
    public String place(String code) {
        return "placed:" + code;
    }

    public String place(int number) {
        return "numeric:" + number;
    }

    public void cancel(String code) {
        System.out.println("cancel:" + code);
    }
}
```

Ba phương thức có thể phân biệt bằng các đặc điểm:

| Phương thức | Kiểu trả về | Kiểu khai báo | Tên | Kiểu tham số |
| --- | --- | --- | --- | --- |
| `place(String)` | `java.lang.String` | `demo.OrderService` | `place` | `java.lang.String` |
| `place(int)` | `java.lang.String` | `demo.OrderService` | `place` | `int` |
| `cancel(String)` | `void` | `demo.OrderService` | `cancel` | `java.lang.String` |

**Java phân biệt overload bằng tên và danh sách kiểu tham số**, không bằng kiểu trả về đơn thuần. Nhưng **mẫu chữ ký pointcut** của AspectJ còn có thể ràng buộc kiểu trả về, modifier và kiểu khai báo. Vì thế `execution(String demo.OrderService.place(String))` là một bộ lọc chặt hơn `execution(* demo.OrderService.place(..))`.

**Join point** là một sự kiện có thể chọn để gắn advice, không đồng nhất với một dòng khai báo phương thức:

- `call(String demo.OrderService.place(String))`: điểm gọi phù hợp, gắn với **call site** (vị trí mã có lời gọi).
- `execution(String demo.OrderService.place(String))`: lúc thân phương thức phù hợp bắt đầu thực thi, gắn với **method body**.
- `get(* demo.OrderService.someField)` / `set(* demo.OrderService.someField)`: sự kiện đọc/ghi trường theo mẫu trường, không phải gọi getter/setter.
- `within(demo.OrderService)` kiểm tra nơi mã của join point **được định nghĩa**; `withincode(* demo.OrderService.place(..))` kiểm tra join point nằm trong mã của phương thức đó.

Ví dụ lời gọi `service.place("A01")` nằm trong `demo.Main.main`: với join point `call`, `within(demo.Main)` có thể đúng và `within(demo.OrderService)` sai. Với join point `execution` của `place`, tình huống đảo lại. Vì vậy chỉ nhìn tên phương thức được gọi không đủ để kết luận biểu thức có khớp.

## 3. Đọc chính xác cú pháp mẫu chữ ký

Dạng khái quát cho phương thức trong AspectJ:

```text
execution(modifiers-pattern? return-type-pattern
          declaring-type-pattern?method-name-pattern(parameter-pattern)
          throws-pattern?)
```

Không có nghĩa phải luôn viết hết mọi phần. Ví dụ:

| Mẫu | Cách hiểu |
| --- | --- |
| `execution(* *(..))` | Thực thi phương thức với kiểu trả về, tên và số lượng/kiểu tham số bất kỳ. |
| `execution(String demo.OrderService.place(String))` | Chỉ phương thức có các thành phần chỉ định đúng mẫu. |
| `execution(* demo.OrderService.place(..))` | Mọi overload tên `place` theo mẫu trên kiểu khai báo tương ứng. |
| `execution(* demo.OrderService.place())` | Chỉ overload không có tham số. |
| `execution(* demo.OrderService.place(*))` | Chính xác một tham số, kiểu bất kỳ. |
| `execution(* demo.OrderService.place(String, ..))` | Tham số đầu là `String`, theo sau là 0 hoặc nhiều tham số khác. |
| `execution(public !static * demo.OrderService.*(..))` | Các phương thức public không static trong phạm vi kiểu và tên đã nêu. |
| `execution(* demo..*.place(..))` | Các kiểu phù hợp trong namespace `demo` và các cấp con theo quy tắc mẫu kiểu. |

Phân biệt chính xác các ký hiệu:

- `*` trong vị trí kiểu trả về hoặc tên: đại diện cho phần tử bất kỳ theo **vị trí** đang xét. `place*` khớp những tên bắt đầu bằng `place`, không tự giới hạn ở tên `place`.
- `()`: không tham số; `(*)`: **một** tham số bất kỳ; `(..)`: **0 hoặc nhiều** tham số bất kỳ; `(String, ..)`: từ một tham số, trong đó đầu tiên phải là `String`.
- `..` trong **mẫu package/type** có tác dụng khác `..` trong **danh sách tham số**. Đừng đọc mọi dấu hai chấm thành wildcard chung.
- `+` trong một *type pattern*, ví dụ `demo.BaseService+`, có thể chọn kiểu gốc và các subtype của nó. Không lẫn `+` với biểu thức cộng trong Java.
- `!` phủ định mẫu/điều kiện được phép; `&&` yêu cầu đồng thời; `||` cho phép một trong các điều kiện. Dùng dấu ngoặc để tránh hiểu sai ưu tiên.
- Tên kiểu đầy đủ `java.lang.String` giúp loại trừ nhầm lẫn tên lớp; tên viết ngắn chỉ nên dùng khi môi trường biên dịch và import giải quyết duy nhất.

Ví dụ điểm dễ nhầm:

```text
execution(* demo.OrderService.place(*))
execution(* demo.OrderService.place(..))
```

Dòng thứ nhất có thể khớp cả `place(String)` và `place(int)` vì mỗi phương thức có đúng một tham số. Dòng thứ hai còn có thể khớp thêm overload không tham số hoặc nhiều tham số. Nếu muốn chỉ chọn tham số `String`, phải ghi kiểu `String` thay cho `*`.

**Kiểu trả về cũng là phần so khớp.** `execution(void demo.OrderService.place(..))` không khớp hai phương thức `place` trên vì chúng trả về `String`. Tên phương thức giống nhau không thể “cứu” một return-type pattern sai.

## 4. Bảng đối chiếu minh bạch trước khi kiểm thử

Giả sử class `demo.OrderService` chỉ có ba phương thức ở mục 2 và tất cả đều được dệt cho `execution`. Với ký hiệu ✓ là khớp:

| Pointcut | `place(String)` | `place(int)` | `cancel(String)` | Giải thích |
| --- | :---: | :---: | :---: | --- |
| `execution(String demo.OrderService.place(String))` | ✓ | ✗ | ✗ | Đúng cả tên, return type và tham số. |
| `execution(* demo.OrderService.place(..))` | ✓ | ✓ | ✗ | Tên `place`, mọi overload. |
| `execution(* demo.OrderService.place(*))` | ✓ | ✓ | ✗ | Một tham số nhưng không ràng buộc kiểu. |
| `execution(* demo.OrderService.*(String))` | ✓ | ✗ | ✓ | Mọi tên, đúng một tham số `String`. |
| `execution(void demo.OrderService.*(..))` | ✗ | ✗ | ✓ | Ràng buộc kiểu trả về `void`. |
| `execution(* demo.OrderService.*())` | ✗ | ✗ | ✗ | Không phương thức nào không có tham số. |

Bảng này kiểm **mẫu chữ ký**. Khi pointcut thực tế có thêm `&& within(...)`, `&& args(...)`, `&& target(...)`, annotation hoặc `cflow(...)`, cần lập thêm cột cho từng điều kiện; kết quả của toàn biểu thức là phép giao/hiệp/phủ định tương ứng. Một điều kiện `&&` sai làm cả pointcut không khớp.

## 5. Cách lấy chứng cứ về chữ ký thực tế

### 5.1. Từ mã nguồn: ghi đủ các thành phần

Đối với mỗi phương thức nghi vấn, chép lại dưới dạng có ngữ cảnh:

```text
public java.lang.String demo.OrderService.place(java.lang.String)
public java.lang.String demo.OrderService.place(int)
public void demo.OrderService.cancel(java.lang.String)
```

Đây là bản ghi **để phân tích**, không phải cú pháp pointcut phải copy nguyên trạng. Tên biến `code`, `number` không tham gia so khớp kiểu tham số. Cũng không được dùng kiểu của giá trị truyền vào để thay thế cho chữ ký đã khai báo: `place(Object)` không trở thành `place(String)` chỉ vì đối số thời điểm chạy là một `String`.

### 5.2. Dùng Java Reflection để xem khai báo được runtime tải

Chương trình độc lập sau đây chạy được bằng JDK 17+, không yêu cầu thư viện AOP:

**Tệp `SignatureInspector.java`**

```java
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.Comparator;

public class SignatureInspector {
    static class Example {
        public String place(String code) { return code; }
        public String place(int number) { return Integer.toString(number); }
        protected void cancel(String code) {}
    }

    public static void main(String[] args) {
        Method[] methods = Example.class.getDeclaredMethods();
        Arrays.sort(methods, Comparator.comparing(Method::getName)
                .thenComparing(m -> Arrays.toString(m.getParameterTypes())));

        for (Method m : methods) {
            String params = Arrays.stream(m.getParameterTypes())
                    .map(Class::getSimpleName)
                    .reduce((a, b) -> a + ", " + b)
                    .orElse("");
            System.out.printf("%s %s %s(%s)%n",
                    Modifier.toString(m.getModifiers()),
                    m.getReturnType().getSimpleName(),
                    m.getName(),
                    params);
        }
    }
}
```

Chạy:

```bash
javac SignatureInspector.java
java SignatureInspector
```

Output:

```text
protected void cancel(String)
public String place(String)
public String place(int)
```

`getDeclaredMethods()` cho các phương thức khai báo trực tiếp trên class, có thể bao gồm private và các phương thức do compiler tạo; **không tự bao gồm các phương thức kế thừa**. `getMethods()` nhìn các phương thức public có thể truy cập, bao gồm kế thừa. Các thông tin của `Method` rất hữu ích để xác minh tên, modifier, return type, parameter types; tuy nhiên **Reflection không thay thế quan sát join point được dệt**. Một phương thức xuất hiện trong Reflection vẫn có thể không có advice vì chưa nằm trong phạm vi weaving, vì `call` không có call site được dệt, hoặc vì điều kiện pointcut khác sai.

Khi nghi ngờ overload, generic hoặc bridge, có thể in bổ sung `m.isBridge()`, `m.isSynthetic()`, `m.toGenericString()`. So sánh tiếp bytecode bằng `javap -p -s -c demo.OrderService` khi cần xem descriptor và lời gọi thực tế. Với `javap`, ký hiệu descriptor như `Ljava/lang/String;` là dạng JVM, không phải văn bản đặt trực tiếp vào mẫu AspectJ.

### 5.3. Từ chính một join point AspectJ đã được dệt

Trong advice phục vụ chẩn đoán, các API `thisJoinPointStaticPart.getKind()` và `getSignature().toLongString()` cho biết loại và chữ ký join point. `thisJoinPoint.getArgs()` cho thấy **giá trị** đối số ở sự kiện đó. Khi in giá trị, lưu ý có thể chứa dữ liệu nhạy cảm, đối tượng lớn hoặc `toString()` gây tác dụng phụ.

**Tách rõ hai tầng chứng cứ:** Reflection/bytecode xác minh thành viên và đường gọi; thông tin join point xác minh sự kiện mà weaver đã bắt được. Không dùng một tầng làm bằng chứng tuyệt đối cho tầng kia.

## 6. Ví dụ AspectJ native: tái hiện lỗi và sửa pointcut

Ví dụ này dùng **AspectJ source weaving** (tệp `.aj`, trình biên dịch `ajc`), không cần container/framework. Cấu trúc:

```text
demo/
  OrderService.java
  Main.java
  Trace.aj
```

**Tệp `demo/OrderService.java`**

```java
package demo;

public class OrderService {
    public String place(String code) {
        return "placed:" + code;
    }

    public String place(int number) {
        return "numeric:" + number;
    }

    public void cancel(String code) {
        System.out.println("cancel:" + code);
    }
}
```

**Tệp `demo/Main.java`**

```java
package demo;

public class Main {
    public static void main(String[] args) {
        OrderService service = new OrderService();
        System.out.println(service.place("A01"));
        System.out.println(service.place(7));
        service.cancel("A01");
    }
}
```

**Tệp `demo/Trace.aj`**

```java
package demo;

public aspect Trace {
    before(): execution(String demo.OrderService.place(String)) {
        System.out.println("[pointcut] place(String)");
    }
}
```

Cài **AspectJ compiler `ajc` hỗ trợ Java 17** (AspectJ 1.9.8 trở lên) và bảo đảm `aspectjrt.jar` tương ứng có trên classpath. Với hệ thống Unix-like đặt `ASPECTJ_HOME` tới thư mục cài AspectJ, dùng:

```bash
ajc -17 -classpath "$ASPECTJ_HOME/lib/aspectjrt.jar" -d out demo/OrderService.java demo/Main.java demo/Trace.aj
java -cp "out:$ASPECTJ_HOME/lib/aspectjrt.jar" demo.Main
```

Trên Windows, chuyển dấu ngăn cách classpath từ `:` sang `;` và dùng cú pháp biến môi trường phù hợp với shell. Lệnh trên yêu cầu `ajc` có trong `PATH`; chạy bằng `javac` đơn thuần sẽ không biên dịch cú pháp `aspect`/`before` của `.aj`.

Stdout dự kiến của mã nguồn nêu trên, khi weaving thành công:

```text
[pointcut] place(String)
placed:A01
numeric:7
cancel:A01
```

Điểm đáng quan sát: advice chạy trước `place(String)`; `place(int)` không bị bắt dù cùng tên; `cancel(String)` không bị bắt dù cùng kiểu tham số. **Đây là bằng chứng đối chiếu mẫu, không phải bằng chứng rằng mọi loại lời gọi đều đã được instrument.**

Thử lần lượt các thay đổi độc lập (mỗi lần chỉ sửa đúng biểu thức trong `Trace.aj`, biên dịch lại rồi chạy):

1. `execution(* demo.OrderService.place(..))`: in log trước **cả hai** overload `place`.
2. `execution(* demo.OrderService.place(String))`: chỉ log overload `String`; bỏ ràng buộc kiểu trả về nhưng vẫn giới hạn tham số.
3. `execution(* demo.OrderService.place())`: không log; biểu thức hợp lệ nhưng không có overload không tham số.
4. `execution(void demo.OrderService.place(String))`: không log; sai return type.
5. `execution(* demo.OrderService.*(String))`: log cho `place(String)` **và** `cancel(String)`.

Các phép thử đó cố ý thay **một điều kiện** tại một thời điểm: nếu sửa đồng thời return type, tên và tham số, ta không biết thành phần nào làm tập join point thay đổi. Hãy ghi mẫu, join point dự kiến, kết quả thực tế vào bảng rồi so sánh.

## 7. Khi chữ ký đúng nhưng pointcut vẫn không khớp

### 7.1. Nhầm `call` và `execution`

`call(...)` chọn sự kiện tại mã **gọi**; `execution(...)` chọn sự kiện vào **thân phương thức**. Với một call site ở class A gọi method class B:

- `call(...) && within(A)` có thể khớp nếu call site ở A.
- `execution(...) && within(B)` có thể khớp nếu thân phương thức định nghĩa ở B.
- Việc weaving chỉ đưa B vào phạm vi mà không đưa A vào có thể cho kết quả khác khi thử `execution` và `call`.
- Một thân phương thức có thể chạy nhiều lần từ nhiều call site; điểm dệt và số lần sự kiện quan sát cần được phân biệt.
- `call` không quan sát mọi chuyển điều khiển giống `execution`: chẳng hạn lời gọi `super` tới instance method có các quy tắc join point đặc biệt.

Khi chẩn đoán, đánh dấu rõ **file chứa lời gọi**, **file chứa phương thức** và **class nào được biên dịch/dệt**, thay vì suy từ tên method.

### 7.2. Kiểu khai báo, interface, kế thừa và dispatch

Java có **kiểu tĩnh** ở call site và **kiểu thực tế** của đối tượng khi chạy. Biểu thức chữ ký (đặc biệt ở `call`) có thể phụ thuộc chữ ký mà compiler nhìn thấy ở vị trí gọi; `execution` liên quan đến method body thực sự thực thi. Đặc biệt khi phương thức được khai báo ở interface hoặc lớp cha, hãy thu thập:

- Kiểu của biến nhận lời gọi (ví dụ `Service`), kiểu đối tượng (ví dụ `DefaultService`).
- Method được khai báo/override ở đâu, chữ ký của phần khai báo và phần override.
- Mẫu kiểu đang viết là `BaseService`, `BaseService+` hay `ConcreteService`.
- Join point là `call` hay `execution` và đoạn bytecode nào đã được dệt.

Không áp dụng một câu “đổi sang tên class runtime là chắc chắn khớp” cho mọi trường hợp. Thử pointcut chỉ tên method với wildcard trong phạm vi hẹp, sau đó thêm type pattern đủ chính xác.

### 7.3. `args(...)` không phải danh sách tham số của `execution(...)`

`execution(* demo.OrderService.place(String))` kiểm tra **chữ ký khai báo**. `args(String)` kiểm tra **kiểu ngữ cảnh/giá trị đối số phù hợp tại join point** theo ngữ nghĩa pointcut. Ví dụ phương thức khai báo `handle(Object)` nhận một `String` có thể khiến điều kiện động về đối số khác với việc yêu cầu chữ ký `handle(String)`. Điều này đặc biệt quan trọng khi đối số có polymorphism hoặc `null`; không đánh đồng giá trị runtime với parameter type khai báo.

Tương tự, `this(SomeType)` kiểm tra đối tượng thực thi hiện tại trong ngữ cảnh join point, còn `target(SomeType)` kiểm tra đối tượng đích. Tại method call hai đối tượng có thể khác nhau; trong ngữ cảnh static, không có instance `this`. Nếu biểu thức `execution(...) && this(...) && target(...)` không khớp, phải xác minh từng thành phần chứ không chỉ method signature.

### 7.4. Điều kiện vị trí và luồng điều khiển

`within(TypePattern)` lọc phạm vi mã định nghĩa join point; `withincode(MethodPattern)` lọc các join point bên trong vùng mã của method/constructor tương ứng. `cflow(P)` chọn join point nằm trong luồng điều khiển của P (bao gồm P); `cflowbelow(P)` loại chính P. Vì thế hai lần gọi cùng một method, từ hai đường chạy khác nhau, có thể cho kết quả khác dù cùng chữ ký.

Ví dụ `execution(* demo.OrderService.*(..)) && cflow(execution(* demo.Main.trigger(..)))` cần cả phương thức đích lẫn ngữ cảnh luồng điều khiển của `trigger`. Nếu không có trigger phù hợp trong stack, phần chữ ký đúng vẫn không đủ.

### 7.5. Annotation, overload, varargs và generic

- `@annotation(Tracked)` yêu cầu annotation theo quy tắc join point hỗ trợ; phân biệt annotation của phương thức với annotation trên **kiểu**, **tham số** hoặc **đối số lúc chạy**. Kiểm tra target của annotation, `@Retention` và đường weaving thay vì suy từ tên.
- `String... values` trong Java là tham số varargs, ở bytecode về cơ bản có dạng mảng `String[]`. Khi mẫu không khớp, kiểm tra chữ ký biên dịch và cách pointcut biểu diễn kiểu tham số.
- Với `List<String>` và `List<Integer>`, Java generics chịu **type erasure**; đừng giả định runtime có thể phân biệt mọi type argument như ở mã nguồn. Dùng descriptor bytecode và giới hạn của weaver làm cơ sở.
- Override với kiểu trả về hiệp biến hoặc implement generic interface có thể phát sinh **bridge/synthetic methods** do compiler tạo. Đầu ra Reflection hoặc `javap -p -v` giúp nhận diện; số advice chạy thực tế còn phụ thuộc join point, kiểu bytecode, phiên bản và phạm vi weaving.
- Constructor dùng pattern khác method: ví dụ `execution(demo.OrderService.new(..))` để chọn constructor execution; không cố tìm constructor tên `OrderService` như method thông thường. Đọc/ghi field cũng có pattern riêng.
- Modifier như `private`/`protected`/`static` ảnh hưởng mẫu chữ ký và khả năng quan sát join point theo từng weaving mechanism. Một công cụ AOP không hỗ trợ chọn private method không đồng nghĩa với việc cú pháp AspectJ `execution(private * *(..))` sai.

## 8. Quy trình gỡ lỗi theo từng lớp

Đi theo thứ tự sau và ghi chứng cứ ngay tại từng bước:

1. **Chốt hiện tượng:** advice mong đợi chạy ở phương thức nào, lúc gọi hay lúc thực thi, số lần mong đợi là bao nhiêu? Nếu có nhiều overload, liệt kê tất cả.
2. **Xác minh class chạy thật:** đúng bản build/classpath, đúng classloader và đúng bytecode? Nếu vừa sửa source nhưng chưa rebuild, mọi phép đối chiếu sau đó có thể vô nghĩa.
3. **Lấy chữ ký:** đọc khai báo, dùng Reflection/`javap` nếu cần; ghi modifier, return type, declaring type, tên, parameter types, annotation, bridge/synthetic flags.
4. **Tách pointcut:** đánh dấu `call`/`execution`, tách method pattern, lexical scope, runtime context, annotation và control-flow conditions.
5. **Lập bảng đúng/sai cho từng thành phần:** mỗi conjunct `&&` có một cột. Nếu một thành phần sai, giải thích *tại sao*, không sửa ngẫu nhiên các thành phần khác.
6. **Thu hẹp mẫu thử:** trong một môi trường kiểm soát, bắt đầu từ `execution(* demo.OrderService.*(..))` với lớp đích cụ thể, xác nhận có sự kiện rồi lần lượt thêm tên, return type, tham số và modifier. Tránh `execution(* *(..))` trên toàn chương trình đang chạy vì quá nhiều sự kiện và log.
7. **Kiểm tra weaving:** có biên dịch/dệt class đích không, dùng compile-time, post-compile hay load-time weaving, class có được tải trước khi weaver hoạt động không, có exclusion/include nào làm mất class? Bật thông tin weave phù hợp với compiler/weaver, chẳng hạn `ajc -showWeaveInfo` khi khả dụng, thay vì suy từ absence of log.
8. **Đối chiếu số sự kiện:** tạo call site tối giản, chạy một phương thức tại một thời điểm, xem thông tin `thisJoinPointStaticPart` ở điểm đã xác nhận dệt. Tách lỗi pointcut khỏi lỗi advice (exception, filter trong body advice, logger level).
9. **Khôi phục mức ràng buộc đúng:** khi đã biết nguyên nhân, viết lại pointcut đủ chặt, có bài kiểm thử khớp và không khớp, rồi chạy lại trên binary thật.

### Mẫu phiếu chẩn đoán

```text
Mục tiêu:          demo.OrderService.place(String)
Join point kind:   execution
Chữ ký đo được:    public java.lang.String demo.OrderService.place(java.lang.String)
Pointcut đang xét: execution(void demo.OrderService.place(String))
Return type:       FAIL — thực tế String, biểu thức yêu cầu void
Declaring type:    PASS
Method name:       PASS
Parameters:        PASS
Weaving:           class được biên dịch/dệt, xác minh riêng
Kết luận:          pointcut không match vì return-type pattern
Bản sửa:           execution(String demo.OrderService.place(String))
```

Phiếu tương tự có thể dùng cho lỗi scope: `call(... ) && within(demo.OrderService)` ở lời gọi đặt trong `demo.Main` có chữ ký method match nhưng lexical scope fail. Giữ hai kết luận tách biệt.

## 9. Những cách sửa dễ gây lỗi mới

| Cách làm vội | Vì sao nguy hiểm | Cách làm có kiểm chứng |
| --- | --- | --- |
| Thay bằng `execution(* *(..))` và để nguyên trong hệ thống | Khớp rộng, làm nhiễu log và có thể gây overhead. | Giới hạn package/type rồi siết dần return/name/params. |
| Đổi `call` thành `execution` mà không xác định mục tiêu | Thay luôn ngữ nghĩa sự kiện và nơi dệt, có thể làm advice chạy lúc khác. | Xác định muốn quan sát call site hay method body. |
| Nhìn log thiếu rồi kết luận pattern sai | Class có thể chưa được dệt; advice có thể lỗi hoặc log bị lọc. | Xác minh build, weaving, chạy thử pointcut tối giản. |
| So sánh `args(String)` với tham số `Object` rồi xem là mâu thuẫn | Nhầm type động với chữ ký khai báo. | Ghi cả parameter type và runtime argument type. |
| Đọc `(..)` như “một tham số bất kỳ” | Bắt cả phương thức 0/nhiều tham số. | Dùng `(*)` khi chính xác một tham số bất kỳ. |
| Chỉ xem mã nguồn generic | Erasure/bridge làm bytecode khác kỳ vọng. | Dùng Reflection và `javap` để đối chiếu binary. |
| Tin rằng mọi phương thức nhìn thấy ở Reflection đều được advice | Reflection liệt kê method, không chứng minh join point đã dệt. | Kiểm tra weave info và chạy test có điểm gọi cụ thể. |

## 10. Bài luyện tập và tự kiểm tra

Với các phương thức sau (giả sử chúng thực sự có `execution` join point trong phạm vi weaving):

```java
public String find(String id) { return id; }
public String find(long id) { return Long.toString(id); }
public void find() {}
public boolean find(String id, int limit) { return true; }
```

Hãy dự đoán số phương thức khớp từng biểu thức:

1. `execution(* *.find(..))` → **4**; không ràng buộc kiểu trả về, tham số.
2. `execution(String *.find(*))` → **2**; hai overload một tham số trả về `String`.
3. `execution(* *.find(String))` → **1**; chính xác một tham số `String`.
4. `execution(* *.find(String, ..))` → **2**; `find(String)` và `find(String,int)`.
5. `execution(void *.find())` → **1**; phương thức không tham số trả về `void`.

Mỗi kết quả chỉ dựa trên **mẫu chữ ký** giả định; nếu thêm điều kiện context hoặc giới hạn weaving, kết quả thực tế có thể nhỏ hơn. Tự thực hành bằng cách đặt các phương thức trong một class riêng, dệt cùng một aspect rồi so sánh ma trận dự đoán với các sự kiện quan sát.

## 11. Checklist trước khi kết luận

- [ ] Đã phân biệt `call`, `execution` hay join point loại khác.
- [ ] Đã ghi chữ ký *đầy đủ* (modifier, return type, declaring type, name, parameter types).
- [ ] Đã giải mã đúng `*`, `()`, `(*)`, `(..)`, `..` ở type pattern và `+`.
- [ ] Đã xét overload, inheritance/interface, generic erasure và bridge khi có liên quan.
- [ ] Đã đánh giá độc lập `within`, `withincode`, `this`, `target`, `args`, annotation và `cflow` nếu biểu thức có chúng.
- [ ] Đã xác minh class/call site được dệt và chạy đúng binary.
- [ ] Đã kiểm thử tối thiểu cả một phương thức **phải match** và một phương thức **không được match**.
- [ ] Pointcut sau sửa đủ hẹp để tránh log sai chỗ và chi phí advice không cần thiết.

**Kết luận:** đối chiếu chữ ký là phép so khớp có cấu trúc giữa *join point kind + chữ ký thật + các điều kiện pointcut + phạm vi weaving*. Khi biết thành phần cụ thể nào không khớp, ta sửa được biểu thức với thay đổi nhỏ, dự đoán được những phương thức bị ảnh hưởng và kiểm chứng kết quả bằng một tình huống có thể lặp lại.

## Tài liệu đọc thêm

- [AspectJ Programming Guide — Pointcuts](https://eclipse.dev/aspectj/doc/released/progguide/semantics-pointcuts.html): ngữ nghĩa các pointcut designator và signature patterns.
- [AspectJ Programming Guide — Join Points and Pointcuts](https://eclipse.dev/aspectj/doc/released/progguide/language-joinPoints.html): ví dụ về `call`/`execution` và tổ hợp điều kiện.
- [AspectJ Development Guide — ajc](https://eclipse.dev/aspectj/doc/latest/devguide/ajc.html): lệnh biên dịch, in thông tin weaving và quản lý tập class đầu vào.
