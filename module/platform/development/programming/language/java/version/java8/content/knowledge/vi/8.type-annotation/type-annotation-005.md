# Receiver parameter và metadata cho receiver trong Java

## 1. Receiver parameter là gì?

Từ Java 8, ngôn ngữ Java cho phép viết **receiver parameter** (tham số receiver) trong một **instance method** hoặc trong constructor của một **inner member class** không static. Đây là một cơ chế cú pháp để **chỉ rõ kiểu của đối tượng nhận lời gọi (receiver)**, chủ yếu nhằm cho phép **type annotation** gắn vào kiểu đó.

Ví dụ một instance method:

```java
class MessageService {
    String format(MessageService this, String text) {
        return text.trim();
    }
}
```

`MessageService this` trong dấu ngoặc là receiver parameter. Nó biểu thị **chính instance `MessageService`** đang nhận lời gọi `format`. Khi gọi:

```java
MessageService service = new MessageService();
String output = service.format(" Java "); // "Java"
```

Caller **chỉ truyền một đối số** `" Java "`; không truyền thêm một `MessageService` vào danh sách tham số. Receiver parameter không phải một biến tham số thông thường. Nó **không thay đổi chữ ký phương thức**, không tạo overload mới, không thay thế từ khóa `this` và không thêm một đối số nguồn ở thời điểm gọi. Nó cũng không tạo ra cơ chế injection hoặc dependency passing.

Trong ví dụ trên, vì receiver parameter không có annotation nên việc viết nó thường không đem lại lợi ích thực tế. Giá trị chủ yếu xuất hiện khi ta gắn **annotation có `@Target(ElementType.TYPE_USE)`** lên kiểu receiver:

```java
void process(@ReceiverLabel("service") MessageService this, String text) {
    // Thân phương thức vẫn dùng this bình thường.
}
```

`@ReceiverLabel` ở ví dụ này là annotation do ứng dụng tự định nghĩa, **không phải annotation có sẵn trong JDK**. Phần tiếp theo sẽ khai báo đầy đủ nó và chỉ cách quan sát bằng Reflection API.

**Điểm cần nhớ:** source code có thể mô tả metadata cho receiver, còn hành vi lời gọi instance method của Java vẫn tuân theo các quy tắc thông thường.

## 2. Receiver khác tham số hình thức bình thường như thế nào?

Xét cú pháp:

```java
void execute(@ReceiverLabel("current") Worker this, String task, int retries) {
    // ...
}
```

Ở đây `Worker this` là receiver parameter; `String task` và `int retries` mới là **formal parameters** (tham số hình thức) của method. Để gọi `execute`, người dùng viết `worker.execute("build", 2)` chứ không phải `worker.execute(worker, "build", 2)`.

| Thuộc tính | Receiver parameter | Formal parameter |
| --- | --- | --- |
| Vai trò | Biểu diễn đối tượng `this` nhận lời gọi hoặc enclosing instance trong inner constructor | Nhận giá trị đối số từ caller |
| Cú pháp điển hình | `Worker this`, `Outer Outer.this` | `String task`, `int retries` |
| Vị trí | Đứng **đầu tiên** trong danh sách khai báo nếu xuất hiện | Theo sau receiver parameter, hoặc bắt đầu danh sách nếu không có receiver |
| Có thể là biến cục bộ để gán lại? | **Không**; không phải khai báo biến | Là biến tham số; có các quy tắc gán riêng |
| Có làm tăng arity khi gọi method? | **Không** | **Có** |
| Có được tính trong `Method.getParameterCount()`? | **Không** | **Có** |
| Gắn type annotation? | Có, bằng annotation dùng được ở `TYPE_USE` | Có thể gắn annotation theo các `@Target` phù hợp |
| Mục đích điển hình | Metadata cho kiểu receiver và công cụ phân tích | Truyền dữ liệu vào phép tính |

Một số chi tiết khác vẫn quan trọng:

- Receiver parameter chỉ có thể xuất hiện ở những vị trí Java Language Specification cho phép.
- Nếu có receiver parameter, nó phải đứng **trước** các formal parameter còn lại.
- Receiver parameter không có `final` như một formal parameter, không dùng để khai báo biến mới tên `this` và không cho phép tự chọn tên như `receiver`.
- `this` bên trong thân instance method vẫn là biểu thức tham chiếu tới đối tượng hiện tại; việc ghi `Worker this` ở header không tạo thêm một đối tượng `this` mới.

### 2.1. Receiver parameter không phải `this` truyền tường minh ở mọi lời gọi

Ở mức trừu tượng JVM, instance method có đối tượng nhận lời gọi. Nhưng phần receiver parameter được viết thêm trong source code **không biến receiver thành một tham số formal riêng** trong chữ ký Java và không bắt caller gửi thêm đối số.

Lời gọi thông thường:

```java
service.format("  hi  ");
```

có cùng dạng với lời gọi khi method được viết không có receiver parameter:

```java
String format(String text) {
    return text.trim();
}
```

Khác biệt có ý nghĩa ở đây là **vị trí cho type annotation** và metadata tương ứng, không phải cách thức truyền dữ liệu.

