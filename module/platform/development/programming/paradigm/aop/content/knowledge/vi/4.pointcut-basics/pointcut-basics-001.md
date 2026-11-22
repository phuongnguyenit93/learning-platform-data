# Chọn điểm theo kiểu, tên và chữ ký phương thức

Trong lập trình hướng khía cạnh (**Aspect-Oriented Programming – AOP**), **pointcut** là quy tắc chọn những **join point** (điểm can thiệp) mà advice được áp dụng. Một phương pháp nền tảng là lọc các điểm liên quan đến phương thức dựa trên ba yếu tố: **kiểu sở hữu (type)**, **tên phương thức (method name)** và **chữ ký phương thức (method signature)**.

Ví dụ, chính sách “ghi audit khi lưu tài liệu” có thể chọn đúng phương thức `DocumentOperations.save(String)`. Nó phải loại trừ `DocumentOperations.save(int)`, `DocumentOperations.find(String)` và `CustomerOperations.save(String)`, mặc dù các phương thức ấy trùng một phần tên, kiểu hoặc tham số.

**Ý tưởng trung tâm:** pointcut phải chọn đúng những điểm cần áp dụng hành vi xuyên suốt, không bao phủ các điểm khác ngoài ý muốn. Điều này ảnh hưởng trực tiếp đến tính đúng đắn của audit, logging, metrics, kiểm soát truy cập và các chính sách AOP khác.

> Bài này mô tả mô hình AOP **nói chung**. Các mẫu `type=...`, `name=...` và `parameters=...` chỉ là **ký pháp khái niệm**, không phải cú pháp pointcut thống nhất hoặc có thể chạy trong một thư viện cụ thể. Khả năng chọn một loại join point còn phụ thuộc kỹ thuật weaving/interception.

## 1. Pointcut đứng ở đâu trong mô hình AOP?

**Join point** là sự kiện/vị trí thực thi mà cơ chế AOP có thể can thiệp. Với phương thức, những kiểu thường được mô hình hóa là **method call** (vị trí phát lời gọi) và **method execution** (ranh giới phương thức đích bắt đầu chạy). Không phải công cụ nào cũng hỗ trợ cả hai.

**Pointcut** là tiêu chí chọn các join point. **Advice** là đoạn xử lý chạy trước, sau, khi lỗi hoặc bao quanh những điểm đã chọn. **Aspect** thường đóng gói pointcut cùng advice phục vụ một mối quan tâm cắt ngang.

```text
Các điểm có thể can thiệp
    |
    |-- DocumentOperations.save(String)
    |-- DocumentOperations.save(int)
    |-- DocumentOperations.find(String)
    |-- CustomerOperations.save(String)
    |-- CustomerOperations.find(String)
    |
    v
Pointcut:
    type       = DocumentOperations
    name       = save
    parameters = [String]
    |
    v
Chỉ chọn DocumentOperations.save(String)
    |
    v
Advice được áp dụng khi join point tương ứng thực sự xảy ra
```

Một phương thức thỏa quy tắc về metadata nhưng bị gọi qua đường mà công cụ không quan sát được thì advice vẫn có thể không chạy. **Matcher đúng** và **weaving/interception bao phủ đúng** là hai điều kiện riêng.

### Số vị trí tĩnh và số lần thực thi động

Một phương thức có thể được gọi nhiều lần, từ nhiều nơi; một call site nằm trong vòng lặp cũng có thể phát sinh nhiều lượt gọi. Nếu một pointcut khớp và cơ chế hỗ trợ mọi lượt đó, advice có thể chạy nhiều lần. Không được suy luận “một method được chọn” là “advice chỉ chạy một lần”.

## 2. Ba điều kiện lọc và phép giao

| Điều kiện | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Kiểu** | Phương thức thuộc API/implementation nào? | `DocumentOperations` |
| **Tên** | Phương thức thực hiện thao tác tên gì? | `save` |
| **Chữ ký** | Tên và danh sách kiểu tham số có phù hợp không? | `save(String)` |
| **Kết hợp** | Cả ba điều kiện có cùng đúng không? | `DocumentOperations.save(String)` |

Một bộ lọc có thể mô tả bằng pseudocode:

```text
matches(joinPoint) =
    typeMatches(joinPoint)
    AND nameMatches(joinPoint)
    AND signatureMatches(joinPoint)
```

