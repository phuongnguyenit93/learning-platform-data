# 13.5 altMetafactory với bridge, marker interface và yêu cầu tuần tự hóa

Một biểu thức lambda trong Java thường được biên dịch thành điểm gọi `invokedynamic` liên kết bởi `java.lang.invoke.LambdaMetafactory`. Phương thức `metafactory` cơ bản tạo đối tượng thực thi một *functional interface* (giao diện có một abstract method về mặt chức năng). Khi cần **nhiều chữ ký method**, **thêm marker interface**, hoặc **hỗ trợ tuần tự hóa**, JVM và compiler có thể dùng biến thể mở rộng `LambdaMetafactory.altMetafactory`.

Ba tên cần nắm chắc:

- **`FLAG_BRIDGES`:** yêu cầu thêm những phương thức có **cùng tên** nhưng chữ ký JVM khác, cùng ủy quyền tới implementation. Chúng giúp nối các view của một abstract method với những dạng chữ ký cần thích nghi.
- **`FLAG_MARKERS`:** thêm một hoặc nhiều interface vào danh sách interface của lớp lambda được sinh; trường hợp thông dụng là những interface đánh dấu không có abstract method riêng.
- **`FLAG_SERIALIZABLE`:** yêu cầu lambda object hỗ trợ Java serialization theo cơ chế `SerializedLambda`, đồng thời đặt ra yêu cầu quan trọng với lớp *capturing* khi deserialize.

Bài học đi từ mô hình linkage–capture–invocation, giao thức `Object... args`, cách xác minh method signature/marker qua Reflection, đến **giới hạn thực tế của serializable lambda**. Có ba chương trình Java 17+ kiểm chứng: gọi `altMetafactory` thủ công để tạo bridge và marker; lambda intersection type do `javac` sinh và serialize/deserialize thành công; và tình huống **manual altMetafactory có `FLAG_SERIALIZABLE` nhưng không đủ điều kiện deserialize**. Các mã nguồn và `stdout` trong bài có thể dùng để tự chạy.

## 1. LambdaMetafactory liên kết những gì?

`LambdaMetafactory` không đơn thuần là một hàm “new lambda”. Javadoc mô tả ba giai đoạn:

1. **Linkage:** bootstrap nhận `Lookup`, tên abstract method, `MethodType` của factory và implementation handle; kết quả là một `CallSite`.
2. **Capture:** target của `CallSite` được gọi với các biến *captured* (nếu có) để tạo hoặc lấy một *function object* thực thi interface.
3. **Invocation:** một method trên function object được gọi; các captured arguments đã lưu và invocation arguments được chuyển tới implementation.

Luồng hình dung:

```text
class file / linker
  LambdaMetafactory.altMetafactory(lookup, "apply", factoryType, args...)
           |
           v
      CallSite  --getTarget()-->  factory MethodHandle
                                      |
                                capture arguments
                                      |
                                      v
                            object implements Mapper
                                + marker(s)
                                + optional bridge(s)
                                + optional serialization protocol
                                      |
                            mapper.apply(...)
                                      |
                                      v
                           implementation MethodHandle
```

Một `CallSite` có thể được dùng để tạo nhiều function objects; số lần tạo object không bằng số lần liên kết. JVM có thể tối ưu capture không có state để tái sử dụng object; **không dựa vào identity `==`, tên lớp lambda, hashCode mặc định hoặc số lần allocation** để thiết kế nghiệp vụ.

### 1.1. `factoryType` không phải chữ ký của abstract method

Ví dụ interface:

```java
@FunctionalInterface
interface Mapper {
    Object apply(Object value);
}
```

Đoạn khai báo minh họa này không phải chương trình độc lập.

- `factoryType = ()Mapper`: target của CallSite không nhận capture và **trả về Mapper**.
- `interfaceMethodType = (Object)Object`: kiểu bytecode của abstract method `apply` trên Mapper.
- `implementation = (String)String`: method thật, có thể là `normalize(String)`.
- `dynamicMethodType = (String)String`: kiểu cụ thể dùng để giới hạn/kiểm tra lời gọi tại runtime.

Bốn yếu tố này **không trùng vai trò**, dù đôi khi chữ ký giống nhau. Với một lambda capture biến `prefix`, `factoryType` có thể là `(String)Mapper` thay vì `()Mapper`, vì caller phải cung cấp prefix khi tạo object. Method `apply` của object vẫn chỉ nhận tham số nghiệp vụ `value`.

## 2. Chữ ký `altMetafactory` và vị trí từng argument

API Java 17:

```java
public static CallSite altMetafactory(
        MethodHandles.Lookup caller,
        String interfaceMethodName,
        MethodType factoryType,
        Object... args) throws LambdaConversionException
```

Đây là chữ ký API, không phải tệp Java độc lập. Dù `args` là `Object...`, Javadoc định nghĩa **một giao thức nghiêm ngặt về vị trí và kiểu**, diễn giải như sau:

```text
args[0] = interfaceMethodType       // MethodType: SAM erased
args[1] = implementation            // MethodHandle: direct
args[2] = dynamicMethodType         // MethodType: instantiated SAM
args[3] = flags                     // int (boxed Integer)

nếu flags có FLAG_MARKERS:
    int altInterfaceCount
    Class<?> altInterfaces[altInterfaceCount]

nếu flags có FLAG_BRIDGES:
    int altMethodCount
    MethodType altMethods[altMethodCount]
```

**Thứ tự cố định:** bốn tham số bắt buộc → **marker count + interfaces** nếu có marker flag → **bridge count + MethodTypes** nếu có bridge flag. `FLAG_SERIALIZABLE` không có count và không làm xuất hiện nhóm args phụ.