## 3. Cú pháp hợp lệ trong instance method

Trong một instance method của lớp `Document`, kiểu receiver phải là lớp/interface nơi method được khai báo và tên receiver phải là `this`:

```java
class Document {
    void save(Document this, String path) {
        System.out.println(path);
    }
}
```

Đây là đoạn code minh họa hợp lệ. Có thể gắn annotation lên kiểu:

```java
class Document {
    void save(@ReceiverLabel("doc") Document this, String path) {
        System.out.println(path);
    }
}
```

`@ReceiverLabel` cần được khai báo như mục 5. Với interface instance method, receiver cũng phải có kiểu là chính interface khai báo method. Ví dụ minh họa:

```java
interface Identifiable {
    String id();

    default String describe(Identifiable this) {
        return "id=" + id();
    }
}
```

`describe` là một default instance method, nên vị trí receiver parameter hợp lệ. Dù có `Identifiable this`, caller vẫn gọi `obj.describe()` **không có đối số**.

### 3.1. Receiver parameter phải đứng đầu

Ví dụ cố ý sai:

```java
class Worker {
    // KHÔNG BIÊN DỊCH: receiver parameter không đứng đầu.
    // void run(String task, Worker this) {}
}
```

Cú pháp đúng là:

```java
class Worker {
    void run(Worker this, String task) {}
}
```

### 3.2. Tên và kiểu receiver không được tùy chọn

Trong class `Worker`, các khai báo sau là sai:

```java
class Worker {
    // KHÔNG BIÊN DỊCH: tên phải là this.
    // void a(Worker receiver) {} // Đây lại là formal parameter bình thường.

    // KHÔNG BIÊN DỊCH nếu viết như receiver:
    // void b(Object this) {}

    // KHÔNG BIÊN DỊCH:
    // void c(Worker worker.this) {}
}
```

Làm rõ dòng đầu: `void a(Worker receiver) {}` **thực tế là một method hợp lệ** nhận một tham số thông thường tên `receiver`. Nó **không phải receiver parameter**, và phải được gọi với một đối số `Worker`. Vì vậy, nếu người lập trình muốn receiver parameter thì phải viết `Worker this`, không thể đổi thành `Worker receiver`. Các dòng `Object this` và `Worker worker.this` là những dạng receiver parameter sai luật trong ngữ cảnh này.

### 3.3. Instance method trong lớp generic

Nếu lớp có tham số kiểu, receiver phải mô tả đúng kiểu lớp trong ngữ cảnh phù hợp. Ví dụ:

```java
class Holder<T> {
    T get(Holder<T> this, T value) {
        return value;
    }
}
```

Đoạn này minh họa rằng receiver có thể dùng kiểu tham số hóa của chính lớp. Nó không cho phép gán một kiểu receiver tùy ý, chẳng hạn biến `Holder<T> this` thành một lớp không liên quan. Với mã generic phức tạp, ưu tiên viết cú pháp tối giản và dùng compiler/JLS để kiểm tra tính đúng đắn.

## 4. Constructor của inner class: receiver là enclosing instance

Receiver parameter trong constructor **khác với receiver của instance method**. Đối với constructor của **non-static inner member class**, receiver parameter biểu diễn **instance của lớp/interface bao ngoài trực tiếp** (immediately enclosing instance) của đối tượng inner class đang được tạo.

Ví dụ:

```java
class Outer {
    class Inner {
        Inner(Outer Outer.this, String name) {
            System.out.println(name);
        }
    }
}
```

Đây là cú pháp hợp lệ. `Outer Outer.this` **không** có nghĩa đang truyền một đối tượng `Inner` vào constructor. Nó mô tả enclosing `Outer` đã gắn với instance `Inner`.

Caller tạo đối tượng theo cú pháp bình thường:

```java
Outer outer = new Outer();
Outer.Inner inner = outer.new Inner("A");
```

Trong source code, caller vẫn chỉ viết đối số `"A"` cho tham số hình thức `String name`. Không viết `outer.new Inner(outer, "A")` để “truyền thêm receiver”.

### 4.1. Vì sao tên `Outer.this` quan trọng?

Trong non-static inner class, Java có khái niệm instance bao ngoài và qualified `Outer.this`. Receiver parameter của constructor dùng:

```text
Outer Outer.this
^^^^^ ^^^^^^^^^^
type  tên receiver: tên đơn giản của lớp bao ngoài + .this
```

Các quy tắc JLS cho constructor của inner class yêu cầu:

- Kiểu receiver là kiểu bao ngoài trực tiếp chứa declaration của inner class.
- Tên receiver dùng **tên đơn giản của kiểu bao ngoài** nối với `.this`.
- Nó đứng ở đầu danh sách nếu constructor còn có formal parameters.
- Nó chỉ hợp lệ ở constructor của inner class trong ngữ cảnh cho phép (không phải mọi constructor Java).

Trong cấu trúc nhiều cấp lồng nhau, cách viết kiểu có thể cần qualified type name phù hợp; không tự đoán receiver luôn là lớp ngoài cùng.