Khi điều kiện kiểu đúng nhưng tên sai, hoặc tên đúng nhưng tham số sai, kết quả phải **không chọn**. Việc ghép các điều kiện bằng AND làm phạm vi hẹp hơn; OR làm phạm vi rộng hơn; NOT loại trừ một tập không mong muốn. Nếu công cụ hỗ trợ biểu thức phức hợp, cần có dấu ngoặc để thể hiện đúng ý định.

**Đừng nhầm việc dùng reflection để tìm các `Method` có metadata phù hợp với AOP đầy đủ.** AOP còn phải kết hợp advice vào join point trong luồng thực thi.

## 3. Lọc theo kiểu (type)

Đây là ranh giới để tránh chọn nhầm hai method cùng tên và tham số nhưng ở hai thành phần không liên quan.

```java
// Khai báo minh họa, chưa phải chương trình chạy độc lập.
interface DocumentOperations {
    void save(String documentId);
}

interface CustomerOperations {
    void save(String customerId);
}
```

Hai giao diện có `save(String)`. Nếu quan tâm audit lưu tài liệu, bộ lọc theo **type = DocumentOperations** loại phương thức của `CustomerOperations`.

### 3.1. “Type” có thể mang những nghĩa khác nhau

Phải xác định cơ chế của bạn xét loại nào:

- **Declaring type:** kiểu thực sự khai báo phương thức. Trong Java reflection, `Method.getDeclaringClass()` cho biết điều này.
- **Static receiver type:** kiểu mà mã caller biết ở compile time (ví dụ biến được khai báo là interface).
- **Runtime receiver/target type:** lớp của đối tượng thực tế nhận lời gọi.
- **Type hierarchy:** một loại chính xác, các subtype, các lớp triển khai interface hoặc một tập kiểu trong package.

Ví dụ:

```java
DocumentOperations operations = new FileDocumentService();
operations.save("D-1");
```

Đây là mã minh họa, giả định `FileDocumentService` triển khai interface. Lời gọi được viết qua kiểu tĩnh `DocumentOperations`, nhưng method chạy thật có thể nằm ở `FileDocumentService`.

Một pointcut chọn **call** ở phía caller có thể dựa vào thông tin phương thức tĩnh của lời gọi; một pointcut chọn **execution** có thể quan tâm đến implementation thực thi. Không tự giả định “type” là runtime class trong mọi ngôn ngữ pointcut.

### 3.2. Kế thừa khiến declaring type khác runtime type

```java
class BaseDocumentService {
    public void save(String id) { }
}

class CachedDocumentService extends BaseDocumentService {
    // Không override: kế thừa save(String).
}
```

Method `save(String)` được **khai báo ở `BaseDocumentService`** dù có thể gọi trên một instance `CachedDocumentService`. `getDeclaredMethods()` của lớp con không bao gồm phương thức kế thừa; `getMethods()` có thể tìm public method được kế thừa.

Do đó, “declaring type chính xác là lớp con” và “target là subtype của lớp cha” là hai quy tắc khác nhau. Chọn kiểu theo contract thật sự cần bao phủ, rồi kiểm thử trường hợp inherited method và override.

### 3.3. Package và subtype không đồng nghĩa

“Thuộc package `com.example.billing`” không có nghĩa “là subtype của `BillingOperations`”. Package là vị trí tổ chức tên; subtype là quan hệ kiểu. Một số DSL phân biệt wildcard cho đúng một package với mẫu bao gồm subpackage. Hãy xác minh cú pháp của công cụ đang dùng.

Một pointcut chọn kiểu theo interface ổn định thường thể hiện intent rõ hơn chỉ khớp class có tên chứa `Service`, nhưng interface cũng không tự bảo đảm mọi implementation sẽ được bao phủ bởi mọi kỹ thuật interception.

## 4. Lọc theo tên phương thức (method name)

Tên là tín hiệu dễ đọc nhưng chưa mô tả đầy đủ hành vi.

### 4.1. Khớp chính xác

`name = "save"` có nghĩa tên phải đúng `save`. Nó không tự khớp `saveAll` hoặc `resave`. Nhưng nó có thể chọn nhiều overload `save(...)` và nhiều type cùng tên method.

### 4.2. Khớp bằng mẫu

Các mục tiêu có thể là:

```text
name exactly "find"                   -> find
name starts with "find"              -> find, findAll, findById
name ends with "Async"               -> loadAsync, publishAsync
name in {"create", "update", "delete"} -> một tập tên rõ ràng
```

Đây là **mô tả ý định**, không phải biểu thức pointcut có thể chạy nguyên xi. Wildcard kiểu glob, biểu thức chính quy và ký pháp của một engine AOP có thể khác nhau. Trong Java, regex dùng các quy tắc khác glob, chẳng hạn `.*` chứ không đơn thuần `*` để đại diện một chuỗi tùy ý.

