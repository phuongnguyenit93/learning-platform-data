# Chọn theo annotation và siêu dữ liệu của chương trình

## Mục tiêu bài học

Một **pointcut** trong Aspect-Oriented Programming (AOP) xác định những **join point** mà advice sẽ áp dụng. Ngoài lựa chọn theo tên, chữ ký, kiểu hoặc vị trí trong chương trình, nhiều cơ chế AOP cho phép chọn dựa trên **annotation** và các dạng **siêu dữ liệu (metadata)** khác. Đây là cách mô tả ý nghĩa của điểm can thiệp mà không phải gắn chặt pointcut với tên hàm.

Ví dụ, thay vì viết “chọn mọi phương thức có tên bắt đầu bằng `process`”, một nhóm phát triển có thể đặt marker `@Observed` lên những thao tác cần đo thời gian. Một pointcut thích hợp sau đó chọn những join point có metadata tương ứng.

Bài học giúp bạn:

1. Phân biệt **annotation là dữ liệu mô tả** với **pointcut là quy tắc chọn** và **advice là hành vi được thực thi**.
2. Hiểu metadata có thể nằm trên **lớp, interface, phương thức, tham số, trường, constructor, annotation khác** hoặc đến từ hệ thống build/runtime.
3. Xác định vai trò của `@Target`, `@Retention`, `@Inherited`, `@Repeatable`, quan hệ kế thừa và cơ chế reflection trong Java.
4. Thiết kế biểu thức ghép giữa metadata với tên, kiểu, phạm vi chương trình và thông tin runtime mà vẫn kiểm soát được tập join point.
5. Phân biệt **metadata ở declaration nào** với **matcher đang đọc declaration nào**, nhất là giữa interface và implementation, phương thức override hoặc method bridge.
6. Hiểu những khác biệt giữa **matching tĩnh**, **matching động**, **proxy** và **weaving**, cùng cách kiểm thử phần được chọn và phần phải loại trừ.

Đây là kiến thức về **AOP nói chung**. Các ví dụ Java 17 dùng annotation và reflection để minh họa cơ chế; không có một cú pháp pointcut áp dụng được cho mọi công cụ AOP.

## 1. Khái niệm nền tảng: ba vai trò không được đánh đồng

| Thành phần | Câu hỏi trả lời | Minh họa |
| --- | --- | --- |
| **Annotation / metadata** | Một phần của chương trình được mô tả bằng thông tin gì? | Phương thức `submit` được đánh dấu `@Observed`. |
| **Join point** | Sự kiện can thiệp có thể xuất hiện ở đâu trong luồng chạy? | Một lần thực thi hoặc một lần gọi `submit`, tùy mô hình AOP. |
| **Pointcut** | Trong các join point khả dụng, chọn những điểm nào? | Chỉ chọn execution của phương thức có marker `@Observed`. |
| **Advice** | Khi điểm được chọn xảy ra thì làm gì? | Đo latency, thêm correlation ID, ghi kết quả. |
| **Weaving / interception** | Làm sao advice thực sự được kết hợp với chương trình? | Proxy, biến đổi mã, instrumentation hoặc một cơ chế khác. |

**Annotation không tự thực thi hành vi.** Trong Java, khai báo:

```java
@Observed
void submit() {
    // logic
}
```

không tự tạo log, đo thời gian hay đổi luồng chạy. Phải có **thành phần đọc marker**, quy tắc chọn điểm và cơ chế thực thi advice. Các công cụ có thể đánh giá annotation khi build, khi nạp lớp hoặc khi runtime; metadata chỉ tạo **cơ sở lựa chọn**.

Nói cách khác:

```text
metadata trên mã
       |
       v
pointcut đọc/diễn giải metadata
       |
       v
lọc join point trong tập được công cụ hỗ trợ
       |
       v
cơ chế AOP kích hoạt advice ở lượt thực thi phù hợp
```

Không có bước nào tự bảo đảm các bước còn lại. Ví dụ, matcher có thể chọn đúng phương thức theo marker nhưng lời gọi đi thẳng vào target và bỏ qua proxy nên không có advice.

## 2. “Siêu dữ liệu của chương trình” rộng hơn một annotation

**Metadata** là thông tin mô tả chương trình hoặc phần tử của chương trình, không nhất thiết là logic trực tiếp xử lý nghiệp vụ. Trong nhiều ngôn ngữ, metadata có thể bao gồm:

- **Annotation / attribute / decorator metadata:** marker, tên chính sách, mức độ quan sát, nhãn kỹ thuật.
- **Kiểu và chữ ký:** tên lớp, interface đã cài đặt, tên method, kiểu tham số và return, visibility, modifier.
- **Cấu trúc sở hữu:** package, namespace, module, kiểu khai báo, quan hệ kế thừa và override.
- **Thông tin build hoặc bytecode:** annotation, cờ compiler, mã sinh, các metadata có thể xuất hiện ở tầng biên dịch nhưng không có ở runtime.
- **Quy ước hoặc registry bên ngoài:** cấu hình được gắn tới các loại và phương thức; có thể được engine AOP nạp thành một tập quy tắc.

Không phải mọi thứ ở trên là *annotation*, và cũng không phải công cụ AOP nào cho phép dùng tất cả làm điều kiện pointcut. Vì vậy cần xác định chính xác **nguồn metadata**, **vị trí lưu**, **thời điểm nó còn tồn tại** và **cách matcher truy cập**.

### 2.1. Marker và annotation có thuộc tính

Một marker rỗng chỉ biểu thị có/không:

