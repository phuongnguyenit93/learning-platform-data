# Xử lý field trùng tên và method ghi đè theo chính sách nhất quán khi dùng Reflection

Khi quét một hệ phân cấp class, **field trùng tên** và **method override** cần hai chính sách riêng. Field ở cha/con vẫn là hai vị trí lưu trữ khác nhau; method override sử dụng quy tắc dispatch động theo receiver. `getDeclaredFields()`/`getDeclaredMethods()` chỉ cho biết khai báo ở từng class và không cam kết thứ tự, nên việc giữ phần tử đầu tiên có thể thay đổi kết quả.

Bài này xây registry có khóa chữ ký rõ ràng, thứ tự duyệt từ lớp cụ thể lên superclass và lựa chọn *closest declaration wins* có chủ đích. Nếu ứng dụng phải bảo toàn mọi field cùng tên, nó phải dùng khóa kèm declaring class hoặc báo collision, thay vì gộp im lặng.

## 1. Field hiding khác method overriding

### 1.1. Field cùng tên là hai trường dữ liệu riêng

~~~java
class Parent {
    public String id = "parent";
}

class Child extends Parent {
    public String id = "child";
}
~~~

`Child.id` **che khuất** (*hide*) `Parent.id` theo cách phân giải tên trong mã nguồn. Nhưng đối tượng `Child` vẫn **chứa cả hai trường**:

- `child.id` đọc trường `Child.id`.
- `((Parent) child).id` đọc trường `Parent.id`.
- `Child.class.getDeclaredField("id")` trả về khai báo ở `Child`.
- `Parent.class.getDeclaredField("id")` trả về khai báo ở `Parent`.
- `Field.get(child)` đọc đúng **trường mà đối tượng `Field` biểu diễn**, kể cả khi receiver là một đối tượng lớp con; nó không tự chuyển sang field cùng tên ở lớp con.

Vì vậy, chọn trường của lớp con làm đại diện cho khóa `id` là **chính sách flatten schema**, không có nghĩa trường ở lớp cha biến mất. Nếu một serializer cần giữ cả hai giá trị, phải dùng khóa có thêm lớp khai báo (ví dụ `Parent#id`, `Child#id`) hoặc báo xung đột; không gộp cả hai một cách im lặng.

### 1.2. Method override là một hành vi được phân phối động

~~~java
class Parent {
    public String label() { return "parent"; }
}

class Child extends Parent {
    @Override
    public String label() { return "child"; }
}
~~~

`Child.label()` **override** `Parent.label()`. Lời gọi instance bình thường `new Child().label()` sử dụng triển khai của `Child`. Kể cả khi lấy một `Method` từ `Parent.class.getDeclaredMethod("label")` rồi `invoke(child)`, lời gọi instance này vẫn sử dụng **dynamic dispatch** nên trả `"child"` (theo quy tắc override của Java).

Ngược lại, `private` method không bị override theo nghĩa thông thường; `static` method được **hide**, không dispatch như instance method; và hai method cùng tên nhưng **khác tập kiểu tham số** là *overload*, không phải override. Một bộ quét thành viên không được gộp tất cả các method chỉ theo tên.

| Tình huống | Bản chất | Quy tắc xử lý phù hợp với registry công khai |
| --- | --- | --- |
| `Parent.id` và `Child.id` | Hai field độc lập; field của lớp con hide field cha | Nếu cần một thuộc tính theo tên: chọn lớp con và báo đã che khuất; nếu cần dữ liệu đầy đủ: giữ cả hai với khóa khác nhau |
| `Parent.label()` và `Child.label()` | Instance method override | Một khóa method theo tên + danh sách kiểu tham số; chọn khai báo hợp lệ ở lớp cụ thể hơn |
| `set(String)` và `set(int)` | Overload | Giữ **hai** khóa khác nhau |
| `Parent.staticMethod()` và `Child.staticMethod()` | Static method hiding | Xử lý riêng theo chính sách static; không coi là override |
| Private method cùng tên/chữ ký trong hai lớp | Không có quan hệ override thông thường | Nếu quét private, định danh theo lớp khai báo và áp dụng access control riêng |
| Method do compiler sinh (`bridge`/`synthetic`) | Thành viên hỗ trợ bytecode, có thể trùng khóa nguồn | Chọn rõ có loại khỏi mô hình API nguồn hay cần giữ cho phân tích bytecode |

## 2. Reflection trả về gì và những giả định cần bỏ