| Đầu vào | Kiểu | Ý nghĩa |
| --- | --- | --- |
| `caller` | `MethodHandles.Lookup` | Lookup của lớp chứa site, phải có quyền thích hợp (*full privilege access*) |
| `interfaceMethodName` | `String` | Tên method trừu tượng được implement, ví dụ `"apply"` |
| `factoryType` | `MethodType` | Input ở capture và kiểu interface trả về từ factory CallSite |
| `interfaceMethodType` | `MethodType` | Chữ ký chức năng chính của functional interface, thường là erasure |
| `implementation` | `MethodHandle` | **Direct method handle** trỏ tới method hoặc constructor thật |
| `dynamicMethodType` | `MethodType` | Chữ ký instantiated có thể hẹp hơn ở kiểu tham chiếu |
| `flags` | `int` | Bitwise OR của `FLAG_BRIDGES`, `FLAG_MARKERS`, `FLAG_SERIALIZABLE` |
| `altInterfaceCount` + interfaces | `int` + `Class<?>` | Danh sách interface bổ sung, chỉ có nếu bật `FLAG_MARKERS` |
| `altMethodCount` + method types | `int` + `MethodType` | Danh sách chữ ký method bổ sung, chỉ có nếu bật `FLAG_BRIDGES` |

Cú pháp lời gọi ví dụ, khi đã chuẩn bị các biến thích hợp:

```java
int flags = LambdaMetafactory.FLAG_MARKERS
          | LambdaMetafactory.FLAG_BRIDGES;

CallSite site = LambdaMetafactory.altMetafactory(
        lookup, "apply", factoryType,
        samType, directImpl, instantiatedType, flags,
        1, Tagged.class,
        1, MethodType.methodType(String.class, String.class));
```

Đây là **đoạn minh họa có biến chưa khai báo**, không phải chương trình độc lập; chương trình đầy đủ ở phần 6.

**Không thêm `markerCount` nếu không bật `FLAG_MARKERS`; không thêm `bridgeCount` nếu không bật `FLAG_BRIDGES`.** Trái lại, nếu bật thì phải cung cấp count (kể cả 0) và đúng số phần tử. Đọc nhầm một `Class` thành `MethodType` hoặc đặt nhóm bridge trước nhóm marker là lỗi cấu trúc protocol, không phải vấn đề generic cast có thể tự sửa.

### 2.1. Kết hợp flags

Không có thứ tự ưu tiên cho ba cờ; kết hợp bằng OR:

```java
int flags = LambdaMetafactory.FLAG_MARKERS
          | LambdaMetafactory.FLAG_BRIDGES
          | LambdaMetafactory.FLAG_SERIALIZABLE;
```

Bảng chuẩn bị `args`:

| `flags` | Phần args sau `samType, impl, instantiatedType, flags` |
| --- | --- |
| `0` | Không có |
| `FLAG_MARKERS` | `markerCount, Marker1.class, ...` |
| `FLAG_BRIDGES` | `bridgeCount, bridgeType1, ...` |
| `FLAG_SERIALIZABLE` | Không thêm count |
| `FLAG_MARKERS \| FLAG_BRIDGES` | Marker group **trước**, bridge group **sau** |
| Cả ba flags | Marker group trước bridge group; không có serialization group |

Số thành phần cần tính **theo cờ**, không cố định cho mọi call. Nhầm mảng các `MethodType` vào một phần tử `Object[]` lồng nhau cũng làm sai protocol. Vì `Object...` hỗ trợ varargs, khi truyền trực tiếp chuỗi args trong Java như ví dụ trên, từng phần tử đi theo đúng thứ tự.

## 3. FLAG_BRIDGES: nhiều chữ ký JVM, một logic implementation

### 3.1. Vì sao cần bridge?

Một interface generic sau *type erasure* có thể có phương thức `apply(Object):Object`, còn logic nghiệp vụ cụ thể làm việc với `String`. Ở JVM, method identity được phân biệt theo name và descriptor; các chữ ký:

```text
apply(Ljava/lang/Object;)Ljava/lang/Object;
apply(Ljava/lang/String;)Ljava/lang/String;
```

là **hai method descriptors khác nhau**. Giao diện chức năng có abstract method kiểu erased, nhưng bộ liên kết có thể cần lớp function object khai báo thêm một phiên bản với chữ ký chuyên biệt. `FLAG_BRIDGES` cho phép yêu cầu các phiên bản method bổ sung cùng gọi vào implementation.

Javadoc nêu đây là cơ chế hỗ trợ tình huống nhiều distinct JVM signatures về mặt ngôn ngữ được xem là cùng chức năng, với thích nghi kiểu tham số/trả về. `altMetafactory` thêm các method **cùng tên `interfaceMethodName`**, không tạo tùy ý method `foo`, `bar` với tên khác.

### 3.2. Phân biệt ba chữ ký

Trong ví dụ:

```text
Mapper.apply:              (Object)Object       <-- interfaceMethodType
implementation.normalize:  (String)String       <-- direct impl MethodHandle
instantiated SAM:          (String)String       <-- dynamicMethodType
additional bridge:         (String)String       <-- altMethods[0]
factory:                   ()Mapper             <-- factoryType
```

`Mapper.apply(Object)` vẫn có thể được gọi từ biến kiểu `Mapper`. Cơ chế tạo lambda dùng instantiated type để kiểm tra/cast đối số thực tế, rồi gọi `normalize(String)`. Bật `FLAG_BRIDGES` làm function class khai báo thêm phiên bản `apply(String)String`. Không cần thêm một Java method nguồn với chữ ký đó.

Khi `mapper.apply(123)` đi qua erased SAM `apply(Object)` và implementation yêu cầu `String`, runtime có thể ném `ClassCastException` theo đường adaptation. Đó **không** phải dấu hiệu “bridge bị lỗi”: sai kiểu tại invocation đã được xác định bởi instantiated method type.

**Điều kiện bridge:** mỗi `MethodType` bổ sung phải có số tham số phù hợp SAM, và tuân thủ các quy tắc type adaptation của metafactory (không phải bất kỳ method type nào cũng được chấp nhận). Không được yêu cầu một method mới nhận hai đối số nếu SAM chỉ có một; cũng không tự động nhân bản implementation bằng tên mới.

### 3.3. Đừng suy diễn từ `Method.isBridge()`