### 4.3. Tên là một phụ thuộc cần kiểm thử khi refactor

Nếu một pointcut chọn `save*`, nó có thể vô tình chọn `saveTemporary` vừa được thêm. Nếu `save` đổi thành `persist`, nó có thể ngừng khớp, dù hành vi nghiệp vụ không đổi. Cần kiểm thử cả phương thức *phải khớp* và *không được khớp* khi đổi tên, thêm overload hoặc chuyển loại.

## 5. Chữ ký phương thức trong Java gồm những gì?

Theo định nghĩa của ngôn ngữ Java, **method signature** gắn với **tên method** và **danh sách các kiểu tham số** theo quy tắc ngôn ngữ (có xét việc điều chỉnh kiểu/generic khi thích hợp). **Return type, modifiers và danh sách `throws` không thuộc chữ ký Java.**

Một **mẫu chọn AOP** vẫn có thể hỗ trợ ràng buộc thêm return type, visibility, static/instance, annotation hoặc type khai báo. Những ràng buộc ấy không nên được gọi lẫn thành “thành phần chữ ký Java”.

### 5.1. Overload: cùng tên, khác tham số

```java
// Mã khai báo minh họa.
class DocumentStore {
    void save(String id) { }
    void save(int id) { }
    void save(String id, boolean overwrite) { }
}
```

| Method | Số/thứ tự kiểu tham số | Có khớp `save(String)`? |
| --- | --- | --- |
| `save(String)` | Một `String` | Có |
| `save(int)` | Một `int` | Không |
| `save(String, boolean)` | `String` rồi `boolean` | Không |

Một pattern chỉ ràng buộc tên `save` sẽ rộng hơn nhiều. Pattern tham số “đúng một String” khác pattern “String đầu tiên, phía sau có thể còn tham số”.

### 5.2. Thứ tự tham số có ý nghĩa

```java
void transfer(String account, long amount);
void transfer(long amount, String account);
```

Hai method trên khác signature vì thứ tự kiểu tham số khác nhau. Nếu matcher chỉ kiểm tra cùng một *tập* kiểu mà quên thứ tự, có thể chọn nhầm. Khi dùng reflection, so sánh `Class<?>[]` theo thứ tự, chẳng hạn `Arrays.equals(...)`.

### 5.3. Primitive và wrapper khác nhau

```java
void setLimit(int max);
void setLimit(Integer max);
```

`int.class` và `Integer.class` là hai loại khác nhau trong reflection. Java có boxing/unboxing tại call site, nhưng matcher chữ ký theo parameter type không tự động coi chúng tương đương. Nếu muốn chọn cả hai, hãy diễn đạt một OR rõ ràng.

### 5.4. Array và varargs

```java
// Hai biến thể minh họa riêng biệt, không được đặt đồng thời
// trong cùng một lớp như hai overload độc lập.
void publish(String[] ids);
void publish(String... ids);
```

Cả hai mang tham số `String[]` ở mức JVM. Không thể overload chỉ dựa vào việc thay cú pháp array bằng varargs vì cùng dạng signature. Reflection `getParameterTypes()` trả `String[].class` trong cả hai trường hợp; `isVarArgs()` có thể giúp kiểm tra method khai báo dưới dạng varargs.

### 5.5. Kiểu trả về và throws là điều kiện *bổ sung*

```java
// Minh họa khai báo, không phải tệp chạy độc lập.
public String find(String id) throws java.io.IOException;
```

- **Signature Java:** `find(String)`.
- **Return type:** `String`; có thể là một điều kiện lọc khác.
- **Visibility:** `public`; có thể là điều kiện lọc khác.
- **Declared exception:** `IOException`; không tạo signature riêng và không bao quát mọi lỗi runtime.

Không thể tạo hai overload Java cùng tên/cùng tham số mà **chỉ khác return type** trong cùng lớp. Vì vậy một pointcut có điều kiện return type đang *lọc thêm*, không làm xuất hiện overload hợp lệ mới.

## 6. Ví dụ Java 17+ chạy được: chọn đúng một overload

Ví dụ này xây một matcher từ **type + name + parameter types**, thêm **return type** làm bộ lọc phụ. Nó dùng `java.lang.reflect.Proxy` trong Java SE để chạy một “before advice” khi một lời gọi đi qua proxy có method phù hợp.

Đây là ví dụ **interception có điều kiện**, chưa phải một công cụ AOP hỗ trợ mọi join point hoặc một cú pháp pointcut chuẩn. Nó cho thấy cả cách khớp lẫn giới hạn khi lời gọi không đi qua proxy.

