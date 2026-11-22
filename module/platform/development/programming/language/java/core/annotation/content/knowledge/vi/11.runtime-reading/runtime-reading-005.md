# Đọc giá trị phần tử qua phương thức của kiểu annotation trong Java

## 1. Vì sao một annotation có các phương thức?

Khi định nghĩa annotation tùy chỉnh bằng `@interface`, những khai báo có dạng phương thức không tham số bên trong nó được gọi là **phần tử annotation** (*annotation elements*). Mỗi phần tử định nghĩa một **tên** và **kiểu giá trị metadata**:

```java
@interface OperationInfo {
    String value();
    int retries() default 0;
    String[] labels() default {};
    Class<?> handler() default Object.class;
}
```

Ở đây, `value()`, `retries()`, `labels()` và `handler()` là những phương thức phần tử. Chúng không có thân phương thức do lập trình viên viết và không nhận đối số. Tại nơi sử dụng, người viết mã cung cấp giá trị cho từng phần tử:

```java
// Minh họa cú pháp sử dụng, chưa phải chương trình hoàn chỉnh.
@OperationInfo(
    value = "ISSUE_TICKET",
    retries = 2,
    labels = {"ticket", "critical"},
    handler = String.class
)
public void issueTicket() {}
```

Annotation này mô tả metadata cho **phương thức `issueTicket`**. Chữ `retries = 2` trong annotation không phải lệnh “tự thử lại hai lần”. Muốn thực hiện retry thực sự, phải có bên xử lý đọc giá trị và áp dụng quy tắc.

**Trọng tâm bài:** tại runtime, sau khi lấy được đối tượng annotation bằng Reflection, ta **gọi các phương thức phần tử không tham số trên chính đối tượng annotation** để nhận lại giá trị metadata:

```java
OperationInfo info = method.getAnnotation(OperationInfo.class);
if (info != null) {
    String action = info.value();
    int attempts = info.retries();
    String[] tags = info.labels();
    Class<?> type = info.handler();
}
```

Đây là API **kiểu tĩnh**: `info` có kiểu `OperationInfo`, vì vậy compiler biết chính xác các phương thức `value()`, `retries()`, `labels()` và `handler()` cùng kiểu trả về của chúng.

## 2. Ba bước để đọc giá trị phần tử lúc chạy