```java
@interface Observed {}
```

Một annotation có thuộc tính mang thêm dữ liệu:

```java
@interface Observed {
    String operation();
    int sampleRate() default 100;
}
```

Ví dụ `@Observed(operation = "checkout", sampleRate = 10)` chứa metadata. Cơ chế AOP có thể dùng sự **hiện diện của annotation** làm điều kiện chọn, hoặc nếu được hỗ trợ thì **đọc thuộc tính** để cấu hình advice. Một số công cụ cho phép bind annotation vào tham số advice; một số đòi code tự tra cứu.

Không nên dùng thuộc tính annotation để cất thông tin nhạy cảm hoặc dữ liệu thay đổi theo từng request. Metadata khai báo thường là **cấu hình tương đối tĩnh**, còn dữ liệu request/transaction là **ngữ cảnh runtime**.

### 2.2. Quy tắc lựa chọn dựa trên ý nghĩa

Ví dụ, xét hai cách mô tả:

```text
Cách theo quy ước tên:
  methodNameStartsWith("save")

Cách theo ý nghĩa:
  methodHasAnnotation("Observed")
```

Cách thứ hai hữu ích khi method tên khác nhau nhưng cùng cần một chính sách kỹ thuật, chẳng hạn `send`, `save`, `publish`. Nó giúp người viết method **công bố điểm áp dụng có chủ đích**. Song marker cũng tạo trách nhiệm: ai phải gắn marker, việc bỏ marker có được review không, và quy tắc kế thừa có khiến một method không mong đợi bị chọn hay không?

### 2.3. Annotation không phải bất biến nghiệp vụ

Gắn `@RequireOwnership` lên một method không tự chứng minh tất cả đường cập nhật dữ liệu đều được bảo vệ. Nếu kiểm tra quyền phụ thuộc chủ sở hữu tài liệu, trạng thái bản ghi hoặc luồng nhiều bước, bất biến cần được đảm bảo ở biên tin cậy và logic nghiệp vụ. AOP có thể giúp áp một chính sách kỹ thuật đã định nghĩa rõ, nhưng metadata + pointcut có thể không bao phủ mọi đường gọi.

## 3. Annotation trong Java: Target, Retention và phạm vi khai báo

Trên Java, `@interface` khai báo một annotation type. Ba nhóm câu hỏi cần tách biệt:

1. **Annotation được phép đặt ở đâu?** Do `@Target` quy định nếu có.
2. **Annotation tồn tại ở giai đoạn nào?** Do `@Retention` quy định.
3. **Công cụ AOP kiểm tra annotation ở declaration nào và tại thời điểm nào?** Do engine/matcher và đường chạy quyết định.

### 3.1. `@Target`: nơi annotation có thể được dùng

Ví dụ:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Target;

@Target({ElementType.TYPE, ElementType.METHOD})
@interface Observed {}
```

Marker trên có thể đặt ở **type declaration** và **method declaration**. Java còn có các phần tử như `FIELD`, `PARAMETER`, `CONSTRUCTOR`, `ANNOTATION_TYPE`, `TYPE_USE`, `TYPE_PARAMETER`, `PACKAGE`, `MODULE` và `RECORD_COMPONENT` (tùy phiên bản). Được phép đặt annotation tại một phần tử **không đồng nghĩa** một engine AOP có join point tương ứng với phần tử đó.

Ví dụ, `@Target(FIELD)` cho phép đánh dấu trường, nhưng một interface dynamic proxy không tự chặn thao tác đọc/ghi field. Muốn chọn **field-access join point**, công cụ phải hỗ trợ loại điểm này cùng cách weaving thích hợp.

Nếu không khai báo `@Target`, annotation có thể được áp lên các loại declaration trong phạm vi quy tắc Java; điều đó không tạo bảo đảm về khả năng matching hoặc interception của AOP.

### 3.2. `@Retention`: SOURCE, CLASS và RUNTIME

| Chính sách | Đặc điểm | Hệ quả với pointcut |
| --- | --- | --- |
| `RetentionPolicy.SOURCE` | Metadata được dùng ở source rồi bị compiler loại khỏi class file. | Không thể dựa vào reflection runtime để đọc trực tiếp annotation này từ class đã biên dịch. Công cụ phân tích source có thể sử dụng nó trước đó. |
| `RetentionPolicy.CLASS` | Metadata được ghi trong class file, nhưng Java reflection không bắt buộc trả về annotation đó ở runtime. | Công cụ đọc/biến đổi bytecode có thể dùng; matcher chỉ dùng reflection runtime không nên trông đợi nó. |
| `RetentionPolicy.RUNTIME` | Metadata có thể được đọc qua reflection ở runtime. | Thích hợp cho ví dụ runtime proxy/reflective matcher. |

**Mặc định của annotation Java khi không có `@Retention` là `RetentionPolicy.CLASS`.** Nếu thiết kế matcher bằng `Method.getAnnotation(...)` hoặc `isAnnotationPresent(...)`, cần annotation có `RUNTIME` retention ở vị trí đang đọc. Không nên suy rằng metadata không đọc được qua reflection thì vô dụng cho **mọi** công cụ AOP: các công cụ hoạt động ở compile/load time có thể xét cấu trúc class file hoặc source.

Ví dụ marker runtime:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Traced {
    String category() default "general";
}
```

Đoạn trên là **khai báo annotation để dùng cùng mã khác**; bản thân nó không phải một chương trình độc lập có `main`.

### 3.3. Một annotation xuất hiện ở đúng vị trí chưa chắc đúng pointcut

