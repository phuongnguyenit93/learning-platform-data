# Thay đổi kiểu tham số, giá trị trả về và quy tắc chuyển đổi kiểu

Trong Java, kiểu dữ liệu xuất hiện ở chữ ký phương thức và tại vị trí gọi quyết định compiler có chấp nhận mã nguồn hay không. Khi nâng cấp thư viện hoặc refactor API, thay đổi một kiểu tham số, kiểu trả về hoặc overload có thể khiến consumer không biên dịch được, chọn một phương thức khác hoặc gặp lỗi khi chạy.

Với Java Compatibility Migration, cần xem xét cả **source compatibility** và **binary compatibility**. Một thay đổi có thể vẫn cho phép source cũ biên dịch sau khi sửa rất ít, nhưng làm bytecode đã phát hành không còn liên kết được. Ngược lại, một thay đổi generic có thể giữ nguyên method descriptor sau type erasure nhưng vẫn làm source consumer thất bại hoặc thay đổi hành vi do cast ở phía gọi.

## 1. Chữ ký phương thức và vai trò của kiểu dữ liệu

Trong Java, chữ ký phương thức (*method signature*) được xác định chủ yếu bởi tên phương thức và kiểu tham số hình thức, sau khi áp dụng các quy tắc về generic và erasure. Kiểu trả về không được dùng để phân biệt hai overload.

Ví dụ:

```java
public String findName(long id) { ... }
public String findName(String code) { ... }
```

Hai phương thức có thể cùng tồn tại vì danh sách kiểu tham số khác nhau. Nhưng Java không cho phép khai báo hai phương thức chỉ khác kiểu trả về:

```java
// Không hợp lệ: không thể overload chỉ bằng kiểu trả về.
public String getValue() { ... }
public CharSequence getValue() { ... }
```

Điều này dẫn đến một điểm cần nhớ khi thay đổi API:

- Thay kiểu tham số làm thay đổi chữ ký nguồn và thường làm thay đổi descriptor của phương thức trong bytecode.
- Thay kiểu trả về không tạo overload mới, nhưng ảnh hưởng tới cách caller sử dụng kết quả và cũng làm thay đổi descriptor ở mức JVM.
- Thêm overload có thể làm thay đổi phương thức được chọn tại những call site vốn đã biên dịch thành công.
- Thay đổi generic type có thể ảnh hưởng kiểm tra kiểu ở source dù descriptor sau erasure không đổi.

## 2. Thay đổi kiểu tham số

Kiểu tham số xác định những đối số nào có thể truyền vào phương thức. Khi kiểu tham số thay đổi, cần kiểm tra các call site, subclass override, method reference, overload và generic type liên quan.

### 2.1. Thay kiểu tham số từ cụ thể sang tổng quát hơn

Giả sử API phiên bản 1 nhận `String`:

```java
public class NameService {
    public void setName(String name) {
        // Xử lý tên.
    }
}
```

Ứng dụng gọi:

```java
NameService service = new NameService();
String name = "An";
service.setName(name);
```

Phiên bản 2 thay tham số thành `CharSequence`:

```java
public class NameService {
    public void setName(CharSequence name) {
        // Xử lý chuỗi tổng quát.
    }
}
```

Lời gọi với `String` vẫn biên dịch vì `String` triển khai `CharSequence`. Đây là một ví dụ thay đổi kiểu tham số mà một số call site vẫn tương thích source.

Tuy nhiên, không thể kết luận toàn bộ consumer đều tương thích. Nếu consumer có subclass override phương thức cũ, kết quả sẽ khác:

```java
public class CustomNameService extends NameService {
    @Override
    public void setName(String name) {
        System.out.println("Custom: " + name);
    }
}
```

Khi thư viện đổi phương thức của lớp cha sang `setName(CharSequence)`, phương thức `setName(String)` trong subclass không còn override phương thức đó. Annotation `@Override` làm compiler báo lỗi. Nếu bỏ annotation, subclass vẫn có một overload riêng nhưng lời gọi dispatch qua kiểu `NameService` sẽ không gọi implementation cũ như trước.

Do đó, khi thay đổi tham số trong API có thể được subclass hóa, cần kiểm tra cả các lớp triển khai/ghi đè bên ngoài thư viện.

### 2.2. Thay kiểu tham số từ tổng quát sang cụ thể hơn