### Bước 1: Định nghĩa annotation có retention phù hợp

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface OperationInfo {
    String value();
    int retries() default 0;
}
```

Có hai điều kiện quan trọng:

- `@Retention(RetentionPolicy.RUNTIME)`: metadata được lưu để API Reflection thông thường có thể truy xuất khi chương trình chạy.
- `@Target(ElementType.METHOD)`: loại annotation có thể được gắn lên **khai báo phương thức**. Vì vậy khi đọc phải truy vấn đối tượng `Method` mô tả đúng phương thức, không phải đối tượng `Class` của lớp.

Nếu bỏ `@Retention`, chính sách mặc định của một annotation tự định nghĩa là `CLASS`. Khi đó annotation có thể được lưu trong bytecode nhưng không hiển thị qua `Method.getAnnotation(...)` của Reflection thông thường.

### Bước 2: Lấy annotation từ đúng thành phần đã gắn

```java
Method method = TicketService.class.getDeclaredMethod("issueTicket");
OperationInfo info = method.getAnnotation(OperationInfo.class);
```

`getDeclaredMethod("issueTicket")` tìm phương thức được khai báo trực tiếp có tên và danh sách kiểu tham số khớp trong `TicketService`. Trong ví dụ này phương thức không nhận tham số, nên không cần thêm `Class<?>` mô tả tham số.

`method.getAnnotation(OperationInfo.class)` nhận một đối tượng `Class` biểu diễn loại annotation. Nhờ generic của API Reflection, kết quả có kiểu `OperationInfo`, **không phải** `String`, `int` hay giá trị của riêng một phần tử. Ta cần lấy **đối tượng annotation trước**, sau đó mới gọi các phần tử.

**Kiểm tra `null` trước khi đọc.** `getAnnotation(...)` có thể trả về `null` nếu phương thức không được gắn annotation đó, hoặc annotation không khả dụng theo retention. Gọi `info.value()` khi `info == null` sẽ gây `NullPointerException`.

### Bước 3: Gọi phương thức phần tử để lấy metadata

```java
if (info != null) {
    System.out.println(info.value());
    System.out.println(info.retries());
}
```

Các lời gọi `info.value()` và `info.retries()` là lời gọi **không tham số** vào đối tượng annotation. Chúng trả lại metadata theo kiểu đã khai báo trong `@interface`.

Đừng viết `info.value("ISSUE_TICKET")`: việc gán giá trị xảy ra ở **nơi sử dụng annotation** theo cú pháp `value = ...`; phương thức phần tử không nhận đối số khi đọc.

## 3. Ví dụ Java 17+ hoàn chỉnh, chạy độc lập

Tạo một tệp **`AnnotationElementValuesDemo.java`** chứa toàn bộ mã sau. Ví dụ không yêu cầu Spring hoặc thư viện bên ngoài.

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface OperationInfo {
    String value();
    int retries() default 0;
    String[] labels() default {};
    Class<?> handler() default Object.class;
}

class TicketService {
    @OperationInfo(
        value = "ISSUE_TICKET",
        retries = 2,
        labels = {"ticket", "critical"},
        handler = String.class
    )
    public void issueTicket() {}

    // "value" là tên phần tử đặc biệt có thể viết dạng rút gọn.
    @OperationInfo("LOOKUP")
    public void lookup() {}

    public void cancel() {}
}

public class AnnotationElementValuesDemo {
    private static void inspect(String methodName)
            throws NoSuchMethodException {

        Method method = TicketService.class
                .getDeclaredMethod(methodName);

        OperationInfo info = method.getAnnotation(OperationInfo.class);
        if (info == null) {
            System.out.println(methodName + ": (none)");
            return;
        }

        System.out.println(methodName
                + ": name=" + info.value()
                + ", retries=" + info.retries()
                + ", labels=" + String.join("|", info.labels())
                + ", handler=" + info.handler().getSimpleName());
    }

    public static void main(String[] args)
            throws NoSuchMethodException {

        inspect("issueTicket");
        inspect("lookup");
        inspect("cancel");

        Method retriesElement = OperationInfo.class
                .getDeclaredMethod("retries");
        System.out.println("Declared default retries: "
                + retriesElement.getDefaultValue());
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 AnnotationElementValuesDemo.java
java AnnotationElementValuesDemo
```

**Stdout chính xác:**

```text
issueTicket: name=ISSUE_TICKET, retries=2, labels=ticket|critical, handler=String
lookup: name=LOOKUP, retries=0, labels=, handler=Object
cancel: (none)
Declared default retries: 0
```

### Phân tích kết quả

**`issueTicket`:** annotation cung cấp đầy đủ bốn phần tử. `info.value()` trả về `"ISSUE_TICKET"`; `info.retries()` trả về `2`; `info.labels()` trả về mảng chứa `"ticket"` và `"critical"` theo thứ tự đã viết. `String.join("|", ...)` nối mảng thành `ticket|critical`. `info.handler()` trả về đối tượng `Class<?>` biểu diễn `String.class`, nên `getSimpleName()` là `String`.

**`lookup`:** cú pháp `@OperationInfo("LOOKUP")` là viết tắt cho `@OperationInfo(value = "LOOKUP")` khi dùng phần tử mang tên `value`. Các phần tử không được cung cấp được lấy từ mặc định trong khai báo loại annotation: `retries() == 0`, `labels()` là mảng rỗng, `handler() == Object.class`. Do mảng rỗng, `String.join("|", ...)` trả về chuỗi rỗng sau `labels=`.

**`cancel`:** phương thức không gắn `@OperationInfo`, nên `getAnnotation` trả về `null`; chương trình in `cancel: (none)` và không cố gọi phần tử trên đối tượng không tồn tại.

**Dòng cuối:** `OperationInfo.class.getDeclaredMethod("retries")` lấy đối tượng `Method` mô tả chính **phần tử khai báo** trong annotation type. `getDefaultValue()` trả về đối tượng giá trị mặc định được khai báo trong `@interface`, ở đây là `0`. Đây là câu hỏi “mặc định của định nghĩa phần tử là gì?”, không phải câu hỏi “phương thức `issueTicket` có giá trị phần tử gì?”.