Lưu file **`PointcutSelectionDemo.java`** bằng UTF-8:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Arrays;

public class PointcutSelectionDemo {
    interface DocumentOperations {
        void save(String id);
        void save(int id);
        String find(String id);
    }

    static final class DocumentService implements DocumentOperations {
        @Override
        public void save(String id) {
            System.out.println("business.save(String): " + id);
        }

        @Override
        public void save(int id) {
            System.out.println("business.save(int): " + id);
        }

        @Override
        public String find(String id) {
            System.out.println("business.find(String): " + id);
            return "found:" + id;
        }
    }

    static boolean matches(Method method) {
        boolean typeMatches =
                method.getDeclaringClass() == DocumentOperations.class;
        boolean nameMatches = method.getName().equals("save");
        boolean parameterMatches = Arrays.equals(
                method.getParameterTypes(),
                new Class<?>[] { String.class });

        // Return type là điều kiện bổ sung, ngoài chữ ký Java.
        boolean returnMatches = method.getReturnType() == void.class;

        return typeMatches && nameMatches
                && parameterMatches && returnMatches;
    }

    static DocumentOperations withAdvice(DocumentOperations target) {
        return (DocumentOperations) Proxy.newProxyInstance(
                DocumentOperations.class.getClassLoader(),
                new Class<?>[] { DocumentOperations.class },
                (proxy, method, arguments) -> {
                    if (matches(method)) {
                        System.out.println(
                                "[advice] " + method.getName() + "(String)");
                    }
                    try {
                        return method.invoke(target, arguments);
                    } catch (InvocationTargetException error) {
                        throw error.getCause();
                    }
                });
    }

