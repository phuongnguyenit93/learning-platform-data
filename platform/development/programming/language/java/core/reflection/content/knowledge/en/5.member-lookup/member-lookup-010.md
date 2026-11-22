# Reflection: Thứ tự thành viên trả về không được bảo đảm là thứ tự khai báo

Khi tra cứu thành viên của một lớp bằng Java Reflection, các API như `Class.getDeclaredMethods()`, `getDeclaredFields()` hay `getDeclaredConstructors()` trả về **mảng các đối tượng mô tả thành viên**, nhưng **không cam kết các phần tử xuất hiện theo thứ tự khai báo trong mã nguồn**. Tương tự, các API lấy thành viên `public` cũng không bảo đảm thứ tự. Nếu chương trình cần kết quả nhất quán, phải tự định nghĩa quy tắc sắp xếp hoặc tra cứu bằng danh tính cụ thể của thành viên.

## 1. Điều gì được bảo đảm, điều gì không?

Giả sử lớp có các phương thức được viết theo thứ tự `zeta`, `alpha(int)`, `alpha()`. Không được mặc định rằng `getDeclaredMethods()[0]` là `zeta` hoặc hai phương thức `alpha` đứng liền nhau theo thứ tự trong tệp Java. Việc chạy thử thấy kết quả giống mã nguồn chỉ phản ánh một lần chạy trong một môi trường, **không tạo thành hợp đồng API**.

| API trên `Class<?>` | Phạm vi thành viên được tìm | Thứ tự mảng trả về |
| --- | --- | --- |
| `getDeclaredMethods()` | Phương thức được khai báo trong chính lớp/interface, kể cả không `public`; không lấy phương thức kế thừa | Không xác định |
| `getMethods()` | Phương thức `public` nhìn thấy từ kiểu, bao gồm các phương thức kế thừa theo quy tắc API | Không xác định |
| `getDeclaredFields()` | Trường được khai báo tại chính kiểu, kể cả `private`; không gồm trường kế thừa | Không xác định |
| `getFields()` | Các trường `public` nhìn thấy, có thể bao gồm trường kế thừa | Không xác định |
| `getDeclaredConstructors()` | Các constructor khai báo tại lớp, kể cả không `public` | Không xác định |
| `getConstructors()` | Các constructor `public` của lớp | Không xác định |

“Không xác định” ở đây có nghĩa là **không có bảo đảm về thứ tự của mảng**; không đồng nghĩa rằng mỗi lần gọi sẽ bị xáo ngẫu nhiên. Trên một JDK cụ thể, bạn có thể quan sát cùng thứ tự rất nhiều lần. Kết quả quan sát đó vẫn không đủ để viết logic phụ thuộc vào vị trí.

Cần phân biệt **tập thành viên** mà mỗi API mô tả với **vị trí các phần tử** trong tập đó. Chọn đúng `getMethods()` hay `getDeclaredMethods()` là quyết định về phạm vi/khả năng truy cập; nó không giải quyết chuyện thứ tự. Việc `getDeclaredFields()` nhìn thấy metadata của trường `private` cũng không tự cấp quyền đọc giá trị trường đó.

## 2. Vì sao không nên suy luận thứ tự từ mã nguồn?

Reflection truy vấn metadata của kiểu đã nạp và tuân theo hợp đồng API của JDK. API tra cứu thành viên không hứa sẽ bảo toàn thứ tự xuất hiện trong tệp `.java`. Cách trình biên dịch tạo bytecode, các thành viên tổng hợp/bridge, cách JVM và thư viện Reflection triển khai, hoặc thay đổi phiên bản công cụ có thể làm thứ tự quan sát được khác đi. Không cần chứng minh một lần chạy bị đảo thứ tự mới kết luận rằng chương trình không được dựa vào thứ tự ấy: **điều quyết định là tài liệu API không bảo đảm**.

Ví dụ, hai cách sau đều dễ sai:

```java
Method first = Example.class.getDeclaredMethods()[0];
// SAI về giả định: first là phương thức xuất hiện đầu tiên trong file .java.

Field firstField = Example.class.getDeclaredFields()[0];
// SAI về giả định: firstField là trường được khai báo đầu tiên.
```