Nếu phiên bản cũ nhận `CharSequence`:

```java
public void setName(CharSequence name) { ... }
```

và phiên bản mới chỉ nhận `String`:

```java
public void setName(String name) { ... }
```

call site truyền `String` vẫn có thể biên dịch. Nhưng code truyền `StringBuilder` hoặc một implementation `CharSequence` khác sẽ không còn hợp lệ:

```java
service.setName(new StringBuilder("An"));
```

Compiler báo không tìm thấy phương thức phù hợp vì `StringBuilder` không phải `String`.

Thay tham số tổng quát bằng kiểu cụ thể hơn thường thu hẹp tập đối số hợp lệ. Nếu cần duy trì tương thích, thư viện có thể giữ overload cũ hoặc tạo adapter, miễn là vẫn thực hiện được đúng hợp đồng.

### 2.3. Thay đổi kiểu primitive

Các kiểu primitive có quy tắc widening và narrowing. Một số thay đổi tham số vẫn chấp nhận được nhờ widening primitive conversion.

Ví dụ, phiên bản cũ nhận `long`:

```java
public void setTimeout(long millis) { ... }
```

Phiên bản mới nhận `int`:

```java
public void setTimeout(int millis) { ... }
```

Call site truyền một giá trị `int` vẫn biên dịch, nhưng call site đang có biến `long` không thể tự động thu hẹp xuống `int`:

```java
long timeout = 5_000L;
service.setTimeout(timeout); // Lỗi: cần narrowing conversion tường minh.
```

Ngược lại, nếu API đổi từ `int` sang `long`, đối số `int` có thể tự widening:

```java
int timeout = 5_000;
service.setTimeout(timeout); // Có thể chuyển int thành long.
```

Dù call site biên dịch được, việc đổi kiểu vẫn có thể làm thay đổi semantics: giới hạn giá trị, overflow, cách tính toán, serialization hoặc giá trị được lưu xuống database.

### 2.4. Thay đổi giữa primitive và wrapper

Java hỗ trợ boxing và unboxing tự động trong nhiều ngữ cảnh.

```java
public void setCount(int count) { ... }

Integer value = 10;
service.setCount(value); // Unboxing Integer thành int.
```

Nếu `value` là `null`, code vẫn biên dịch nhưng ném `NullPointerException` khi unboxing.

Ngược lại:

```java
public void setCount(Integer count) { ... }

int value = 10;
service.setCount(value); // Boxing int thành Integer.
```

Thay `int` bằng `Integer` có thể thay đổi cách biểu diễn giá trị vắng mặt: `0` và `null` không giống nhau. Nó cũng có thể ảnh hưởng đến overload resolution, hiệu năng do boxing/unboxing và các API nhận generic type.

### 2.5. Thay đổi tham số generic

Generic type được kiểm tra ở compile time và Java áp dụng type erasure khi tạo bytecode. Tuy nhiên, type argument vẫn quan trọng đối với source compatibility.

Giả sử API cũ:

```java
public void addNames(List<String> names) { ... }
```

API mới đổi thành:

```java
public void addNames(List<Object> names) { ... }
```

Call site dùng `List<String>` không còn biên dịch vì generic Java là invariant: `List<String>` không phải subtype của `List<Object>`.

Điểm đáng chú ý là sau type erasure, cả hai tham số đều có erasure là `List`. Method descriptor ở JVM có thể vẫn là:

```text
(Ljava/util/List;)V
```

Vì vậy, một binary cũ có thể vẫn liên kết được, trong khi source được biên dịch lại lại thất bại. Đây là ví dụ rõ ràng cho thấy source compatibility và binary compatibility không đồng nhất.

Nếu phương thức chỉ đọc dữ liệu, wildcard có thể phù hợp hơn:

```java
public void printNames(List<? extends CharSequence> names) {
    for (CharSequence name : names) {
        System.out.println(name);
    }
}
```

`? extends` cho phép nhận các danh sách có phần tử là subtype của `CharSequence`, nhưng không cho phép thêm một giá trị tùy ý vào danh sách đó (ngoại trừ `null`). Nếu phương thức cần ghi vào collection, hãy chọn generic contract phù hợp thay vì đổi type argument một cách máy móc.

### 2.6. Thay đổi tham số mảng và varargs

