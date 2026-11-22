# Phân biệt vòng đời của annotation với vòng đời của đối tượng được đánh dấu trong Java

## 1. Hai khái niệm “vòng đời” cần phân biệt

Trong Java, **annotation** là metadata được gắn vào một vị trí trong mã nguồn: khai báo class, interface, method, field, constructor, parameter, package, module hoặc vị trí sử dụng kiểu, tùy theo `@Target`. **Đối tượng Java** là một instance được tạo ra trong quá trình chạy chương trình, ví dụ `new OrderService()`. Hai thứ có quan hệ về mặt mô tả nhưng **không chia sẻ cùng một vòng đời**.

- **Vòng đời annotation** trong ngữ cảnh `@Retention` nói đến mức độ thông tin annotation được compiler giữ lại: chỉ trong source, trong class file hoặc có thể truy xuất qua reflection ở runtime.
- **Vòng đời object** nói đến thời điểm một instance được tạo, được chương trình tham chiếu/sử dụng và cuối cùng trở nên không còn reachable để có thể được garbage collector thu hồi.
- **Lớp/class** là một cấp khác với object: nhiều instance có thể được tạo từ cùng một class, còn annotation trên khai báo class mô tả **kiểu**, không phải từng instance cụ thể.

Ví dụ:

```java
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Audited {}

@Audited
class OrderService {
    int count;
}

OrderService first = new OrderService();
OrderService second = new OrderService();
```

Đoạn trên chỉ minh họa quan hệ, không phải chương trình chạy độc lập. `@Audited` nằm trên **khai báo class** `OrderService`. Dù hai object `first` và `second` là hai instance khác nhau, chúng không nhận hai bản annotation class độc lập. `first.count` và `second.count` lại là hai giá trị instance riêng biệt.

Điều cần tránh là suy luận: “Có một object mới được tạo thì annotation trên class cũng được tạo thêm, và object bị GC thì annotation trên class bị mất”. Cả hai ý đều không đúng với cách metadata của Java hoạt động.

## 2. Ba chính sách lưu giữ annotation: SOURCE, CLASS, RUNTIME

`@Retention` xác định annotation có được giữ lại sau quá trình biên dịch và có được Java reflection quan sát ở runtime hay không.

| Chính sách | Có trong mã nguồn? | Lưu vào `.class` của thành phần được đánh dấu? | Reflection thông thường ở runtime đọc được? |
| --- | --- | --- | --- |
| `RetentionPolicy.SOURCE` | Có | Không | Không |
| `RetentionPolicy.CLASS` | Có | Có | Không |
| `RetentionPolicy.RUNTIME` | Có | Có | Có, khi đúng đích và annotation hiện diện |

Ví dụ:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.SOURCE)
@interface SourceHint {}

@Retention(RetentionPolicy.CLASS)
@interface ClassHint {}

@Retention(RetentionPolicy.RUNTIME)
@interface RuntimeHint {}
```

Các khai báo trên là đoạn mã minh họa; để biên dịch cần đặt chúng ở vị trí hợp lệ trong tệp Java cùng các import. Nếu không viết `@Retention` cho một annotation type, chính sách **mặc định là `CLASS`**.

**SOURCE:** compiler nhìn thấy annotation khi xử lý nguồn; annotation này không được giữ lại như annotation của chương trình đã biên dịch. Nó phù hợp cho các kiểm tra và quy ước được thực hiện khi biên dịch. Chẳng hạn `@Override` là một annotation tiêu biểu với retention `SOURCE`. Việc annotation không còn trong class file **không nói gì về việc instance của class có thể tồn tại bao lâu**.

**CLASS:** compiler giữ annotation trong class file, nhưng các API reflection thông thường như `Class.getAnnotation(...)` không cung cấp annotation này. Công cụ phân tích bytecode có thể đọc metadata trong class file. Nó cũng không phụ thuộc vào việc một instance cụ thể còn sống hay đã được GC.

**RUNTIME:** compiler lưu annotation để Java runtime có thể dùng reflection quan sát, ví dụ qua `Class.getAnnotation`, `Field.getAnnotation` hoặc `Method.getAnnotation` đúng với vị trí annotation được gắn. “RUNTIME” **không có nghĩa** annotation là một object sống cho đến lúc JVM tắt, cũng không có nghĩa Java tự thực thi logic ghi trong tên annotation.

Chính sách retention thuộc **định nghĩa annotation type** và áp dụng cho tất cả lần dùng hợp lệ của annotation type ấy. Hai lần dùng cùng một annotation type không thể tùy chọn retention khác nhau ngay tại vị trí gắn.

## 3. Trục thời gian: từ source đến object

Có thể hình dung những diễn biến độc lập sau:

```text
Nguồn Java
  │   @SourceHint  @ClassHint  @RuntimeHint
  ▼