Đây là các *đoạn minh họa giả định sai*, không phải chương trình độc lập. Phần tử `[0]` chỉ có nghĩa là phần tử đầu tiên **trong mảng trả về lần đó**, không mang ý nghĩa “khai báo đầu tiên”. Nếu mảng rỗng, truy cập `[0]` còn gây `ArrayIndexOutOfBoundsException`.

## 3. Ví dụ Java 17+: sắp xếp trước khi sử dụng

Ví dụ sau khai báo phương thức theo một thứ tự, nhưng **không in mảng Reflection thô** để tránh gắn một output cố định cho thứ tự không được bảo đảm. Thay vào đó, chương trình định nghĩa một khóa hiển thị gồm tên phương thức và các kiểu tham số, rồi sắp xếp theo khóa đó. Lớp ví dụ không có phương thức overload với cùng tên và danh sách tham số nhưng khác kiểu trả về, nên khóa hiển thị đủ để xác định thứ tự trong ví dụ này.

Tạo tệp `MemberOrderDemo.java`:

```java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.Comparator;
import java.util.stream.Collectors;

public class MemberOrderDemo {
    static class Example {
        public void zeta() {}

        public void alpha(int value) {}

        public void alpha() {}
    }

    private static String signature(Method method) {
        String parameters = Arrays.stream(method.getParameterTypes())
                .map(Class::getTypeName)
                .collect(Collectors.joining(", "));
        return method.getName() + "(" + parameters + ")";
    }

    public static void main(String[] args) {
        Method[] methods = Example.class.getDeclaredMethods();

        Arrays.sort(methods, Comparator.comparing(MemberOrderDemo::signature));

        for (Method method : methods) {
            System.out.println(signature(method));
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac MemberOrderDemo.java
java MemberOrderDemo
```

Output sau khi đã sắp xếp:

```text
alpha()
alpha(int)
zeta()
```

Vì sao output này ổn định trong ví dụ?

1. `getDeclaredMethods()` tìm ba phương thức do `Example` khai báo, bất kể thứ tự ban đầu của chúng trong mảng.
2. `signature()` tạo khóa rõ ràng: tên phương thức kết hợp danh sách kiểu tham số. Nhờ vậy hai overload `alpha()` và `alpha(int)` được phân biệt.
3. `Arrays.sort(...)` sắp xếp theo khóa chuỗi trước khi vòng `for` in ra. Thứ tự ở output là **quy tắc do ứng dụng lựa chọn**, không phải thứ tự nguồn được Reflection tự cung cấp.

Mã này chỉ phục vụ cho việc hiển thị/duyệt có thứ tự; việc sắp xếp mảng không thay đổi khai báo của lớp hay metadata của JVM. Nếu muốn thứ tự theo tên trường, có thể sử dụng `Arrays.sort(fields, Comparator.comparing(Field::getName))` sau khi lấy `Field[] fields = SomeClass.class.getDeclaredFields()`; nhớ import `java.lang.reflect.Field`.

## 4. Khi muốn tìm đúng thành viên: tra cứu theo danh tính

Nếu đã biết tên và kiểu tham số, **tránh chọn phương thức bằng chỉ số mảng**. Dùng API tra cứu theo chữ ký:

```java
Method noArgs = Example.class.getDeclaredMethod("alpha");
Method withInt = Example.class.getDeclaredMethod("alpha", int.class);
```

Hai câu lệnh này là **đoạn mã nằm trong ngữ cảnh ví dụ ở mục 3**, có thể đặt vào `main` (và cần xử lý hoặc khai báo `NoSuchMethodException`). Chúng không phụ thuộc `getDeclaredMethods()` sắp xếp ra sao.

- Phương thức: `getDeclaredMethod(name, parameterTypes...)` hoặc `getMethod(name, parameterTypes...)`; cần xét cả tên lẫn danh sách kiểu tham số vì Java hỗ trợ overload.
- Trường: `getDeclaredField(name)` hoặc `getField(name)`.
- Constructor: `getDeclaredConstructor(parameterTypes...)` hoặc `getConstructor(parameterTypes...)`; constructor được phân biệt bằng kiểu tham số, không bằng tên tùy ý.