Tham số varargs:

```java
public void log(String... messages) { ... }
```

được biểu diễn như tham số mảng `String[]` ở mức method signature/descriptor. Việc thay đổi giữa `String[]` và `String...` không tạo ra hai chữ ký khác nhau; khác biệt chính là cách call site được phép truyền danh sách đối số.

Thêm hoặc thay đổi overload có varargs có thể làm thay đổi lựa chọn phương thức, đặc biệt khi call site truyền `null`, một mảng hoặc số lượng đối số thay đổi. Cần compile lại các consumer có cách gọi như vậy để phát hiện lời gọi mơ hồ hoặc lựa chọn overload ngoài dự kiến.

## 3. Thay đổi kiểu trả về

Kiểu trả về quyết định kiểu dữ liệu mà caller nhận được. Khi kiểu trả về thay đổi, những biểu thức sử dụng kết quả cần được kiểm tra lại.

### 3.1. Thay kiểu trả về cụ thể bằng kiểu tổng quát hơn

API cũ:

```java
public String getDisplayName() {
    return "An";
}
```

Caller:

```java
String name = service.getDisplayName();
```

API mới:

```java
public CharSequence getDisplayName() {
    return "An";
}
```

Caller cũ không còn biên dịch vì `CharSequence` không thể tự động chuyển thành `String`:

```java
String name = service.getDisplayName(); // Lỗi kiểu dữ liệu.
```

Nếu caller chỉ cần một abstraction rộng hơn, có thể sửa kiểu biến:

```java
CharSequence name = service.getDisplayName();
```

Nhưng nếu caller cần API riêng của `String`, việc đổi kiểu biến không đủ; cần xác định cách chuyển đổi đúng, ví dụ `toString()` khi semantics cho phép.

### 3.2. Thay kiểu trả về tổng quát bằng kiểu cụ thể hơn

Nếu API đổi từ `CharSequence` sang `String`, nhiều caller đang nhận kết quả vào `CharSequence` vẫn biên dịch vì `String` là subtype. Caller đang dùng method reference hoặc generic inference cũng có thể nhận được kiểu cụ thể hơn.

Ví dụ:

```java
CharSequence name = service.getDisplayName();
```

vẫn hợp lệ nếu phương thức mới trả về `String`.

Tuy nhiên, thay đổi return type vẫn cần xem xét các subclass override. Một lớp con đang override bằng `CharSequence` sẽ không thể tiếp tục override nếu kiểu trả về của lớp cha được thu hẹp thành `String`, vì `CharSequence` không phải subtype của `String`.

### 3.3. Covariant return type trong override

Java cho phép phương thức override trả về kiểu con của kiểu trả về ở lớp cha. Đây gọi là *covariant return type*.

```java
class Animal {}
class Dog extends Animal {}

class AnimalFactory {
    Animal create() {
        return new Animal();
    }
}

class DogFactory extends AnimalFactory {
    @Override
    Dog create() {
        return new Dog();
    }
}
```

`Dog` là subtype của `Animal`, nên override hợp lệ. Caller có thể nhìn thấy kiểu trả về cụ thể hơn khi tham chiếu qua `DogFactory`:

```java
Dog dog = new DogFactory().create();
Animal animal = new DogFactory().create();
```

Nếu API lớp cha đổi kiểu trả về từ `Animal` thành một kiểu hẹp hơn không tương thích với kiểu trả về của subclass, source code của subclass có thể không còn biên dịch. Khi thiết kế thư viện được phép kế thừa, cần kiểm tra các override ở consumer.

### 3.4. Kiểu trả về không tạo overload

Java không cho phép phân biệt overload chỉ bằng return type. Vì vậy, nếu cần cung cấp một API mới với kiểu trả về khác mà vẫn giữ API cũ, thường phải dùng tên phương thức khác hoặc một kiểu wrapper/adapter riêng.

Ví dụ:

```java
public String getName() {
    return currentName;
}

public Optional<String> findName() {
    return Optional.ofNullable(currentName);
}
```

Cách này giúp người dùng chuyển đổi có chủ đích và tránh thay đổi bất ngờ ở mọi call site.

### 3.5. Ảnh hưởng của return type tới generic inference và method reference

Kiểu trả về tham gia vào quá trình kiểm tra kiểu của biểu thức và có thể ảnh hưởng tới generic inference hoặc method reference.