- `getDeclaredFields()` và `getDeclaredMethods()` chỉ lấy thành viên **được khai báo trực tiếp** trong kiểu đang xét; chúng không tự thêm thành viên thừa kế. Mảng kết quả **không có thứ tự được đảm bảo**.
- `getFields()` và `getMethods()` trả các thành viên `public` phù hợp, kể cả thành viên kế thừa từ superclass/superinterface. Thứ tự của các mảng này cũng **không được đảm bảo**. Riêng `getMethods()` còn có quy tắc chọn các phương thức cụ thể hơn theo JDK, không nên suy luận chỉ bằng “phần tử đầu tiên”.
- `getDeclaredMethods()` có thể trả **bridge/synthetic method** do compiler tạo, đôi khi cùng tên + kiểu tham số nhưng khác kiểu trả về.
- `getDeclaringClass()` cho biết thành viên được **khai báo ở lớp nào**. Thông tin này rất quan trọng khi xử lý hiding, override, log hoặc cache metadata.
- `getParameterTypes()` phản ánh **kiểu tham số runtime sau type erasure**; `getGenericParameterTypes()` dành cho nhu cầu giữ metadata kiểu tổng quát. Không dùng riêng `getReturnType()` để phân biệt overload theo ngữ nghĩa Java.
- `getModifiers()`, `Modifier.isPublic(...)`, `Field.isSynthetic()`, `Method.isBridge()` và `Method.isSynthetic()` giúp lọc; nhưng tính `public` của member chưa đảm bảo có quyền gọi nếu **lớp khai báo/package/module** không truy cập được.

Ví dụ về kiểu trả về covariant: `Parent.score(): Number` và `Child.score(): Integer` có thể cần compiler tạo một **bridge method** ở `Child` để giữ tương thích sau biên dịch. Nếu registry lấy ngẫu nhiên phần tử đầu tiên của `Child.getDeclaredMethods()`, bộ dữ liệu có thể chứa cả method nguồn và bridge, hoặc chọn kiểu trả về không mong muốn.

## 3. Định nghĩa chính sách trước khi triển khai

Một chính sách minh họa cho **registry thuộc tính và hành vi công khai của class thông thường**:

1. **Đầu vào**: một `Class<?>` đại diện cho lớp cụ thể.
2. **Phạm vi**: chỉ thành viên `public instance` do class hiện tại và các superclass (trừ `Object`) khai báo; bỏ `static`, `synthetic` và `bridge`. Bỏ qua interface/default methods trong lượt quét đơn giản này.
3. **Thứ tự class**: đi từ lớp cụ thể lên superclass gần nhất rồi tiếp tục tới tổ tiên. *Closest declaration wins*.
4. **Thứ tự trong từng class**: sắp xếp field theo `Field.getName()` và method theo khóa chữ ký ổn định, tuyệt đối không dựa thứ tự mảng Reflection.
5. **Khóa của field**: `field.getName()`. Nếu tên trùng, giữ field của class cụ thể hơn. Quyết định này làm mất field cùng tên ở lớp cha **khỏi góc nhìn registry**, không xóa field trong object.
6. **Khóa của method**: `methodName(parameterType1,parameterType2,...)`, dùng danh sách **kiểu tham số runtime theo đúng thứ tự**. Không gộp các overload; không đưa return type vào khóa API nguồn. Nếu key trùng, giữ khai báo ở class cụ thể hơn.
7. **Xử lý xung đột**: ghi nhận cả “khai báo được chọn” lẫn “khai báo bị che/ghi đè” khi sản phẩm cần audit hoặc cảnh báo; quyết định rõ đây là chính sách cho schema, mapper hay dispatcher.

Đây là **quy ước của công cụ**, không phải một thuật toán tổng quát thay thế mọi quy tắc kế thừa của Java. Giới hạn `public instance` khiến ví dụ tránh nhiều trường hợp phức tạp về private, package-private khác package, protected, accessibility xuyên module, interface default/diamond và generics. Nếu công cụ thực sự phải xử lý các trường hợp đó, hãy bổ sung chính sách riêng; không mở rộng quyền một cách ngầm định.

## 4. Ví dụ Java 17+ chạy độc lập: quét có thứ tự và khóa rõ ràng

Lưu nội dung sau thành **`ToolPolicyDemo.java`**:

~~~java
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

public class ToolPolicyDemo {
    public interface Feature {
        default String tag() { return "interface"; }
    }

    public static class Parent {
        public String id = "parent";
        public String label() { return "parent"; }
        public Number score() { return 10; }
        public void update(String text) {}
    }