Các bản `getDeclared...` truy vấn khai báo của chính kiểu, còn bản không có `Declared` dùng quy tắc thành viên `public` của API tương ứng. Tra cứu sai tên/chữ ký có thể ném `NoSuchMethodException` hoặc `NoSuchFieldException`; đó là lỗi tra cứu, không liên quan đến thứ tự. Với các class có phương thức bridge/synthetic hay các trường hợp bytecode đặc biệt, nên kiểm tra thêm `isBridge()`, `isSynthetic()` và metadata liên quan thay vì giả định nguồn Java đơn giản luôn mô tả trọn bộ thành viên được phản chiếu.

## 5. Chọn tiêu chí thứ tự phù hợp với mục đích

Một quy tắc sắp xếp là hợp lệ khi **được công bố rõ và đủ để phân biệt các phần tử cần phân biệt**. Một số mục đích phổ biến:

| Mục đích | Quy tắc nên chọn |
| --- | --- |
| Danh sách trường trong giao diện hoặc tài liệu | Sắp xếp `Field::getName` nếu chỉ cần thứ tự tên |
| Danh sách phương thức có overload | Sắp xếp bằng tên + danh sách kiểu tham số; bổ sung kiểu trả về/kiểu khai báo khi cần phân biệt các phương thức đặc biệt |
| So sánh kết quả Reflection trong test | Chuẩn hóa thành set/map theo khóa, hoặc sắp xếp theo khóa xác định trước khi so sánh |
| Chạy các handler/plugin theo ưu tiên nghiệp vụ | Dùng metadata ưu tiên riêng (ví dụ annotation `@Order` do ứng dụng định nghĩa), kết hợp khóa phụ để xử lý trường hợp trùng ưu tiên |
| Cần chính xác thứ tự xuất hiện trong mã nguồn | Thu thập từ AST/source hoặc metadata được ghi nhận lúc build; không suy ra chỉ từ vị trí trong mảng Reflection |

Với ứng dụng thực tế, một `Comparator` chỉ so sánh tên phương thức có thể trả kết quả bằng nhau cho các overload. Khi đó các overload vẫn có thể giữ vị trí theo thứ tự đầu vào vốn không được bảo đảm. Muốn một **thứ tự tổng rõ ràng** cho danh sách phương thức, hãy thêm các khóa phụ theo yêu cầu, chẳng hạn danh sách tên kiểu tham số, kiểu trả về và tên kiểu khai báo. Nếu cần một danh tính ổn định qua quá trình build, hãy thống nhất định dạng tên kiểu/chữ ký trong hệ thống thay vì phụ thuộc vào `toString()` như một chuẩn lưu trữ tự chế.

**Chú ý:** tên phương thức không thể hiện thứ tự khai báo. Sắp xếp theo tên chỉ tạo thứ tự bảng chữ cái, **không phục hồi thứ tự mã nguồn**. Nếu nghiệp vụ yêu cầu `validate` chạy trước `save`, mã phải thể hiện quy tắc ấy bằng thứ tự thao tác rõ ràng hoặc metadata ưu tiên, không dựa vào việc phương thức nào xuất hiện trước trong `getDeclaredMethods()`.

## 6. Những bẫy thực tế

**Bẫy 1 — Test chạy xanh trên máy này nên thứ tự là đúng.** Test so sánh mảng theo vị trí có thể hoạt động trên JDK hiện tại nhưng thiếu cơ sở theo hợp đồng API. Hãy so sánh tập chữ ký khi chỉ quan tâm thành viên tồn tại, hoặc sắp xếp trước khi kiểm tra thứ tự đầu ra.

**Bẫy 2 — `getDeclaredMethods()` nghĩa là theo thứ tự declared.** Chữ `Declared` chỉ nói **phạm vi tìm kiếm** là thành viên khai báo tại chính kiểu; không nói về **thứ tự khai báo**.