Ví dụ:

```java
Supplier<String> supplier = service::getDisplayName;
```

Nếu `getDisplayName()` đổi từ `String` thành `CharSequence`, method reference không còn phù hợp với `Supplier<String>`. Có thể cần đổi target type:

```java
Supplier<CharSequence> supplier = service::getDisplayName;
```

Tương tự, kiểu trả về của một generic method có thể ảnh hưởng đến type argument được suy luận. Khi thay đổi API, cần kiểm tra các call site dùng method chaining, lambda, method reference và generic helper, không chỉ những dòng gán trực tiếp vào biến.

## 4. Quy tắc chuyển đổi kiểu trong Java

Compiler chỉ chấp nhận các phép chuyển đổi được Java Language Specification cho phép trong từng ngữ cảnh. Một phép chuyển đổi hợp lệ khi gán biến chưa chắc hợp lệ khi gọi phương thức hoặc chọn overload.

### 4.1. Identity conversion

Identity conversion không thay đổi kiểu. Ví dụ, truyền một biến `String` vào tham số `String`:

```java
void print(String value) { }

String name = "An";
print(name);
```

Đây là trường hợp đơn giản nhất và thường ít rủi ro khi API không thay đổi.

### 4.2. Widening primitive conversion

Widening primitive conversion chuyển một giá trị primitive sang kiểu có phạm vi biểu diễn rộng hơn theo quy tắc Java. Ví dụ:

```java
byte b = 10;
short s = b;
int i = s;
long l = i;
float f = l;
double d = f;
```

Một số đường chuyển đổi thường gặp:

| Từ | Có thể widening tới |
|---|---|
| `byte` | `short`, `int`, `long`, `float`, `double` |
| `short` | `int`, `long`, `float`, `double` |
| `char` | `int`, `long`, `float`, `double` |
| `int` | `long`, `float`, `double` |
| `long` | `float`, `double` |
| `float` | `double` |

`boolean` không chuyển đổi sang kiểu số. Widening không có nghĩa mọi giá trị đều được bảo toàn chính xác: chuyển `long` sang `float` hoặc `double` có thể mất độ chính xác do số thực có số bit significand hữu hạn.

### 4.3. Narrowing primitive conversion

Narrowing chuyển sang kiểu có phạm vi hẹp hơn và thường yêu cầu cast tường minh:

```java
long total = 1_000L;
int count = (int) total;
```

Nếu giá trị vượt phạm vi của kiểu đích, kết quả có thể bị tràn hoặc mất thông tin. Cast không tự kiểm tra giá trị có an toàn hay không.

Java có một ngoại lệ trong assignment context: một biểu thức hằng kiểu `int` có giá trị biểu diễn được trong `byte`, `short` hoặc `char` có thể được gán mà không cần cast:

```java
byte small = 10; // Hợp lệ: hằng int nằm trong phạm vi byte.
```

Nhưng ngoại lệ này không áp dụng giống vậy cho method invocation:

```java
void accept(byte value) { }

accept(10); // Không hợp lệ: method invocation không tự narrowing int xuống byte.
```

Sự khác nhau giữa assignment context và method invocation context là một nguồn lỗi phổ biến khi thay đổi kiểu tham số.

### 4.4. Widening reference conversion

Một object có thể được tham chiếu qua kiểu cha hoặc interface mà nó triển khai:

```java
String text = "Java";
CharSequence sequence = text;
Object value = text;
```

Phép chuyển đổi này không thay đổi object thực tế, chỉ thay đổi kiểu tĩnh mà compiler dùng để kiểm tra truy cập.

Nếu API đổi tham số từ subtype sang supertype, một số call site có thể tiếp tục biên dịch nhờ widening reference conversion. Tuy nhiên, thay đổi đó có thể ảnh hưởng override, overload và semantics của implementation.

### 4.5. Narrowing reference conversion và cast

Chuyển từ kiểu cha xuống kiểu con cần cast:

```java
Object value = "Java";
String text = (String) value;
```

Compiler có thể chấp nhận cast nhưng runtime kiểm tra kiểu object thực tế. Nếu object không phải `String`, chương trình ném `ClassCastException`.