Trong ví dụ, `issueTicket()`, `lookup()` và `cancel()` **không được gọi thực thi**; mã chỉ dùng Reflection để đọc annotation. Do vậy không có tác dụng nghiệp vụ phát sinh tự động từ những annotation đã gắn.

## 4. Phân biệt hai cách gọi phương thức liên quan đến annotation

| Mã Java | Đối tượng nhận lời gọi | Trả về | Ý nghĩa |
| --- | --- | --- | --- |
| `method.getAnnotation(OperationInfo.class)` | `Method` mô tả phương thức nghiệp vụ | `OperationInfo` hoặc `null` | Tìm annotation được gắn vào phương thức |
| `info.value()` | Đối tượng annotation `OperationInfo` | `String` | Đọc giá trị phần tử `value` |
| `info.retries()` | Đối tượng annotation `OperationInfo` | `int` | Đọc giá trị phần tử `retries` |
| `info.labels()` | Đối tượng annotation `OperationInfo` | `String[]` | Đọc giá trị mảng `labels` |
| `info.handler()` | Đối tượng annotation `OperationInfo` | `Class<?>` | Đọc loại class đã lưu |
| `element.getDefaultValue()` | `Method` mô tả phần tử trong chính annotation type | `Object` hoặc `null` | Đọc **giá trị mặc định của khai báo**, không gắn với một chỗ sử dụng cụ thể |

Đối tượng annotation nhận từ Reflection là một đối tượng **triển khai giao diện annotation** phù hợp do môi trường Java cung cấp. Dù trong `@interface` chỉ có khai báo phần tử không chứa thân, chương trình vẫn có thể gọi các phương thức đó ở runtime để nhận metadata đã lưu. Lập trình viên không cần tự `new OperationInfo()` và thực tế không thể khởi tạo annotation theo cách thông thường như class nghiệp vụ.

`OperationInfo.class` là **loại annotation**; `info` là **một giá trị annotation đọc tại vị trí sử dụng**; `TicketService.class` là class chứa các phương thức nghiệp vụ. Ba đối tượng này phục vụ các câu hỏi Reflection khác nhau.

## 5. Giá trị bắt buộc, mặc định và cú pháp `value`

### Phần tử bắt buộc

```java
@interface Route {
    String path();
}
```

`path()` không có giá trị mặc định. Nơi sử dụng phải cung cấp giá trị, ví dụ `@Route(path = "/tickets")`. Gắn `@Route` mà không cung cấp `path` là lỗi biên dịch. Khi đọc annotation hợp lệ, `route.path()` trả lại chuỗi đã gắn.

### Phần tử có mặc định

```java
@interface RetryHint {
    int times() default 3;
}
```

Nếu dùng `@RetryHint`, gọi `hint.times()` trả về `3`. Nếu dùng `@RetryHint(times = 5)` thì trả về `5`. Giá trị mặc định nằm trong **định nghĩa loại annotation**; khi đọc, API đã cung cấp giá trị thực tế theo nơi sử dụng hoặc mặc định tương ứng. Không cần tự kiểm tra “phần tử có được viết hay không” để sử dụng giá trị.

**Một giới hạn quan trọng:** sau khi gọi `hint.times()` và nhận `3`, API này không trực tiếp cho biết tác giả đã bỏ qua phần tử để lấy mặc định hay đã viết tường minh `times = 3`. Nếu yêu cầu phân biệt **cú pháp nguồn** giữa bỏ qua và chỉ định tường minh, cần cách phân tích thích hợp ở compile-time/source; không nên suy diễn từ giá trị runtime.

### Phần tử đặc biệt tên `value`

```java
@interface Label {
    String value();
    int order() default 0;
}

// Hai cách sử dụng có cùng ý nghĩa cho phần tử value:
@Label("IMPORTANT")
class A {}

@Label(value = "IMPORTANT")
class B {}
```

Tên `value` cho phép cú pháp đơn giản khi đó là phần tử được truyền theo dạng rút gọn. Nếu muốn gán đồng thời nhiều phần tử, phải dùng tên rõ ràng theo ngữ pháp phù hợp, chẳng hạn `@Label(value = "IMPORTANT", order = 2)`.