### 4.2. Không hợp lệ với constructor của top-level hoặc static nested class

Một lớp top-level thông thường không có enclosing instance, nên không thể tự thêm `ClassName this` vào constructor để làm receiver:

```java
class TopLevel {
    // KHÔNG BIÊN DỊCH nếu bỏ comment:
    // TopLevel(TopLevel this) {}
}
```

Tương tự, constructor của `static nested class` không có immediately enclosing instance theo nghĩa trên; không dùng `Outer Outer.this`. Theo tài liệu Reflection API, constructor của top-level, static member, local hoặc anonymous class không có receiver type khả dụng cho `getAnnotatedReceiverType()`.

**Đừng nhầm** khả năng một inner-class constructor có tham số synthetic/mandated ở bytecode với receiver parameter trong cú pháp nguồn. Chúng là hai khái niệm khác nhau: receiver parameter là vị trí cú pháp cho type annotation, còn chi tiết chuyển đổi enclosing instance thành tham số thực thi phản ánh cách compiler biểu diễn inner class.

## 5. Khai báo type annotation để gắn vào receiver

Để gắn annotation vào *type use* của receiver, hãy khai báo annotation với `ElementType.TYPE_USE`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE_USE)
@interface ReceiverLabel {
    String value();
}
```

Giải thích từng annotation:

- `@Target(ElementType.TYPE_USE)` cho phép `@ReceiverLabel` xuất hiện ở vị trí sử dụng kiểu, trong đó có kiểu receiver.
- `@Retention(RetentionPolicy.RUNTIME)` yêu cầu metadata còn khả dụng cho Reflection API lúc chạy.
- `String value()` là giá trị nhãn do ứng dụng quy định; khi viết `@ReceiverLabel("service")`, chuỗi `"service"` là annotation element `value`.
- Bản thân annotation **không tự kiểm tra logic nghiệp vụ**. Nếu muốn ý nghĩa “receiver không null”, “receiver an toàn luồng”, hoặc “đang giữ lock”, bạn cần một công cụ phân tích, bộ xử lý annotation hay chính sách kiểm tra phù hợp.

Trong chương trình chạy độc lập ở mục 11, annotation được khai báo dưới dạng nested annotation để tránh tạo nhiều tệp.

### 5.1. `TYPE_USE` không giống `PARAMETER`

`@Target(ElementType.PARAMETER)` dùng cho **declaration annotation trên formal parameter**. Receiver parameter **không phải formal parameter**, nên không thể suy luận rằng annotation chỉ có `PARAMETER` là đủ để gắn lên receiver type.

Ví dụ minh họa (các khai báo cần đặt trong ngữ cảnh hợp lệ):

```java
@Target(ElementType.PARAMETER)
@interface ArgumentNote {
}

@Target(ElementType.TYPE_USE)
@interface ReceiverNote {
}

class Sample {
    void run(@ReceiverNote Sample this,
             @ArgumentNote String text) {}
}
```

`@ReceiverNote` ở đây áp dụng cho **kiểu của receiver**, còn `@ArgumentNote` áp dụng cho **khai báo tham số `text`**. Đừng nhầm vì cả hai đều xuất hiện trong cặp ngoặc của method.

Một annotation có thể khai báo nhiều `ElementType` nếu thật sự cần dùng ở nhiều loại vị trí, nhưng hãy thiết kế target theo mục đích và đọc đúng Reflection API.

### 5.2. Retention quyết định nơi metadata còn tồn tại

| Retention | Tình trạng metadata | Có đọc được bằng core reflection tại runtime không? |
| --- | --- | --- |
| `SOURCE` | Chỉ cần trong source; compiler không lưu như runtime metadata | Không |
| `CLASS` | Lưu trong class file theo luật Java, nhưng không có yêu cầu phơi bày qua core reflection | Không, đối với annotation dùng trực tiếp qua Reflection API thông thường |
| `RUNTIME` | Có thể đọc bằng Reflection API nếu annotation nằm ở target và API hỗ trợ | Có |

Nếu không khai báo retention rõ, mặc định là `CLASS`. Do đó, để chương trình dùng `getAnnotatedReceiverType().getAnnotation(...)` hoạt động theo mong đợi, cần `@Retention(RetentionPolicy.RUNTIME)`.

Annotation gắn vào kiểu receiver là **metadata mô tả vị trí type-use**, không tự kích hoạt kiểm tra null hoặc chặn gọi method. Một thư viện phân tích tĩnh có thể chọn diễn giải metadata đó, nhưng hành vi không đến từ core Java chỉ nhờ annotation xuất hiện trong source.

## 6. Metadata trong class file dành cho receiver

Java Virtual Machine Specification định nghĩa cấu trúc metadata cho **type annotation**. Với annotation có retention phù hợp, compiler có thể ghi thuộc tính:

- `RuntimeVisibleTypeAnnotations` cho annotation khả dụng tại runtime.
- `RuntimeInvisibleTypeAnnotations` cho annotation được lưu trong class file nhưng không phơi bày bởi cơ chế reflection thông thường.

Trong bảng `target_type` của JVM specification:

| `target_type` | Vị trí type annotation |
| --- | --- |
| `0x14` | Kiểu trả về của method hoặc kiểu đối tượng được tạo |
| **`0x15`** | **Kiểu receiver của method hoặc constructor** |
| `0x16` | Kiểu của formal parameter của method, constructor hoặc lambda |

Vì vậy, type annotation trên receiver được phân biệt với annotation trên kiểu của tham số hình thức thông thường. `0x15` là thông tin về **vị trí metadata**, không phải mã opcode khiến phương thức chạy khác đi.

Đối với receiver type, phần `target_info` dùng dạng `empty_target` theo JVMS. Các chi tiết bytecode cụ thể là mức nâng cao; thường bạn chỉ cần Reflection API hoặc một thư viện đọc class file khi phát triển công cụ phân tích.

### 6.1. Xem metadata bằng `javap`

Sau khi biên dịch tệp có type annotation trên receiver, có thể dùng:

```bash
javap -v ReceiverMetadataDemo$Service
```

Trên shell có xử lý ký tự `$`, hãy đặt tên lớp nested trong dấu nháy thích hợp, chẳng hạn `'ReceiverMetadataDemo$Service'` trên shell Unix, để không bị shell mở rộng biến môi trường. Trên Windows PowerShell, có thể dùng dấu nháy đơn tương tự.

Đầu ra của `javap -v` khá dài và phụ thuộc bản compiler/JDK; không nên viết test phụ thuộc hoàn toàn vào cách trình bày văn bản của lệnh này. Mục tiêu là kiểm tra các thuộc tính `RuntimeVisibleTypeAnnotations` hoặc `RuntimeInvisibleTypeAnnotations` và target receiver tương ứng.

## 7. Reflection: `Executable.getAnnotatedReceiverType()`

Từ Java 8, `java.lang.reflect.Executable` có phương thức:

```java
AnnotatedType getAnnotatedReceiverType()
```

`Method` và `Constructor` kế thừa khả năng này. Nó trả về một `AnnotatedType` mô tả **type use của receiver**, hoặc `null` khi executable thuộc loại **không thể có receiver parameter** theo quy tắc API.

Cách truy vấn:

```java
Method m = Service.class.getDeclaredMethod(
        "process", String.class);