Khi API đổi kiểu trả về từ `String` thành `Object`, caller có thể thêm cast để biên dịch, nhưng đây không phải sửa chữa an toàn nếu chưa có bảo đảm về kiểu object thực tế.

### 4.6. Boxing và unboxing

Boxing chuyển primitive thành wrapper tương ứng; unboxing làm ngược lại:

```java
int count = 5;
Integer boxed = count; // Boxing.

Integer stored = 10;
int unboxed = stored;  // Unboxing.
```

Unboxing `null` ném `NullPointerException`. Boxing cũng có thể tạo object và ảnh hưởng tới allocation/performance trong vòng lặp lớn hoặc API được gọi thường xuyên.

Không có phép chuyển đổi boxing kết hợp widening primitive theo mọi chiều. Ví dụ, `int` không tự boxing thành `Long`; `Integer` không tự chuyển thành `Long` chỉ vì `int` có thể widening thành `long`.

### 4.7. Numeric promotion trong biểu thức

Trong nhiều phép toán số học, `byte`, `short` và `char` được promote lên `int` trước khi thực hiện phép toán:

```java
byte a = 1;
byte b = 2;
// byte result = a + b; // Lỗi: biểu thức có kiểu int.
byte result = (byte) (a + b);
```

Nếu phép toán có `long`, `float` hoặc `double`, các toán hạng được promote theo quy tắc binary numeric promotion. Khi thay đổi kiểu tham số hoặc return type, cần xem cả kiểu của biểu thức được truyền vào, không chỉ kiểu khai báo của biến ban đầu.

### 4.8. Null và kiểu tham chiếu

`null` có thể gán cho kiểu tham chiếu, nhưng không thể gán cho primitive. Khi API thay wrapper bằng primitive, call site truyền `null` không còn biên dịch hoặc có thể bị unboxing gây lỗi tùy ngữ cảnh.

`null` cũng có thể làm overload trở nên mơ hồ:

```java
void send(String value) { }
void send(java.nio.file.Path value) { }

send(null); // Lỗi: String và Path không có quan hệ subtype với nhau.
```

Khi bổ sung overload cho API công khai, hãy xem các call site có truyền literal `null` hoặc biểu thức có kiểu tham chiếu rộng.

## 5. Overload resolution và thay đổi hành vi call site

Compiler không chọn overload chỉ dựa trên số lượng tham số. Nó xét kiểu tĩnh của đối số, các phép chuyển đổi được phép, generic inference, varargs và quy tắc chọn phương thức cụ thể nhất.

### 5.1. Các giai đoạn tìm overload

Ở mức khái quát, Java xét các phương thức phù hợp theo thứ tự:

1. Pha strict invocation: các phép identity, widening primitive và widening reference phù hợp.
2. Pha loose invocation: cho phép thêm boxing/unboxing cùng các chuyển đổi được quy định.
3. Pha variable arity: xét các phương thức varargs khi các pha trước không tìm được phương thức phù hợp.

Khi có nhiều phương thức phù hợp trong cùng pha, compiler chọn phương thức cụ thể nhất theo quan hệ kiểu. Nếu không có một phương thức cụ thể nhất duy nhất, lời gọi bị báo ambiguous.

### 5.2. Thêm overload có thể đổi phương thức được gọi

Phiên bản thư viện ban đầu:

```java
public void send(Object value) {
    System.out.println("object");
}
```

Ứng dụng gọi:

```java
send("hello");
```

Sau khi thư viện thêm overload:

```java
public void send(String value) {
    System.out.println("string");
}
```

Source cũ vẫn biên dịch, nhưng lời gọi `send("hello")` giờ chọn overload `String` vì đây là kiểu cụ thể hơn. Hành vi thực thi có thể thay đổi dù không có lỗi compiler.

Nếu bổ sung hai overload nhận hai kiểu không liên quan, lời gọi truyền `null` có thể trở nên mơ hồ:

```java
public void send(String value) { }
public void send(java.nio.file.Path value) { }

send(null); // Không xác định được overload phù hợp nhất.
```

Đây là lý do việc thêm API cũng cần được đánh giá về source compatibility, không chỉ việc xóa hoặc đổi tên API.

### 5.3. Overload với primitive, wrapper và widening

Ví dụ:

```java
void choose(long value) {
    System.out.println("long");
}

void choose(Integer value) {
    System.out.println("Integer");
}

choose(1);
```