javac biên dịch
  ├── SOURCE: không phát ra annotation tương ứng trong class file
  ├── CLASS:  lưu metadata vào class file
  └── RUNTIME: lưu metadata được reflection hỗ trợ
  ▼
.class được nạp/định nghĩa thành class lúc chạy
  │
  ├── Có thể kiểm tra class metadata bằng reflection (RUNTIME)
  │
  ├── new Example() ──► object A ──► được dùng ──► có thể đủ điều kiện GC
  │
  └── new Example() ──► object B ──► được dùng ──► có thể đủ điều kiện GC
```

Đây là sơ đồ học thuật, không phải mô tả mọi chi tiết của class loading hoặc garbage collector.

- **Biên dịch:** kiểm tra annotation theo quy tắc kiểu/target, có thể phục vụ công cụ xử lý annotation, rồi lưu metadata theo retention. Một class có thể được biên dịch ngay cả khi chưa có instance nào.
- **Nạp class:** JVM tạo/duy trì biểu diễn runtime của class khi class được nạp và sử dụng theo quy tắc JVM. Annotation `RUNTIME` của class, method, field... có thể được reflection truy xuất. Class không nhất thiết được khởi tạo thành instance để xem annotation trên `Class<?>`.
- **Khởi tạo instance:** mỗi `new` tạo một object với trạng thái instance riêng. `@Retention` không quyết định lúc object được tạo, constructor có được gọi hay không, hoặc vòng đời object.
- **Giải phóng instance:** object có thể trở nên unreachable và đủ điều kiện GC. Thời điểm thu gom không được bảo đảm và không thể suy ra từ annotation trên class. Metadata class không bị “xóa một phần” chỉ vì một instance mất đi.
- **Dỡ class/class loader:** JVM có thể giải phóng dữ liệu gắn với class/class loader khi không còn dùng theo điều kiện của runtime. Đó là vấn đề về vòng đời class và class loader, **khác** với vòng đời từng instance và cũng khác với retention policy.

Một `Class` trong runtime được xác định bởi tên nhị phân **và class loader định nghĩa nó**. Không nên nói đơn giản “chỉ có một Class object cho mỗi tên class trên toàn JVM” khi có nhiều class loader. Nhưng trong một ngữ cảnh nạp class thông thường, nhiều instance được tạo từ cùng một class đều trỏ về cùng biểu diễn runtime của class ấy.

## 4. Ví dụ Java 17+ đầy đủ, có thể chạy

Ví dụ sau sử dụng ba retention khác nhau trên **cùng một class**. Sau đó chương trình tạo hai instance để chứng minh trạng thái instance có thể khác nhau trong khi metadata của khai báo class không đổi.

Lưu nguyên đoạn dưới đây vào tệp **`AnnotationVsObjectDemo.java`**:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Field;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
@interface SourceMarker {}

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.CLASS)
@interface ClassMarker {}

@Target({ElementType.TYPE, ElementType.FIELD})
@Retention(RetentionPolicy.RUNTIME)
@interface RuntimeLabel {
    String value();
}

@SourceMarker
@ClassMarker
@RuntimeLabel("report-service")
final class ReportService {
    @RuntimeLabel("instance-counter")
    private int counter;

    ReportService(int counter) {
        this.counter = counter;
    }

    void increment() { counter++; }
    int counter() { return counter; }
}

public class AnnotationVsObjectDemo {
    public static void main(String[] args) throws NoSuchFieldException {
        ReportService first = new ReportService(1);
        ReportService second = new ReportService(10);
        Class<?> type = ReportService.class;
        Field field = type.getDeclaredField("counter");

        System.out.println("SOURCE via reflection: " + type.isAnnotationPresent(SourceMarker.class));
        System.out.println("CLASS via reflection: " + type.isAnnotationPresent(ClassMarker.class));
        System.out.println("RUNTIME via reflection: " + type.isAnnotationPresent(RuntimeLabel.class));
        System.out.println("Class label: " + type.getAnnotation(RuntimeLabel.class).value());
        System.out.println("Field label: " + field.getAnnotation(RuntimeLabel.class).value());
        System.out.println("Before: " + first.counter() + ", " + second.counter());
        first.increment();
        System.out.println("After: " + first.counter() + ", " + second.counter());
        System.out.println("Same runtime Class: " + (first.getClass() == second.getClass()));
    }
}
```