Trong source Java thông thường, compiler sinh *synthetic bridge method* để đáp ứng erasure/override và Reflection có `Method.isBridge()`. Nhưng danh sách **additional bridge signatures** từ `FLAG_BRIDGES` là một yêu cầu protocol; **không có hợp đồng rằng tất cả method bổ sung phải hiển thị `isBridge()==true`**. Chẳng hạn OpenJDK có thể sinh các method đó nhưng không gắn JVM `ACC_BRIDGE` như một compiler-generated bridge cổ điển.

Khi kiểm tra `FLAG_BRIDGES`, ưu tiên:

- Đối chiếu **tên, tham số, kiểu trả về** của những method mà function class thật sự khai báo.
- Đối chiếu call behavior với implementation.
- Khi cần bytecode chi tiết, xem metadata thích hợp, nhưng đừng dựa vào tên lớp lambda hoặc khả năng dump hidden class trong mọi JDK.

## 4. FLAG_MARKERS: mở rộng interface mà không thêm implementation method khác

`FLAG_MARKERS` cho phép thêm danh sách các interface mà function object triển khai. Thông thường đó là **marker interface không có abstract method riêng**, dùng để gắn ngữ nghĩa hoặc phân loại object:

```java
public interface Tagged {}
public interface FastPath {}
```

Đây là các khai báo minh họa. Nếu `factoryType` trả `Mapper` và `altInterfaces` chứa `Tagged.class`, `FastPath.class`, object có thể dùng qua biến `Mapper` mà `mapper instanceof Tagged` và `mapper instanceof FastPath` đều đúng.

**Cẩn trọng:** một marker interface “trống” không khiến logic `Mapper.apply` thay đổi; nó chỉ mở rộng tập interface của object. Nếu interface thêm vào có abstract method **khác tên hoặc chữ ký** mà metafactory không tạo implementation, bạn có thể gặp vấn đề hợp đồng interface, lỗi linkage hoặc `AbstractMethodError` khi gọi. Đừng dùng FLAG_MARKERS như cách tự triển khai mọi method của một interface tùy ý.

Các interface bổ sung phải tuân thủ giới hạn của `altMetafactory`: interface hợp lệ, type visibility, khả năng linkage, kiểu loader/module phù hợp. `Class<?>` trong marker list không phải `Class.forName` string và không được thay bằng tên text.

### 4.1. Marker và giao diện chính không giống nhau

`factoryType.returnType()` xác định **giao diện chính** được trả về khi capture. Nếu trả `Mapper`, ta vẫn ép kết quả của `factory.getTarget().invokeExact()` thành `Mapper`. `Tagged`/`FastPath` không đổi `factoryType` thành một tuple hay giao diện khác.

Với hệ thống plugin, marker có thể dùng cho routing/annotation-like capability detection bằng `instanceof`, nhưng hãy nhớ **marker không tự thực thi các kiểm tra bảo mật hoặc quyền truy cập**. Lớp do factory tạo là implementation detail; không thiết kế logic dựa vào tên lớp được sinh như `$$Lambda`.

## 5. FLAG_SERIALIZABLE: yêu cầu tuần tự hóa thực sự là gì?

`FLAG_SERIALIZABLE` yêu cầu function object triển khai `java.io.Serializable` và có phương thức `writeReplace` trả một đại diện kiểu `java.lang.invoke.SerializedLambda`. Đây là cơ chế serialization của **metadata về lambda factory và captured arguments**, không phải serialize toàn bộ bytecode/class của lambda thành một format lâu dài.

`SerializedLambda` chứa các nhóm dữ kiện:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `capturingClass` | Lớp nơi lambda được capture (theo `caller` và site tương ứng) |
| `functionalInterfaceClass` | Interface chính được biểu diễn bằng tên binary dạng slash |
| `functionalInterfaceMethodName/Signature` | Tên và descriptor SAM |
| `implClass/implMethodName/implMethodSignature` | Implementation method đã liên kết |
| `implMethodKind` | Loại `MethodHandle` trực tiếp trỏ method/constructor |
| `instantiatedMethodType` | Kiểu instantiated của SAM |
| `capturedArgs[]` | Những giá trị được capture khi function object được tạo |

Đường đi khi *serialize*:

```text
lambda object implements Serializable
          |
   ObjectOutputStream.writeObject
          |
   writeReplace()
          |
   SerializedLambda(metadata + capturedArgs)
          |
        bytes
```

Đường đi khi *deserialize*:

```text
ObjectInputStream.readObject
          |
   SerializedLambda.readResolve()
          |
   tìm trong capturing class:
   private/static $deserializeLambda$(SerializedLambda)
          |
   validate metadata hợp lệ + tái tạo lambda
          |
       function object
```

Theo Javadoc, **lớp capturing phải cung cấp `$deserializeLambda$(SerializedLambda)` phù hợp**. Khi `javac` tự sinh bytecode cho serializable lambda expression, compiler thường tạo helper đó cùng kiểm tra identity của lambda site, nhờ vậy roundtrip có thể hoạt động. Nhưng nếu bạn gọi `altMetafactory(..., FLAG_SERIALIZABLE)` **thủ công** mà capturing class không có hook phù hợp, Java có thể serialize ra bytes nhưng **deserialize thất bại**.

### 5.1. “`instanceof Serializable`” chưa đủ

Ba tầng phải tách riêng:

1. Function object được đánh dấu `Serializable`.
2. **Captured state** thực sự có thể serialize (tất cả giá trị bắt được phải xử lý được bởi Java serialization).
3. Capturing class có cơ chế **deserialize và xác thực SerializedLambda** thích hợp.

Bật một flag chỉ giải quyết tầng thứ nhất và hỗ trợ cấu trúc tầng hai/ba. Nếu captured object không serializable, serialization có thể ném `NotSerializableException`. Nếu hook thiếu, không tương thích hoặc metadata đã thay đổi, deserialization có thể thất bại. Nếu package/module/class loader khác với lúc tạo bytes, việc tìm class và xác minh lambda cũng có thể gặp vấn đề.

