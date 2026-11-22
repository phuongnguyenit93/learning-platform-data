# Chọn phương thức nạp chồng và tránh khớp ngoài ý muốn bằng pointcut trong AOP

**Nạp chồng phương thức (method overloading)** cho phép nhiều phương thức mang cùng tên nhưng khác danh sách tham số. Đây là cơ chế phổ biến trong Java để cung cấp nhiều cách gọi một chức năng. Tuy nhiên, đối với lập trình hướng khía cạnh (Aspect-Oriented Programming, **AOP**), việc lựa chọn pointcut chỉ bằng **tên phương thức** dễ vô tình can thiệp vào nhiều phương thức nạp chồng vốn có mục đích, dữ liệu, điều kiện và tác dụng phụ khác nhau.

Ví dụ, lớp xử lý thanh toán có cả `pay(String orderId)` và `pay(String orderId, boolean retry)`. Nếu một khía cạnh kiểm toán được yêu cầu áp dụng **chỉ với thao tác một tham số**, pointcut kiểu “mọi phương thức có tên `pay`” quá rộng: nó có thể khớp cả phiên bản hai tham số. Một chính sách thử lại, giới hạn tần suất, bảo mật hoặc chuyển đổi kết quả được áp nhầm còn có thể làm sai hợp đồng nghiệp vụ.

Bài này trình bày cách **chọn đúng overload theo chữ ký**, nhận diện những tình huống khó như `null`, kiểu nguyên thủy, varargs, generics, kế thừa, phương thức cầu nối và khác biệt giữa **điểm gọi** với **điểm thực thi**. Cú pháp pointcut minh họa bằng một mô hình AOP có điều kiện chọn phương thức; các đặc điểm không thuộc Java chuẩn sẽ được ghi rõ. Ví dụ Java 17 độc lập giúp kiểm tra hành vi thực tế.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích thế nào là overload trong Java và phân biệt với override.
2. Xác định tập phương thức mà một pointcut dự kiến chọn, dựa trên **tên + số lượng + thứ tự + kiểu tham số**, thay vì chỉ nhìn tên.
3. Phân biệt **chữ ký khai báo của phương thức** với **kiểu thực của giá trị truyền vào**, nhất là khi đối số là `null` hoặc một đối tượng đa hình.
4. Hiểu lý do điểm **method call** và **method execution** có thể đòi hỏi điều kiện khác nhau trong mô hình AOP.
5. Nhận diện rủi ro khi dùng wildcard, varargs, generic erasure, bridge method, method inheritance hoặc proxy.
6. Viết bộ lọc chữ ký tường minh và kiểm tra cả những phương thức **phải khớp** lẫn **không được khớp**.
7. Giữ nguyên kết quả, ngoại lệ và tác dụng phụ của các overload khi advice chỉ có mục đích quan sát.

## 2. Hiểu đúng nạp chồng trong Java

Xét một bộ chuyển đổi thông tin:

```java
class Formatter {
    String format(String text) { return "text=" + text; }
    String format(Object value) { return "object=" + value; }
    String format(String text, int times) { return "batch=" + text + ":" + times; }
}
```

Đây là **đoạn minh họa**, chưa phải chương trình độc lập. Ba phương thức có cùng tên `format` nhưng khác **danh sách tham số**:

| Chữ ký minh họa | Số tham số | Kiểu theo thứ tự |
| --- | ---: | --- |
| `format(String)` | 1 | `String` |
| `format(Object)` | 1 | `Object` |
| `format(String, int)` | 2 | `String`, `int` |

Trong Java, để xác định overload cần quan tâm đến **kiểu và thứ tự các tham số**. Tên tham số không phân biệt overload. Chỉ đổi **kiểu trả về** cũng không tạo được một overload hợp lệ khi tên và danh sách tham số trùng nhau.

Ví dụ sau không hợp lệ nếu hai khai báo nằm trong cùng một lớp:

```java
int count(String item) { return 1; }
long count(String item) { return 1L; } // Lỗi biên dịch: trùng chữ ký.
```

Cả hai cùng có `count(String)`. Kiểu trả về quan trọng khi kiểm tra hợp đồng/cách gắn advice, nhưng **không phải khóa phân biệt overload** của hai khai báo này.

### 2.1. Nạp chồng (overload) và ghi đè (override) khác nhau

- **Overload:** cùng tên, danh sách tham số khác; Java lựa chọn phiên bản thích hợp chủ yếu ở **thời điểm biên dịch** theo kiểu biểu thức và các quy tắc giải quyết overload.
- **Override:** lớp con cung cấp hiện thực cho phương thức có quan hệ ghi đè với phương thức lớp cha/giao diện; đối với phương thức instance có khả năng dispatch động, **hiện thực được chạy** được quyết định tại thời gian chạy theo đối tượng nhận.

Ví dụ:

```java
class Parent {
    String use(Object value) { return "parent-object"; }
    String use(String value) { return "parent-string"; }
}
class Child extends Parent {
    @Override
    String use(Object value) { return "child-object"; }
}
```

Với `Parent item = new Child()`, lời gọi `item.use((Object) "x")` chọn chữ ký `use(Object)` rồi thực thi phiên bản ghi đè ở `Child`. Còn `item.use("x")` chọn `use(String)` và sử dụng hiện thực được kế thừa từ `Parent`. Nếu dùng pointcut, phải hỏi đang chọn **chữ ký nào**, **loại join point nào** và **mã nào thực sự chạy**.

## 3. Vì sao pointcut theo tên dễ khớp sai?

Giả sử một dịch vụ có:

```java
void submit(String orderId);
void submit(String orderId, int copies);
void submit(Object payload);
```

Một pointcut với ý tưởng “mọi phương thức tên `submit`” sẽ không phân biệt ba hành vi:

- `submit(String)` có thể là đường xử lý một đơn hàng đã được xác minh;
- `submit(String, int)` có thể là thao tác tạo nhiều bản hoặc thực hiện theo lô;
- `submit(Object)` có thể là cổng tiếp nhận chung và cần kiểm tra kiểu đầu vào khác.

Áp **ghi log kỹ thuật** nhầm có thể dẫn tới log dư. Áp **kiểm toán bắt buộc**, **retry**, **kiểm soát quyền** hoặc **giới hạn tần suất** nhầm có thể nghiêm trọng hơn: bỏ sót sự kiện, nhân đôi tác dụng phụ hoặc chặn thao tác hợp lệ.

Vấn đề không nằm ở tính năng overload của Java; nó nằm ở việc **pointcut biểu đạt thiếu điều kiện lựa chọn** so với yêu cầu chính sách.

### 3.1. Ba tập cần tách biệt

Khi đánh giá một pointcut, hãy phân biệt ba tập:

1. **Tập mong muốn:** những thao tác nghiệp vụ mà chính sách cần áp dụng theo thiết kế.
2. **Tập khớp theo biểu thức:** những join point thực tế được cú pháp pointcut lựa chọn trong mô hình AOP.
3. **Tập có hiệu lực khi chạy:** những join point vừa khớp vừa nằm trong phạm vi được weaving hoặc thực sự đi qua proxy/interceptor.

Một biểu thức đúng về chữ ký nhưng được áp ở đường gọi không qua proxy vẫn không chạy advice. Ngược lại, một cơ chế weaving hoạt động tốt vẫn có thể áp nhầm phương thức khi pointcut dùng mẫu tham số quá rộng. Cần kiểm chứng **cả bộ lọc lẫn cơ chế thực thi**.

## 4. Cách chọn overload bằng chữ ký chính xác

Một điều kiện cơ bản có thể gồm:

```text
loại join point
    AND phạm vi kiểu/lớp/gói
    AND tên phương thức
    AND số lượng tham số
    AND kiểu từng tham số theo đúng thứ tự
    AND điều kiện bổ sung (nếu cần)
```

Với yêu cầu “chỉ đo việc xử lý một mã đơn hàng kiểu String”, điều kiện lý tưởng cần chỉ ra `submit(String)`. Đừng tự mở rộng sang `submit(Object)` dù tại thời gian chạy đối số có thể cũng là một `String`.

### 4.1. Ví dụ cú pháp pointcut dành riêng cho AspectJ

Trong một mô hình AOP có bộ chỉ định `execution` như AspectJ, hai biểu thức minh họa sau có ý nghĩa khác nhau:

```text
execution(* example.orders.OrderService.submit(java.lang.String))
execution(* example.orders.OrderService.submit(..))
```

- Biểu thức **đầu** chọn điểm thực thi có **một tham số được khai báo là `String`** tại mẫu kiểu và tên đã chỉ định.
- Biểu thức **sau** dùng `..` để chấp nhận **danh sách tham số bất kỳ**, nên có thể chọn cả các overload `submit()`, `submit(String)`, `submit(Object)`, `submit(String, int)` nếu các điểm thực thi đó thuộc tập kiểu khớp.

Ký hiệu ở trên **không phải Java thuần**, không chạy bằng `javac`, và không phải lời hứa công nghệ AOP nào cũng dùng cú pháp đó. Khi áp dụng công cụ cụ thể, cần kiểm chứng cách nó hiểu kiểu, phạm vi, wildcard và các phương thức kế thừa.

Điều kiện khớp chính xác hai tham số có thể biểu đạt:

```text
execution(* example.orders.OrderService.submit(java.lang.String, int))
```

Đổi thứ tự tham số hoặc đổi `int` thành `java.lang.Integer` sẽ tạo **chữ ký khác**. Sự giống nhau về ý nghĩa nghiệp vụ không làm chúng tương đương khi lọc theo kiểu khai báo.

### 4.2. Chọn đúng lớp hoặc vai trò

Một biểu thức tên/phương thức có thể khớp cùng tên ở các lớp khác nhau. Vì vậy ngoài danh sách tham số, thường cần xác định **lớp khai báo**, **kiểu đích**, **giao diện nghiệp vụ**, **package** hoặc **vai trò thành phần**.

Ví dụ, hai lớp `OrderService` và `ReportService` đều có `submit(String)`, nhưng chỉ `OrderService` cần kiểm toán đơn hàng. Biểu thức dùng wildcard cho mọi kiểu có phương thức `submit(String)` sẽ quá rộng.

Cần phân biệt giữa một tên kiểu **được viết trong biểu thức** và khả năng khớp của công nghệ đối với kiểu kế thừa, kiểu runtime hoặc proxy. Không nên suy từ văn bản biểu thức rằng mọi lời gọi trên đối tượng đúng tên đều được chặn.

### 4.3. Chọn theo hợp đồng thay vì tình cờ trùng tên

Nếu nhiều lớp cùng triển khai một giao diện `AuditedCommand` với `execute(Command)`, việc giới hạn theo **vai trò của giao diện và chữ ký** có thể rõ hơn chọn tên `execute` trên toàn hệ thống.

Tuy nhiên, một đối tượng có thể đồng thời triển khai nhiều giao diện hoặc sở hữu nhiều overload `execute`. Khi dùng kiểu/giao diện làm điều kiện, vẫn cần quyết định **điểm gọi hay điểm thực thi**, **chữ ký nào** và **đường nào được cơ chế AOP hỗ trợ**.

## 5. Sự lựa chọn overload của trình biên dịch không phụ thuộc hoàn toàn kiểu runtime

Điểm dễ nhầm là một biến mang đối tượng `String` **không đồng nghĩa** mọi lời gọi trên biến đó chọn overload `String`.

Xét:

```java
void accept(String value);
void accept(Object value);
```