Lời gọi chọn `choose(long)` vì widening primitive thuộc pha strict invocation và được xét trước pha cần boxing thành `Integer`. Nếu thay đổi overload hoặc kiểu đối số, phương thức được chọn có thể thay đổi.

Khi migration API, hãy kiểm tra những call site dùng literal số, wrapper, `null`, generic method, lambda và method reference. Các vị trí này thường nhạy với thay đổi overload hơn những lời gọi có biến kiểu cụ thể.

## 6. Generic type, erasure và bridge method

### 6.1. Type erasure không loại bỏ ảnh hưởng source

Java generic được thực thi bằng type erasure. Ví dụ, `List<String>` và `List<Integer>` có cùng raw type `List` ở runtime. Tuy nhiên, compiler vẫn kiểm tra type argument khi biên dịch source.

Do đó, đổi tham số từ `List<String>` sang `List<Object>` có thể giữ nguyên descriptor sau erasure nhưng làm consumer không biên dịch lại được. Ngược lại, nếu implementation mới giả định mọi phần tử là `Object` trong khi caller cũ đã biên dịch theo một hợp đồng khác, lỗi có thể chỉ xuất hiện khi chạy.

### 6.2. Name clash do erasure

Hai phương thức có generic signature khác nhau nhưng cùng erasure không thể được overload:

```java
void process(List<String> values) { }

// Không hợp lệ: cùng erasure là process(List).
void process(List<Integer> values) { }
```

Compiler báo name clash vì hai method descriptor sau erasure trùng nhau. Khi thay đổi generic API, hãy kiểm tra cả erasure, type bounds và các overload hiện có.

### 6.3. Bridge method

Compiler có thể sinh bridge method để duy trì đa hình sau type erasure hoặc hỗ trợ covariant return. Ví dụ:

```java
class Box<T> {
    T get() { return null; }
}

class StringBox extends Box<String> {
    @Override
    String get() { return "value"; }
}
```

Compiler có thể sinh method bridge trong `StringBox` để lời gọi qua kiểu đã xóa generic vẫn dispatch đúng. Bridge là chi tiết bytecode do compiler quản lý; không nên dựa vào việc tự tạo bridge hoặc coi mọi thay đổi generic đều tự động được bảo vệ bởi erasure.

## 7. Ảnh hưởng tới binary compatibility

Source compatibility là khả năng biên dịch lại source consumer. Binary compatibility là khả năng bytecode đã biên dịch trước đó liên kết với phiên bản thư viện mới.

JVM method descriptor bao gồm kiểu tham số và kiểu trả về. Vì vậy, đổi kiểu tham số hoặc kiểu trả về có thể làm descriptor thay đổi.

Ví dụ, binary cũ được biên dịch để gọi:

```java
String getName()
```

descriptor có phần mô tả return type là `Ljava/lang/String;`. Nếu thư viện mới chỉ còn:

```java
CharSequence getName()
```

descriptor mới kết thúc bằng `Ljava/lang/CharSequence;`. Binary cũ có thể không tìm thấy method descriptor mà nó đã tham chiếu và gặp `NoSuchMethodError`.

Tương tự, đổi tham số `String` thành `CharSequence` làm descriptor thay đổi từ `(Ljava/lang/String;)V` sang `(Ljava/lang/CharSequence;)V`. Dù source consumer truyền `String` vẫn có thể biên dịch, binary consumer cũ vẫn cần method descriptor cũ để liên kết.

Nếu thư viện cần duy trì binary compatibility, giải pháp thường là giữ method cũ và cho nó delegate sang implementation mới:

```java
public void setName(String name) {
    setName((CharSequence) name);
}

public void setName(CharSequence name) {
    // Implementation mới.
}
```

Với return type, Java source không thể khai báo hai method chỉ khác return type. Vì vậy, để duy trì descriptor cũ, thường phải giữ method cũ và thêm method tên khác cho API mới, hoặc dùng một cơ chế bridge bytecode được kiểm soát bởi công cụ chuyên biệt. Không nên giả định thay return type là thay đổi an toàn chỉ vì caller source có thể sửa dễ dàng.

## 8. Thiết kế API để giảm rủi ro migration

### 8.1. Giữ overload cũ trong giai đoạn chuyển tiếp