AnnotatedType receiverType = m.getAnnotatedReceiverType();
ReceiverLabel label =
        receiverType.getAnnotation(ReceiverLabel.class);
```

Đây là đoạn minh họa cần `Service` và `ReceiverLabel` được định nghĩa, cùng import `java.lang.reflect.Method` và `java.lang.reflect.AnnotatedType`. Không phải tệp độc lập.

### 7.1. Ba trạng thái quan trọng của receiver metadata

**Trường hợp A — instance method có annotation trên receiver type:** `getAnnotatedReceiverType()` thường là `AnnotatedType` không null, và `getAnnotation(ReceiverLabel.class)` trả annotation được giữ ở `RUNTIME`.

**Trường hợp B — instance method không có receiver parameter hoặc không annotation vào receiver type:** theo tài liệu `Executable`, API vẫn trả **`AnnotatedType` không null**, mô tả một kiểu receiver có **không có annotation**. Do đó, **không thể lấy `getAnnotatedReceiverType() != null` làm bằng chứng source code đã viết receiver parameter**.

**Trường hợp C — static method hoặc constructor của top-level/static nested/local/anonymous class:** API trả **`null`** vì loại executable đó không thể có receiver parameter.

| Executable | `getAnnotatedReceiverType()` |
| --- | --- |
| Instance method có receiver annotation runtime | `AnnotatedType` chứa annotation khi truy vấn đúng target |
| Instance method không khai báo receiver parameter | `AnnotatedType` không có annotation |
| Instance method có receiver nhưng không có annotation runtime | `AnnotatedType` không có annotation runtime |
| Static method | `null` |
| Constructor của non-static inner member class | `AnnotatedType` mô tả enclosing receiver type; có thể có annotation |
| Constructor của top-level hoặc static nested class | `null` |

**Cảnh báo quan trọng:** `getAnnotatedReceiverType() == null` **không phải** kiểm tra đối tượng receiver khi gọi có null hay không. Đây là trạng thái metadata của **khai báo method/constructor**.

### 7.2. Đọc annotation đúng vị trí

`getAnnotations()` trên `Method` dùng để đọc **declaration annotations** của chính method. Annotation trên *receiver type* có vị trí riêng. Vì thế:

```java
Method m = Service.class.getDeclaredMethod(
        "process", String.class);

ReceiverLabel receiverAnnotation =
        m.getAnnotatedReceiverType()
                .getAnnotation(ReceiverLabel.class);

// Không tương đương với:
ReceiverLabel methodAnnotation =
        m.getAnnotation(ReceiverLabel.class);