Các lời gọi sau biểu đạt những lựa chọn khác nhau:

```java
accept("A");             // Chọn accept(String).
accept((Object) "A");    // Chọn accept(Object).
Object value = "A";
accept(value);           // Chọn accept(Object).
accept(null);            // Chọn accept(String): cụ thể hơn Object.
```

Đây là **mã minh họa** bên trong một ngữ cảnh đã khai báo các phương thức. Lựa chọn overload trong Java dựa trên **kiểu của biểu thức ở thời điểm biên dịch**, độ áp dụng của các ứng viên và quy tắc chọn phương thức cụ thể nhất. Sau khi chữ ký được chọn, dispatch động có thể chọn **hiện thực override** thích hợp ở thời gian chạy.

### 5.1. `null` có thể chọn overload hoặc làm lời gọi mơ hồ

Với `accept(String)` và `accept(Object)`, `accept(null)` hợp lệ và chọn `String` vì `String` cụ thể hơn `Object`.

Nhưng nếu có hai overload không có quan hệ cụ thể hơn:

```java
void check(String value);
void check(Integer value);

// check(null);  // Lỗi biên dịch: cả check(String) và check(Integer) đều phù hợp.
check((String) null);    // Chọn check(String).
check((Integer) null);   // Chọn check(Integer).
```

Các khai báo và lời gọi là **minh họa**, phải đặt trong ngữ cảnh Java phù hợp. Việc ép kiểu rõ ràng giải quyết mơ hồ tại **điểm gọi**. Pointcut chọn chữ ký `check(String)` không cần suy đoán giá trị `null` là kiểu nào: nó lựa chọn theo **phương thức khai báo**.

### 5.2. `int`, `Integer`, widening và boxing

Những chữ ký sau là khác nhau:

```java
void record(int code);
void record(Integer code);
void record(long code);
```

Java có những quy tắc áp dụng overload theo chuyển đổi kiểu, mở rộng kiểu nguyên thủy và boxing/unboxing. Không được đoán chỉ từ chữ `record(1)` rằng mọi overload liên quan số nguyên đều được gọi. Trong trường hợp có đúng ba khai báo trên, `record(1)` chọn `record(int)` vì khớp trực tiếp.

Còn `Integer boxed = 1; record(boxed)` chọn `record(Integer)` trong ngữ cảnh này. Nếu một pointcut chỉ định `int`, nó **không đồng nghĩa** chọn cả phiên bản `Integer`.

Phân tích **overload được chọn** phải dựa trên quy tắc ngôn ngữ và tập ứng viên cụ thể. Phân tích **join point được chọn** tiếp theo dựa trên cú pháp pointcut và loại điểm can thiệp.

### 5.3. Thứ tự tham số là một phần quan trọng của mẫu

`send(String destination, int priority)` và `send(int priority, String destination)` là hai overload khác nhau. Mẫu chỉ kiểm tra “có String và int” nhưng bỏ thứ tự sẽ không biểu đạt đầy đủ chữ ký.

Tên biến `destination` hoặc `priority` không tham gia quyết định overload; phải kiểm tra **kiểu ở đúng vị trí**.

## 6. Ví dụ Java 17 chạy được: chỉ ghi log cho `submit(String)`

Để quan sát hậu quả của một pointcut rộng/hẹp mà không phải cài thư viện ngoài, ví dụ này dùng **JDK dynamic proxy** làm bộ chặn lời gọi qua giao diện. Bộ lọc ở đây dùng reflection để chọn **đúng chữ ký phương thức**; nó minh họa tư duy pointcut, nhưng không phải bộ weaving chặn mọi điểm thực thi trong JVM.

Tạo tệp `OverloadPointcutDemo.java`:

```java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;
import java.util.Arrays;

public class OverloadPointcutDemo {
    interface SubmissionPort {
        String submit(String code);
        String submit(Object payload);
        String submit(String code, int copies);
    }

    static final class SubmissionService implements SubmissionPort {
        @Override
        public String submit(String code) {
            return "text:" + code;
        }

        @Override
        public String submit(Object payload) {
            return "object:" + payload;
        }

        @Override
        public String submit(String code, int copies) {
            return "batch:" + code + ":" + copies;
        }
    }

    static boolean selected(Method method) {
        return method.getName().equals("submit")
                && Arrays.equals(
                        method.getParameterTypes(),
                        new Class<?>[] { String.class });
    }

    static SubmissionPort observe(SubmissionPort target) {
        return (SubmissionPort) Proxy.newProxyInstance(
                SubmissionPort.class.getClassLoader(),
                new Class<?>[] { SubmissionPort.class },
                (proxy, method, args) -> {
                    if (selected(method)) {
                        System.out.println("[AUDIT] submit(String)");
                    }

                    try {
                        return method.invoke(target, args);
                    } catch (InvocationTargetException ex) {
                        throw ex.getCause();
                    }
                });
    }

    public static void main(String[] args) {
        SubmissionPort port = observe(new SubmissionService());

        System.out.println(port.submit("A"));
        System.out.println(port.submit((Object) "A"));
        System.out.println(port.submit("B", 2));
        System.out.println(port.submit(null));
        System.out.println(new SubmissionService().submit("C"));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac -encoding UTF-8 OverloadPointcutDemo.java
java OverloadPointcutDemo
```

Đầu ra chính xác:

```text
[AUDIT] submit(String)
text:A
object:A
batch:B:2
[AUDIT] submit(String)
text:null
text:C
```

**Phân tích các dòng:**