`@Traced` trên một method không tự có nghĩa “mọi method call tương ứng được bắt”. Nếu pointcut chọn **method execution**, loại sự kiện được xét có thể khác với **method call**. Nếu công cụ chỉ chặn lời gọi qua proxy, có annotation vẫn không khiến lời gọi trực tiếp target chạy advice.

Bất kỳ kết luận nào về độ phủ đều cần xác nhận **join-point kind + vị trí metadata + matcher + đường interception**.

## 4. Khác biệt giữa annotation trên method và annotation trên type

Xét:

```java
@Observed
class ImportService {
    void importFile() { }
    void validate() { }
}
```

Có hai cách thiết kế pointcut rất khác:

- **Chọn method được annotation trực tiếp:** matcher hỏi chính declaration của `importFile` có `@Observed` không. Nếu chỉ có marker ở class, một phép tra cứu `Method.getAnnotation(Observed.class)` đơn giản thường **không** trả về marker của class.
- **Chọn method nằm trong type có annotation:** matcher hỏi *declaring type* hoặc **runtime target type** có marker `@Observed` không. Khi đó có thể chọn cả `importFile` và `validate` theo quy tắc của matcher.

Hai câu hỏi này khác nhau. Đặt annotation ở class thường mang ngữ nghĩa **một nhóm method cùng thuộc chính sách**, nhưng không mặc nhiên là hành vi của mọi engine. Cần xác nhận matcher xét type khai báo, hierarchy, interface hay runtime class.

### 4.1. Annotation trên interface và implementation

Xét:

```java
interface FileApi {
    @Traced
    void save();
}

class FileService implements FileApi {
    @Override
    public void save() {}
}
```

Trên Java reflection thông thường, `FileApi.class.getMethod("save")` và `FileService.class.getMethod("save")` là **hai đối tượng `Method` mô tả hai declaration khác nhau**. `getAnnotation(Traced.class)` trên method của implementation không tự lấy annotation đã đặt ở method interface.

Vì vậy:

- Matcher xem **interface method** có thể thấy `@Traced`.
- Matcher xem **implementation method** có thể không thấy annotation nếu chỉ đặt marker trên interface.
- Một công cụ AOP có thể chủ động duyệt interface/implementation rồi hợp nhất metadata; đó là **khả năng riêng của công cụ**, không phải mặc định của Java reflection.
- Một proxy theo interface thường nhận method mô tả lời gọi qua **interface**; một cơ chế weaving có thể dùng loại metadata khác.

**Quy tắc học tập:** Luôn hỏi “annotation đặt ở đâu?” và “pointcut đọc `Method` hoặc `Class` nào?” trước khi kết luận đã chọn hay chưa.

### 4.2. Overload, override và generic bridge method

Method `save(String)` và `save(byte[])` là hai declaration khác nhau. Đánh dấu một overload không tự đánh dấu overload còn lại.

Khi override, annotation đặt trên method ở superclass hoặc interface không tự được kế thừa theo quy tắc `@Inherited` dành cho **class-level annotation**. Một công cụ có thể định nghĩa chiến lược riêng để tìm marker trên method bị override.

Với generics và *type erasure*, Java compiler có thể tạo **bridge method** để đảm bảo dispatch. Matcher dựa vào reflection/bytecode có thể gặp method synthetic hoặc bridge. Để tránh chọn sai hoặc xử lý trùng, cần hiểu engine có bỏ qua, ánh xạ hoặc chuẩn hóa bridge method không; thử nghiệm bằng generic interface nếu phạm vi quan trọng.

## 5. `@Inherited`, `@Repeatable` và meta-annotation: các giới hạn tinh tế

### 5.1. `@Inherited` chỉ áp dụng theo quy tắc class-level

Java cung cấp `@Inherited` để biểu thị một annotation **trên class** có thể được class con kế thừa khi truy vấn annotation bằng cơ chế Java reflection phù hợp.

Ví dụ ý tưởng:

```java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@interface AuditedType {}

@AuditedType
class BaseService {}

class ChildService extends BaseService {}
```

Trong ví dụ, `ChildService.class.isAnnotationPresent(AuditedType.class)` có thể trả về `true` theo quy tắc `@Inherited`. Tuy nhiên:

- `@Inherited` **không** làm annotation trên method tự động kế thừa sang method override.
- Quy tắc kế thừa này liên quan tới **superclass**, không có nghĩa annotation ở một interface tự động thành class annotation ở lớp cài interface.
- Matcher của một công cụ AOP có thể dùng phép tìm annotation riêng khác với `Class.getAnnotation`; cần kiểm tra hợp đồng.

### 5.2. `@Repeatable`: một declaration có thể có nhiều annotation cùng loại

Java cho phép loại annotation được `@Repeatable` xuất hiện nhiều lần với một container annotation. Ví dụ một method có thể mang hai nhãn kỹ thuật khác nhau để mô tả hai nhóm quan sát.

Với reflection, `getAnnotationsByType(SomeAnnotation.class)` là API thích hợp để thu thập các annotation cùng loại được lặp theo hợp đồng của Java; chỉ dùng `getAnnotation` có thể bỏ qua cách biểu diễn qua container trong một số tình huống. Khi công cụ AOP chọn theo “có annotation” và annotation ấy repeatable, cần xác minh matcher hiểu **container và các phần tử bên trong** thế nào.

Không được suy “hai annotation cùng loại = advice chạy hai lần”: việc có nhiều marker là thông tin, còn số advice được kích hoạt phụ thuộc **pointcut, cấu hình và từng occurrence**.