**Không cam kết tương thích lâu dài:** serializable lambda không phải format schema bền vững cho dữ liệu lưu dài hạn hoặc gửi giữa hai version ứng dụng. Compiler có thể thay tên implementation method, descriptors, bố cục capture, class identity khi code được sửa hoặc build lại. Tránh dùng bytes của lambda như hợp đồng dữ liệu public hoặc message protocol.

### 5.2. Bảo mật deserialization

`SerializedLambda.readResolve` gọi về capturing class. Helper `$deserializeLambda$` cần **kiểm tra metadata** chứ không chấp nhận các tên method/class tùy ý từ stream để dựng MethodHandle có đặc quyền. Nếu muốn custom serializer, nên dùng DTO phiên bản hóa, whitelist các hành vi được phép và ranh giới trust rõ ràng.

Không deserialise object từ nguồn không đáng tin chỉ vì đây là “lambda Java chuẩn”. Java deserialization nói chung có nguy cơ xử lý object graph/phần tử không an toàn; xem xét object input filters hoặc thay bằng format dữ liệu minh bạch khi cần.

### 5.3. Marker Serializable và FLAG_SERIALIZABLE

`java.io.Serializable` chính nó là marker interface, nhưng trong protocol `altMetafactory` **serialization có cơ chế riêng `FLAG_SERIALIZABLE`**. Không nên chỉ thêm `Serializable.class` vào `altInterfaces` rồi giả định roundtrip hoàn tất. Nếu serializability là yêu cầu, phải kiểm tra cả flag, captured args, helper của capturing class và mô hình versioning.

## 6. Ví dụ Java 17+ đầy đủ: bridge + nhiều marker interfaces

Tạo tệp **`AltMetafactoryDemo.java`** với toàn bộ mã sau:

```java
import java.lang.invoke.CallSite;
import java.lang.invoke.LambdaMetafactory;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Arrays;
import java.util.Locale;

public class AltMetafactoryDemo {
    @FunctionalInterface
    public interface Mapper {
        Object apply(Object value);
    }

    public interface Tagged {}
    public interface FastPath {}

    public static String normalize(String value) {
        return value.trim().toUpperCase(Locale.ROOT);
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodHandle implementation = lookup.findStatic(
                AltMetafactoryDemo.class, "normalize",
                MethodType.methodType(String.class, String.class));

        MethodType sam = MethodType.methodType(Object.class, Object.class);
        MethodType instantiated = MethodType.methodType(String.class, String.class);
        MethodType bridge = MethodType.methodType(String.class, String.class);

        int flags = LambdaMetafactory.FLAG_MARKERS
                  | LambdaMetafactory.FLAG_BRIDGES;

        CallSite factory = LambdaMetafactory.altMetafactory(
                lookup, "apply", MethodType.methodType(Mapper.class),
                sam, implementation, instantiated, flags,
                2, Tagged.class, FastPath.class,
                1, bridge);

        Mapper mapper = (Mapper) factory.getTarget().invokeExact();
        System.out.println("factory=" + factory.type());
        System.out.println("mapper=" + mapper.apply("  java  "));
        System.out.println("tagged=" + (mapper instanceof Tagged));
        System.out.println("fast=" + (mapper instanceof FastPath));
        System.out.println("serializable="
                + (mapper instanceof java.io.Serializable));

        System.out.println("methods=" +
                Arrays.stream(mapper.getClass().getDeclaredMethods())
                    .filter(m -> m.getName().equals("apply"))
                    .map(m -> m.getName() + "("
                            + m.getParameterTypes()[0].getSimpleName()
                            + ")->" + m.getReturnType().getSimpleName())
                    .sorted()
                    .toList());

        try {
            mapper.apply(123);
        } catch (ClassCastException error) {
            System.out.println("badInput="
                    + error.getClass().getSimpleName());
        }
    }
}
```

Biên dịch/chạy với JDK 17+:

```bash
javac --release 17 AltMetafactoryDemo.java
java AltMetafactoryDemo
```

`stdout` trên OpenJDK 17+ (các dòng trong chương trình chủ ý không in tên lớp lambda có thể thay đổi):

```text
factory=()Mapper
mapper=JAVA
tagged=true
fast=true
serializable=false
methods=[apply(Object)->Object, apply(String)->String]
badInput=ClassCastException
```

### 6.1. Phân tích từng dòng

- `factory=()Mapper` cho thấy kết quả linkage là factory **không cần captured arguments**; khi capture, target trả `Mapper`.
- `mapper=JAVA` chứng minh lời gọi qua abstract method erased `apply(Object)` được thích nghi sang implementation `normalize(String)`, sau đó trả `String` dưới kiểu `Object`.
- `tagged=true` và `fast=true` xác nhận hai marker interface đã được thực thi về mặt cấu trúc. Chúng không cung cấp method nghiệp vụ bổ sung.
- `serializable=false` vì ví dụ không bật `FLAG_SERIALIZABLE`, interface `Mapper` và marker `Tagged/FastPath` đều không kế thừa `Serializable`.
- `methods=[apply(Object)->Object, apply(String)->String]` chứng minh class kết quả có **hai chữ ký cùng tên `apply`**, tương ứng erased SAM và extra method type từ `FLAG_BRIDGES`.
- `badInput=ClassCastException` vì instantiated type hẹp xuống `String`. `mapper.apply(123)` đi qua erased SAM nhưng không thể chuyển `Integer` thành `String`.

Trong ví dụ, `implementation` tạo bằng `lookup.findStatic` là **direct MethodHandle**. Nó không bị `bindTo`, `asType` hoặc các combinator khác biến thành non-direct handle trước khi truyền vào metafactory. Quy tắc direct method handle là điều kiện của `LambdaMetafactory`; không được thay `implementation` tùy ý bằng một method handle tổng hợp rồi nghĩ mọi JVM phải chấp nhận.

**Không dùng `mapper.getClass().getName()` làm output cố định.** JDK có thể dùng hidden lambda class, tên không thuộc API ổn định. Kết quả tên và metadata nội bộ không nên là public contract.