Dù nơi sử dụng có thể viết `@Label("IMPORTANT")`, lúc đọc vẫn gọi **`label.value()`**, không phải `label.getValue()`. Phương thức getter tự đặt theo JavaBeans như `getValue()` **không tự được sinh ra**.

## 6. Các kiểu giá trị phần tử và cách xử lý khi đọc

Phần tử annotation có các kiểu được Java cho phép: kiểu nguyên thủy, `String`, `Class`, enum, một annotation khác và **mảng một chiều** của những kiểu ấy. Khi đọc chúng bằng phương thức phần tử, Java trả về kiểu phù hợp với khai báo:

| Khai báo phần tử | Lời gọi đọc | Kết quả điển hình |
| --- | --- | --- |
| `int retries();` | `info.retries()` | `int`, ví dụ `2` |
| `String value();` | `info.value()` | `String`, ví dụ `"ISSUE_TICKET"` |
| `Class<?> handler();` | `info.handler()` | `Class<?>`, ví dụ `String.class` |
| `String[] labels();` | `info.labels()` | `String[]` |
| `Priority priority();`, với `Priority` là enum | `info.priority()` | Hằng enum như `Priority.HIGH` |
| `Nested nested();`, với `Nested` là annotation type | `info.nested()` | Đối tượng annotation `Nested` có phần tử riêng |

Giá trị phần tử không được là một object/service tùy ý, `List<String>`, `Map` hoặc `null`. Điều này giới hạn metadata vào các dạng Java có thể biểu diễn trong annotation.

### Mảng: đọc và xử lý có chủ đích

Đọc `info.labels()` trả về một mảng `String[]`. Có thể:

- Duyệt bằng vòng `for` hoặc stream nếu cần xử lý từng nhãn.
- Dùng `Arrays.toString(info.labels())` khi muốn in dạng `[ticket, critical]`.
- Dùng `String.join("|", info.labels())` nếu muốn ghép thành một chuỗi như ví dụ.

Đối với mảng chứa annotation lồng nhau, cần lấy từng đối tượng annotation rồi tiếp tục gọi phương thức phần tử của loại annotation lồng nhau. Không thể ép mảng annotation thành `String[]` nếu kiểu phần tử không phải `String`.

Không nên chỉnh sửa một mảng trả về và kỳ vọng metadata gốc thay đổi. Giá trị annotation được xác định từ metadata, không phải cấu hình mutable để ứng dụng thay đổi qua lời gọi getter.

### `Class<?>` không phải một instance của handler

Khi `info.handler()` trả về `String.class`, đó là **metadata biểu diễn loại class**, không phải một đối tượng `String` được tạo tự động. Nếu một framework muốn sử dụng class ấy để tạo đối tượng, nó phải có logic và điều kiện khởi tạo riêng; annotation không tự làm việc đó.

## 7. Đọc phần tử bằng Reflection động

Các ví dụ trước biết trước loại `OperationInfo`, nên gọi `info.value()`, `info.retries()` là đơn giản và an toàn về kiểu. Nếu đang viết công cụ kiểm tra annotation **chưa biết tên phần tử lúc biên dịch**, ta có thể khám phá các phương thức của chính annotation type:

```java
// Minh họa ngắn; giả sử đã có biến OperationInfo info != null.
// Đoạn này dùng java.lang.reflect.Method và cần xử lý ngoại lệ Reflection.
Class<? extends java.lang.annotation.Annotation> annotationType =
        info.annotationType();

for (Method element : annotationType.getDeclaredMethods()) {
    String name = element.getName();
    Object actualValue = element.invoke(info);
    Object defaultValue = element.getDefaultValue();

    // Một công cụ có thể lưu name, actualValue, defaultValue
    // hoặc phân tích theo kiểu của từng phần tử.
}
```