Với **JDK 17 trở lên**, mở terminal tại thư mục chứa tệp:

```bash
javac --release 17 AnnotationVsObjectDemo.java
java AnnotationVsObjectDemo
```

**Stdout chính xác:**

```text
SOURCE via reflection: false
CLASS via reflection: false
RUNTIME via reflection: true
Class label: report-service
Field label: instance-counter
Before: 1, 10
After: 2, 10
Same runtime Class: true
```

Kết quả đã được đối chiếu bằng biên dịch `javac --release 17` và thực thi chương trình trên JDK tương thích.

### Phân tích kết quả

1. `ReportService` có ba annotation trên **type declaration**. `SourceMarker` có retention `SOURCE`; `ClassMarker` có retention `CLASS`; `RuntimeLabel` có retention `RUNTIME`.
2. `isAnnotationPresent(SourceMarker.class)` trả `false`. Compiler đã bỏ annotation đó khỏi metadata class file; việc object `first` và `second` đang tồn tại không thể làm nó xuất hiện.
3. `isAnnotationPresent(ClassMarker.class)` cũng trả `false`. Điều đó **không chứng minh metadata CLASS không có trong file**; nó chỉ có nghĩa API runtime reflection ở đây không hiển thị annotation retention `CLASS`.
4. `isAnnotationPresent(RuntimeLabel.class)` trả `true`. Phần tử `value()` của annotation class có giá trị `"report-service"`.
5. `Field` đại diện cho **khai báo field** `counter` và mang annotation runtime riêng `"instance-counter"`. Dù `first.counter` là `1` còn `second.counter` là `10`, khai báo field trong class vẫn là một; annotation field không lưu riêng mỗi giá trị field.
6. `first.increment()` chỉ thay đổi trạng thái của object `first` từ `1` thành `2`; trạng thái object `second` vẫn là `10`. Các giá trị metadata trên class và field cũng không đổi.
7. `first.getClass() == second.getClass()` là `true`: hai instance có cùng class runtime trong ví dụ này, bất kể vòng đời và trạng thái của từng object.

### Có thể quan sát CLASS retention trong bytecode

Nếu muốn kiểm chứng thêm sau khi biên dịch, dùng lệnh sau (đầu ra dài và tùy trình bày theo phiên bản JDK, nên không đưa stdout cố định):

```bash
javap -v ReportService
```

Trong phần verbose của class file, công cụ `javap` có thể cho thấy `RuntimeInvisibleAnnotations` với `ClassMarker` và `RuntimeVisibleAnnotations` với `RuntimeLabel`. `SourceMarker` không được phát ra như annotation của `ReportService` trong class file. Từ **“Invisible”** ở đây nói về **khả năng hiển thị qua reflection**, không nói rằng annotation gắn với object đã bị xóa.

## 5. Tách bạch ba loại dữ liệu trong ví dụ