## 7. Ví dụ Java 17+ đầy đủ: lambda intersection type có serialization

Khi viết mã nguồn Java thay vì tự gọi `altMetafactory`, compiler có thể chuẩn bị đúng bootstrap arguments, interface bổ sung, writeReplace và helper deserialize. Một *intersection cast* vừa yêu cầu `Function` vừa thêm `Tagged` và `Serializable`:

Tạo tệp **`SerializableLambdaDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;
import java.lang.invoke.SerializedLambda;
import java.util.function.Function;

public class SerializableLambdaDemo {
    interface Tagged {}

    static Function<String, String> create(String prefix) {
        return (Function<String, String> & Tagged & Serializable)
                (value -> prefix + value.trim());
    }

    public static void main(String[] args) throws Exception {
        Function<String, String> original = create("id=");
        System.out.println("original=" + original.apply("  A7  "));
        System.out.println("serializable="
                + (original instanceof Serializable));
        System.out.println("tagged=" + (original instanceof Tagged));

        System.out.println("hook="
                + (SerializableLambdaDemo.class.getDeclaredMethod(
                        "$deserializeLambda$", SerializedLambda.class) != null));

        ByteArrayOutputStream buffer = new ByteArrayOutputStream();
        try (ObjectOutputStream output = new ObjectOutputStream(buffer)) {
            output.writeObject(original);
        }

        Object restored;
        try (ObjectInputStream input = new ObjectInputStream(
                new ByteArrayInputStream(buffer.toByteArray()))) {
            restored = input.readObject();
        }

        @SuppressWarnings("unchecked")
        Function<String, String> copy = (Function<String, String>) restored;
        System.out.println("restored=" + copy.apply("  B8 "));
        System.out.println("restoredTagged=" + (restored instanceof Tagged));
    }
}
```

```bash
javac --release 17 SerializableLambdaDemo.java
java SerializableLambdaDemo
```

`stdout`:

```text
original=id=A7
serializable=true
tagged=true
hook=true
restored=id=B8
restoredTagged=true
```

**Điều gì được kiểm tra?**

1. Lambda capture giá trị `prefix="id="`, là một `String` có thể serialize. Kết quả sau deserialize vẫn sử dụng cùng prefix.
2. Function object implements cả `Serializable` lẫn `Tagged`, dù kiểu biến Java là `Function<String,String>`.
3. Compiler sinh helper `$deserializeLambda$(SerializedLambda)` tại capturing class; Reflection trong ví dụ **chỉ kiểm tra sự tồn tại**, không gọi helper bằng input tùy ý.
4. `ObjectOutputStream` ghi đại diện lambda; `ObjectInputStream` gọi logic resolve và tái tạo function object, có thể là một instance khác. So sánh hành vi `apply` mới là điều quan trọng.
5. Trường hợp này có khả năng roundtrip vì chương trình không thay đổi code/compiler metadata giữa serialize và deserialize và captured argument là serializable. **Không suy ra mọi serializable lambda có thể lưu lâu dài qua nâng cấp ứng dụng**.

### 7.1. Xem `altMetafactory` thật trong class file

Chạy:

```bash
javap -v -p SerializableLambdaDemo
```

Tìm trong output:

- Method handle của bootstrap trỏ tới `java/lang/invoke/LambdaMetafactory.altMetafactory`.
- Instruction `invokedynamic` dùng cho lambda trong method `create`.
- `BootstrapMethods` với các static arguments gồm method types, implementation handle và flags/marker data.
- Method `private static java.lang.Object $deserializeLambda$(java.lang.invoke.SerializedLambda)` (chữ ký hiển thị có thể kèm các chi tiết khác).

`javap` chỉ xem class file và bootstrap metadata; nó **không đếm số lần JVM đã thực thi bootstrap** và không chứng minh tương thích serialization giữa những build khác nhau.

Có thể có các instruction `invokedynamic` khác dành cho nối chuỗi qua `StringConcatFactory`. Không nhầm chúng với bootstrap dành cho lambda.

## 8. Ví dụ đối chứng: tự bật FLAG_SERIALIZABLE vẫn có thể deserialize thất bại

Ở đây ta **tự gọi `altMetafactory`** (không có lambda expression serializable trong source của capturing class), rồi serialize function object. Bật flag khiến object implement `Serializable` và `writeReplace` có thể ghi ra `SerializedLambda`; nhưng capturing class **không tự nhiên nhận được helper `$deserializeLambda$`**.

Tạo tệp **`ManualSerializablePitfall.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serializable;
import java.lang.invoke.CallSite;
import java.lang.invoke.LambdaMetafactory;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.util.Arrays;

public class ManualSerializablePitfall {
    interface Mapper { String map(String value); }

    public static String normalize(String value) {
        return value.trim();
    }

    public static void main(String[] args) throws Throwable {
        MethodHandles.Lookup lookup = MethodHandles.lookup();
        MethodType signature =
                MethodType.methodType(String.class, String.class);
        MethodHandle direct = lookup.findStatic(
                ManualSerializablePitfall.class, "normalize", signature);

        CallSite factory = LambdaMetafactory.altMetafactory(
                lookup, "map", MethodType.methodType(Mapper.class),
                signature, direct, signature,
                LambdaMetafactory.FLAG_SERIALIZABLE);

        Mapper mapper = (Mapper) factory.getTarget().invokeExact();
        System.out.println("serializable=" + (mapper instanceof Serializable));
        System.out.println("call=" + mapper.map("  hi  "));

        boolean hasHook =
                Arrays.stream(ManualSerializablePitfall.class.getDeclaredMethods())
                    .anyMatch(m -> m.getName().equals("$deserializeLambda$"));
        System.out.println("hasHook=" + hasHook);

        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        try (ObjectOutputStream out = new ObjectOutputStream(bytes)) {
            out.writeObject(mapper);
        }
        System.out.println("wroteBytes=" + (bytes.size() > 0));

        boolean restored = false;
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(bytes.toByteArray()))) {
            in.readObject();
            restored = true;
        } catch (Exception expected) {
            // Chỉ thử nghiệm thất bại dự kiến: thiếu deserialization hook.
        }
        System.out.println("roundtripSucceeded=" + restored);
    }
}
```