    public static void main(String[] args) {
        DocumentOperations target = new DocumentService();
        DocumentOperations service = withAdvice(target);

        service.save("DOC-7");
        service.save(42);
        System.out.println(service.find("DOC-7"));

        // Gọi trực tiếp: không qua proxy.
        target.save("DIRECT");
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 PointcutSelectionDemo.java
java PointcutSelectionDemo
```

**Standard output chính xác:**

```text
[advice] save(String)
business.save(String): DOC-7
business.save(int): 42
business.find(String): DOC-7
found:DOC-7
business.save(String): DIRECT
```

### 6.1. Vì sao chỉ dòng đầu có advice?

`service.save("DOC-7")` gọi overload `save(String)` trên interface proxy, thỏa cả type, name, params và return. Handler in dòng `[advice]` trước khi `method.invoke(...)` chuyển tiếp sang target.

`service.save(42)` có tham số khai báo `int`, nên không thỏa `parameterMatches`. `service.find("DOC-7")` không thỏa `nameMatches`. `target.save("DIRECT")` khớp chữ ký về mặt metadata nhưng **đi trực tiếp tới target**, bỏ qua handler. Đây là bằng chứng việc định nghĩa bộ lọc đúng chưa đảm bảo mọi đường gọi đã được interception.

### 6.2. Vai trò từng API reflection

- `Method.getDeclaringClass()`: biết type **khai báo method**. Ở ví dụ, đối tượng `Method` được handler nhận từ interface proxy; không nên diễn giải nó là runtime class của target.
- `Method.getName()`: lấy tên method, không có thông tin số/kiểu tham số.
- `Method.getParameterTypes()`: lấy danh sách `Class<?>` của tham số sau erasure, có thứ tự.
- `Method.getReturnType()`: lấy kiểu trả về, dùng như bộ lọc bổ sung.
- `Method.invoke(target, arguments)`: gọi method trên target, và có thể bọc ngoại lệ do target ném trong `InvocationTargetException`; đoạn `catch` mở lớp bọc để giữ lỗi gốc.

Ví dụ chọn đúng một overload và có kết quả cố định, nên có thể kiểm chứng dễ dàng. Nó không minh họa interception của private/static method, weaving vào bytecode hay lời gọi nội bộ.

## 7. Wildcard và chọn một họ phương thức

Không phải lúc nào cần chọn chính xác một method. Một chính sách đo thời gian có thể muốn chọn toàn bộ các phương thức truy vấn trong cùng một API.

| Mục tiêu | Ký pháp ý tưởng | Phạm vi |
| --- | --- | --- |
| Một overload | `type=DocumentOperations; name=save; params=[String]` | Chỉ một chữ ký |
| Tất cả overload cùng tên | `type=DocumentOperations; name=save; params=ANY` | Mọi `save(...)` |
| Một họ tên | `type=DocumentOperations; name startsWith save` | `save`, `saveAll`,... |
| Tất cả method của type | `type=DocumentOperations; name=ANY; params=ANY` | Phạm vi rất rộng |
| Nhiều type | `type in [DocumentOperations, ArchiveOperations]` | Hai nhóm API |

Đây là **ký pháp minh họa**, không phải biểu thức có thể sao chép vào mọi AOP engine. Các cú pháp wildcard có thể khác về dấu chấm package, subtype, số tham số hoặc mẫu kiểu trả về.

### 7.1. Không có tham số khác với mọi tham số

- `params=[]`: chính xác **không có** tham số.
- `params=[String]`: đúng **một** `String`.
- `params=ANY`: mọi số lượng và kiểu tham số.
- `params=startsWith([String])`: tham số đầu là `String`, có thể có những tham số khác **nếu DSL thực sự hỗ trợ**.

Đây là những ý nghĩa khác nhau. Một lỗi phổ biến là dùng mẫu rộng “bất kỳ danh sách tham số” trong khi chủ ý chỉ chọn `run()`.

### 7.2. Wildcard type và wildcard name là hai phép lọc riêng

“Class thuộc một package” không tương đương “method bắt đầu bằng tên `save`”. Hai quy tắc nên ghép tường minh:

```text
type matches a defined set of storage APIs
AND method name starts with "save"
AND parameters exactly [String]
AND NOT type belongs to internal diagnostics
```

Khi dùng DSL thật, kiểm tra liệu pattern package bao gồm subpackage, class lồng nhau hoặc subtype hay không. Không suy ra ý nghĩa các ký hiệu glob/regex từ ngôn ngữ khác.

## 8. Type ở call site khác type ở execution

Giả sử:

```java
// Mã minh họa, không phải file hoàn chỉnh.
interface Processor {
    void process(String data);
}

class FileProcessor implements Processor {
    @Override
    public void process(String data) { }
}

class NetworkProcessor implements Processor {
    @Override
    public void process(String data) { }
}

void handle(Processor processor) {
    processor.process("x");
}
```

Một vị trí gọi `processor.process("x")` viết qua **kiểu tĩnh `Processor`** có thể dẫn đến execution trong **`FileProcessor` hoặc `NetworkProcessor`** tùy runtime object.

Do đó:

- Bộ lọc cho **method call join point** có thể dựa vào method được tham chiếu ở phía caller.
- Bộ lọc cho **method execution join point** có thể dựa vào class triển khai đang chạy.
- Nếu engine chỉ cung cấp một loại join point, không thể giả định có đầy đủ metadata của phía còn lại.
- Một interface contract không tự động làm mọi kiểu weaving/interception bao phủ chính xác mọi implementation và lời gọi.

**Khi thiết kế quy tắc theo type, luôn xác định rõ cần match declaring type, kiểu compile time, kiểu target runtime hay cả hierarchy.** Đây là quyết định về semantics của pointcut, không đơn giản là lựa chọn chuỗi tên class.

## 9. Overriding và method được thừa kế

```java
class BaseExporter {
    public String export(String id) {
        return "base:" + id;
    }
}

class CsvExporter extends BaseExporter {
    @Override
    public String export(String id) {
        return "csv:" + id;
    }
}
```

Cả hai method có tên `export` và tham số `String`, nhưng declaring type khác nhau. Dynamic dispatch có thể chọn override của `CsvExporter`. Pointcut chọn **declaring type chính xác là BaseExporter** không mặc nhiên đồng nghĩa với chọn **mọi method có chữ ký đó trên subtype của BaseExporter**.

Nếu một lớp con không override, method kế thừa có thể vẫn được khai báo ở lớp cha. Nếu interface chứa `default method`, cần kiểm tra cách cơ chế AOP xử lý phần thân default và method proxy. Không nên chỉ tìm trong `getDeclaredMethods()` của lớp con rồi kết luận không có execution nào liên quan.

## 10. Generics và type erasure: chữ ký nguồn khác metadata runtime

Một ví dụ:

```java
interface Sink<T> {
    void accept(T value);
}

class StringSink implements Sink<String> {
    @Override
    public void accept(String value) {
        System.out.println(value);
    }
}
```

Đây là khai báo minh họa. Do **type erasure**, tham số `T` không có upper bound riêng trong `Sink<T>` trở thành `Object` ở descriptor liên quan. Compiler có thể tạo **bridge method** trong `StringSink` để duy trì overriding, ngoài method `accept(String)` do người lập trình viết.

Hệ quả với pointcut:

- `Method.getParameterTypes()` trả kiểu sau erasure, có thể khác cách một người đọc type parameter trong source.
- `getGenericParameterTypes()` trả metadata `Type`, cần diễn giải type variable và các generic declaration.
- `isBridge()` và `isSynthetic()` giúp nhận diện method do compiler sinh.
- Nếu cơ chế can thiệp dùng bytecode, cần kiểm thử việc khớp bridge method và số lần advice chạy. Không tự khẳng định mọi engine có cùng cách loại hoặc gộp bridge method.

Trường hợp generics không phải lý do bỏ qua ràng buộc signature; nó cho thấy phải hiểu **signature đang xét được lấy từ cấp độ nào**.

## 11. Ranh giới kỹ thuật: proxy và bytecode weaving

Một rule chọn metadata có thể đúng hoàn toàn nhưng **công cụ không bắt được join point mong muốn**.

| Cơ chế | Có thể quan sát ở đâu? | Lưu ý |
| --- | --- | --- |
| Runtime proxy dựa trên interface | Lời gọi thực sự đi qua proxy | Gọi trực tiếp target và lời gọi nội bộ có thể bỏ qua advice |
| Proxy bằng subclass | Lời gọi qua lớp con trung gian | Các ràng buộc final/private/static có thể ngăn override |
| Compile-time weaving | Mã đã được biến đổi khi biên dịch | Phải đảm bảo build dùng artifact được weave |
| Load-time weaving | Lớp được biến đổi khi JVM nạp | Phụ thuộc class loader/cấu hình nạp |
| Post-compile weaving | Bytecode đã biên dịch được biến đổi | Phải kiểm chứng artifact chính xác được xử lý |

Đừng coi một proxy nhận lời gọi là “mọi method call join point của chương trình”, hoặc coi nó đã weave execution vào thân target. Những khái niệm liên quan nhưng phạm vi khác nhau.

### Self-invocation

```java
class DocumentWorker {
    void run() {
        save("A"); // lời gọi nội bộ
    }

    void save(String id) { }
}
```

Với proxy đứng ngoài target, `this.save("A")` trong target thường không đi vòng ra proxy để chạy handler lần nữa. Nhưng về mặt mô hình, vẫn có một biểu thức gọi và một lần execution. **Giới hạn này thuộc đường interception qua proxy**, không phải mệnh đề “self-invocation không thể là join point” trong mọi AOP.

### Private, static, final và constructor

Những thành phần này có metadata tên/chữ ký ở mức thích hợp nhưng **khả năng can thiệp** phụ thuộc loại join point và weaving. Dynamic proxy interface không thể tự chặn private method, static call hoặc constructor. Weaving bytecode có thể hỗ trợ loại điểm khác, nhưng cũng không mặc nhiên hỗ trợ tất cả.

## 12. Những bộ lọc phụ có giá trị

Bên cạnh type + name + Java signature, một số hệ thống còn hỗ trợ:

| Bộ lọc phụ | Ý nghĩa | Điều cần chú ý |
| --- | --- | --- |
| Return type | Chỉ method trả `String` hoặc `CompletionStage` | Trả generic hay raw type? |
| Visibility | Chỉ method `public` | Không đồng nghĩa mọi public method đều chặn được |
| Static/instance | Chọn method của instance | Static không có instance receiver |
| Annotation | Chọn method có metadata như `@Audited` | Annotation ở interface/implementation? |
| Runtime argument | Chọn theo kiểu/giá trị đối số lúc chạy | Khác declared parameter type |
| Context | Chọn theo ngữ cảnh lời gọi | Cần kiểm soát thread, async, bảo mật |
| Exclusions | Bỏ qua lớp hạ tầng hoặc method nội bộ | Tránh recursion và đo lường nhiễu |

Ví dụ “chọn method nhận `Object` nhưng runtime argument là `String`” khác “chọn method **khai báo** tham số `String`”. Cùng một lời gọi có thể thỏa một điều kiện mà không thỏa điều kiện kia. Đây là khác biệt giữa **kiểu khai báo** và **giá trị runtime**.

Annotation tự nó cũng không kích hoạt AOP. Chỉ khi pointcut đọc metadata và có cơ chế weaving/interception phù hợp, advice mới thực thi tại các điểm được chọn.

## 13. Thiết kế pointcut đúng theo yêu cầu

Thay vì viết một biểu thức thật rộng từ đầu, hãy xác định từng yếu tố:

1. **Concern:** Chính sách áp dụng cho hành vi nào (ví dụ audit lưu tài liệu)?
2. **Loại join point:** Phía caller (*method call*) hay phía callee (*method execution*)?
3. **Ranh giới type:** Interface, implementation, declaring type chính xác, hierarchy hay package?
4. **Method name:** Tên chính xác hay một tập/pattern? Đổi tên có làm rule mất hiệu lực?
5. **Parameter types:** Số lượng, thứ tự, primitive/wrapper, array, varargs, erasure?
6. **Điều kiện phụ:** Return type, visibility, annotation, runtime context có thực sự cần?
7. **Loại trừ:** Những phương thức hạ tầng nào không thuộc chính sách?
8. **Cơ chế weave:** Call path nào được bao phủ, call path nào bypass?
9. **Kiểm thử:** Ca phải khớp, không được khớp, ngoại lệ, overload, override, reflection và lời gọi nội bộ.
10. **Thay đổi về sau:** Kiểm chứng lại tập điểm được chọn sau refactor API.

Pointcut dùng tên và kiểu quá rộng thường gây **false positive**: advice chạy ở chỗ không nên. Pointcut quá hẹp hoặc phụ thuộc một signature đã đổi gây **false negative**: nơi cần advice lại bị bỏ lọt. Cả hai đều có thể nghiêm trọng nếu concern là audit hoặc kiểm soát truy cập.

### Ma trận kiểm thử ví dụ

Giả sử rule:

```text
declaring type = DocumentOperations
name           = save
parameterTypes = [String]
```

| Phương thức | Type | Name | Parameters | Kết quả |
| --- | --- | --- | --- | --- |
| `DocumentOperations.save(String)` | Đúng | Đúng | Đúng | **Chọn** |
| `DocumentOperations.save(int)` | Đúng | Đúng | Sai | Không chọn |
| `DocumentOperations.find(String)` | Đúng | Sai | Đúng | Không chọn |
| `DocumentOperations.save(String, boolean)` | Đúng | Đúng | Sai | Không chọn |
| `CustomerOperations.save(String)` | Sai | Đúng | Đúng | Không chọn |
| `DocumentOperations.save(String[])` | Đúng | Đúng | Sai | Không chọn |

Bảng mô tả kết quả **matcher logic**, chưa chứng minh những method tương ứng sẽ chạy advice trong runtime. Test tích hợp phải gọi qua đúng cơ chế AOP, đồng thời kiểm tra rằng đường không khớp không có advice.

### Khi nhiều aspect cùng khớp

Nếu aspect `Audit` và `Timing` cùng chọn `save(String)`, cả hai advice có thể được áp dụng. **Pointcut quyết định có chọn hay không; precedence quyết định thứ tự advice khi chúng cùng khớp.** Nếu quanh một lời gọi có nhiều around advice, chúng có thể lồng nhau. Thứ tự ảnh hưởng phạm vi đo thời gian, context và xử lý lỗi; không suy đoán thứ tự mặc định của mọi engine là giống nhau.

## 14. Các trường hợp nâng cao cần kiểm chứng

### 14.1. Đổi signature sau refactor

Đổi `save(String)` thành `save(DocumentRequest)` có thể khiến pointcut cũ không còn khớp. Thêm overload `save(String, boolean)` không làm rule chính xác tự động chọn overload mới. Đổi interface hoặc di chuyển method lên base type có thể làm thay đổi declaring type. Vì vậy các thay đổi API phải kích hoạt kiểm thử tập khớp.

### 14.2. Bytecode sinh tự động

Bridge và synthetic methods có thể xuất hiện trong bytecode dù không hiển thị như một method viết tay bình thường. Một matcher chỉ dựa tên/param nhưng không xét `isBridge()`/`isSynthetic()` có thể quan sát phạm vi khác dự kiến trong một số cơ chế. Cần kiểm chứng trên artifact biên dịch và runtime thật.

### 14.3. Reflection và method handles

Một thân method có thể thực thi qua reflection mà source caller không có biểu thức trực tiếp `target.save(...)` tương ứng. Pointcut ở execution của target và pointcut ở vị trí gọi `Method.invoke(...)` là hai ranh giới khác nhau. Việc hỗ trợ từng ranh giới phụ thuộc weaving.

### 14.4. Async và công việc hoàn tất sau lời gọi

Nếu method gửi tác vụ rồi trả về một `CompletableFuture`, advice đo quanh lời gọi **gửi tác vụ** chưa chắc đo được **thời gian hoàn thành công việc**. Chọn đúng type/name/signature của method submit không đủ nếu mục tiêu là đo task execution; cần chọn hoặc theo dõi đúng ranh giới hoàn tất.

### 14.5. Recursion, advice và side effect

Một method đệ quy tạo nhiều lượt execution; lời gọi nội bộ có thể không đi qua proxy. Nếu around advice gọi tiếp nhiều lần, một thao tác có side effect cũng có thể bị thực thi nhiều lần. Pointcut chọn **đúng method** chưa đảm bảo hành vi an toàn nếu advice có quyền bỏ qua hoặc lặp thao tác.

## 15. Các lỗi thường gặp

1. **Chỉ dùng tên method**, khiến nhiều overload/type không liên quan đều khớp.
2. **Nhầm return type là thành phần chữ ký Java**, dù nó chỉ có thể là một bộ lọc pointcut bổ sung.
3. **Quên thứ tự/số lượng tham số**, nên `process(String, int)` bị coi như `process(int, String)`.
4. **Coi `int` và `Integer` là cùng kiểu khai báo** vì Java hỗ trợ boxing/unboxing.
5. **Coi array và varargs là hai overload hợp lệ** với cùng kiểu phần tử.
6. **Nhầm declaring type với runtime target type**, làm bỏ lọt inherited/overridden method.
7. **Dùng wildcard quá rộng**, vô tình áp dụng advice cho method được thêm sau này.
8. **Giả định mọi method match metadata đều được advice chặn**, bỏ qua phạm vi weave/proxy.
9. **Bỏ qua generics erasure và bridge method**, dẫn đến matcher sai trên bytecode thật.
10. **Không kiểm thử đường gọi trực tiếp hoặc nội bộ**, nơi proxy có thể bị bỏ qua.
11. **Đổi tên/chữ ký method nhưng không cập nhật test pointcut**, tạo false negative.
12. **Không giới hạn hạ tầng của advice**, làm advice tự gọi vào chính join point và gây reentrancy.

## 16. Bài tập thực hành

1. Trong `PointcutSelectionDemo.java`, đổi `parameterMatches` từ `String.class` sang `int.class`. Dự đoán và chạy xác minh phương thức nào có dòng `[advice]`.
2. Xóa điều kiện tham số, chỉ giữ type và name. Vì sao cả `save(String)` và `save(int)` có advice?
3. Thêm `save(String, boolean)` vào interface và implementation; chứng minh rule gốc không chọn method mới.
4. Thêm interface `CustomerOperations` có `save(String)` và đề xuất matcher loại đúng bằng điều kiện type.
5. Đổi tên `save(String)` thành `persist(String)`. Thiết kế regression test phát hiện pointcut cũ đã không còn bao phủ hành vi lưu.
6. Dùng reflection so sánh `getDeclaredMethods()` và `getMethods()` trên một class kế thừa method public.
7. Kiểm tra `isVarArgs()` cho hai cách khai báo `String[]` và `String...` ở **hai method/class riêng**, để tránh lỗi trùng signature.
8. Với `Sink<T>`/`StringSink`, dùng reflection in `getParameterTypes()`, `isBridge()` và `isSynthetic()`; giải thích kết quả.
9. Gọi trực tiếp `target.save("DOC-7")` rồi gọi qua `service.save("DOC-7")`. Vì sao trường hợp đầu không có advice dù đúng chữ ký?
10. Viết bảng gồm ít nhất năm method “phải được chọn” và năm method “không được chọn” cho một chính sách cụ thể, rồi kiểm thử tại runtime để phát hiện cả false positive và false negative.

**Tự kiểm tra:** `save(String)` và `save(int)` có cùng signature Java không? `getDeclaringClass()` có luôn là runtime class của target không? Vì sao return type có thể là điều kiện của pointcut nhưng không thuộc signature Java? Một bộ matcher trả `true` có chứng minh proxy đã bắt được mọi lời gọi không?

## Kết luận

**Chọn join point theo kiểu, tên và chữ ký** cho phép aspect có phạm vi rõ ràng và có thể kiểm chứng. **Type** xác định API/implementation liên quan, **method name** xác định thao tác, còn **danh sách kiểu tham số** giúp phân biệt overload theo đúng quy tắc Java. Những điều kiện như return type, visibility hay annotation có thể bổ sung khi cơ chế hỗ trợ nhưng không thay đổi định nghĩa chữ ký Java. Để áp dụng an toàn, luôn xem xét thừa kế, đa hình, generics, ranh giới call/execution và đường đi weaving/interception, đồng thời duy trì kiểm thử các điểm khớp và không khớp sau mỗi lần refactor.