| Thông tin | Thuộc về đâu? | Có thay đổi khi gọi `new ReportService(...)` lần nữa? |
| --- | --- | --- |
| `@RuntimeLabel("report-service")` | Metadata của khai báo `ReportService` | Không tạo một annotation trên class mới chỉ vì có thêm instance |
| `@RuntimeLabel("instance-counter")` | Metadata của **khai báo field** `counter` | Không tạo metadata field khác cho từng object |
| `first.counter` | Trạng thái riêng của object `first` | Object mới có giá trị khởi tạo riêng |
| `second.counter` | Trạng thái riêng của object `second` | Không bị sửa khi thao tác với `first.counter` |
| Biến tham chiếu `first`, `second` | Các tham chiếu đến instance khi chương trình chạy | Có thể thay đổi, thoát khỏi phạm vi hoặc không còn giữ object reachable |
| `ReportService.class` | Biểu diễn runtime của kiểu trong class loader đang sử dụng | Không tạo một class mới chỉ do mỗi lần `new` |

Một annotation được đặt trên **method declaration** cũng mô tả phương thức, không mô tả riêng từng lần gọi method. Ví dụ `@Tracked` trên `void handle()` không sinh một annotation mới cho lần gọi thứ nhất, thứ hai... Một annotation được đặt trên **parameter declaration** mô tả tham số trong chữ ký, không phải một annotation mới được tạo cho mỗi đối số truyền vào lúc gọi.

Đối với **type-use annotations** (ví dụ chú thích vị trí sử dụng kiểu với `ElementType.TYPE_USE`), nơi metadata được biểu diễn và cách truy xuất có thể khác annotation trên declaration. Tuy nhiên, nó vẫn là metadata gắn với vị trí khai báo/sử dụng kiểu trong chương trình đã biên dịch, **không mặc nhiên là trạng thái động riêng của từng object**.

## 6. Khi runtime đọc annotation thì có tạo object không?

Có hai khái niệm cần tách biệt:

- **Metadata được lưu:** với `RUNTIME`, annotation và các giá trị của nó được lưu trong biểu diễn đã biên dịch và được runtime hỗ trợ truy xuất theo API reflection.
- **Đối tượng biểu diễn annotation:** khi gọi `ReportService.class.getAnnotation(RuntimeLabel.class)`, JVM/thư viện reflection có thể tạo hoặc cung cấp một đối tượng triển khai interface annotation để mã Java gọi `value()`.

Do đó, **đối tượng Java đại diện cho annotation khi reflection** và **instance của `ReportService` được đánh dấu** là các đối tượng thuộc hai mục đích khác nhau. Đừng dựa vào số lượng đối tượng annotation đại diện được tạo, việc cache hay phép so sánh tham chiếu `==` giữa hai lần gọi reflection: đó không phải hợp đồng cần thiết để hiểu retention. Khi cần kiểm tra giá trị annotation, dùng API và nội dung element, không suy luận danh tính object đại diện.

Annotation type là một dạng interface theo mô hình ngôn ngữ; reflection trả về giá trị có kiểu annotation tương ứng. Nhưng các element annotation **không có setter để thay đổi metadata trên class**. Giá trị đọc từ annotation là dữ liệu khai báo, không là biến instance của đối tượng được đánh dấu.

Ví dụ, đoạn sau là minh họa sử dụng trong phương thức có quyền truy cập `ReportService` và `RuntimeLabel`:

```java
RuntimeLabel label = ReportService.class.getAnnotation(RuntimeLabel.class);
System.out.println(label.value()); // report-service
```

Gọi `new ReportService(100)` trước hoặc sau đoạn này cũng không khiến `label.value()` trở thành `"100"`. Nếu chương trình cần lưu metadata tùy biến **cho từng instance**, hãy dùng field, một cấu trúc dữ liệu bên ngoài ánh xạ instance sang metadata, hoặc một cơ chế runtime phù hợp với bài toán; annotation trên class không đảm nhận vai trò đó.

## 7. Annotation RUNTIME và garbage collection: các hiểu lầm quan trọng

Giả sử một object được tạo:

```java
ReportService service = new ReportService(10);
service = null;
```

Đoạn code chỉ là minh họa và không đủ để khẳng định lúc nào một object thật sự bị thu gom. Gán `null` cho một biến chỉ bỏ một tham chiếu; nếu còn tham chiếu mạnh khác, object vẫn có thể reachable. Nếu object đã unreachable, garbage collector **có thể** thu hồi nó tại thời điểm phù hợp.

Nhưng việc object đó bị thu hồi:

- **Không thay đổi retention** của `SourceMarker`, `ClassMarker` hoặc `RuntimeLabel`.
- **Không làm mất annotation** `@RuntimeLabel("report-service")` khỏi mô tả kiểu `ReportService` khi class đó vẫn đang được nạp và có thể truy xuất trong runtime.
- **Không đồng nghĩa class bị unload**. Class unloading liên quan đến khả năng giải phóng biểu diễn class và class loader, chịu các điều kiện riêng của JVM.
- **Không chứng minh annotation đã được thực thi hay không**. Logic nghiệp vụ chỉ xuất hiện khi có code thực sự tiêu thụ annotation.

Ngược lại, retention `SOURCE` **không khiến object sống ngắn hơn**, retention `CLASS` **không khiến object tồn tại chỉ trong lúc biên dịch**, và retention `RUNTIME` **không giữ mọi instance của class sống đến khi JVM kết thúc**. Tên các mức retention chỉ thể hiện phạm vi lưu giữ annotation **qua các giai đoạn biên dịch/runtime**, không phải thuật toán quản lý bộ nhớ của object.

**Không dùng `System.gc()` để “chứng minh” vòng đời annotation**: lời gọi đó không bảo đảm GC chạy hoặc thu gom một object cụ thể. Việc đọc class annotation trước/sau khi một instance trở nên unreachable có thể giúp giải thích khái niệm, nhưng không cần dựa vào thời điểm GC để xác nhận quy tắc retention.

## 8. @Inherited có biến annotation thành thuộc tính của instance?

Không. `@Inherited` là một **meta-annotation** tác động đến quy tắc tìm annotation trên **class** khi class con không khai báo trực tiếp annotation cùng kiểu.

Ví dụ (đoạn minh họa hợp lệ, không phải chương trình có `main`):

```java
import java.lang.annotation.Inherited;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Inherited
@Retention(RetentionPolicy.RUNTIME)
@interface Team {
    String value();
}

@Team("core")
class BaseService {}

class DerivedService extends BaseService {}
```

`DerivedService.class.getAnnotation(Team.class)` có thể trả annotation `@Team("core")` được kế thừa về mặt tra cứu. Tuy nhiên:

- Điều này áp dụng theo quy tắc `@Inherited` khi tìm annotation trên **khai báo class qua superclass**, không phải sao chép một annotation mới cho mỗi instance.
- `@Inherited` không làm annotation từ interface tự động áp dụng lên class triển khai.
- `@Inherited` không tự áp dụng quy tắc kế thừa tương tự cho annotation trên method, field hay parameter.
- Nó không quyết định lifetime của một object `new DerivedService()`.

Ví dụ thêm một object lớp con rồi làm mất tham chiếu tới object đó không thay đổi cách `DerivedService.class.getAnnotation(Team.class)` được xác định.

## 9. Framework có thể thay đổi hành vi object từ annotation như thế nào?

Một số framework dùng reflection, classpath scanning, bytecode instrumentation hoặc annotation processing để đọc metadata và quyết định cấu hình hay hành vi. Ví dụ, một framework có thể thấy annotation `@Managed` trên một class, tạo một instance và đưa nó vào một container, hoặc gắn hành vi bổ sung khi gọi method.

Ở đây cần tách ba bước:

1. **Định nghĩa/đặt annotation:** mô tả metadata ở mã nguồn.
2. **Giữ annotation theo retention:** quy định nguồn/class file/runtime có quan sát được metadata bằng những cơ chế nào.
3. **Có mã tiêu thụ metadata:** compiler plugin, annotation processor, framework hoặc logic do bạn viết đọc annotation rồi quyết định **có tạo object, giữ tham chiếu, gọi method hay hủy tài nguyên hay không**.

Ví dụ `@Retention(RUNTIME)` đơn lẻ không tạo object nào và không đăng ký bean. Một framework có thể dùng annotation để quản lý object, nhưng **vòng đời do framework và mã ứng dụng quản lý**, không phải do chính retention tự vận hành.

Nếu annotation type có retention `SOURCE`, một annotation processor vẫn có thể đọc được nó trong các vòng xử lý nguồn tại compile time. Nếu retention `CLASS`, công cụ phân tích bytecode có thể quan sát metadata. Nếu retention `RUNTIME`, reflection có thể đọc khi chạy. Mỗi công cụ phải dùng cơ chế phù hợp; đừng đồng nhất việc “annotation được lưu” với “annotation được xử lý tự động”.