- `info.annotationType()` trả về đối tượng `Class` của loại annotation thực tế.
- `getDeclaredMethods()` trả về các phương thức **được khai báo trong loại annotation**, tức các phần tử ở ví dụ đơn giản này. **Thứ tự mảng không được đảm bảo**, nên cần sắp xếp theo tên nếu muốn xuất kết quả ổn định.
- `element.invoke(info)` gọi **phương thức phần tử** trên đối tượng annotation tại runtime và trả về `Object`. Giá trị nguyên thủy như `int` được boxing thành `Integer`.
- `element.getDefaultValue()` đọc giá trị mặc định ở **khai báo loại annotation**, không phải giá trị tại vị trí sử dụng; phần tử không có `default` thì kết quả là `null`.

Khác với gọi typed API như `info.retries()`, gọi `Method.invoke(...)` có ngoại lệ Reflection cần xử lý, có thể cần kiểm soát quyền truy cập ở các trường hợp tổng quát, và mất an toàn kiểu trực tiếp khi kết quả trả về dưới dạng `Object`. **Khi đã biết loại annotation, ưu tiên phương thức phần tử có kiểu tĩnh**; chỉ dùng cơ chế động khi thực sự xây tool/framework tổng quát.

### Không nhầm phần tử với các phương thức của `java.lang.annotation.Annotation`

Mọi đối tượng annotation đều có một số API chung như `annotationType()`, `equals(...)`, `hashCode()` và `toString()`. Đây không phải các phần tử tùy chỉnh `value()`, `retries()` của riêng `OperationInfo`.

Đặc biệt, `info.toString()` có thể hiển thị annotation dạng văn bản, nhưng không nên viết parser dựa trên chuỗi ấy để lấy metadata. Hãy đọc trực tiếp từng phần tử hoặc dùng Reflection phù hợp.

## 8. Một số lỗi thường gặp và cách sửa

**Lỗi 1: Gọi `method.value()` trên đối tượng `Method` nghiệp vụ.** `Method` đại diện cho một khai báo method, không có `value()` của `OperationInfo`. Cần lấy `OperationInfo info = method.getAnnotation(OperationInfo.class)` trước, rồi mới gọi `info.value()`.

**Lỗi 2: Không kiểm tra `null`.** Không phải mọi phương thức đều được gắn annotation; hãy xử lý trường hợp không có metadata trước khi truy xuất phần tử.

**Lỗi 3: Thiếu `@Retention(RUNTIME)`.** Annotation vẫn có thể biên dịch với retention mặc định `CLASS` nhưng Reflection thông thường không thấy nó trên thành phần đích.

**Lỗi 4: Đọc nhầm vị trí.** Annotation được gắn trên phương thức thì hỏi từ `Method`; nếu được gắn trên class thì hỏi từ `Class`; nếu được gắn trên kiểu sử dụng (`TYPE_USE`) thì các API như `getAnnotatedReturnType()` có thể mới phù hợp.

**Lỗi 5: Cho rằng `default` nghĩa là getter có thân phương thức.** `int retries() default 0;` là giá trị mặc định của annotation element, không phải default method trong interface Java thông thường và không thực hiện logic retry.

**Lỗi 6: Tưởng `getDefaultValue()` trả giá trị đang gắn tại vị trí sử dụng.** Nó trả giá trị khai báo mặc định, kể cả khi nơi sử dụng đã override bằng giá trị khác. Muốn biết giá trị thực tế, gọi `info.retries()`.

**Lỗi 7: Gọi `getValue()` thay vì `value()`.** Phần tử không tuân quy tắc getter JavaBeans trừ khi người thiết kế đặt đúng tên như vậy (và đặt tên hợp lệ). Với `String value();`, phương thức cần gọi là `value()`.

**Lỗi 8: Coi annotation là logic nghiệp vụ.** `@OperationInfo(retries = 2)` chỉ là metadata. Muốn thực hiện retry phải có consumer sử dụng `retries()` để tổ chức hành vi và xử lý lỗi.

**Lỗi 9: Dựa vào thứ tự `getDeclaredMethods()`.** Thứ tự các phần tử do Reflection liệt kê không phải thứ tự nguồn được bảo đảm; công cụ cần output ổn định phải sắp xếp.