1. `port.submit("A")` chọn `submit(String)`: bộ lọc khớp, in `[AUDIT]`, sau đó chương trình trả `text:A`.
2. `port.submit((Object) "A")` chọn `submit(Object)` dù đối tượng thực là `String`: bộ lọc theo **tham số khai báo** không khớp, chỉ in `object:A`.
3. `port.submit("B", 2)` chọn overload hai tham số; `Arrays.equals` trả `false` vì danh sách tham số không đúng một `String`.
4. `port.submit(null)` chọn `submit(String)` vì `String` cụ thể hơn `Object`; bộ lọc khớp. Phép nối chuỗi tạo `text:null`.
5. `new SubmissionService().submit("C")` gọi **trực tiếp** đối tượng đích, không đi qua proxy nên không in `[AUDIT]`, dù chữ ký là `submit(String)`.

**Điểm đáng chú ý:** `method.getParameterTypes()` trả các **kiểu tham số được khai báo trong chữ ký**, không phải kiểu của giá trị trong mảng `args`. Đó là lý do chính sách quan sát một overload không nên quyết định bằng `args[0] instanceof String`. Với `submit(Object)` và đối tượng `"A"`, kiểm tra theo giá trị runtime sẽ sai mục tiêu.

Cách kiểm tra bằng `Arrays.equals` thích hợp cho ví dụ reflection này. Một ngôn ngữ pointcut thật có cú pháp và quy tắc khớp riêng; phải hiểu **đặc tả của nó**, không coi đoạn mã Java này là trình phân tích pointcut phổ quát.

### 6.1. Điều gì xảy ra nếu chỉ kiểm tra tên?

Nếu thay `selected` bằng:

```java
return method.getName().equals("submit");
```

thì cả ba overload sẽ được chọn khi đi qua proxy. Trong ví dụ này có thêm hai dòng `[AUDIT]` tương ứng với `submit(Object)` và `submit(String, int)`. Tuy nhiên, lời gọi trực tiếp `new SubmissionService().submit("C")` vẫn **không đi qua proxy**. Hai vấn đề độc lập là:

- **Pointcut quá rộng:** khớp nhầm overload.
- **Đường can thiệp không bao phủ:** lời gọi bỏ qua proxy.

Cần giải quyết từng vấn đề đúng nguyên nhân; việc làm pointcut hẹp không tự khắc phục đường bypass, và việc đưa mọi người gọi qua proxy không tự làm pointcut chính xác.

### 6.2. Bảo toàn hợp đồng khi advice chỉ quan sát

Ví dụ chỉ in một dòng trước khi chuyển lời gọi và chuyển tiếp kết quả. Khi reflection bọc lỗi đích trong `InvocationTargetException`, handler ném lại `getCause()` để giữ ngoại lệ gốc.

Trong hệ thống thật, advice theo dõi nên tránh:

- Gọi `method.invoke` nhiều lần khi chưa thiết kế retry an toàn.
- Thay kết quả trả về giữa các overload có hợp đồng khác nhau.
- Chuyển đổi ngoại lệ thành thành công hoặc nuốt lỗi.
- Ghi toàn bộ đối số nhạy cảm vào log.
- Áp nhầm chính sách thử lại lên overload có tác dụng phụ khác với overload định áp dụng.

## 7. Nhiều kiểu khớp: kiểu khai báo, giá trị runtime và bối cảnh

“Phương thức nhận String” có thể được hiểu theo vài cách không tương đương:

| Cách hiểu | Điều kiện muốn kiểm tra | Trường hợp `submit(Object)` nhận `"A"` |
| --- | --- | --- |
| **Chữ ký khai báo** | Tham số đầu khai báo `String` | Không khớp |
| **Đối số runtime** | Giá trị được truyền thực tế là một `String` | Có thể khớp theo điều kiện runtime |
| **Kiểu đối tượng đích** | Đối tượng nhận thuộc loại hoặc vai trò nhất định | Phụ thuộc đối tượng, không phụ thuộc riêng overload |
| **Vị trí từ vựng** | Điểm gọi/phương thức nằm trong phần mã đã chỉ định | Phụ thuộc nơi chứa join point |
| **Tên phương thức** | Tên là `submit` | Khớp nếu không thêm điều kiện tham số |

Nhiều mô hình AOP phân biệt điều kiện dựa trên **chữ ký tĩnh** với điều kiện theo **đối số runtime**. Trong một ngôn ngữ pointcut cụ thể, cú pháp lấy/so khớp đối số có thể khác cú pháp chọn chữ ký phương thức. Nếu mục tiêu của bài là “chọn overload `submit(String)`”, hãy dựa vào chữ ký; dùng kiểu giá trị runtime làm tiêu chí sẽ chọn nhầm `submit(Object)` trong những lần người gọi đưa vào chuỗi.

### 7.1. Kiểu tham số khai báo và kiểu trả về

Không phải mọi mẫu phương thức đều chỉ quan tâm danh sách tham số. Một pointcut có thể thêm điều kiện kiểu trả về, phạm vi truy cập, annotation, kiểu khai báo và nhiều thuộc tính khác tùy công cụ.

Cần nhớ hai câu khác nhau:

- **Java phân biệt các overload hợp lệ bằng danh sách tham số**, không thể chỉ đổi kiểu trả về để khai báo thêm overload.
- **Một biểu thức pointcut có thể dùng kiểu trả về như một điều kiện lọc bổ sung** nếu mô hình AOP hỗ trợ.

Không nên vì kiểu trả về không phân biệt overload mà kết luận nó vô nghĩa đối với mọi pointcut.

### 7.2. Tham số được khai báo ở giao diện hay lớp hiện thực

Trong ví dụ proxy, đối tượng `Method` được handler nhận thường mô tả phương thức giao diện được gọi. Khi làm việc với weaving tại điểm thực thi lớp đích, join point có thể gắn với phương thức khai báo hoặc hiện thực ở một lớp khác.