### 5.3. Meta-annotation: annotation mô tả annotation khác

Một annotation có thể được gắn lên **annotation type** để thể hiện phân loại:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.ANNOTATION_TYPE)
@interface ObservabilityMarker {}

@ObservabilityMarker
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Counted {}
```

Method gắn `@Counted` **không mặc nhiên có trực tiếp `@ObservabilityMarker`** theo phép `method.isAnnotationPresent(ObservabilityMarker.class)`. Một matcher muốn nhận diện meta-annotation phải đọc các annotation được gắn trên method, rồi kiểm tra annotation type của chúng có marker `@ObservabilityMarker` hay không, hoặc dùng API chuyên biệt nếu công cụ cung cấp.

Một số engine AOP hỗ trợ meta-annotation/composed annotation; một số chỉ tìm annotation trực tiếp. Đây là khác biệt có ý nghĩa về **mô hình matching**, không chỉ cách đặt tên marker.

## 6. Chọn điểm theo metadata: bốn cấp độ phổ biến

Bốn kiểu lựa chọn dưới đây có thể được hỗ trợ riêng rẽ hoặc kết hợp, tùy công cụ.

### Cấp 1: Chọn theo sự hiện diện của annotation

Giả mã:

```text
methodExecution
AND methodHasAnnotation("Observed")
```

Chỉ chọn những occurrence method execution mà matcher nhận diện marker phù hợp. Với static matching, engine có thể xác định từ chữ ký/bytecode trước; với runtime matching, nó có thể tra cứu reflective metadata.

### Cấp 2: Chọn theo thuộc tính annotation

Giả mã:

```text
methodHasAnnotation("Observed")
AND annotationAttribute("category") == "io"
```

Không phải DSL nào cũng có phép so sánh thuộc tính trực tiếp. Một cách khác là bind annotation instance vào advice để policy đọc giá trị `category`. Cần phân biệt **điều kiện chọn điểm** với **dữ liệu cấu hình hành vi advice sau khi đã chọn**.

### Cấp 3: Ghép annotation với kiểu, tên và phạm vi

Giả mã:

```text
methodExecution
AND (methodHasAnnotation("Observed") OR typeHasAnnotation("MonitoredType"))
AND NOT belongsToModule("internal.instrumentation")
```

Dấu ngoặc làm rõ phạm vi loại trừ: nếu viết `A OR (B AND NOT C)` thay vì `(A OR B) AND NOT C`, một nhánh có thể bỏ qua điều kiện cấm. Khi quy tắc có **OR + NOT**, cần có negative tests cho mọi nhánh.

### Cấp 4: Kết hợp metadata tĩnh với ngữ cảnh runtime

Giả mã:

```text
methodHasAnnotation("Sampled")
AND runtimeContext.sampled == true
```

Metadata cho phép xác định ứng viên; điều kiện runtime có thể thay đổi theo từng lần gọi. Một method được đánh dấu giống nhau nhưng có thể được advice chọn ở lượt này và không chọn ở lượt khác. Không phải mọi công cụ cho phép matcher đọc runtime context hoặc bind tham số; không nên coi giả mã như cú pháp chung.

### 6.1. Cần tách “đánh dấu để chọn” và “đánh dấu để cấu hình”

Nếu `@Observed(category = "payment")` chỉ dùng để **chọn** điểm, policy có thể coi mọi method có annotation giống nhau. Nếu category dùng để **định tuyến số liệu** sau khi advice chạy, annotation trở thành dữ liệu đầu vào của advice. Nếu category quyết định **có chạy advice hay không**, matcher cần năng lực so sánh giá trị.

Cùng một annotation có thể đóng nhiều vai trò, nhưng viết tài liệu phải nêu rõ vai trò nào đang được dùng để tránh hiểu nhầm.

## 7. Ví dụ Java 17 chạy được: chọn theo marker và loại trừ metadata

Ví dụ này dùng **JDK dynamic proxy** để minh họa một phần ý tưởng AOP. Handler đọc annotation ở **interface method**, chọn theo công thức:

```text
hasAnnotation(Tracked)
AND NOT hasAnnotation(Internal)
```

Nếu được chọn, handler ghi thông báo trước/sau hoặc khi target ném exception. Đây là ví dụ runnable bằng Java chuẩn để học **cách matcher dùng metadata**, không phải một AOP engine hoàn chỉnh.

Tạo tệp `AnnotationPointcutDemo.java`:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Proxy;

public class AnnotationPointcutDemo {
    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Tracked {
        String category();
    }

    @Retention(RetentionPolicy.RUNTIME)
    @Target(ElementType.METHOD)
    @interface Internal {}

    interface TaskApi {
        @Tracked(category = "orders")
        String submit(String id);

        @Tracked(category = "health")
        @Internal
        String sync();

        String status();
    }

    static final class TaskService implements TaskApi {
        @Override
        public String submit(String id) {
            if (id == null || id.isBlank()) {
                throw new IllegalArgumentException("id required");
            }
            System.out.println("TARGET submit " + id);
            return "ACCEPTED " + id;
        }

        @Override
        public String sync() {
            System.out.println("TARGET sync");
            return "SYNCED";
        }

        @Override
        public String status() {
            System.out.println("TARGET status");
            return "READY";
        }
    }

    static TaskApi observed(TaskApi target) {
        return (TaskApi) Proxy.newProxyInstance(
                TaskApi.class.getClassLoader(),
                new Class<?>[] { TaskApi.class },
                (proxy, method, arguments) -> {
                    Tracked tracked = method.getAnnotation(Tracked.class);
                    boolean selected = tracked != null
                            && !method.isAnnotationPresent(Internal.class);

                    if (selected) {
                        System.out.println("ADVICE before "
                                + tracked.category() + ":" + method.getName());
                    }

                    try {
                        Object result = method.invoke(target, arguments);
                        if (selected) {
                            System.out.println("ADVICE success " + method.getName());
                        }
                        return result;
                    } catch (InvocationTargetException ex) {
                        if (selected) {
                            System.out.println("ADVICE failure " + method.getName());
                        }
                        throw ex.getCause();
                    }
                }
        );
    }

    public static void main(String[] args) {
        TaskApi target = new TaskService();
        TaskApi proxy = observed(target);

        System.out.println("RESULT " + proxy.submit("A-7"));
        System.out.println("RESULT " + proxy.sync());
        System.out.println("RESULT " + proxy.status());

        try {
            proxy.submit("");
        } catch (IllegalArgumentException ex) {
            System.out.println("CALLER caught " + ex.getMessage());
        }

        System.out.println("RESULT " + target.submit("DIRECT"));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac AnnotationPointcutDemo.java
java AnnotationPointcutDemo
```