## 10. Các trường hợp kiểm tra hiểu đúng

**Trường hợp A: một class có annotation, chưa có object nào.**

Bạn vẫn có thể lấy `ReportService.class.getAnnotation(RuntimeLabel.class)` khi class được dùng hợp lệ trong runtime. Không cần gọi `new ReportService(...)` trước để annotation khai báo class xuất hiện.

**Trường hợp B: tạo 1.000 object từ một class có annotation.**

Bạn có 1.000 instance (khi chúng thực sự được tạo), mỗi instance có trạng thái riêng. Điều đó không tương đương 1.000 annotation độc lập gắn trên khai báo class. Reflection trên cùng runtime `Class` vẫn đọc thông tin khai báo class.

**Trường hợp C: xóa tham chiếu đến một object.**

Nếu object không còn reachable, nó có thể được thu gom. Annotation gắn trên khai báo class vẫn được định nghĩa theo retention/class metadata khi class tồn tại; không được kết luận retention đổi thành `SOURCE` hoặc annotation đã biến mất.

**Trường hợp D: dùng annotation CLASS nhưng muốn `getAnnotation(...)` nhận được giá trị.**

Kết quả reflection là không có annotation đó. Nếu muốn đọc qua API reflection ở runtime, sửa định nghĩa annotation thành `@Retention(RetentionPolicy.RUNTIME)` và biên dịch mã tương ứng. Giữ `CLASS` vẫn có thể hữu ích cho công cụ đọc class file.

**Trường hợp E: annotate một field có giá trị khác nhau ở từng object.**

Annotation mô tả **khai báo field**. Giá trị field instance có thể thay đổi theo object. Nếu một bộ xử lý muốn xem giá trị thực tế của field tại một thời điểm, nó cần làm thêm thao tác đọc giá trị của field trên instance cụ thể; dữ liệu từ `Field.getAnnotation(...)` không chứa giá trị runtime đó.

**Trường hợp F: đọc annotation trên method sau nhiều lần gọi method.**

`Method.getAnnotation(...)` vẫn cho metadata gắn với khai báo method (nếu có retention phù hợp). Nó không phản ánh số lần gọi, kết quả tính toán, thời gian chạy hoặc những tham số đã truyền vào, trừ khi một hệ thống khác tự thu thập chúng.

## 11. Checklist áp dụng trong dự án

Khi thiết kế hoặc giải thích annotation, tự hỏi:

1. **Annotation được gắn vào đâu?** Class, field, method, parameter, type use, package hay module? Dùng `@Target` phù hợp.
2. **Ai cần đọc annotation và vào giai đoạn nào?** Compiler/annotation processor, công cụ đọc bytecode hay Java reflection lúc chạy? Chọn `@Retention` đúng nhu cầu.
3. **Dữ liệu là metadata cố định của khai báo hay trạng thái động của từng instance?** Metadata dùng annotation; trạng thái động dùng field hoặc một cơ chế runtime phù hợp.
4. **Ai thực sự sử dụng metadata để thực hiện hành vi?** Xác định rõ processor/framework/logic. Không giả định gắn annotation tự thực hiện tác vụ.
5. **Có đang nhầm vòng đời class/class loader với object?** Tạo object và GC là một tiến trình; nạp/dỡ class và lưu giữ metadata là tiến trình khác.
6. **Ví dụ có kiểm chứng được không?** Biên dịch với JDK 17+, kiểm tra stdout cho reflection và object state, dùng `javap -v` khi cần phân biệt metadata `CLASS` với `RUNTIME`.

**Ghi nhớ:** `SOURCE`, `CLASS` và `RUNTIME` mô tả **vòng đời lưu giữ metadata annotation**, còn `new`, tham chiếu và garbage collection mô tả **vòng đời instance được tạo từ class**. Hai trục này độc lập. Annotation gắn lên khai báo class, field hoặc method không trở thành trạng thái riêng của từng object chỉ vì có thêm object được khởi tạo.