    public static class Child extends Parent implements Feature {
        public String id = "child";
        @Override public String label() { return "child"; }
        @Override public Integer score() { return 20; }
        public void update(int number) {}
    }

    static Map<String, Field> fields(Class<?> leaf) {
        Map<String, Field> result = new LinkedHashMap<>();

        for (Class<?> c = leaf; c != null && c != Object.class;
                c = c.getSuperclass()) {
            Arrays.stream(c.getDeclaredFields())
                    .filter(f -> Modifier.isPublic(f.getModifiers())
                            && !Modifier.isStatic(f.getModifiers())
                            && !f.isSynthetic())
                    .sorted(Comparator.comparing(Field::getName))
                    .forEach(f -> result.putIfAbsent(f.getName(), f));
        }
        return result;
    }

    static String key(Method m) {
        String params = Arrays.stream(m.getParameterTypes())
                .map(Class::getTypeName)
                .collect(Collectors.joining(","));
        return m.getName() + "(" + params + ")";
    }

    static Map<String, Method> methods(Class<?> leaf) {
        Map<String, Method> result = new LinkedHashMap<>();

        for (Class<?> c = leaf; c != null && c != Object.class;
                c = c.getSuperclass()) {
            Arrays.stream(c.getDeclaredMethods())
                    .filter(m -> Modifier.isPublic(m.getModifiers())
                            && !Modifier.isStatic(m.getModifiers())
                            && !m.isBridge() && !m.isSynthetic())
                    .sorted(Comparator.comparing(ToolPolicyDemo::key))
                    .forEach(m -> result.putIfAbsent(key(m), m));
        }
        return result;
    }