**Lỗi 10: Giả định mọi giá trị phần tử đều luôn đọc thành công trong mọi môi trường.** Ở trường hợp nhị phân không tương thích hoặc loại enum/class được tham chiếu không còn phù hợp, runtime có thể phát sinh lỗi như `IncompleteAnnotationException`, `EnumConstantNotPresentException` hoặc `TypeNotPresentException`. Với hệ thống thực tế có thay đổi phiên bản thư viện, cần quản lý tương thích và lỗi đọc metadata; ví dụ chạy độc lập phía trên không gặp các tình huống này.

## 9. Bài tập kiểm tra kiến thức

**Bài 1.** Cho `@interface Rule { String code(); int priority() default 1; }` và `@Rule(code = "A")` trên một method. Sau khi lấy đối tượng `Rule rule` bằng Reflection, gọi gì để đọc mã và mức ưu tiên?

**Đáp án:** `rule.code()` cho `"A"` và `rule.priority()` cho `1`. Cả hai đều là phương thức phần tử không tham số.

**Bài 2.** Khác nhau giữa `method.getAnnotation(Rule.class)` và `rule.code()` là gì?

**Đáp án:** Lời gọi đầu lấy **đối tượng annotation** gắn trên method; lời gọi sau đọc **một phần tử metadata** từ đối tượng ấy.

**Bài 3.** Trong ví dụ chạy được, vì sao `lookup` có `retries=0` dù chỉ gắn `@OperationInfo("LOOKUP")`?

**Đáp án:** `retries()` có `default 0` trong khai báo loại annotation. Khi nơi sử dụng không cung cấp `retries`, lời gọi phần tử nhận giá trị mặc định.

**Bài 4.** `OperationInfo.class.getDeclaredMethod("retries").getDefaultValue()` cho kết quả gì nếu `issueTicket` đã đặt `retries = 2`?

**Đáp án:** Vẫn trả về `0`, vì đó là **default ở khai báo phần tử**. Muốn đọc `2` của vị trí `issueTicket`, cần lấy annotation của chính method ấy rồi gọi `info.retries()`.

**Bài 5.** Một phương thức không gắn `@OperationInfo`, kết quả `method.getAnnotation(OperationInfo.class)` là gì?

**Đáp án:** `null`; chương trình phải kiểm tra trước khi gọi `value()` hay `labels()`.

**Bài 6.** Giá trị `handler = String.class` tạo sẵn một instance `String` không?

**Đáp án:** Không. Nó biểu diễn **loại class** dưới dạng metadata. `info.handler()` trả về `Class<?>`, không phải đối tượng nghiệp vụ.

**Bài 7.** Nếu một công cụ cần in tên mọi phần tử annotation mà chưa biết chúng trước khi biên dịch, nên dùng API nào?

**Đáp án:** `info.annotationType().getDeclaredMethods()` để liệt kê, đọc `Method.getName()` và có thể dùng `Method.invoke(info)` để lấy giá trị. Cần xử lý ngoại lệ và sắp xếp nếu cần thứ tự cố định.

**Bài 8.** Tại sao chỉ đọc `info.toString()` rồi tách chuỗi không phải cách nên dùng để lấy giá trị?

**Đáp án:** Cách đó làm mất thông tin kiểu trực tiếp, có thể lỗi với mảng, annotation lồng nhau, ký tự đặc biệt và khác biệt cách trình bày; Java đã có phương thức phần tử có kiểu rõ ràng.

## 10. Tóm tắt quy trình tư duy

Khi cần đọc annotation lúc chạy, hãy xác định **nó gắn vào loại thành phần nào**, kiểm tra retention `RUNTIME`, lấy đúng đối tượng Reflection (`Class`, `Method`, `Field`...), lấy annotation thông qua `getAnnotation(...)` hoặc `getDeclaredAnnotation(...)`, kiểm tra `null`, sau đó gọi **các phương thức phần tử của annotation type** như `info.value()`, `info.retries()`, `info.labels()`.

Kết quả là **giá trị metadata** với kiểu được khai báo, đã áp dụng default nếu vị trí sử dụng không gán tường minh. Nếu muốn từ giá trị ấy sinh ra logging, retry, mapping hoặc một chính sách nghiệp vụ, phải viết và kích hoạt **bên xử lý** riêng; việc đọc phần tử không tự tạo hành vi.