Nếu công cụ chọn theo `declaring type`, `target type`, kiểu cha hoặc kiểu của đối tượng runtime, tập điểm sẽ khác nhau khi có lớp con, giao diện, nhiều cấp kế thừa hoặc proxy. Cần thử các lớp hiện thực thực tế và ghi rõ **đang khớp theo kiểu nào**.

## 8. Method call và method execution: chọn overload ở điểm nào?

Giả sử:

```java
class Receiver {
    void process(String text) { }
    void process(Object value) { }
}
```

Một đoạn mã phía người gọi thực hiện:

```java
Receiver receiver = new Receiver();
Object input = "A";
receiver.process(input); // Chọn chữ ký process(Object).
```

Đây là **đoạn minh họa**.

Trong một mô hình AOP hỗ trợ cả hai:

- **Method call join point:** điểm lời gọi ở phía mã của người gọi. Có thể lọc theo nơi phát sinh lời gọi, chữ ký được chọn và các điều kiện khác.
- **Method execution join point:** điểm thực thi phương thức ở phía đích. Có thể lọc theo kiểu/thành viên được thực thi và phạm vi mã đích.

Trong ví dụ, lời gọi mang chữ ký `process(Object)`, bất kể `input` đang giữ đối tượng `String`. Nếu lớp con override `process(Object)`, dispatch động có thể chuyển tới hiện thực lớp con. Điều kiện pointcut tại phía call và execution vì thế **không nhất thiết tương đương**, nhất là khi xét cả nơi gọi, nơi khai báo, kế thừa và nhiều lớp hiện thực.

Một cơ chế dựa trên proxy có thể chỉ nhìn thấy cuộc gọi qua đối tượng đại diện. Một cơ chế weaving trực tiếp vào mã lớp có thể hỗ trợ loại join point khác. Không suy ra mọi kiểu advice đều có thể được cài theo cùng một cách.

### 8.1. Tránh nhầm lời gọi nội bộ

Khi một phương thức của chính đối tượng gọi `this.process("A")`, compiler vẫn chọn overload dựa trên kiểu biểu thức. Nhưng với proxy bao quanh bên ngoài đối tượng, đường gọi nội bộ này thường **không quay lại proxy**; nó có thể bỏ qua advice dù chữ ký `process(String)` hoàn toàn khớp.

Vấn đề ở đây là **phạm vi có hiệu lực**, không phải cách giải overload. Nếu cần can thiệp lời gọi nội bộ, phải chọn cơ chế có join point phù hợp hoặc đưa chính sách vào ranh giới rõ ràng mà mọi đường đều đi qua.

## 9. Varargs: một nguồn khớp quá rộng

Java cho phép tham số biến độ dài:

```java
void send(String... messages) { }
```

Ở mức khai báo JVM/reflection, varargs được biểu diễn qua **tham số mảng** (trường hợp này là `String[]`) kèm metadata varargs. Một lời gọi như `send("A", "B")` là cách gọi thuận tiện do compiler xử lý; nó không có nghĩa runtime có một overload hai tham số `String, String`.

Nếu có thêm `send(String)`, một lời gọi `send("A")` thông thường sẽ ưu tiên overload cố định phù hợp trong quá trình giải overload; còn `send("A", "B")` dùng varargs.

Đối với pointcut:

- **Chữ ký varargs** có dạng tham số mảng tại mức method descriptor.
- **Số đối số viết tại điểm gọi** có thể khác số tham số được khai báo của phương thức.
- Một wildcard cho danh sách tham số có thể chọn cả `send(String)` và `send(String...)` dù hai API có ý nghĩa khác nhau.

Nếu cần chính xác, phải tìm hiểu công cụ dùng ngữ nghĩa varargs ở cấp nguồn hay chữ ký bytecode, rồi kiểm thử cách biểu thức khớp phương thức tương ứng.

## 10. Generics, type erasure và bridge methods

Java thực hiện **xóa kiểu tổng quát (type erasure)** khi biên dịch phần lớn thông tin kiểu generic. Ví dụ:

```java
interface Handler<T> {
    T handle(T value);
}

class TextHandler implements Handler<String> {
    @Override
    public String handle(String value) {
        return value.trim();
    }
}
```

Đây là đoạn minh họa. Tại cấp bytecode, sự tương thích giữa phương thức generic của giao diện và phương thức chuyên biệt của lớp hiện thực có thể khiến compiler tạo **bridge method** tổng hợp để giữ ngữ nghĩa đa hình sau xóa kiểu.

Hệ quả với AOP:

1. Trong mã nguồn, bạn thấy `handle(String)`, nhưng reflection hoặc một bộ weaving ở bytecode có thể nhìn thấy **thêm phương thức tổng hợp/cầu nối** liên quan `handle(Object)`, tùy hiện thực và điểm đang quan sát.
2. Một pointcut chỉ lọc tên `handle` hoặc chọn quá rộng theo kiểu tham số có thể ghi nhận không đúng số lần nếu cơ chế chọn cả đường cầu nối và hiện thực.
3. Một số công cụ có xử lý đặc biệt cho bridge/synthetic methods; một số biểu lộ chúng như các điểm thực thi riêng. **Không có quy tắc chung rằng một lời gọi chắc chắn tạo hai lần advice.**

Khi dùng reflection để kiểm tra, `Method.isBridge()` và `Method.isSynthetic()` giúp nhận diện một số phương thức do compiler sinh. Nhưng quyết định bỏ chúng khỏi pointcut vẫn phải xét ngữ nghĩa cần theo dõi và khả năng của cơ chế đang dùng.

### 10.1. Không overload các kiểu generic chỉ khác tham số kiểu bị xóa giống nhau

Hai khai báo như:

```java
void inspect(java.util.List<String> values) { }
void inspect(java.util.List<Integer> values) { } // Không hợp lệ: cùng erasure.
```

