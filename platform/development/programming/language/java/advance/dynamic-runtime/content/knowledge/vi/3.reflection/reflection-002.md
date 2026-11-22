# 3.2 Không phụ thuộc thứ tự member do reflection trả về; sắp xếp tường minh theo chữ ký

## 1. Vì sao phải quan tâm đến thứ tự?

Java Reflection cho phép lấy danh sách phương thức, trường và constructor của một lớp. Ví dụ:

```java
Method[] methods = SomeType.class.getDeclaredMethods();
Field[] fields = SomeType.class.getDeclaredFields();
Constructor<?>[] constructors = SomeType.class.getDeclaredConstructors();
```

**Không được suy ra thứ tự của các phần tử này từ thứ tự khai báo trong mã nguồn.** Theo hợp đồng API `java.lang.Class`, các mảng trả về từ `getDeclaredMethods()`, `getMethods()`, `getDeclaredFields()`, `getFields()`, `getDeclaredConstructors()` và `getConstructors()` **không được sắp xếp theo bất kỳ thứ tự xác định nào**. Thứ tự tình cờ nhìn thấy trên một JDK, compiler hay lần chạy không tạo thành bảo đảm cho lần chạy khác.

Ví dụ, nếu lớp khai báo:

```java
void finish() {}
void start() {}
void pause() {}
```

thì `getDeclaredMethods()[0]` **không có nghĩa** là phương thức `finish` hay “phương thức khai báo đầu tiên”. Không thể dựa vào thứ tự “đang thấy đúng” trong log hoặc bài kiểm thử để kết luận có hợp đồng thứ tự.

Hệ quả khi chương trình dùng Reflection để sinh tài liệu, ánh xạ dữ liệu, đăng ký handler, tạo lệnh CLI, kiểm tra snapshot hoặc tính fingerprint: đầu ra có thể bị đảo thứ tự, test chập chờn, diff phát sinh không cần thiết, hoặc nguy hiểm hơn, logic vô tình gọi nhầm member được chọn theo chỉ số.

**Quy tắc:** Nếu thứ tự ảnh hưởng đến kết quả, hãy **chọn quy tắc rõ ràng và sắp xếp trước khi sử dụng**. Nếu đang tìm đúng một member, hãy tra cứu theo tên/chữ ký thay vì chọn vị trí trong mảng.

## 2. Hiểu đúng API và phạm vi của member

| API | Những member được liệt kê | Bảo đảm thứ tự? |
| --- | --- | --- |
| `getDeclaredMethods()` | Method khai báo trong chính lớp/interface, kể cả private, nhưng không gồm method kế thừa; có thể có bridge/synthetic method do compiler tạo. | Không |
| `getMethods()` | Method public nhìn thấy từ lớp/interface, kể cả method kế thừa theo quy tắc API. | Không |
| `getDeclaredFields()` / `getFields()` | Field được khai báo tại lớp / các field public có thể truy cập, gồm phần kế thừa theo quy tắc API. | Không |
| `getDeclaredConstructors()` / `getConstructors()` | Constructor khai báo trong lớp / constructor public của lớp; constructor không được kế thừa. | Không |

Lưu ý sự khác nhau giữa **thứ tự danh sách member** và **thứ tự tham số trong một chữ ký**. `Method.getParameterTypes()` và `Constructor.getParameterTypes()` trả về các kiểu tham số **theo thứ tự khai báo của chính lời gọi đó**. Do đó, `run(String, int)` và `run(int, String)` là hai chữ ký khác nhau, và bạn phải giữ đúng thứ tự khi xây khóa.

Không nên mở rộng quy tắc này thành “mọi API Reflection đều không có thứ tự”: một số API phản ánh những cấu trúc vốn có thứ tự xác định (ví dụ các thành phần của record). Hãy đọc hợp đồng của đúng API được sử dụng.

## 3. “Sắp xếp theo chữ ký” thực sự là sắp xếp theo gì?

### 3.1. Method: tên và danh sách kiểu tham số có thứ tự

Ở mức ngôn ngữ Java, hai overload được phân biệt chủ yếu bằng tên và các kiểu tham số. Ví dụ:

```java
void save(String key) {}
void save(int id) {}
void save(String key, boolean overwrite) {}
```