```bash
javac --release 17 ManualSerializablePitfall.java
java ManualSerializablePitfall
```

`stdout` trong môi trường thử nghiệm:

```text
serializable=true
call=hi
hasHook=false
wroteBytes=true
roundtripSucceeded=false
```

**Điểm học tập quan trọng:** file serialization có thể ghi thành công nhưng roundtrip không thành công, do `SerializedLambda.readResolve` không tìm được deserialization hook phù hợp trong capturing class. Ví dụ cố ý bắt `Exception` và in boolean **chỉ để chứng minh thất bại dự kiến**; code sản phẩm không nên nuốt ngoại lệ serialization. Nếu cần log, ghi exception class và cause với ngữ cảnh, không tin dữ liệu từ một stream tùy ý.

Nếu xây runtime framework thật sự cần serializable callback, cách phổ biến an toàn hơn là **không dựa vào serialize Java lambda trực tiếp**: lưu identifier của handler, version schema và dữ liệu capture DTO được phép; khi load, chọn handler từ registry đáng tin và tái tạo callback theo ứng dụng.

## 9. Linkage invariants: vì sao có lúc altMetafactory từ chối?

Javadoc `LambdaMetafactory` mô tả các điều kiện với bốn danh sách kiểu:

- `factoryType` có **K** tham số capture `(D1,...,Dk)` và kiểu trả về interface `Rd`.
- `interfaceMethodType` có **N** tham số chức năng `(U1,...,Un)` và return `Ru`.
- `implementation.type()` có **M** tham số thực tế `(A1,...,Am)` và return `Ra`. Với method instance, handle có receiver trong list tham số.
- `dynamicMethodType` có **N** tham số instantiated `(T1,...,Tn)` và return `Rt`.

Các invariant quan trọng:

```text
K + N = M

factoryType.parameterType(i) == implementation.type().parameterType(i)
    cho i trong các captured inputs (so sánh chính xác loại kiểu)

dynamicMethodType.parameterCount() == interfaceMethodType.parameterCount()

instantiated reference arguments không được rộng hơn theo cách làm mất
hợp đồng của erased SAM; adaptation còn tuân theo JVM/Javadoc rules.
```

Về đầu vào của lời gọi interface, khi `Ti` và `Ui` khác nhau thì chúng phải là reference types và `Ti` là subtype của `Ui`. Return type cũng có quy tắc tương tự: instantiated return phải phù hợp return của SAM (hoặc giống nhau). Các tham số của instantiated SAM cần thích nghi được sang implementation; primitive widening và boxing/unboxing được xét theo những quy tắc cụ thể của metafactory chứ **không** tương đương mọi conversion tùy ý của `MethodHandle.asType`.

Ví dụ hợp lệ ở phần 6:

```text
K = 0                       // factory ()Mapper
N = 1                       // Mapper.apply(Object)
M = 1                       // normalize(String)
K + N = M = 1

SAM (Object)Object
instantiated (String)String  // String subtype Object
impl (String)String          // direct static method
```

Nếu method implementation cần hai tham số mà factory không capture gì còn SAM chỉ có một, `K+N != M` nên linkage không hợp lệ. Nếu `factoryType` trả một class thường không phải interface functional, đó cũng là cấu hình sai. Nếu direct `MethodHandle` bị biến thành adapter non-direct trước khi truyền vào, metafactory có thể từ chối.

### 9.1. Captured receiver có được tính vào K không?

Có. Với implementation instance `StringBuilder.append(String)`, handle sau `findVirtual` mang receiver đầu tiên, ví dụ kiểu `(StringBuilder,String)StringBuilder`. Nếu factory capture receiver `StringBuilder` và SAM có một tham số `String`, khi đó `K=1`, `N=1`, `M=2`. Factory type phải mô tả receiver là input của giai đoạn capture; trong function object, method invocation chỉ còn tham số SAM.

**Không nhầm receiver capture với một bridge hoặc marker.** Những thứ đó độc lập với số lượng captured arguments.

### 9.2. Erased type, instantiated type và bridge type khác gì?

| Thông tin | Thời điểm/vị trí dùng | Ví dụ |
| --- | --- | --- |
| SAM erased `interfaceMethodType` | Method descriptor của functional interface | `(Object)Object` |
| Instantiated `dynamicMethodType` | Kiểm tra/cast ở invocation theo specialization | `(String)String` |
| Direct implementation `MethodHandle` | Code thật sự được ủy quyền | `normalize(String):String` |
| Extra bridge `MethodType` | Bổ sung entry method cùng tên cho function object | `(String)String` |
| Factory `MethodType` | Khi capture tạo function object | `()Mapper` hoặc `(Prefix)Mapper` |

Một người có thể dùng từ “bridge” để chỉ phần thích nghi erased→instantiated hoặc **method bổ sung** do FLAG_BRIDGES tạo; để tránh nhập nhằng, hãy diễn đạt rõ khi nào nói tới *additional method signature*.

## 10. Chọn marker, bridge và serialization theo nhu cầu thật

**Chỉ cần một functional method bình thường**: `metafactory` thường đủ; không thêm flags cho “đẹp” hoặc vì nghĩ altMetafactory luôn nhanh hơn.

**Cần thêm một hay nhiều phiên bản method cùng tên với descriptor khác**: dùng `FLAG_BRIDGES`, bảo đảm mọi signature thích nghi với SAM và implementation, tránh khái niệm “thêm API method tùy ý”.

**Cần interface đánh dấu**: dùng `FLAG_MARKERS` với danh sách interface hợp lệ. Nếu cần method bổ sung thật sự với logic khác, hãy thiết kế class/giao diện/adapter phù hợp thay vì gắn interface có abstract methods vào danh sách marker.

**Cần Java serialization**: `FLAG_SERIALIZABLE` mới là yêu cầu về serializable lambda object, nhưng phải có capturing-class deserializer và captured values serializable, cộng với chính sách version, class loading và security rõ ràng. Với dữ liệu lưu lâu hoặc trao đổi qua mạng, ưu tiên schema riêng thay vì serializing lambda.