không thể cùng xuất hiện như hai overload trong một lớp Java. Cả hai xóa kiểu thành danh sách tham số tương đương `List` ở cấp JVM. Một pointcut cũng không thể dựa vào một overload không tồn tại trong chương trình hợp lệ.

Nếu chương trình thực sự có các overload mang danh sách tham số bytecode khác nhau, phải chọn đúng chữ ký sau khi cân nhắc quá trình biên dịch và các phương thức do compiler tạo.

## 11. Kế thừa, ghi đè và nhiều kiểu điểm nhận

Một phương thức có thể được kế thừa không cần khai báo lại. Ví dụ lớp con kế thừa `process(String)` từ lớp cha, nhưng tự ghi đè `process(Object)`. Người đọc chỉ nhìn lớp con có thể bỏ sót overload được kế thừa.

Ngoài ra, nếu interface khai báo `submit(String)` và lớp hiện thực cung cấp cùng chữ ký, pointcut theo **phạm vi interface**, **kiểu lớp hiện thực** hay **vị trí từ vựng của mã** có thể khớp khác nhau tùy loại join point.

Khi đánh giá:

- Xác định tập phương thức mà Java coi là khả dụng trên **kiểu biên dịch của biến nhận**.
- Xác định chữ ký được chọn cho từng lời gọi.
- Xác định phương thức đích thực sự được dispatch.
- Xác định loại join point mà công nghệ hỗ trợ và vị trí đoạn mã được weaving.
- Xác nhận lời gọi đi qua cơ chế AOP cần thiết.

Một ứng dụng có nhiều lớp con, lớp trang trí hoặc proxy càng cần kiểm tra những đường này. **Tên phương thức + tên lớp hiển thị** không đủ chứng minh advice khớp đúng overload.

## 12. Overload và annotation

Một số hệ thống tổ chức chính sách theo annotation đặt trên phương thức. Đây là cách mô tả ý định áp một chính sách:

```java
import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
@interface Observed { }

class TransferPort {
    @Observed
    void transfer(String account) { }

    void transfer(String account, int retries) { }
}
```

Đây là đoạn **minh họa**, không phải ví dụ đầy đủ về weaving. Annotation `@Observed` chỉ được đặt trên `transfer(String)`; overload hai tham số không tự mang annotation đó.

Nếu một pointcut chọn theo annotation phương thức, cần kiểm tra **annotation có được lấy từ phương thức khai báo trên interface, từ lớp hiện thực hay theo một quy tắc tìm kiếm khác**. Không thể mặc định annotation ở một overload, interface hoặc lớp cha tự áp sang overload khác.

Annotation có thể khiến phạm vi dễ đọc hơn, nhưng vẫn phải kiểm tra cơ chế thực thi và các đường gọi bỏ qua proxy hoặc chưa được weaving.

## 13. Dựng một pointcut an toàn theo từng bước

### Bước 1 — Viết yêu cầu ở mức nghiệp vụ

Ví dụ: “Ghi sự kiện kiểm toán khi thực thi `approve(String id)` của cổng phê duyệt, không ghi `approve(String id, boolean force)` và không ghi những phương thức cùng tên trong báo cáo.”

Đây là yêu cầu cụ thể hơn “ghi mọi lời gọi `approve`”.

### Bước 2 — Liệt kê các overload có liên quan

Bảng mẫu:

| Phương thức | Có áp dụng? | Lý do |
| --- | --- | --- |
| `ApprovalPort.approve(String)` | Có | Đúng thao tác cốt lõi cần kiểm toán |
| `ApprovalPort.approve(String, boolean)` | Không | Đường thao tác đặc biệt, chính sách khác |
| `ApprovalPort.approve(Object)` | Không | Cổng chung khác hợp đồng |
| `ReportPort.approve(String)` | Không | Trùng tên nhưng khác thành phần |
| `ApprovalPort.approve(Integer)` | Không | Khác kiểu khai báo |

Nếu yêu cầu thật sự là “mọi thao tác phê duyệt đều phải được kiểm toán”, danh sách **phải được mở rộng có chủ đích**, không thu hẹp tùy tiện để giảm log.

### Bước 3 — Chọn loại join point

Bạn cần quan sát **phương thức thực thi** hay **điểm gọi**? Nếu công nghệ chỉ chặn phương thức qua proxy, bạn có chấp nhận mọi người gọi phải dùng proxy không? Nếu muốn can thiệp ở call join point trong một package của người gọi, công cụ có hỗ trợ loại điểm đó không?

Đây là lựa chọn về cơ chế, không thể tự giải bằng wildcard.

### Bước 4 — Chọn bộ lọc hẹp

Kết hợp loại join point, phạm vi kiểu, tên, số và thứ tự kiểu tham số. Chỉ sử dụng wildcard ở những chiều được phép mở rộng. Nếu lọc theo annotation hoặc interface, vẫn cần xác minh overload và kiểu runtime.

### Bước 5 — Thêm loại trừ có lý do

Loại trừ mã của chính khía cạnh, các bộ giám sát nội bộ hoặc các thành phần phụ trợ không cần chính sách. Nhưng tránh dùng pointcut “mọi thứ” rồi loại trừ không ngừng; một điều kiện bao gồm nhỏ và rõ ràng thường dễ kiểm toán hơn.

### Bước 6 — Kiểm thử khớp và không khớp

Không chỉ thử trường hợp `approve("A")` có advice. Phải chứng minh `approve("A", true)`, `approve((Object) "A")`, phương thức trùng tên lớp khác và đường bypass **không được áp nhầm**, trừ khi yêu cầu thiết kế ghi khác.

### Bước 7 — Kiểm tra kết quả và tác dụng phụ

Một bộ lọc đúng vẫn có thể làm sai hành vi nếu advice chặn lời gọi, thay tham số hoặc thực thi tác vụ nhiều lần. Với chính sách chỉ quan sát, chuyển tiếp kết quả và lỗi gốc thường là lựa chọn phù hợp. Với chính sách bảo mật hoặc giao dịch, cần xác minh tất cả đường truy cập bắt buộc được bao phủ.