Chỉ sắp xếp theo `Method::getName` là **chưa đủ**: cả ba cùng tên `save`. Comparator coi chúng bằng nhau ở khóa tên; sắp xếp ổn định sẽ giữ lại thứ tự đầu vào vốn không được bảo đảm.

Một khóa sắp xếp hữu ích:

1. Tên method: `getName()`.
2. Danh sách **kiểu tham số theo đúng vị trí**: `getParameterTypes()`.
3. Kiểu trả về: `getReturnType()`.
4. Lớp khai báo: `getDeclaringClass()`, đặc biệt quan trọng khi kết hợp member từ nhiều lớp hoặc dùng `getMethods()`.

**Vì sao đưa kiểu trả về vào khóa mặc dù Java không cho overload chỉ khác return type?** Bytecode của JVM có thể chứa những method cùng tên và cùng kiểu tham số nhưng khác kiểu trả về, chẳng hạn bridge method được compiler tạo để triển khai generic hoặc covariant return. Javadoc của `getDeclaredMethods()` nói rõ rằng trường hợp này có thể trả về **nhiều `Method`**. Nếu dùng khóa chỉ gồm tên và tham số, chúng sẽ bị coi bằng nhau.

Để hiển thị, chuỗi có thể giống:

```text
save(int):void
save(java.lang.String):void
save(java.lang.String,boolean):void
```

Đây là **khóa hiển thị do ứng dụng định nghĩa**, không phải lời hứa Java Reflection trả về đúng định dạng ấy. Khi cần đối chiếu member giữa nhiều lớp, thêm tên lớp khai báo vào khóa. Khi cần định danh xuyên class loader có các lớp trùng tên, còn phải có ID provider/loader ổn định do ứng dụng quản lý; tên nhị phân của lớp một mình chưa đủ.

### 3.2. Field và constructor có khóa riêng

- **Field:** tên trường `getName()`, kiểu `getType()`; thêm lớp khai báo nếu gom nhiều lớp.
- **Constructor:** tên lớp khai báo và danh sách kiểu tham số `getParameterTypes()` theo thứ tự; không có return type.
- **Modifier, annotation, generic type:** có thể bổ sung nếu **bài toán cụ thể** yêu cầu, nhưng không tự động biến chúng thành thứ tự ưu tiên nghiệp vụ.

Nên dùng `Class.getName()` hoặc `Class.getTypeName()` để tạo chuỗi kiểu; tránh dựa vào tên biến tham số (thường không được lưu nếu thiếu tùy chọn biên dịch `-parameters`), thứ tự mã nguồn, `hashCode()` hay identity hash của JVM. `getParameterTypes()` phản ánh kiểu sau erasure: `List<String>` và `List<Integer>` đều có raw class là `java.util.List`; khi cần biểu diễn generics cho tài liệu, phân tích thêm `getGenericParameterTypes()` và xác định chính sách riêng.

## 4. Ví dụ chạy được: sắp xếp method, constructor và field

Ví dụ sau cố tình khai báo các member theo thứ tự không phải thứ tự chữ cái. Chương trình **sắp xếp mảng** trước khi in nên kết quả không phụ thuộc cách `getDeclared...()` liệt kê ban đầu.

Tạo file **`ReflectionOrderDemo.java`**:

```java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;
import java.util.stream.Collectors;

public class ReflectionOrderDemo {
    public static final class Endpoint {
        public String label;
        private int code;

        public Endpoint(int code) {
            this.code = code;
        }

        public Endpoint() {
        }

        public void send(String message) {
        }

        public int status() {
            return code;
        }

        public void send(int retries) {
        }
    }

    // Thứ tự và kiểu tham số dùng cho key và phần hiển thị.
    private static String parameters(Class<?>[] types) {
        return Arrays.stream(types)
                .map(Class::getTypeName)
                .collect(Collectors.joining(","));
    }

    private static String methodKey(Method method) {
        return method.getName()
                + "(" + parameters(method.getParameterTypes()) + "):"
                + method.getReturnType().getTypeName()
                + "@" + method.getDeclaringClass().getName();
    }

    private static String constructorKey(Constructor<?> constructor) {
        return constructor.getDeclaringClass().getName()
                + "(" + parameters(constructor.getParameterTypes()) + ")";
    }

    private static String fieldKey(Field field) {
        return field.getDeclaringClass().getName()
                + "#" + field.getName()
                + ":" + field.getType().getTypeName();
    }

    public static void main(String[] args) {
        Method[] methods = Endpoint.class.getDeclaredMethods();
        Arrays.sort(methods,
                Comparator.comparing(ReflectionOrderDemo::methodKey));

        System.out.println("METHODS");
        for (Method method : methods) {
            System.out.println(method.getName()
                    + "(" + parameters(method.getParameterTypes()) + "):"
                    + method.getReturnType().getTypeName());
        }

        Constructor<?>[] constructors =
                Endpoint.class.getDeclaredConstructors();
        Arrays.sort(constructors,
                Comparator.comparing(ReflectionOrderDemo::constructorKey));

        System.out.println("CONSTRUCTORS");
        for (Constructor<?> constructor : constructors) {
            System.out.println("Endpoint("
                    + parameters(constructor.getParameterTypes()) + ")");
        }

        Field[] fields = Endpoint.class.getDeclaredFields();
        Arrays.sort(fields,
                Comparator.comparing(ReflectionOrderDemo::fieldKey));

        System.out.println("FIELDS");
        for (Field field : fields) {
            System.out.println(field.getName()
                    + ":" + field.getType().getTypeName());
        }
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 --release 17 ReflectionOrderDemo.java
java ReflectionOrderDemo
```

Stdout:

```text
METHODS
send(int):void
send(java.lang.String):void
status():int
CONSTRUCTORS
Endpoint()
Endpoint(int)
FIELDS
code:int
label:java.lang.String
```

Giải thích:

- `Method[]`, `Constructor<?>[]`, `Field[]` là các mảng riêng biệt. `Arrays.sort(array, comparator)` chỉ đổi vị trí phần tử trong mảng; **không sửa phương thức hoặc định nghĩa class**.
- `methodKey` dùng tên method, **thứ tự kiểu tham số**, return type và declaring class. Do vậy hai overload `send(int)` và `send(String)` có khóa khác nhau, bất kể `getDeclaredMethods()` ban đầu trả về thứ tự nào.
- `constructorKey` không dùng return type; `Endpoint()` đứng trước `Endpoint(int)` theo quy tắc chuỗi đã chọn.
- `fieldKey` đưa `code` trước `label` theo thứ tự từ điển.
- Tên kiểu dùng `getTypeName()` dễ đọc; kiểu mảng có dạng `java.lang.String[]`. Chuỗi khóa là **chính sách do ta tự định nghĩa**. Nếu muốn ưu tiên method không có tham số hoặc ít tham số trước, hãy dùng một comparator nhiều cấp rõ ràng thay vì mặc nhiên coi thứ tự từ điển là quy tắc nghiệp vụ.

Không phải lúc nào cũng cần dựng chuỗi khóa. Với tập member lớn, có thể so sánh trực tiếp từng thành phần để giảm tạo chuỗi tạm. Với công cụ dựng tài liệu hoặc cấu hình khởi động, khóa dễ đọc như trên thường đủ rõ và dễ kiểm thử.

## 5. Vì sao `Method::getName` chưa đủ: bridge method

Khi dùng generic, compiler có thể tạo thêm **bridge method** để bảo đảm tính tương thích sau type erasure. Hai method phản chiếu có thể cùng tên và cùng danh sách tham số nhưng **khác return type**.

Ví dụ độc lập, lưu thành **`BridgeSortDemo.java`**:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;

public class BridgeSortDemo {
    interface Value<T> {
        T read();
    }

    static final class TextValue implements Value<String> {
        @Override
        public String read() {
            return "ok";
        }
    }