Nếu thay đổi kiểu tham số nhưng vẫn có thể duy trì semantics, giữ overload cũ và chuyển tiếp:

```java
public void setName(String name) {
    setName((CharSequence) name);
}

public void setName(CharSequence name) {
    // Xử lý theo hợp đồng mới.
}
```

Có thể đánh dấu overload cũ deprecated để consumer chuyển dần. Chỉ xóa nó ở một major release có thông báo và migration guide rõ ràng.

### 8.2. Chọn abstraction phù hợp ngay từ đầu

Nếu phương thức chỉ cần đọc nội dung ký tự, nhận `CharSequence` có thể phù hợp hơn `String`. Nếu cần sửa dữ liệu, có thể cần một abstraction khác hoặc sao chép dữ liệu vào kiểu nội bộ. Đừng mở rộng kiểu tham số nếu implementation không thể hỗ trợ đúng mọi implementation của abstraction đó.

Với collection, cân nhắc wildcard theo nguyên tắc producer/consumer:

- Dùng `? extends T` khi chủ yếu đọc giá trị kiểu T từ collection.
- Dùng `? super T` khi chủ yếu ghi giá trị kiểu T vào collection.

Đây là cách thiết kế generic API linh hoạt hơn mà vẫn giữ được type safety.

### 8.3. Tránh overload không cần thiết

Nhiều overload gần nhau có thể làm lời gọi với `null`, lambda hoặc literal số trở nên khó đoán. Nếu hai hành vi khác nhau đáng kể, tên phương thức riêng có thể giúp call site rõ ràng hơn.

### 8.4. Không dùng cast để che giấu thay đổi hợp đồng

Ép kiểu có thể làm compiler hết báo lỗi nhưng đẩy lỗi sang runtime. Trước khi thêm cast, cần chứng minh object thực tế luôn có kiểu đích hoặc có kiểm tra phù hợp. Với numeric narrowing, cần xác nhận giới hạn giá trị và xử lý overflow.

## 9. Quy trình đánh giá thay đổi kiểu trong một đợt migration

1. **Chốt API baseline:** lưu artifact cũ, public API, generic signature và phiên bản dependency.
2. **Tìm consumer:** xác định mọi module, dịch vụ hoặc ứng dụng gọi API, kế thừa class hoặc implement interface liên quan.
3. **So sánh khai báo:** ghi nhận thay đổi tham số, return type, generic bounds, checked exception, visibility và overload.
4. **Biên dịch lại consumer:** compile toàn bộ source consumer với thư viện mới để phát hiện lỗi kiểu và overload.
5. **Kiểm tra binary:** nếu cần hỗ trợ binary đã phát hành, chạy consumer cũ với thư viện mới hoặc dùng công cụ phân tích binary compatibility.
6. **Kiểm tra hành vi:** test overload dispatch, null, boxing/unboxing, numeric boundaries, generic collection, serialization và exception.
7. **Duy trì chuyển tiếp:** giữ adapter/overload hoặc phát hành major version có migration guide khi không thể duy trì hợp đồng cũ.
8. **Ghi nhận quyết định:** lưu lý do đổi kiểu, consumer bị ảnh hưởng, phiên bản loại bỏ API cũ và thời hạn hỗ trợ.

### 9.1. Tìm call site và override

Tìm kiếm theo tên API là bước đầu, nhưng cần kiểm tra thêm:

- Các lớp con có `@Override` phương thức đó.
- Các interface implementation trong module khác.
- Method reference như `service::getValue` hoặc `service::setValue`.
- Lambda và generic helper có type inference phụ thuộc return type.
- Call site truyền `null`, literal số, wrapper hoặc collection generic.
- Reflection gọi method theo tên và kiểu tham số.

Source search không phải lúc nào cũng tìm được quan hệ được tạo động. Với thư viện công khai, cần xem xét các consumer ngoài repository nếu không kiểm soát toàn bộ hệ sinh thái.

### 9.2. Công cụ hỗ trợ

`javap -s` hiển thị descriptor của phương thức trong bytecode:

```bash
javap -classpath old-library.jar -s com.example.NameService
javap -classpath new-library.jar -s com.example.NameService
```

So sánh output giúp nhận ra thay đổi descriptor. `javap -v` có thể hiển thị thêm generic signature, flags và bridge method.