Stdout theo đúng thứ tự:

```text
ADVICE before orders:submit
TARGET submit A-7
ADVICE success submit
RESULT ACCEPTED A-7
TARGET sync
RESULT SYNCED
TARGET status
RESULT READY
ADVICE before orders:submit
ADVICE failure submit
CALLER caught id required
TARGET submit DIRECT
RESULT ACCEPTED DIRECT
```

### 7.1. Bảng đối chiếu tập được chọn

| Method trên interface | `@Tracked`? | `@Internal`? | Có advice khi gọi qua proxy? |
| --- | --- | --- | --- |
| `submit` | Có; category = `orders`. | Không. | **Có**, cả success và failure. |
| `sync` | Có; category = `health`. | Có. | **Không**, vì điều kiện NOT loại bỏ. |
| `status` | Không. | Không. | **Không**, vì thiếu điều kiện chọn dương. |

Lời gọi `target.submit("DIRECT")` không xuất hiện thông báo advice vì **đi thẳng vào target**, không thông qua proxy. Đây là giới hạn của cơ chế JDK proxy trong ví dụ, không phải mọi kiểu weaving.

### 7.2. Vì sao xử lý exception như vậy?

`Method.invoke(target, arguments)` bọc exception do target ném vào `InvocationTargetException`. Handler ghi sự kiện thất bại và `throw ex.getCause()` để caller nhận `IllegalArgumentException` gốc. Nếu handler nuốt lỗi rồi trả mặc định, hợp đồng method bị thay đổi ngoài ý định.

Nếu chính **advice ghi log** ném exception, ví dụ chưa đặt chính sách xử lý riêng. Trong hệ thống thật phải quyết định logging/metrics lỗi thì nghiệp vụ có tiếp tục không; điều này phụ thuộc mức độ bắt buộc của chính sách.

### 7.3. Vì sao `@Internal` cần đọc ở cùng nơi với `@Tracked`?

Trong demo, cả hai marker được đặt ở **method interface** và handler dùng `Method` của interface. Nếu chỉ chuyển `@Internal` xuống implementation, handler có thể không thấy điều kiện loại trừ và vô tình chạy advice cho `sync`. Đây là một ví dụ thực tế về lỗi **metadata khác declaration mà matcher đang đọc**.

### 7.4. Bài tập thay đổi chính xác một yếu tố

1. Bỏ `@Internal` ở `TaskApi.sync`: lời gọi qua proxy bắt đầu phát thông báo advice theo category `health`.
2. Chuyển `@Tracked` của `TaskApi.submit` sang `TaskService.submit` nhưng **giữ nguyên handler**: matcher kiểm tra method interface không thấy marker nữa, vì vậy không áp dụng advice cho `submit`.
3. Đổi `@Retention(RetentionPolicy.RUNTIME)` thành `CLASS` cho `Tracked`: matcher dùng reflection không nhận được annotation theo cách hiện tại.
4. Giữ nguyên annotation nhưng gọi trực tiếp `target.submit("X")`: target chạy, proxy handler không chạy.
5. Thêm một method overload ở interface và chỉ gắn marker cho một overload: dự đoán overload nào được chọn.

Mỗi thay đổi cần được kiểm tra cùng **expected stdout** và ghi rõ điều kiện nào trong pointcut đã đổi.

## 8. Phân biệt metadata tĩnh và dữ liệu thực thi

Metadata như annotation thường được cố định theo artifact chương trình. Một join point khi runtime xảy ra lại có thông tin biến đổi:

- **Receiver:** object thực hiện method thực sự có kiểu nào?
- **Arguments:** đối số hiện tại có giá trị gì?
- **Result/exception:** method trả về bình thường hay ném lỗi?
- **Thread/context:** đang ở tác vụ hoặc correlation context nào?
- **Thời điểm:** lần gọi hiện tại diễn ra trước/sau sự kiện nào?

Một pointcut dùng annotation và một điểm dựa vào tham số có thể biểu diễn hai tầng:

```text
STATIC:  methodHasAnnotation("Traced")
DYNAMIC: argument("important") == true

SELECT: STATIC AND DYNAMIC
```

Ở một cơ chế có hỗ trợ matching động, một method có marker được gọi mười lần, chỉ bốn lần thỏa `important=true`, thì advice có thể chạy ở bốn occurrence (giả sử không có các giới hạn khác). Không dùng số method có marker để suy ra số lời gọi advice.