**Cần cả ba**: bitwise OR các flags, truyền marker count/group rồi bridge count/group đúng thứ tự. Trước khi tạo CallSite, validate tất cả types và direct implementation. Nếu code sử dụng flag serializable nhưng lớp caller không có hook tương ứng, đừng quảng cáo “roundtrip an toàn” chỉ vì `instanceof Serializable` đúng.

## 11. Quy tắc truy cập, class loader và an toàn khi dùng runtime linker

### 11.1. Lookup và implementation handle

`caller` phải là `Lookup` có full privilege access theo Javadoc. JVM cấp lookup phù hợp khi thực thi `invokedynamic`; còn khi thử nghiệm thủ công trong `main`, `MethodHandles.lookup()` từ class đang gọi có thể đáp ứng. `publicLookup()` thường **không thay thế trực tiếp** được trong những trường hợp này.

`implementation` phải là **direct method handle**, chẳng hạn lấy bằng `Lookup.findStatic`, `Lookup.findVirtual`, `Lookup.findConstructor` hoặc unreflect một direct member theo quy tắc. Một handle đã qua `insertArguments`, `asType` hoặc `filterArguments` thường không còn là direct handle, dù vẫn có thể gọi được. `LambdaMetafactory` không hứa chấp nhận mọi handle gọi được.

### 11.2. Marker interface trong môi trường module/plugin

Các marker phải là interface phù hợp và nhìn thấy/áp dụng được trong ngữ cảnh lớp lambda sinh ra. Khi có nhiều class loader, hai interface **cùng binary name** nhưng do loader khác tạo **không phải cùng một `Class<?>`**. Không dùng class name text làm identity. Plugin loader có thể gây `ClassCastException` hoặc linkage error khi caller/implementation/marker không thuộc các vùng truy cập tương thích.

Cache `CallSite` hoặc function object ở một static map sống lâu cũng có thể giữ class loader của plugin, MethodHandle và captured objects. Đây là **lifetime issue**, không tự được giải quyết bằng marker hoặc bridge.

### 11.3. Ưu tiên giải pháp ở Java source khi có thể

Nếu chỉ muốn một object thực thi `Function<String,String>` và marker/Serializable, intersection cast ở Java source dễ hiểu và được compiler chuẩn bị helper đúng hơn việc tự lắp payload Object...:

```java
Function<String, String> action =
        (Function<String, String> & Tagged & java.io.Serializable)
        (text -> text.trim());
```

Đoạn minh họa này giả định `Tagged` hợp lệ và có import `Function`. Không tự thực thi được nếu thiếu những khai báo đó; dùng `SerializableLambdaDemo` để chạy nguyên tệp.

## 12. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Phương pháp kiểm tra |
| --- | --- | --- |
| `LambdaConversionException` khi tạo CallSite | `factoryType` sai, SAM/instantiated/impl type không hợp lệ, handle không direct, Lookup thiếu quyền hoặc linkage invariant vi phạm | In `factoryType`, `samType`, `impl.type()`, `instantiatedType` và lookup context |
| `ClassCastException` khi gọi qua SAM | Erased SAM nhận `Object`, instantiated type đòi `String` và value không chuyển được | Xem kiểu thực value và `dynamicMethodType` |
| `WrongMethodTypeException` khi gọi factory target | `invokeExact` tại call site có kiểu kết quả/đối số khác `factoryType` | So sánh `factory.getTarget().type()` với kiểu static của lời gọi |
| Marker `instanceof` không đúng | Thiếu `FLAG_MARKERS` hoặc marker list không đúng, nhận object từ factory khác | Xem flags/count/interfaces; test class identity theo loader |
| Method phụ không xuất hiện | Thiếu `FLAG_BRIDGES`/`altMethodCount`, sai thứ tự Object... args | Xem danh sách declared methods và các descriptors |
| `Method.isBridge()==false` | Additional method không nhất thiết mang cờ bytecode `ACC_BRIDGE` | Kiểm tra chữ ký và method behavior thay vì ép phải có isBridge |
| `Serializable==true` nhưng không đọc lại được | Thiếu `$deserializeLambda$` hoặc hook không chấp nhận metadata | Xem capturing class và root exception khi deserialize |
| `NotSerializableException` trong `writeObject` | Một captured argument hoặc object liên quan không serializable | Kiểm tra captured values; thiết kế DTO bất biến/serializable |
| Deserialization fail sau nâng cấp version | Thay đổi implementation method, captured state, class name/descriptor/loader | Không dùng serialized lambda làm schema bền vững |
| Lambda class name thay đổi | JVM sử dụng generated/hidden class, naming không ổn định | Không lưu class name lambda như identifier nghiệp vụ |
| Mismatch `K+N!=M` | Số captured parameters và SAM arguments không đủ cho implementation | Viết rõ `factoryType`, `samType`, `implementation.type()` |
| Thêm một interface có method khác vào markers | Marker không phải nơi implement thêm API methods tùy ý | Dùng interface đánh dấu hoặc class adapter thực sự |
| `javap` thấy nhiều invokedynamic | String concatenation và lambda có bootstrap khác nhau | Đọc `BootstrapMethods` theo từng instruction |
| Hành vi khi serialize khác ý định bảo mật | Java deserialization có thể kích hoạt reconstruction dựa trên metadata | Chỉ nhận trusted data; dùng schema versioned/allowlist |

**Thứ tự debug gợi ý:**