```

Trong ví dụ `@ReceiverLabel` được khai báo `TYPE_USE` và gắn vào `Service this`, nên truy vấn `getAnnotatedReceiverType()` mới phản ánh vị trí cần đọc. Không lấy `m.getAnnotation(...)` rồi kết luận receiver annotation bị mất.

Cũng không nên tìm receiver trong `m.getParameterAnnotations()`: phương thức đó trả declaration annotations theo **formal parameters**, không đại diện cho receiver type-use.

### 7.3. `Method.getParameterCount()` không cộng thêm receiver

Giả sử method là:

```java
String process(@ReceiverLabel("service") Service this,
               String input) {
    return input.trim();
}
```

Khi reflection:

```java
Method m = Service.class.getDeclaredMethod(
        "process", String.class);

int count = m.getParameterCount(); // 1
```

Chỉ có formal parameter `String input`, do đó `count == 1`. Receiver parameter là metadata syntax, **không thêm đối số Java cho method**.

Đối với constructor của inner member class, reflection có thể hiển thị một **enclosing-instance parameter** do compiler biểu diễn. Đừng dùng sự khác nhau này để kết luận receiver parameter nguồn là một formal parameter; đó là chi tiết khác của việc biên dịch inner class.

## 8. Receiver parameter và các lỗi cú pháp phổ biến

### 8.1. Không cho phép receiver trong static method

`static` method không nhận một instance `this` như instance method, nên khai báo sau sai:

```java
class Utility {
    // KHÔNG BIÊN DỊCH:
    // static void process(Utility this, String input) {}
}
```

Bạn cũng không thể viết `this` trong thân static method. Khi cần một đối tượng phục vụ tính toán ở static method, hãy khai báo formal parameter bình thường với tên như `service`; không được giả vờ nó là receiver parameter.

### 8.2. Không cho phép receiver trong top-level constructor

```java
class RecordHolder {
    // KHÔNG BIÊN DỊCH:
    // RecordHolder(RecordHolder this) {}
}
```

Receiver parameter ở constructor chỉ dùng cho các trường hợp inner-class constructor được JLS cho phép, không phải “một cách khác để khai báo `this` cho mọi constructor”.

### 8.3. Không thể đổi tên receiver

`this` trong receiver parameter là từ khóa bắt buộc. `Service current` chỉ là formal parameter thông thường, không thể đại diện receiver nếu khai báo sai mục đích.

### 8.4. Không thể tùy tiện thay đổi kiểu receiver

Trong instance method của `Service`, viết `Object this` không hợp lệ vì `Object` không phải kiểu khai báo phương thức theo luật receiver parameter. Với phương thức trong interface, kiểu receiver phải là interface nơi method được khai báo.

### 8.5. Không thể đặt receiver sau tham số thường

Receiver parameter phải đứng đầu danh sách. Nếu method `process` đã nhận `String input`, hãy đặt `Service this` trước `String input`, không đặt cuối.

### 8.6. Annotation `PARAMETER` không thay thế `TYPE_USE`

Nếu annotation chỉ được cho phép ở `ElementType.PARAMETER`, nó dành cho **formal parameter declaration**, không phải vị trí receiver type-use. Hãy xác định đúng `@Target`.

### 8.7. `CLASS` retention nhưng lại mong reflection nhìn thấy

Metadata có thể đã được ghi vào class file theo retention, nhưng core reflection không có nghĩa vụ cung cấp annotation `CLASS`. Nếu cần truy vấn khi chạy, chọn `RetentionPolicy.RUNTIME`.

### 8.8. Nhầm khái niệm với method reference `TypeName::method`

Khi thấy `String::length`, một đối tượng `String` được cung cấp như receiver theo hợp đồng functional interface tại lúc gọi callback. Đây là **method reference**.

Ngược lại, `void work(Service this)` là **receiver parameter declaration** trong header instance method. Hai cơ chế khác nhau dù đều dùng từ “receiver”. Không suy luận rằng khai báo receiver parameter thay đổi chữ ký SAM, thứ tự đối số của lambda hoặc cách chọn overload.

## 9. Ứng dụng thực tế và giới hạn của metadata

Receiver annotation hữu ích khi bạn muốn mô tả **ràng buộc về đối tượng nhận lời gọi** ở mức type-use để công cụ phân tích hoặc framework tự định nghĩa có thể hiểu được:

- Một hệ thống kiểm tra tĩnh muốn ghi chú kỳ vọng về trạng thái hoặc quyền sở hữu của receiver.
- Công cụ phân tích nullness hoặc thread confinement có quy ước type annotation riêng.
- Công cụ build/documentation cần đọc type annotation để sinh báo cáo kỹ thuật về method receiver.
- Công cụ bytecode hoặc reflection cần phân biệt annotation trên receiver với annotation trên formal parameter và return type.

Ví dụ một annotation mang tên `@HoldingLock` có thể biểu thị rằng caller cần giữ một lock trước khi gọi method. Nhưng **tên annotation không tự tạo ra kiểm tra lock**. Cần một tool hoặc runtime interceptor có hiểu biết cụ thể để kiểm chứng; không được kết luận annotation làm JVM tự đồng bộ.

Cách thiết kế đúng:

1. Xác định metadata cần biểu thị điều gì và bên nào sẽ đọc.
2. Chọn `@Target(TYPE_USE)` phù hợp, retention đáp ứng nhu cầu.
3. Gắn annotation lên đúng receiver type trong instance method hoặc inner-class constructor.
4. Viết test cho metadata bằng reflection (khi `RUNTIME`) hoặc công cụ đọc class file.
5. Tách biệt quy tắc được **mô tả** với quy tắc được **thực thi** bởi code hoặc tooling.
6. Không phụ thuộc vào thứ tự hoặc formatting của output `javap` để đưa ra kết luận nghiệp vụ.

### 9.1. Receiver parameter không cung cấp “đối tượng mới” cho framework

Một framework muốn inject service vào method thường dùng constructor parameter, field, hoặc formal parameter thông thường, với chiến lược dependency injection rõ ràng. Receiver parameter **không** đại diện cho một đối số do framework truyền thêm. Nó chỉ mô tả `this` hoặc immediately enclosing instance đã có.

### 9.2. Receiver annotation không tự “truyền” theo override

Khi một lớp override instance method, mỗi khai báo method có bộ metadata riêng. Đừng giả định annotation trên receiver type của superclass/interface mặc nhiên xuất hiện trong kết quả `getAnnotatedReceiverType()` của method override trong lớp con. Muốn suy ra quan hệ metadata giữa các method override, công cụ phải xét hệ phân cấp và chính sách kế thừa/annotation cụ thể.

`@Inherited` trong `java.lang.annotation` áp dụng cho một số trường hợp annotation trên **class declaration**, không phải cơ chế chung để receiver type-use annotation tự động lan truyền.

## 10. Chương trình Java hoàn chỉnh: method và inner-class receiver

Chương trình dưới đây dùng hoàn toàn API/cú pháp hợp lệ từ **Java 8**, biên dịch được trên JDK 17+ và không cần thư viện ngoài JDK. Nó kiểm tra:

1. Một instance method có receiver annotation giữ ở `RUNTIME`.
2. Một instance method thông thường **không có** receiver annotation.
3. Static method không có receiver type khả dụng.
4. `Method.getParameterCount()` không đếm receiver parameter.
5. Constructor của non-static inner member class có annotation trên enclosing receiver.
6. Constructor top-level không có receiver parameter khả dụng.
7. `Method.getAnnotation(...)` không thay thế `getAnnotatedReceiverType().getAnnotation(...)`.

Tạo tệp **`ReceiverMetadataDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.AnnotatedType;
import java.lang.reflect.Constructor;
import java.lang.reflect.Method;