**Lưu ý về metadata sửa được lúc chạy:** Một số ngôn ngữ hỗ trợ metadata động hoặc monkey-patching; trên JVM có cơ chế instrumentation và class loading riêng. Không nên áp trực giác của một ngôn ngữ lên ngôn ngữ khác. Với Java annotation runtime, nên coi metadata declaration là thông tin ổn định của class đang được nạp, trừ khi có cơ chế biến đổi được xác định rõ.

## 9. Cùng một annotation, nhiều join-point model khác nhau

Metadata có thể giống nhau nhưng pointcut chọn **loại sự kiện** khác nhau:

| Loại cần chọn | Điều cần xác minh |
| --- | --- |
| **Method execution** | Engine có nhận diện method implementation được thực thi? Nó đọc metadata ở interface, override hay implementation? |
| **Method call** | Engine có hỗ trợ điểm ở phía caller không? Metadata của method được gọi lấy theo kiểu tĩnh hay target runtime? |
| **Constructor execution/call** | Công cụ có hỗ trợ join point constructor không? Annotation ở constructor được đọc theo cách nào? |
| **Field get/set** | Công cụ có quan sát field access hay chỉ method wrapper? Annotation `@Target(FIELD)` không đủ để tạo hook. |
| **Type initialization** | Công cụ có hỗ trợ loại điểm này không? Metadata type được xác định tại thời điểm nào? |
| **Runtime proxy invocation** | Caller có đi qua proxy thật không? Proxy đọc `Method` nào? Lời gọi nội bộ có bị bỏ qua? |

Không có “cú pháp annotation pointcut” duy nhất đảm bảo chọn tất cả loại điểm. Trước khi viết matcher, phải chọn **join point kind** phù hợp với chính sách. Ví dụ: “theo dõi mọi lần lưu dữ liệu” cần xem việc đặt hook ở method execution của tầng lưu trữ có bao phủ được mọi đường gọi hay không; một marker trên interface đơn thuần không giải quyết mọi vấn đề độ phủ.

## 10. Vị trí và mức độ kế thừa của metadata

Để kiểm thử một pointcut theo annotation, hãy lập một **ma trận declaration** thay vì chỉ thử một method đơn giản:

| Trường hợp | Câu hỏi quan trọng |
| --- | --- |
| Annotation trên interface method | Matcher có duyệt interface method không? |
| Annotation trên implementation method | Matcher có duyệt method thực thi hay chỉ method interface không? |
| Annotation trên type | Pointcut đang chọn type annotation hay method annotation? |
| Superclass có `@Inherited` trên type | Matcher có tuân quy tắc Java reflection hoặc chiến lược kế thừa khác không? |
| Override method | Annotation ở method gốc có được matcher tìm thấy theo chính sách riêng không? |
| Overload cùng tên | Annotation gắn chính xác cho chữ ký nào? |
| Method generic/bridge | Công cụ có normalize bridge/synthetic và không xử lý trùng không? |
| Repeatable annotation | Matcher hiểu annotation trực tiếp và container ra sao? |
| Meta-annotation | Matcher có duyệt annotation type hay chỉ annotation trực tiếp? |
| Annotation giữ ở `CLASS`, không phải `RUNTIME` | Công cụ dùng bytecode matcher hay reflection runtime? |

Không có một đáp án “có/không” cho mọi hàng trên mọi công cụ. Thay vì đoán, hãy tạo class/method thử, quan sát **positive matching**, **negative matching** và đường gọi thực tế.

### Ví dụ về “cùng tên” nhưng metadata khác nhau

Giả sử interface có `process(String)`, implementation override và class khác có method trùng tên. Một pointcut “method có tên process” có thể chọn cả ba theo phạm vi rộng, trong khi marker đặt ở **một declaration duy nhất**. Metadata giúp chỉ định **ý nghĩa**, nhưng vẫn phải xác định engine giải quyết quan hệ interface/implementation như thế nào.

## 11. Thiết kế pointcut ghép với annotation mà vẫn kiểm soát phạm vi

Một bài toán thực tế: đo latency cho thao tác của nhóm I/O được đánh dấu hoặc thuộc một interface quan sát, nhưng phải bỏ qua module chứa bộ đo.

Viết bằng lời:

> Chọn method execution trong biên I/O, khi method có marker `@Observed` **hoặc** type có marker `@MeasuredType`, **và không** thuộc module instrumentation.

Giả mã:

```text
execution(method in IO boundary)
AND (
    methodHasAnnotation("Observed")
    OR targetTypeHasAnnotation("MeasuredType")
)
AND NOT belongsToModule("instrumentation")
```

Phải xác định:

- **`execution`:** Công cụ có method-execution join point không?
- **`methodHasAnnotation`:** Đọc marker trên method nào?
- **`targetTypeHasAnnotation`:** Là type khai báo hay runtime target type? Có xét superclass, interface không?
- **`NOT instrumentation`:** Loại trừ có bao phủ toàn bộ nhánh OR chưa?
- **`IO boundary`:** Là phạm vi module/package/class nào, có thay đổi theo refactor không?
- **Kết quả:** Advice chạy mỗi occurrence thỏa rule hay chỉ ở biên proxy?

### 11.1. Điều kiện loại trừ cần được áp cho toàn bộ nhánh OR

Khác biệt:

```text
(A OR B) AND NOT C       // C loại khỏi cả A và B
A OR (B AND NOT C)       // nhánh A vẫn được chọn dù C đúng
```