Các công cụ phân tích API/binary compatibility như japicmp hoặc Revapi có thể hỗ trợ phát hiện thay đổi public API giữa hai artifact. Cần cấu hình đúng phạm vi module, filter và policy vì tool không tự biết hợp đồng nào là chủ ý thay đổi.

Đối với source compatibility, phép kiểm tra có giá trị trực tiếp nhất vẫn là biên dịch lại các consumer đại diện với API mới. Với binary compatibility, cần kiểm tra artifact đã biên dịch trước đó. Với behavioral compatibility, cần chạy test trên các trường hợp đầu vào và luồng nghiệp vụ quan trọng.

## 10. Ví dụ tổng hợp: thay đổi kiểu có thể ảnh hưởng nhiều lớp

Giả sử thư viện cũ:

```java
public class ReportService {
    public String format(int count) {
        return "count=" + count;
    }
}
```

Consumer:

```java
ReportService service = new ReportService();
String text = service.format(10);
```

Trong phiên bản mới, thư viện đổi tham số thành `long` và return type thành `CharSequence`:

```java
public class ReportService {
    public CharSequence format(long count) {
        return "count=" + count;
    }
}
```

Lời gọi `service.format(10)` vẫn có thể tìm được phương thức nhờ widening từ `int` sang `long`. Nhưng phép gán kết quả vào `String` không còn hợp lệ vì kiểu trả về là `CharSequence`.

Ngay cả khi sửa consumer:

```java
CharSequence text = service.format(10);
```

binary cũ vẫn tham chiếu descriptor có tham số `int` và return `String`. Nếu thư viện chỉ phát hành method mới, binary cũ có thể gặp `NoSuchMethodError`. Nếu `ReportService` được subclass ở consumer, method override cũ cũng cần được cập nhật.

Một thiết kế chuyển tiếp có thể giữ API cũ:

```java
public class ReportService {
    @Deprecated(since = "2.0", forRemoval = true)
    public String format(int count) {
        return format((long) count).toString();
    }

    public CharSequence format(long count) {
        return "count=" + count;
    }
}
```

Đoạn code minh họa việc giữ method cũ để consumer có thời gian chuyển đổi. Trong thư viện thực tế, cần xác nhận chuyển đổi từ `int` sang `long` và `CharSequence` sang `String` giữ đúng semantics, xử lý null và hiệu năng theo hợp đồng cũ.

## 11. Checklist cho thay đổi kiểu API

- [ ] Đã ghi nhận method signature và descriptor trước/sau thay đổi.
- [ ] Đã kiểm tra tất cả call site và kiểu tĩnh của đối số.
- [ ] Đã rà soát subclass override và interface implementation.
- [ ] Đã xem xét widening/narrowing primitive và nguy cơ mất dữ liệu.
- [ ] Đã kiểm tra boxing/unboxing, đặc biệt với `null`.
- [ ] Đã kiểm tra generic invariance, wildcard, erasure và name clash.
- [ ] Đã đánh giá overload resolution với literal, `null`, lambda và method reference.
- [ ] Đã kiểm tra return type ở assignment, chaining và generic inference.
- [ ] Đã xác định source compatibility và binary compatibility riêng biệt.
- [ ] Đã biên dịch lại consumer và chạy binary cũ nếu yêu cầu tương thích.
- [ ] Đã kiểm thử hành vi, boundary value, exception và serialization.
- [ ] Đã có adapter/deprecation/migration guide nếu API cũ cần giai đoạn chuyển tiếp.

## 12. Kết luận

Thay đổi kiểu tham số và return type có thể ảnh hưởng tới call site, override, overload, generic inference và method descriptor. Các phép chuyển đổi tự động của Java như widening, boxing và unboxing giúp một số source tiếp tục biên dịch, nhưng không đảm bảo hành vi không đổi. Narrowing, generic invariance, overload ambiguity và null thường là các điểm dễ phát sinh lỗi.

Khi thay đổi API trong Java Compatibility Migration, hãy kiểm tra cả source consumer và binary đã phát hành, xem xét quy tắc chuyển đổi kiểu tại từng call site, rồi giữ adapter hoặc overload cũ khi cần một giai đoạn chuyển tiếp. Chỉ xác nhận migration sau khi compile, liên kết binary và test hành vi đều đáp ứng hợp đồng đã công bố.