1. Log metadata đầu vào một cách có kiểm soát: `name`, `factoryType`, `samType`, `impl.type()`, `instantiatedType`, `flags`, markerCount, bridgeCount.
2. Xác nhận thứ tự các phần tử `Object... args`. Không nhầm MethodType với Class object hoặc count với flag.
3. Kiểm tra implementation là **direct** và caller có quyền.
4. Tạo CallSite; nếu bị từ chối, xử lý `LambdaConversionException` tại linkage chứ không che bằng cast ở capture.
5. Kiểm tra `site.type()` rồi gọi `site.getTarget().invokeExact(...)` với kiểu **chính xác**.
6. Kiểm tra `instanceof` marker, declared methods và invocation behavior.
7. Với serialization, thử cả **write** và **read**, không dừng ở `instanceof Serializable` hoặc byte array không rỗng; thử thêm failure/rebuild/version change.
8. Nếu đang phân tích compiler output, dùng `javap -v -p` để ghép mỗi instruction `invokedynamic` với đúng bootstrap entry.

## 13. Bài tập thực hành

**Bài 1 — giao thức arguments.** Muốn thêm một marker interface `Audited` và một bridge type `(String)String`. Cần flags gì và thứ tự các args sau bộ ba mandatory?

**Đáp án:** `FLAG_MARKERS | FLAG_BRIDGES`. Sau `samType,impl,dynamicType` là `flags, 1, Audited.class, 1, MethodType.methodType(String.class,String.class)`. Marker group luôn trước bridge group.

**Bài 2 — factory và SAM.** Một lambda không capture và thực thi `Consumer.accept(String)`. `factoryType` nhận mấy đối số? SAM nhận mấy?

**Đáp án:** Factory không capture nên có `0` tham số và return interface `Consumer`; SAM `accept` có `1` tham số, thường descriptor erased là `(Object)void`. `factoryType` và `interfaceMethodType` không phải cùng thứ.

**Bài 3 — bridge và erased method.** Với `Mapper.apply(Object):Object` và implementation `normalize(String):String`, vì sao có thêm `apply(String):String` khi dùng `FLAG_BRIDGES`?

**Đáp án:** Đó là additional method signature được yêu cầu; function object có hai entry methods cùng tên, cùng ủy quyền tới implementation sau adaptation. Erased SAM vẫn tồn tại để đáp ứng interface.

**Bài 4 — marker.** Vì sao `instanceof Tagged` có thể đúng dù `Mapper` không khai báo `extends Tagged`?

**Đáp án:** Vì lớp function object do `altMetafactory` tạo trực tiếp implements các interface được liệt kê khi bật `FLAG_MARKERS`.

**Bài 5 — serialization.** `FLAG_SERIALIZABLE` bật và `writeObject` chạy xong. Có chứng minh `readObject` chắc chắn thành công không?

**Đáp án:** Không. Cần captured values hợp lệ, helper `$deserializeLambda$(SerializedLambda)` ở capturing class, kiểm tra identity và môi trường class loader/version tương thích. Manual `altMetafactory` không tự thêm helper vào class nguồn.

**Bài 6 — invariant.** `factoryType` có K=2 captured arguments, SAM N=1 nhưng implementation handle chỉ có M=2 tham số. Có link được không?

**Đáp án:** Không, vì `K + N = 3 != M = 2`. Phải chọn đúng direct implementation hoặc thiết kế lại capture/functional method arity.

**Bài 7 — method bridge flag.** Nếu Reflection thấy hai declared methods `apply(Object)Object` và `apply(String)String` nhưng `isBridge()` ở method thêm là `false`, có thể kết luận FLAG_BRIDGES bị bỏ qua không?

**Đáp án:** Không. `FLAG_BRIDGES` quy định extra method signatures, không bắt buộc mọi implementation phải gắn cờ ACC_BRIDGE mà `Method.isBridge` nhận diện. Kiểm tra chữ ký/hành vi.

**Bài 8 — captured state.** Một serializable lambda capture `new Object()` vào một closure. Dù lambda implements `Serializable`, serialization có thể thất bại vì sao?

**Đáp án:** `Object` không implements `Serializable` nên khi stream ghi captured argument có thể ném `NotSerializableException`. Cần DTO serializable hoặc không serialize closure này.

**Bài 9 — kiến trúc.** Hệ thống muốn lưu callback “normalize, upper, trim” lâu dài ở database. Nên lưu byte của lambda hay lưu identifier + dữ liệu capture?

**Đáp án:** Ưu tiên identifier/version của handler, schema dữ liệu capture được duyệt và factory tái tạo callback. Serialized lambda phụ thuộc metadata compiler, implementation method, capturing class và class loader nên không phải schema dài hạn ổn định.

## 14. Tài liệu chuẩn để đối chiếu

- Oracle JDK 17 — [`LambdaMetafactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/LambdaMetafactory.html): protocol của `metafactory` và `altMetafactory`, `FLAG_BRIDGES`, `FLAG_MARKERS`, `FLAG_SERIALIZABLE`, linkage invariants và adaptation.
- Oracle JDK 17 — [`SerializedLambda`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/SerializedLambda.html): metadata của lambda được serialize, captured args, `readResolve` và `$deserializeLambda$`.
- Oracle JDK 17 — [`MethodHandle`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandle.html): typed handles, direct handle và `invokeExact` tại call site.
- Oracle JDK 17 — [`MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `findStatic`, `findVirtual`, caller privileges và quyền truy cập.
- Oracle JDK 17 — [`MethodType`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodType.html): factory type, SAM erased/instantiated type và signature checks.
- Oracle JDK 17 — [`ObjectInputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/ObjectInputStream.html): yêu cầu và rủi ro khi deserialize Java objects.
- Oracle JDK 17 — [`javap`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): xem `invokedynamic`, constant pool và `BootstrapMethods`.

**Ghi nhớ:** `altMetafactory` không “tự đoán” interface/method được mở rộng. Bạn phải đưa đúng **SAM erased type**, **direct implementation handle**, **instantiated type**, **flags** và các nhóm count/arguments theo đúng thứ tự. `FLAG_BRIDGES` thêm chữ ký method cùng tên; `FLAG_MARKERS` thêm interface đánh dấu; `FLAG_SERIALIZABLE` kích hoạt serialization protocol nhưng **không miễn yêu cầu `$deserializeLambda$` và serializable captured state**. Kiểm tra cả linkage, capture, invocation và deserialize trước khi tin một function object có đầy đủ khả năng cần thiết.