public class ReceiverMetadataDemo {

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.TYPE_USE)
    public @interface ReceiverLabel {
        String value();
    }

    static final class Service {

        String process(@ReceiverLabel("service-instance")
                       Service this, String input) {
            return "run:" + input.trim();
        }

        String plain() {
            return "plain";
        }

        static String helper() {
            return "static";
        }
    }

    final class Inner {
        private final String id;

        Inner(@ReceiverLabel("enclosing-instance")
              ReceiverMetadataDemo ReceiverMetadataDemo.this,
              String id) {
            this.id = id;
        }

        String id() {
            return id;
        }
    }

    public static void main(String[] args) throws Exception {
        Service service = new Service();
        System.out.println(service.process(" clean "));

        Method process = Service.class.getDeclaredMethod(
                "process", String.class);
        AnnotatedType processReceiver =
                process.getAnnotatedReceiverType();
        ReceiverLabel methodLabel =
                processReceiver.getAnnotation(ReceiverLabel.class);

        System.out.println("Method receiver annotation: "
                + methodLabel.value());
        System.out.println("Formal parameter count: "
                + process.getParameterCount());
        System.out.println("Method declaration annotation: "
                + (process.getAnnotation(ReceiverLabel.class) != null));

        Method plain = Service.class.getDeclaredMethod("plain");
        AnnotatedType plainReceiver =
                plain.getAnnotatedReceiverType();
        System.out.println("Plain receiver available: "
                + (plainReceiver != null));
        System.out.println("Plain receiver annotations: "
                + plainReceiver.getAnnotations().length);

        Method helper = Service.class.getDeclaredMethod("helper");
        System.out.println("Static receiver null: "
                + (helper.getAnnotatedReceiverType() == null));

        Constructor<?> innerConstructor =
                Inner.class.getDeclaredConstructors()[0];
        AnnotatedType enclosingReceiver =
                innerConstructor.getAnnotatedReceiverType();
        ReceiverLabel enclosingLabel =
                enclosingReceiver.getAnnotation(ReceiverLabel.class);
        System.out.println("Constructor receiver annotation: "
                + enclosingLabel.value());

        ReceiverMetadataDemo owner = new ReceiverMetadataDemo();
        Inner inner = owner.new Inner("M1");
        System.out.println("Inner id: " + inner.id());

        Constructor<ReceiverMetadataDemo> topLevelConstructor =
                ReceiverMetadataDemo.class.getDeclaredConstructor();
        System.out.println("Top-level receiver null: "
                + (topLevelConstructor.getAnnotatedReceiverType() == null));
    }
}
```

Biên dịch và chạy:

```bash
javac ReceiverMetadataDemo.java
java ReceiverMetadataDemo
```

**Stdout dự kiến chính xác:**

```text
run:clean
Method receiver annotation: service-instance
Formal parameter count: 1
Method declaration annotation: false
Plain receiver available: true
Plain receiver annotations: 0
Static receiver null: true
Constructor receiver annotation: enclosing-instance
Inner id: M1
Top-level receiver null: true
```

**Giải thích từng dòng:**

1. `service.process(" clean ")` in `run:clean`, vì chỉ truyền chuỗi và method `trim` chuỗi đầu vào.
2. `process.getAnnotatedReceiverType()` nhận được type-use annotation `@ReceiverLabel("service-instance")` từ receiver `Service this`.
3. `getParameterCount()` bằng 1: method chỉ có formal parameter `String input`, không cộng receiver.
4. `process.getAnnotation(ReceiverLabel.class)` trả null vì annotation đặt trên receiver type-use, không phải declaration của method.
5. Instance method `plain()` vẫn có một `AnnotatedType` biểu thị receiver type, dù không khai báo receiver parameter trong source. Danh sách annotation trên type đó có độ dài 0.
6. Static method `helper()` có `getAnnotatedReceiverType() == null` vì không có receiver instance để biểu thị.
7. Constructor `Inner` khai báo `ReceiverMetadataDemo ReceiverMetadataDemo.this` với type annotation `"enclosing-instance"`. Reflection đọc metadata đó từ receiver type của constructor.
8. `owner.new Inner("M1")` vẫn chỉ cung cấp đối số hình thức `String id` trong source; `id()` trả lại `M1`.
9. Constructor của top-level class `ReceiverMetadataDemo` không có receiver type khả dụng, nên reflection trả null.

Ví dụ cố ý không in danh sách `getDeclaredConstructors()` hoặc thứ tự tham số synthetic của bytecode, vì các chi tiết đó không cần để minh họa receiver parameter và có thể gây hiểu nhầm. Trong class `Inner` chỉ có một constructor được khai báo, nên việc lấy phần tử `[0]` ở đây rõ nghĩa.

### 10.1. Có thể dùng Reflection API trên interface và superclass không?

Có. Ví dụ `Method` được lấy từ một interface hoặc superclass vẫn có phương thức `getAnnotatedReceiverType()` nếu method là instance method. Tuy nhiên, hãy luôn xác định rõ **method declaration nào** được lấy, vì metadata của từng declaration không phải lúc nào cũng được “kế thừa” như hành vi dispatch instance method.

## 11. Kiểm thử thực tế cho receiver annotations

### 11.1. Kiểm thử retention và target

Khi tạo annotation dùng trong nhiều module, viết test đảm bảo:

- Annotation type có `@Target(ElementType.TYPE_USE)`.
- Nếu dùng reflection ở runtime, annotation có `@Retention(RUNTIME)`.
- Reflection truy vấn chính xác method/constructor muốn kiểm tra.
- `AnnotatedType.getAnnotation(ReceiverLabel.class)` trả đúng value.
- Annotation không bị đọc nhầm từ method-level hoặc parameter-level.

Không nên kiểm tra chỉ bằng `Method.getAnnotations().length` rồi suy luận receiver metadata. Truy vấn đó thuộc một loại annotation khác.

### 11.2. Kiểm tra trường hợp không có annotation

`getAnnotatedReceiverType() != null` ở instance method không có annotation vẫn hoàn toàn hợp lệ. Để hỏi receiver có `@ReceiverLabel` không, dùng:

```java
AnnotatedType receiver = method.getAnnotatedReceiverType();
boolean hasLabel = receiver != null
        && receiver.isAnnotationPresent(ReceiverLabel.class);