    public static void main(String[] args) {
        Method[] methods = TextValue.class.getDeclaredMethods();

        // Với lớp demo này, mọi method đều tên "read", không có tham số.
        // Return type phân biệt bridge method với method từ mã nguồn.
        Arrays.sort(methods, Comparator
                .comparing(Method::getName)
                .thenComparing(method -> method.getReturnType().getName()));

        for (Method method : methods) {
            System.out.println(method.getName() + "():"
                    + method.getReturnType().getTypeName()
                    + " bridge=" + method.isBridge()
                    + " synthetic=" + method.isSynthetic());
        }
    }
}
```

```bash
javac -encoding UTF-8 --release 17 BridgeSortDemo.java
java BridgeSortDemo
```

Stdout khi biên dịch bằng `javac` chuẩn trên JDK 17:

```text
read():java.lang.Object bridge=true synthetic=true
read():java.lang.String bridge=false synthetic=false
```

Lý do: `Value<T>.read()` sau erasure trả về `Object`; compiler sinh bridge `Object read()` để chuyển lời gọi đến implementation `String read()`. Cả hai có tên `read` và **không có tham số**; nếu sắp xếp chỉ theo tên hoặc chỉ theo tên + tham số, comparator trả về 0 giữa chúng. Sắp xếp Java ổn định lúc ấy vẫn giữ thứ tự đầu vào không được bảo đảm.

Ví dụ dùng comparator rút gọn vì lớp chỉ có hai method không tham số. Trong thư viện xử lý **nhiều lớp, nhiều overload**, hãy dùng khóa đầy đủ như ở mục 4 hoặc comparator nhiều tầng có cả parameter types, return type và declaring class.

Nếu mục tiêu là **danh sách API viết trong mã nguồn**, có thể có chính sách lọc:

```java
Method[] sourceLikeMethods = Arrays.stream(
        TextValue.class.getDeclaredMethods())
        .filter(method -> !method.isBridge() && !method.isSynthetic())
        .sorted(Comparator.comparing(Method::getName)
                .thenComparing(method -> method.getReturnType().getName()))
        .toArray(Method[]::new);
```

Đây là **đoạn mã minh họa chính sách lọc**, không phải chương trình chạy độc lập. Không lọc bridge/synthetic một cách vô điều kiện: công cụ phân tích bytecode, framework dispatch hoặc debugger có thể **cần** những member đó. Việc compiler sinh ra cấu trúc gì còn phụ thuộc phiên bản compiler và mã nguồn cụ thể; ứng dụng không nên hardcode số lượng bridge method cho mọi lớp.

## 6. Thiết kế comparator rõ ràng theo nhu cầu

### 6.1. Thứ tự từ điển nhất quán

Đối với tài liệu API hoặc snapshot, có thể chọn:

```java
Comparator<Method> bySignature = Comparator
        .comparing(Method::getName)
        .thenComparingInt(Method::getParameterCount)
        .thenComparing(m -> Arrays.stream(m.getParameterTypes())
                .map(Class::getName)
                .collect(Collectors.joining(",")))
        .thenComparing(m -> m.getReturnType().getName())
        .thenComparing(m -> m.getDeclaringClass().getName());
```

**Đoạn này là phần bổ sung trong một lớp hoặc phương thức có import `java.lang.reflect.Method`, `java.util.Arrays`, `java.util.Comparator`, `java.util.stream.Collectors`; không phải file Java độc lập.**

Quy tắc là: **tên → số tham số → kiểu tham số theo vị trí → return type → lớp khai báo**. So với mục 4, cách này đưa method ít tham số hơn lên trước trong cùng nhóm tên. Cả hai đều hợp lệ; điều quan trọng là công bố và áp dụng nhất quán **một** chính sách.

Nếu bạn cần thứ tự tương thích ngược cho một công cụ đã phát hành, **đừng âm thầm đổi comparator**; thứ tự mới có thể làm thay đổi nội dung sinh ra hoặc checksum của artifact dù tập member không đổi.

### 6.2. Khóa so sánh phải đủ phân biệt

Một comparator trả về 0 khi so sánh hai member khác nhau có thể khiến thứ tự cuối cùng phụ thuộc thứ tự Reflection đầu vào. Sự ổn định của thuật toán sort chỉ giữ nguyên thứ tự của các phần tử **được comparator coi là bằng nhau**; nó không tự sửa một comparator thiếu thông tin.

Với method trong phạm vi class loader thông thường, khóa dựa trên **declaring class + tên + parameter types + return type** phân biệt các method phản chiếu có descriptor khác nhau. Khi kết hợp member từ nhiều class loader mà các lớp có thể trùng tên nhị phân, cần cung cấp **identity ổn định của plugin/provider** từ cấu hình ứng dụng. Không dùng `System.identityHashCode(...)` hoặc thứ tự phát hiện loader nếu yêu cầu kết quả xác định xuyên lần chạy.

### 6.3. Sắp xếp nội dung, không quyết định ý nghĩa nghiệp vụ

Có hai loại thứ tự cần tách riêng:

- **Thứ tự trình bày:** bảng phương thức, dòng tài liệu, snapshot, manifest. Sắp xếp chữ ký rất phù hợp.
- **Thứ tự thực thi hoặc ưu tiên:** migration phải chạy theo version; handler phải chạy theo priority; interceptor có before/after rõ ràng. **Không suy diễn thứ tự này từ chữ ký hoặc vị trí Reflection trả về.** Dùng cấu hình thứ tự, dependency graph, annotation priority có hợp đồng rõ, hoặc một cấu trúc đăng ký được kiểm soát. Chỉ dùng sort chữ ký để phá hòa nếu chính sách đã quy định như vậy.

Ví dụ sai:

```java
// Sai: "method đầu tiên" là ngẫu nhiên theo hợp đồng API.
Method handler = Handler.class.getDeclaredMethods()[0];
```

Nếu bạn biết chính xác tên và parameter types thì tra cứu trực tiếp:

```java
Method handler = Handler.class.getDeclaredMethod(
        "handle", String.class);