    public static void main(String[] args) throws Exception {
        Child child = new Child();
        Map<String, Field> fieldMap = fields(Child.class);
        Map<String, Method> methodMap = methods(Child.class);

        System.out.println("field owner: " +
                fieldMap.get("id").getDeclaringClass().getSimpleName());
        System.out.println("field values: " +
                fieldMap.get("id").get(child) + "/" + ((Parent) child).id);
        System.out.println("label owner: " +
                methodMap.get("label()").getDeclaringClass().getSimpleName());
        System.out.println("label call: " +
                methodMap.get("label()").invoke(child));
        System.out.println("score return type: " +
                methodMap.get("score()").getReturnType().getSimpleName());
        System.out.println("overloads kept: " +
                methodMap.containsKey("update(int)") + "/" +
                methodMap.containsKey("update(java.lang.String)"));
        System.out.println("bridge count: " +
                Arrays.stream(Child.class.getDeclaredMethods())
                        .filter(Method::isBridge).count());
        System.out.println("base Method.invoke: " +
                Parent.class.getDeclaredMethod("label").invoke(child));
        System.out.println("class-only sees interface default: " +
                methodMap.containsKey("tag()"));
        System.out.println("getMethod sees default: " +
                Child.class.getMethod("tag").invoke(child));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac ToolPolicyDemo.java
java ToolPolicyDemo
~~~

Kết quả khi biên dịch bằng `javac` Java 17+:

~~~text
field owner: Child
field values: child/parent
label owner: Child
label call: child
score return type: Integer
overloads kept: true/true
bridge count: 1
base Method.invoke: child
class-only sees interface default: false
getMethod sees default: interface
~~~

Đọc kết quả theo chính sách đã chọn:

- `field owner: Child`: registry lấy field gần lớp đích nhất theo tên `id`. Dòng kế tiếp chứng minh field `Parent.id` vẫn tồn tại, có giá trị khác; `Field.get(child)` đọc field của đúng lớp khai báo.
- `label owner: Child`: `putIfAbsent` giữ method override ở lớp con, vì quét `Child` trước `Parent`. `label call: child` phản ánh hành vi override.
- `score return type: Integer`: khai báo nguồn ở `Child` được chọn; bộ lọc `!m.isBridge()` bỏ method bridge mà `javac` tạo do kiểu trả về covariant.
- `overloads kept: true/true`: `update(int)` và `update(String)` có khóa khác nhau nên cả hai được giữ.
- `bridge count: 1`: demo làm hiện rõ bridge trong metadata của `Child`; đây là kết quả của ví dụ cụ thể khi dùng `javac`, không phải lời khẳng định mọi compiler hay mọi override đều phải sinh chính xác một bridge.
- `base Method.invoke: child`: chọn `Method` khai báo tại `Parent` **không** cố định triển khai `Parent` khi gọi instance method trên một `Child`; dynamic dispatch vẫn áp dụng.
- `class-only sees interface default: false`: thuật toán có chủ ý chỉ đi dọc superclass, chưa duyệt `Feature`; nhưng `Child.class.getMethod("tag")` tìm được default method public thừa kế từ interface và gọi được.

### Vì sao dùng `LinkedHashMap` và `putIfAbsent`?

`LinkedHashMap` giữ thứ tự chèn của các entry để kết quả lặp lại ổn định khi các đầu vào và chính sách không đổi. Quét từ lớp con lên lớp cha, dùng `putIfAbsent(key, member)` để khai báo đầu tiên (lớp cụ thể nhất) chiếm khóa. Sắp xếp **trước khi chèn** loại bỏ sự phụ thuộc vào thứ tự `getDeclaredFields()`/`getDeclaredMethods()` vốn không được đảm bảo.

Trong ví dụ, khóa chữ ký method là chuỗi để dễ quan sát. Ở một hệ thống xử lý nhiều class loader, hai lớp khác nhau có thể cùng tên nhị phân. Nếu tính duy nhất phải phản ánh **identity của `Class<?>`**, hãy dùng một key cấu trúc (ví dụ record chứa method name và `List<Class<?>>` parameter types) thay vì chỉ dựa vào `Class.getTypeName()`; chuẩn hóa thêm module/loader nếu lưu cache bền vững hoặc xuất metadata liên tiến trình.

## 5. Mở rộng chính sách theo nhu cầu của công cụ

### 5.1. Muốn giữ tất cả field bị hide

Nếu mục tiêu là debugger, ORM có metadata rõ ràng, serializer lossless hoặc công cụ kiểm tra dữ liệu ở mọi tầng kế thừa, chính sách “một tên một field” có thể **không đủ**.

Giải pháp: lưu `Map<DeclaringClassAndName, Field>` (hoặc danh sách các field cùng tên) với khóa cấu trúc gồm `field.getDeclaringClass()` và `field.getName()`. Sau đó ánh xạ sang tên hiển thị có namespace rõ ràng: `Parent#id` và `Child#id`. Nếu format đầu ra chỉ chấp nhận một khóa `id`, cần chính sách loại trừ hoặc báo collision có chủ đích, tránh âm thầm ghi đè giá trị cha.

Khi dùng annotation để đặt tên logic (ví dụ hai field vật lý khác tên nhưng cùng `@JsonProperty`), **collision của tên logic** còn khác collision của tên Java. Khóa, chính sách ưu tiên và bước phát hiện xung đột phải được xác định ở đúng tầng mapping.

### 5.2. Muốn hỗ trợ method từ interface và default method

Một registry chỉ quét superclass như ví dụ sẽ bỏ `default` method của interface. Có hai hướng:

- Với API public đã kế thừa, xem xét `Class.getMethods()` hoặc `getMethod(name, parameterTypes...)` để dựa vào phép phân giải public method mà Reflection cung cấp, rồi lọc/sắp xếp và xác định chính sách nhóm.
- Nếu cần biết **vị trí khai báo trong interface graph**, chủ động duyệt `getInterfaces()`, loại trùng interface, ưu tiên class method so với interface default theo quy tắc Java, rồi xử lý trường hợp nhiều interface liên quan. Sắp xếp tên/interface cho deterministic output, nhưng việc chọn triển khai phải tuân thủ quan hệ kế thừa/most-specific, **không dùng thứ tự alphabet thay cho ngữ nghĩa override**.

Ví dụ ở mục 4 cố tình cho thấy `methodMap` không chứa `tag()` còn `getMethod("tag")` thì chứa: đây là **giới hạn công khai của chính sách minh họa**, không phải lỗi của Reflection.

### 5.3. Static, private, protected, package-private và module

- Method `static` cùng chữ ký trong hai lớp được **hide**, không có dynamic dispatch. Nếu registry xử lý static factory, dùng nhóm và ưu tiên riêng; không nhập vào registry instance.
- Method `private` của cha không bị override; nếu công cụ cần đọc private, khóa phải giữ lớp khai báo hoặc phân biệt metadata, không cho method cùng tên ở con “thay thế” private cha theo suy luận override.
- `protected` và package-private phải xét **package, quan hệ kiểu và khả năng thực sự truy cập**. Package-private giữa hai package khác nhau không tự trở thành một quan hệ override.
- Ngoài `Modifier.isPublic`, module `exports`/`opens`, visibility của lớp khai báo và lookup context có thể quyết định khả năng sử dụng. `setAccessible(true)` có giới hạn trong Java 17+ với JPMS và có thể ném `InaccessibleObjectException`; không xem việc tìm được metadata là đủ quyền gọi.
- Constructor **không được kế thừa**, vì vậy không đưa `getDeclaredConstructors()` vào cùng thuật toán override/hiding.

Với công cụ xử lý rộng hơn ví dụ, cần kiểm tra accessibility bằng chính API được dùng (Reflection, `MethodHandles.Lookup`, `canAccess` khi có đối tượng phù hợp) và theo chính sách của sản phẩm. Nếu không đủ quyền, báo lỗi rõ ràng thay vì chọn một thành viên khác ngẫu nhiên.

### 5.4. Generic, bridge và kiểu trả về covariant

Java xác định overload chủ yếu từ **tên method và danh sách kiểu tham số**, không tạo overload mới chỉ nhờ kiểu trả về khác nhau. Ở bytecode/Reflection, compiler có thể thêm bridge sau type erasure hoặc khi return type covariant. Vì vậy:

1. Đối với **mô hình API ở cấp Java source**, thường nên lọc `isBridge()`/`isSynthetic()` trước khi nhóm.
2. Đối với **bytecode analyzer**, có thể cần giữ cả bridge, nhưng khóa lúc đó có thể bao gồm **return type** và thông tin declaring class, kèm cờ bridge/synthetic.
3. Với generic type metadata, phân biệt `getParameterTypes()` (erased runtime types) và `getGenericParameterTypes()`. Dữ liệu generic là phần mô tả cần lưu thêm; nó không phải lý do để chọn tùy ý một method trùng runtime signature.

Nếu library yêu cầu hỗ trợ bytecode không thông thường hoặc class sinh động, đừng giả định mọi trùng lặp đều là bridge; kiểm tra nhóm đã lọc và đưa ra quyết định rõ ràng khi vẫn còn collision.

## 6. Kiểm tra tính nhất quán trước khi đưa vào framework

Một bộ quét đáng tin cậy nên có các đặc điểm có thể kiểm chứng:

| Tiêu chí | Cách kiểm chứng |
| --- | --- |
| Kết quả độc lập với thứ tự mảng Reflection | Hoán vị danh sách đầu vào trước khi sort/group; kết quả chọn vẫn giống nhau |
| Field cùng tên không làm mất dữ liệu ngoài ý muốn | Có test `Parent.id`/`Child.id`, kiểm tra chính sách “flatten” hay “keep all” |
| Override khác overload | `label()` chỉ có một entry ở class gần nhất; `update(String)` và `update(int)` cùng tồn tại |
| Bridge không làm sai kiểu trả về của API nguồn | Thử override covariant; kiểm tra `isBridge()` và kiểu trả về của entry được chọn |
| Interface default được xử lý theo quy tắc đã công bố | Thử `getMethod`, hoặc kiểm tra rõ phạm vi class-only |
| Quyền truy cập được xử lý | Thử public trên kiểu không public, private across modules, và xử lý lỗi truy cập |
| Kết quả ổn định khi cache | Khóa cache gắn `Class<?>`/ClassLoader và chính sách lọc; không dùng chỉ tên class nếu có nhiều loader |
| Thành viên bị bỏ được giải thích | Với dữ liệu quan trọng, log khai báo gốc/chọn/bị bỏ theo chính sách, tránh silent collision |

Lỗi phổ biến cần tránh là đặt `Map.put(name, member)` trong vòng lặp không định nghĩa thứ tự: “lần cuối thắng” tùy thuộc thứ tự JVM trả về. Ngay cả `putIfAbsent` cũng chỉ đúng khi **đầu vào đã được sắp xếp và thứ tự lớp đã được thiết kế**.

**Ghi nhớ:** field hiding giữ **nhiều ô lưu trữ**; method overriding xác định **triển khai instance được gọi**. Registry Reflection phải nêu rõ sẽ giữ tất cả hay chọn một đại diện, với khóa và thứ tự ổn định. Chính sách minh họa dùng “lớp con trước, cùng class sort, field theo tên, method theo tên + tham số, lọc bridge/synthetic/static” để tạo một kết quả dễ dự đoán; khi thêm interface hoặc non-public member, phải mở rộng chính sách tương ứng.

**Tham khảo tài liệu Java SE 21:**
- [`Class`: `getDeclaredFields`, `getDeclaredMethods`, `getMethods`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html)
- [`Method`: `invoke`, `isBridge`, `isSynthetic`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html)
- [`Field`: `get` và `getDeclaringClass`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Field.html)