## 14. Những lỗi rất thường gặp

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Chỉ lọc tên phương thức | Mọi overload cùng tên có thể bị chọn | Lọc đủ danh sách kiểu tham số và phạm vi kiểu |
| Dùng wildcard `..` vô điều kiện | Khớp bất kỳ số và kiểu tham số trong mô hình có cú pháp đó | Chỉ dùng khi chủ ý bao gồm mọi overload |
| Dựa vào `args[0] instanceof String` để chọn `submit(String)` | `submit(Object)` vẫn có thể nhận đối tượng String | Chọn theo chữ ký khai báo |
| Coi `null` là một overload riêng | `null` không mang kiểu phương thức độc lập | Phân tích quy tắc compiler và ép kiểu rõ khi cần |
| Xem `int` và `Integer` là một chữ ký | Đây là hai kiểu khác nhau | Xác minh primitive/boxed và thứ tự tham số |
| Xem varargs là mọi số tham số của method descriptor | Varargs được biểu diễn dạng mảng | Kiểm tra chữ ký thực và cách công cụ xử lý varargs |
| Bỏ qua generic erasure và bridge methods | Bytecode có thể có phương thức tổng hợp | Kiểm tra phương thức thực và ngữ nghĩa công cụ |
| Nhầm overload với override | Chọn chữ ký và chọn hiện thực là hai giai đoạn | Kiểm tra kiểu biểu thức người gọi, kiểu runtime và join point |
| Chỉ test overload được chọn | Không phát hiện trường hợp bị khớp ngoài ý muốn | Viết ca âm cho các overload còn lại |
| Tin rằng khớp pointcut là advice chắc chắn chạy | Proxy/bytecode weaving có phạm vi riêng | Kiểm tra lời gọi thực tế và artifact đã kết hợp |
| Dùng chính sách retry chung cho mọi overload | Có thể thử lại thao tác có tác dụng phụ không an toàn | Phân loại hợp đồng và idempotency riêng |

## 15. Kiểm thử pointcut: ma trận khẳng định dương và âm

Một bộ test hữu ích phải kiểm tra **chính sách áp đúng nơi** và **không áp ngoài nơi**.

| Ca | Kỳ vọng nếu chỉ chọn `submit(String)` |
| --- | --- |
| `submit("A")` | Có advice |
| `submit((Object) "A")` | Không có advice |
| `submit("A", 2)` | Không có advice |
| `submit(null)` khi chỉ tồn tại overload `String` và `Object` | Có advice vì chọn `String` |
| `submit((Object) null)` | Không có advice |
| `ReportService.submit(String)` ngoài phạm vi kiểu | Không có advice |
| Gọi thẳng đối tượng gốc khi cơ chế là proxy | Không có advice qua proxy, cần ghi nhận giới hạn |
| Lời gọi `this.submit("A")` từ bên trong đối tượng đích khi chỉ có proxy ngoài | Thường không đi qua proxy, cần kiểm tra |
| Lớp con override `submit(String)` | Kiểm tra ngữ nghĩa của join point và cơ chế triển khai |
| Điều kiện aspect động hoặc class được tải lại | Xác minh pointcut và đường can thiệp vẫn đúng |

Một số ca kiểm thử cũng cần kiểm chứng **giá trị trả về, ngoại lệ** và số lần thực thi tác vụ đích, bởi “có advice” không đủ chứng minh chính sách không gây tác dụng phụ.

### 15.1. Nếu xuất hiện log ở overload ngoài phạm vi

Chẩn đoán theo thứ tự:

1. Chụp chữ ký phương thức thực sự được gọi bằng cách kiểm tra tên, kiểu tham số và kiểu khai báo; không chỉ đọc loại dữ liệu runtime.
2. Kiểm tra wildcard trong pointcut: có phải đã chọn danh sách tham số tùy ý?
3. Kiểm tra điều kiện lọc theo `args`, kiểu đích hoặc annotation có mở rộng tập khớp hơn dự kiến?
4. Kiểm tra khác biệt giữa overload và override, kể cả phương thức kế thừa.
5. Kiểm tra có nhiều aspect hoặc hai lớp proxy cùng can thiệp không.
6. Kiểm tra bridge/synthetic methods và quá trình chuyển tiếp lời gọi nếu công nghệ liên quan.
7. Sửa lại quy tắc, sau đó kiểm thử **cả những phương thức không được chọn**.

### 15.2. Nếu thiếu log ở overload đúng chữ ký

Đừng lập tức thêm wildcard. Trước tiên hãy kiểm tra:

- Lời gọi có thực sự chọn chữ ký mong đợi ở thời điểm biên dịch?
- Loại join point được yêu cầu có được công nghệ hỗ trợ?
- Phương thức được gọi qua proxy hay trực tiếp đối tượng gốc?
- Lớp chứa điểm thực thi có nằm trong phạm vi weaving không?
- Phương thức có thuộc kiểu/gói/annotation mà bộ lọc thực sự dùng không?
- Có lời gọi nội bộ, đường phản chiếu hoặc lớp khác đang được sử dụng không?
- Advice trước đó có chặn chuỗi, đổi luồng thực thi hoặc ném lỗi không?

Việc nới rộng pointcut có thể che giấu nguyên nhân thiếu hiệu lực và tạo thêm các kết quả khớp ngoài ý muốn.

## 16. Tình huống nâng cao: khi thay đổi API làm pointcut đổi nghĩa

Giả sử lúc đầu có `save(String id)`. Một phiên bản sau bổ sung `save(String id, boolean overwrite)`. Nếu pointcut cũ là “mọi `save(..)`”, chính sách lập tức có thể áp thêm phương thức mới mà không ai chủ động sửa pointcut. Đây là **thay đổi phạm vi do phát triển API**, dù bản thân aspect không đổi.