```

Hai đoạn trên **đều là trích đoạn minh họa**, giả sử `Handler` có method `handle(String)` và mã xử lý `NoSuchMethodException`. Cách thứ hai chọn theo chữ ký, không cần sort cả danh sách. Nếu cần chọn theo **return type** khi bytecode có method cùng tên/tham số nhưng khác return type, hãy liệt kê rồi lọc theo yêu cầu, không chọn vị trí.

## 7. Lỗi thường gặp và cách phòng tránh

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dựa vào `getDeclaredMethods()[0]` hoặc vòng lặp theo thứ tự trả về | Chọn khác member khi đổi JDK/compiler, kết quả flaky | Tìm theo chữ ký hoặc sort trước khi dùng. |
| Chỉ sort theo tên method | Các overload bằng khóa, vẫn lệ thuộc thứ tự ban đầu | Thêm parameter types; với reflection đầy đủ thêm return type và declaring class. |
| Sort theo tên **tham số** | Tên có thể không hiện diện và có thể thay khi refactor | Dùng `getParameterTypes()`, giữ đúng thứ tự tham số. |
| Bỏ qua bridge/synthetic | Trùng tên/tham số, snapshot bất ổn hoặc API bị lặp | Định nghĩa chính sách giữ/lọc; nếu giữ thì đưa return type vào khóa. |
| Giả sử thứ tự `getFields()` là thứ tự khai báo | Member kế thừa được trộn theo quy tắc API, thứ tự không xác định | Sort và thêm declaring class vào khóa khi có nhiều nguồn. |
| Dùng `Method.toString()`/`toGenericString()` làm định danh bền vững của dữ liệu | Chuỗi mô tả dành cho con người và có thể không khớp schema/version ứng dụng | Tạo schema khóa riêng từ thuộc tính đã chọn; quản lý thay đổi định dạng. |
| Dùng `HashSet` / `HashMap` sau khi đã sort rồi mong iteration giữ thứ tự | Mất thứ tự do cấu trúc tập hợp | Giữ `List` đã sort hoặc dùng cấu trúc bảo toàn thứ tự khi cần. |
| Dùng chữ ký để quyết định thứ tự chạy migration, validator hay interceptor | Sai thứ tự nghiệp vụ dù đầu ra “ổn định” | Mô hình hóa ưu tiên/phụ thuộc bằng dữ liệu tường minh. |
| Mặc định dùng locale của máy khi so sánh tên | Kết quả có thể khác theo locale | Với khóa kỹ thuật nên dùng thứ tự chuỗi xác định (ví dụ `String.compareTo`), hoặc cấu hình locale nếu thực sự sắp xếp cho người dùng. |

Các thao tác sắp xếp chỉ cần metadata; **không cần** `setAccessible(true)` hoặc gọi method. Trong môi trường module, quyền đọc metadata/khả năng truy cập có quy tắc riêng; cố vượt encapsulation chỉ để lấy danh sách sắp xếp là không cần thiết.

## 8. Kiểm thử tính xác định

Một kiểm thử hữu ích cần so sánh **kết quả sau khi sắp xếp** với bộ chữ ký mong đợi, không kiểm tra thứ tự raw do Reflection trả về. Với `Endpoint` ở mục 4, test có thể assert thứ tự chuỗi là:

```text
send(int):void
send(java.lang.String):void
status():int
```

Để kiểm tra comparator có bỏ sót thuộc tính quan trọng, đưa vào fixture ít nhất:

1. Hai overload cùng tên nhưng khác số/kiểu tham số.
2. Method trả về khác nhau qua cơ chế bridge hoặc covariant override.
3. Một class có cả field public/private và hai constructor.
4. Nếu có tập member kế thừa, một số method từ superclass/interface.

**Không kiểm tra rằng raw array phải có một thứ tự cụ thể**. Bạn có thể trộn ngẫu nhiên danh sách đầu vào trong test rồi sort lại, sau đó đối chiếu cùng kết quả kỳ vọng. Nếu output vẫn đổi, comparator đang có khóa trùng mà chưa có quy tắc phá hòa hoặc bước biến đổi tiếp theo không bảo toàn thứ tự.

Với công cụ sinh tài liệu/metadata, nên duy trì golden file của chuỗi chữ ký sau chuẩn hóa và đánh dấu phiên bản chính sách sắp xếp khi đó là một phần format công khai. Điều này giúp diff phản ánh thay đổi API thực sự thay vì thay đổi ngoài ý muốn của runtime.

## 9. Câu hỏi tự kiểm tra

**1. Vì sao code `Arrays.sort(methods, Comparator.comparing(Method::getName))` vẫn có thể cho đầu ra khác nhau?**

Vì các overload có cùng tên được comparator coi bằng nhau; sort ổn định vẫn giữ thứ tự ban đầu vốn do Reflection trả về không được bảo đảm.

**2. Khi nào cần kiểu trả về trong khóa sắp xếp method?**

Khi muốn phân biệt đầy đủ các `Method` phản chiếu, đặc biệt với bridge/synthetic method hoặc bytecode có cùng tên và cùng parameter types nhưng khác return type. Return type không phải tiêu chí overload thông thường ở mức mã nguồn Java.

**3. Nếu chỉ muốn gọi method `handle(String)` thì có nên sắp xếp `getDeclaredMethods()` rồi lấy vị trí tương ứng?**

Không. Dùng `getDeclaredMethod("handle", String.class)` và xử lý lỗi tra cứu nếu không có. Sort chỉ cần khi bạn thật sự phải xuất danh sách hoặc xử lý theo một thứ tự xác định.

**4. Sort theo chữ ký có đảm bảo trình tự chạy các migration đúng không?**

Không. Chữ ký tạo ra thứ tự kỹ thuật có thể lặp lại, nhưng migration đòi hỏi thứ tự nghiệp vụ theo version, dependency hoặc cấu hình riêng.

**5. `getParameterTypes()` có trả về parameter type theo thứ tự ngẫu nhiên như `getDeclaredMethods()` không?**

Không. `getParameterTypes()` biểu diễn danh sách kiểu tham số **theo thứ tự khai báo của executable**. Chính vì thế phải giữ đúng thứ tự này khi tạo key.

## 10. Ghi nhớ

- **Reflection liệt kê member nhưng không bảo đảm thứ tự** cho các mảng method/field/constructor nêu trên.
- Khi cần kết quả xác định, **sort bằng comparator tường minh**: với method tối thiểu cần tên và danh sách tham số; khi xử lý member phản chiếu đầy đủ phải xét return type và declaring class để tránh hòa khóa do bridge/inheritance.
- **Sort đầu ra và chọn hành vi là hai bài toán khác nhau.** Dùng chữ ký cho trình bày, fingerprint, snapshot; dùng hợp đồng ưu tiên/phụ thuộc riêng cho thứ tự thực thi.
- **Kiểm thử kết quả chuẩn hóa**, không dựa vào thứ tự raw của JDK.

### Tài liệu chính thức

- [`Class` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): hợp đồng của `getMethods()`, `getDeclaredMethods()`, `getFields()`, `getDeclaredFields()`, `getConstructors()` và `getDeclaredConstructors()`.
- [`Method` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html): `getParameterTypes()`, `getReturnType()`, `isBridge()`, `isSynthetic()`.
- [`Constructor` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html) và [`Field` (Java SE 17)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Field.html).