Nếu C biểu thị mã logging nội bộ, biểu thức thứ hai có thể khiến logging gọi lại chính aspect và phát sinh recursion. Dùng dấu ngoặc rõ ràng và kiểm thử method vừa thỏa A vừa thỏa C.

### 11.2. Binding annotation ở những nhánh khác nhau

Nếu một số công cụ cho phép advice nhận đối tượng annotation qua biến binding, thì biểu thức OR gồm:

```text
hasAnnotation(Tracked, bind annotation as tag)
OR typeMatches(ObservedType)
```

có thể tạo trường hợp nhánh thứ hai khớp nhưng **không có giá trị `tag`**. Engine có thể từ chối, yêu cầu mọi nhánh bind nhất quán hoặc định nghĩa quy tắc riêng. Đừng coi phép OR Boolean là đủ chứng minh binding hợp lệ. Có thể tách thành hai pointcut/advice hoặc thiết kế nguồn cấu hình chung rõ ràng.

## 12. Trường hợp nên và không nên dùng annotation-based pointcut

### Nên cân nhắc

- Một nhóm method hoặc type cần cùng **chính sách quan sát kỹ thuật**, không phụ thuộc chi tiết nghiệp vụ.
- Các nhóm tên khác nhau nhưng chung **ngữ nghĩa chọn**, chẳng hạn cần trace hoặc ghi chỉ số.
- Muốn nhà phát triển nhìn ngay ở declaration biết một chính sách sẽ được áp dụng.
- Tập điểm chọn cần được quản lý qua review và test rõ ràng; annotation có chủ sở hữu và quy ước sử dụng.
- Cơ chế interception/weaving đã được chứng minh bao phủ đường chạy dự kiến.

### Cần cân nhắc phương án khác

- Quyết định giá, trạng thái đơn hàng, quyền sở hữu dữ liệu hoặc quy tắc domain quan trọng: nên biểu diễn bằng domain service/policy hoặc workflow tường minh.
- Chính sách bắt buộc không được bỏ sót bất kỳ đường truy cập nào, nhưng chỉ dựa vào marker do con người nhớ gắn: nên có biên bảo vệ tin cậy và kiểm soát invariant thực tế.
- Một vài method cần xử lý khác nhau về thứ tự hoặc ngữ nghĩa: lời gọi trực tiếp, decorator hay interceptor tại biên rõ có thể dễ bảo trì hơn.
- Marker cần lưu dữ liệu thay đổi theo từng người dùng hoặc request: dùng runtime context phù hợp thay vì cố ép giá trị động vào annotation declaration.
- Mỗi loại method cần nhiều ngoại lệ riêng khiến pointcut trở nên dài và khó kiểm thử: rà soát lại ranh giới trách nhiệm và cách phân nhóm concern.

**Tiêu chí quan trọng:** Một annotation-based pointcut tốt không chỉ tiện gắn marker mà phải giúp người bảo trì **trả lời được chính xác những điểm nào được chọn và vì sao**.

## 13. Vấn đề bảo trì, bảo mật và vận hành

### 13.1. Pointcut có thể im lặng mất hiệu lực sau refactor

Đổi tên package/class, tách interface, di chuyển marker hoặc chuyển một method sang đường gọi mới có thể làm matcher thay đổi tập được chọn mà logic nghiệp vụ vẫn chạy bình thường. Cần kiểm thử độ phủ và review tác động khi thay declaration/metadata.

### 13.2. Annotation không phải một hàng rào bảo mật

Nếu advice kiểm tra quyền nhưng một số đường gọi bỏ qua proxy hoặc một vài method không gắn marker, kiểm tra có thể bị bỏ qua. Ngoài việc test metadata, phải bảo vệ bất biến tại **biên tin cậy** hoặc tầng nghiệp vụ liên quan. Không dùng annotation làm bằng chứng duy nhất rằng mọi đường truy cập đã được bảo vệ.

### 13.3. Tránh pointcut quá rộng và logging thông tin nhạy cảm

Một `@Observed` áp lên cả type có thể vô tình theo dõi method truy cập dữ liệu nhạy cảm. Advice không nên tự động in toàn bộ đối số/kết quả; cần cơ chế masking, sampling và kiểm soát cardinality. Logging ở hot path có thể tác động lớn hơn overhead của chính interception.

### 13.4. Phải kiểm thử lỗi của target và lỗi của advice

Một advice có thể ghi thành công khi method return, nhưng điều đó không chứng minh transaction đã được commit hoặc sự kiện đã lưu bền vững. Nếu ghi đo lường lỗi, policy fail-open/fail-closed cần rõ. Không để exception do advice gây ra vô tình thay thế lỗi gốc khi không có chủ đích.

### 13.5. Bất đồng bộ làm thay đổi mốc quan sát

Method trả `Future`/promise có thể kết thúc lời gọi trước khi công việc thực sự hoàn thành. Annotation trên method không tự làm advice quan sát được completion của task; cần hook tại mốc phù hợp nếu mục tiêu là đo latency end-to-end. Context như correlation ID cũng không tự truyền qua mọi scheduler/thread.

## 14. Quy trình kiểm thử annotation pointcut

Đề xuất một ma trận đủ bao phủ tính năng và ranh giới:

| Ca | Input/thiết lập | Kỳ vọng |
| --- | --- | --- |
| Positive direct marker | Method interface có `@Tracked`, gọi qua proxy. | Advice chạy đúng lần, đọc được category. |
| Negative missing marker | Method không có marker, gọi qua proxy. | Không có hành vi advice. |
| Negative excluded | Method có `@Tracked` và `@Internal`. | Điều kiện loại trừ thắng. |
| Error path | Method được chọn ném exception. | Advice failure chạy; caller nhận lỗi theo hợp đồng. |
| Direct target | Bỏ qua proxy. | Handler proxy không chạy. |
| Annotation trên implementation | Marker chỉ có ở implementation. | Quan sát và ghi rõ matcher interface-only có/không tìm thấy. |
| Marker trên type | Chỉ đánh dấu class. | Phân biệt type matcher với method matcher. |
| Override/overload | Marker ở method gốc hoặc một overload. | Tập pointcut khớp đúng đặc tả. |
| `SOURCE`/`CLASS` retention | Runtime matcher đọc qua reflection. | Không giả định marker vẫn xuất hiện. |
| Repeatable/meta-annotation | Marker lặp hoặc được bọc qua meta-annotation. | Hành vi đúng theo matcher công cụ đang dùng. |
| Async | Method được chọn trả handle công việc. | Tách return của method và completion thật. |
| Performance | Pointcut được gọi nhiều lần. | Đo overhead, log volume, cấp phát và không lộ dữ liệu. |

**Thứ tự QA hợp lý:**

1. Kiểm tra annotation declaration, `@Target`, `@Retention`, thuộc tính và nơi khai báo.
2. Kiểm tra matcher đang đọc đúng `Class`, `Method` hay thông tin bytecode nào.
3. Kiểm tra loại join point mà công cụ hỗ trợ.
4. Kiểm tra đường can thiệp thực tế: proxy hay weaving, có bao phủ caller không.
5. Chạy positive/negative tests, đường lỗi và trường hợp kế thừa/metadata khác tầng.
6. Kiểm thử concurrency và mức tải nếu advice sử dụng context hoặc có chi phí đáng kể.

Không chỉ kiểm tra “advice có chạy tại một ví dụ”; cần kiểm tra cả **nơi không được chạy** và đường có nguy cơ bypass.

## 15. Câu hỏi tự đánh giá

**1.** Một Java method có `@Tracked` nhưng không có công cụ nào đọc annotation hoặc kết hợp advice. Điều gì xảy ra?

**Đáp án:** Marker vẫn là metadata theo retention; không tự phát sinh hành vi AOP.

**2.** Vì sao `@Retention(RUNTIME)` cần thiết trong ví dụ JDK proxy?

**Đáp án:** Handler dùng reflection runtime để lấy annotation từ `Method`; nếu marker không được giữ ở runtime thì matcher này không quan sát được.

**3.** Marker trên method của interface có tự trở thành marker trên method implementation khi dùng `Method.getAnnotation` không?

**Đáp án:** Không. Hai declaration khác nhau; matcher phải chủ động duyệt hoặc hợp nhất nếu muốn hỗ trợ.

**4.** `@Inherited` có làm method override tự kế thừa annotation từ method superclass không?

**Đáp án:** Không. `@Inherited` trong Java quy định tra cứu annotation trên **class** theo superclass, không phải kế thừa method annotation.

**5.** `@Observed` trên một class có làm `Method.isAnnotationPresent(Observed.class)` của tất cả method true không?

**Đáp án:** Không mặc nhiên. Phải dùng type matcher hoặc logic tìm annotation trên declaring/runtime class phù hợp.

**6.** Một annotation repeatable xuất hiện hai lần. Có thể kết luận advice chạy hai lần không?

**Đáp án:** Không. Số annotation là dữ liệu; pointcut/advice có quy tắc matching và số occurrence riêng.

**7.** Có một method được marker `@Tracked` nhưng gọi trực tiếp target trong hệ thống chỉ dùng proxy. Advice có chắc chạy không?

**Đáp án:** Không. Điều kiện metadata có thể đúng nhưng handler không nhận lời gọi bỏ qua proxy.

**8.** Một method có marker `@Counted` và annotation type `Counted` có meta-annotation `@ObservabilityMarker`. Vì sao `method.isAnnotationPresent(ObservabilityMarker.class)` không phải cách chắc chắn để chọn method?

**Đáp án:** Vì `ObservabilityMarker` được khai báo trên **annotation type**, không trực tiếp trên method. Cần matcher hỗ trợ meta-annotation hoặc tự duyệt metadata nhiều cấp.

**9.** Lợi ích và rủi ro của chọn theo annotation thay vì tên method là gì?

**Đáp án:** Marker biểu đạt ý nghĩa và ít phụ thuộc quy ước tên hơn; nhưng gắn thiếu marker, đặt sai declaration, retention không phù hợp hoặc đường interception không bao phủ sẽ khiến advice bị bỏ qua.

## Kết luận

Chọn join point theo annotation và metadata là cách làm cho pointcut thể hiện **ngữ nghĩa và ý định áp dụng** thay vì chỉ dựa vào tên/chữ ký. Muốn chính xác, cần giải quyết đồng thời bốn câu hỏi: **metadata nằm ở đâu, còn tồn tại ở giai đoạn nào, matcher đọc chính xác declaration nào, và đường thực thi có đi qua cơ chế AOP hay không**. Khi sử dụng Java, đặc biệt lưu ý retention, type-vs-method, interface-vs-implementation, `@Inherited`, repeatable/meta-annotation và khả năng proxy/weaving. Một pointcut theo annotation đáng tin phải có positive tests, negative tests, đường lỗi và bằng chứng về độ phủ runtime.