**Bẫy 3 — Sắp xếp chỉ theo `Method::getName`.** Khi overload cùng tên, comparator đó không phân biệt được `load()` và `load(String)`. Thêm tham số (và khóa phụ khác nếu cần) để tránh kết quả còn phụ thuộc thứ tự ban đầu.

**Bẫy 4 — Nhầm thành viên kế thừa với thành viên trực tiếp.** `getMethods()` có thể trả phương thức `public` được kế thừa, còn `getDeclaredMethods()` không dùng để liệt kê toàn bộ phương thức kế thừa. Việc đổi API sẽ thay đổi *thành phần* của danh sách, không làm thứ tự trở nên đáng tin hơn.

**Bẫy 5 — Cố gắng lấy thứ tự nguồn từ `.class` bằng chỉ số.** Class file hoặc thư viện phân tích bytecode có thể có thứ tự riêng nhưng Reflection không cam kết phản ánh thứ tự đó. Thậm chí thứ tự metadata trong class file cũng không nhất thiết tương ứng thứ tự phát biểu trong mã nguồn gốc sau các bước sinh/chuyển đổi mã.

**Bẫy 6 — Áp dụng kết luận cho mọi API Reflection.** Quy tắc ở đây nói về các mảng thành viên như `getDeclaredMethods()`, `getMethods()`, `getDeclaredFields()` và constructor. Một API khác có thể có hợp đồng thứ tự riêng: ví dụ `getRecordComponents()` của record trả các component theo thứ tự khai báo trong record header. Luôn đọc tài liệu của **đúng phương thức API** đang sử dụng.

## 7. Checklist áp dụng

1. Xác định cần *tìm một thành viên* hay *duyệt nhiều thành viên*.
2. Nếu tìm một thành viên, dùng API theo tên/chữ ký; không lấy phần tử theo index rồi đoán ý nghĩa.
3. Nếu duyệt nhiều thành viên, chọn `getDeclared...` hay bản `public` theo đúng phạm vi nghiệp vụ.
4. Quy định thứ tự ở tầng ứng dụng (tên, chữ ký, ưu tiên annotation, v.v.) rồi sort **trước** khi hiển thị, xử lý theo thứ tự hoặc xuất tài liệu.
5. Kiểm tra overload, inherited members, bridge/synthetic members và tiêu chí xử lý khóa bằng nhau khi liên quan.
6. Trong test, chỉ khẳng định thứ tự do **chính ứng dụng** thiết lập, không khẳng định thứ tự mảng thô của Reflection.

### Tự kiểm tra

- Nếu `getDeclaredFields()` trả về `[b, a]` trong một lần chạy nhưng mã nguồn khai báo `a` rồi `b`, JDK có vi phạm hợp đồng không? **Không.** API không hứa thứ tự khai báo.
- Có thể tin `getDeclaredMethods()[0]` là phương thức đầu tiên trong file Java khi đã chạy thử mười lần cùng kết quả không? **Không.** Số lần quan sát không thay thế hợp đồng.
- Khi muốn danh sách phương thức luôn theo tên và chữ ký, nên làm gì? **Tạo khóa so sánh gồm tên + danh sách kiểu tham số (cùng khóa phụ khi cần), rồi sắp xếp rõ ràng.**
- Có thể dùng `getDeclaredMethod("process", String.class)` để tìm phương thức overload tương ứng mà không cần biết vị trí mảng không? **Có**, miễn phương thức đó thực sự tồn tại với chữ ký tương ứng trong phạm vi API.

### Tài liệu tham khảo

- Oracle Java SE 21, [`Class` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html): mô tả phạm vi của `getMethods()`, `getDeclaredMethods()`, `getFields()`, `getDeclaredFields()`, `getConstructors()`, `getDeclaredConstructors()` và điều khoản phần tử trong các mảng này không được sắp xếp theo bất kỳ thứ tự cụ thể nào.
- Oracle Java SE 21, [`Method` API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Method.html): chữ ký, tham số, phương thức bridge và synthetic.

**Ghi nhớ:** Reflection cho biết *thành viên nào được tìm thấy* theo hợp đồng của từng API. Khi thứ tự có ý nghĩa, **ứng dụng phải tự xác lập thứ tự đó**.