```

Đoạn này minh họa cần `method` và `ReceiverLabel` có sẵn. Với static method, `receiver == null`; với unannotated instance method, `receiver != null` nhưng `hasLabel == false`.

### 11.3. Kiểm tra constructor của inner class

Khi phản chiếu constructor inner class, không đồng nhất ba thứ:

- **Enclosing-instance receiver type** (đọc qua `getAnnotatedReceiverType()`).
- **Formal parameters** được khai báo trong source, như `String id`.
- **Tham số synthetic/mandated** mà compiler có thể biểu diễn trong bytecode để mang enclosing instance.

Hãy dựa trên API Reflection và JLS cho loại thông tin bạn cần, thay vì cố suy ra toàn bộ từ số lượng tham số ở bytecode.

## 12. Những lỗi thường gặp và cách sửa

| Sai lầm | Điều sai | Cách đúng |
| --- | --- | --- |
| Nghĩ `Service this` là một đối số bắt buộc của `service.run(...)` | Receiver parameter không phải formal parameter | Chỉ truyền đối số formal như bình thường |
| Khai báo `void f(Service receiver)` rồi gọi đó là receiver parameter | Đây là formal parameter tên receiver | Muốn receiver parameter thì phải viết `Service this` |
| Viết receiver parameter ở static method | Static method không có receiver instance | Chuyển thành instance method hoặc dùng formal parameter |
| Viết receiver parameter ở top-level constructor | Không thuộc phạm vi constructor được JLS cho phép | Chỉ dùng cho non-static inner member class constructor phù hợp |
| Viết `Inner this` ở inner constructor muốn mô tả outer instance | Constructor receiver phải biểu thị immediately enclosing type | Dùng `Outer Outer.this` |
| Đặt receiver sau `String value` | Receiver parameter phải đứng đầu | Đưa receiver lên trước |
| Dùng `@Target(PARAMETER)` thay cho `TYPE_USE` | Receiver không phải formal parameter declaration | Cho phép annotation trên `TYPE_USE` |
| Dùng `@Retention(CLASS)` rồi mong `getAnnotation` thấy được | Core reflection không trả annotation CLASS-retained | Dùng `RUNTIME` nếu cần đọc lúc chạy |
| `Method.getAnnotation(Tag.class)` trả null nên tưởng metadata mất | Receiver annotation nằm trên receiver type | Dùng `getAnnotatedReceiverType().getAnnotation(Tag.class)` |
| `getAnnotatedReceiverType() != null` nên nghĩ source có khai báo receiver | Instance method không annotation vẫn có AnnotatedType trống | Kiểm tra annotation trên AnnotatedType |
| `getAnnotatedReceiverType() == null` nên nghĩ receiver runtime là null | Đây là phân loại executable, không phải giá trị đối tượng khi gọi | Phân biệt reflection metadata và runtime receiver |
| Nghĩ receiver annotation tự kiểm tra null/lock | Annotation không tự áp đặt chính sách | Dùng checker/framework có hiểu annotation |
| Nhầm receiver parameter với method reference `Type::method` | Hai cú pháp phục vụ hai mục đích | Phân biệt declaration metadata và callback expression |
| Coi `@Inherited` làm receiver annotation tự lan sang override | Không phải cơ chế kế thừa type-use annotation chung | Xét từng declaration theo công cụ và chính sách riêng |

## 13. Checklist áp dụng vào dự án

1. **Bạn thật sự cần metadata receiver không?** Nếu không có tool/phần code nào đọc nó, bỏ receiver parameter cho code gọn.
2. **Method có phải instance method?** Nếu static, không dùng receiver parameter.
3. **Constructor có thuộc non-static inner member class được phép?** Nếu là top-level/static nested, không dùng.
4. **Kiểu và tên receiver có đúng JLS?** Trong method dùng kiểu khai báo cùng `this`; trong inner constructor dùng enclosing type cùng `Outer.this`.
5. **Receiver ở vị trí đầu danh sách?** Không để sau formal parameters.
6. **Annotation đặt trên type use?** Kiểm tra `@Target(TYPE_USE)`.
7. **Tool chạy lúc runtime có cần metadata không?** Nếu có, dùng `@Retention(RUNTIME)`.
8. **Đang đọc annotation từ đâu?** Receiver: `getAnnotatedReceiverType()`; formal parameter: `getAnnotatedParameterTypes()`/`getParameterAnnotations()` tùy mục đích; method declaration: `Method.getAnnotations()`.
9. **Đã phân biệt không annotation với không có receiver type chưa?** Instance method unannotated vẫn có thể có `AnnotatedType` không null.
10. **Đã kiểm thử trên JDK/source level dự án chưa?** Receiver parameter/type annotations có từ Java 8 và vẫn hợp lệ; không cần tính năng preview hay thư viện đã ngừng hỗ trợ.
11. **Tooling đọc class file có phân biệt target không?** Kiểu receiver dùng `target_type=0x15`, khác formal parameter `0x16`.
12. **Đã mô tả rõ annotation có tác dụng gì?** Metadata chỉ mang thông tin; việc enforce cần cơ chế riêng.

**Kết luận:** Receiver parameter (`TypeName this` trong instance method, `Outer Outer.this` trong constructor của non-static inner member class) là một **vị trí cú pháp dành cho metadata về receiver type**. Nó không tạo biến mới, không tăng số formal parameters, không thay đổi cách gọi method. Khi annotation là `TYPE_USE` và có `RUNTIME` retention, bạn có thể truy vấn qua `Executable.getAnnotatedReceiverType()`. Đây là phần của hệ thống type annotation được giới thiệu từ Java 8 và tiếp tục có giá trị trong việc xây dựng công cụ phân tích Java hiện đại.

## Tài liệu tham khảo chuẩn

- Java Language Specification, **`8.4 Method Declarations / receiver parameter**: https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4
- Java Language Specification, **`8.4.1 Formal Parameters**: https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.4.1
- Java Language Specification, **`8.8 Constructor Declarations**: https://docs.oracle.com/javase/specs/jls/se25/html/jls-8.html#jls-8.8
- Java SE API, **`Executable.getAnnotatedReceiverType()`**: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Executable.html
- Java SE API, **`java.lang.annotation.ElementType.TYPE_USE`**: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/annotation/ElementType.html
- Java Virtual Machine Specification, **`4.7.20 Type Annotations`**: https://docs.oracle.com/javase/specs/jvms/se22/html/jvms-4.html#jvms-4.7.20