Ngược lại, nếu pointcut chọn chính xác `save(String)`, phiên bản mới không tự được kiểm toán. Nếu tất cả hành vi ghi dữ liệu bắt buộc phải có kiểm toán, cần đánh giá lại yêu cầu, cập nhật chính sách có chủ đích và bổ sung kiểm thử.

Vì thế, khi thêm overload hãy hỏi:

- Overload mới có cùng hợp đồng về bảo mật, đo lường, kiểm toán, timeout và retry không?
- Nó có cùng ranh giới thành công/thất bại và khả năng thực thi lặp không?
- Pointcut hiện tại mở rộng tự động hay cần cập nhật? Sự mở rộng ấy có đúng chính sách không?
- Có ca kiểm thử nào bảo vệ danh sách những phương thức phải/không được can thiệp không?

Một **pointcut hẹp** giúp giảm khớp nhầm nhưng không tự bảo đảm đầy đủ chính sách khi hệ thống phát triển. Cần quản lý phạm vi AOP như một phần của hợp đồng API.

## 17. Bài tập vận dụng

### Bài 1 — Dự đoán overload Java

Cho:

```java
void print(String value);
void print(Object value);
```

Phân tích `print("x")`, `print((Object) "x")`, `print(null)` và `Object x = "x"; print(x)`. Phương thức nào được chọn?

**Đáp án:** Lần lượt `print(String)`, `print(Object)`, `print(String)`, `print(Object)`. Kiểu của biểu thức khi biên dịch quan trọng hơn kiểu runtime của đối tượng đang nằm trong biến `Object`.

### Bài 2 — Kiểm tra pointcut quá rộng

Một lớp có `charge(String)`, `charge(String, int)`, `charge(Object)`. Pointcut chọn mọi phương thức tên `charge` với danh sách tham số bất kỳ. Yêu cầu chỉ ghi log phiên bản một `String`. Điều gì sai và nên sửa thế nào?

**Đáp án:** Pointcut quá rộng vì nó chọn cả hai overload không mong muốn. Cần thêm điều kiện khớp đúng kiểu khai báo, số lượng và thứ tự tham số, giới hạn kiểu/lớp và kiểm thử âm cho hai overload còn lại.

### Bài 3 — Kiểu runtime đánh lừa

Một bộ lọc kiểm tra `args[0] instanceof String`. Người gọi thực thi `send((Object) "A")`. Nếu lớp có cả `send(String)` và `send(Object)`, bộ lọc có đảm bảo chỉ chọn `send(String)` không?

**Đáp án:** Không. Lời gọi được giải thành `send(Object)` nhưng đối số runtime là `String`, nên phép `instanceof` có thể đúng. Cần chọn theo chữ ký khai báo nếu mục tiêu là overload `String`.

### Bài 4 — `null` và mơ hồ

Một lớp có `verify(String)` và `verify(Integer)`. Vì sao `verify(null)` không biên dịch? Làm thế nào để chọn một overload xác định?

**Đáp án:** Hai kiểu không có quan hệ cụ thể hơn nhau nên lời gọi mơ hồ. Ép kiểu `(String) null` hoặc `(Integer) null` tại điểm gọi sẽ chọn một chữ ký cụ thể.

### Bài 5 — Kế thừa và bridge

Một lớp triển khai `Handler<String>` và override `handle(String)`. Bộ đo ở cấp bytecode phát hiện hai phương thức có tên `handle`, một phương thức cầu nối. Có nên khẳng định ngay hai lần advice tương ứng mỗi lần gọi không?

**Đáp án:** Không. Cần kiểm tra phương thức nào là bridge/synthetic, kiểu join point, cơ chế weaving và đường gọi thực tế. Một số cơ chế xử lý/loại trừ bridge khác nhau; không có kết luận phổ quát chỉ từ số phương thức reflection nhìn thấy.

### Bài 6 — Bảo toàn hợp đồng

Một advice được áp nhầm `transfer(Account, int)` và tự retry khi timeout, trong khi chính sách dự kiến chỉ áp `transfer(String requestId)`. Vì sao lỗi này nguy hiểm hơn log dư?

**Đáp án:** Phiên bản `Account, int` có thể thực hiện chuyển tiền; retry không bảo đảm an toàn nếu tác dụng phụ của lần trước đã xảy ra. Cần sửa phạm vi pointcut, xác định điều kiện idempotency và kiểm soát lỗi ở ranh giới nghiệp vụ phù hợp.

## 18. Ghi nhớ

- **Overload khác nhau bởi danh sách kiểu tham số; chỉ trùng tên không có nghĩa cùng hợp đồng.**
- Pointcut chọn overload an toàn cần xét **loại join point + phạm vi kiểu + tên + số lượng/thứ tự/kiểu tham số**; wildcard phải có mục đích rõ.
- **Kiểu tham số khai báo không phải kiểu đối số runtime.** Chữ ký `submit(Object)` có thể nhận một đối tượng `String`, nhưng vẫn là overload `Object`.
- Lựa chọn overload khi biên dịch khác với chọn hiện thực override khi chạy; method call và method execution cũng là các điểm can thiệp khác nhau.
- `null`, primitive/boxed, varargs, type erasure, bridge methods và kế thừa có thể làm việc chọn điểm phức tạp hơn dự kiến.
- **Khớp pointcut** và **advice thật sự chạy** là hai phép kiểm tra riêng; proxy, weaving và đường gọi giới hạn hiệu lực.
- Luôn có **ca dương và ca âm** để tránh khớp ngoài ý muốn; một chính sách chỉ quan sát phải bảo toàn kết quả, lỗi gốc và số lần thực thi nghiệp vụ.
