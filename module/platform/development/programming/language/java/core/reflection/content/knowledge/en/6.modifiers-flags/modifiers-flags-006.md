# `isSynthetic()` và các cấu trúc do trình biên dịch sinh trong Java Reflection

## 1. `synthetic` nghĩa là gì?

Khi biên dịch Java, trình biên dịch đôi khi phải tạo thêm class, field, method hoặc thành phần khác để thực hiện đúng ngữ nghĩa Java trên JVM. Một số thành phần này không tương ứng với khai báo trực tiếp hoặc ngầm định trong mã nguồn: chúng được gọi là **synthetic** và được đánh dấu trong dữ liệu của class file.

Qua Reflection, `isSynthetic()` giúp phân biệt những cấu trúc được đánh dấu *synthetic* với cấu trúc thông thường. Phương thức trả `boolean`:

- `true`: cấu trúc được class file/JVM phản ánh là synthetic.
- `false`: không có chỉ dấu synthetic tương ứng; **không đồng nghĩa** với “chắc chắn do lập trình viên tự gõ”. Java có những thành phần được sinh ra nhưng hợp lệ ở cấp ngôn ngữ và không được đánh dấu synthetic.

Ví dụ điển hình: để bảo đảm một phương thức ghi đè sau **type erasure** vẫn được gọi đúng, `javac` có thể sinh ra một *bridge method* không viết trong mã nguồn. Ngược lại, constructor mặc định do compiler cấp khi class không khai báo constructor thường **không synthetic**. Vì vậy không thể dùng `isSynthetic()` làm bộ phát hiện tuyệt đối mọi thứ do compiler tạo ra.

**Phạm vi quan trọng:** `isSynthetic()` phản ánh đặc tính ở mức **binary/runtime**, không kiểm tra văn bản mã nguồn và không phân tích body của một method. Tên có ký tự `$` cũng không đủ chứng minh một thành phần là synthetic.

## 2. Gọi `isSynthetic()` ở đâu?

| Thành phần Reflection | API | Dùng để hỏi |
| --- | --- | --- |
| Kiểu (class/interface) | `Class<?>.isSynthetic()` | Bản thân kiểu có synthetic modifier hay không? |
| Trường dữ liệu | `Field.isSynthetic()` | Trường đó có được đánh dấu synthetic không? |
| Phương thức | `Method.isSynthetic()` | Phương thức đó có được đánh dấu synthetic không? |
| Constructor | `Constructor<?>.isSynthetic()` | Constructor đó có được đánh dấu synthetic không? |
| Tham số được mô tả qua Reflection | `Parameter.isSynthetic()` | Tham số có phải thành phần synthetic không? |

`Field`, `Method`, `Constructor` đều triển khai giao diện `java.lang.reflect.Member`, giao diện có `isSynthetic()`; `Class` và `Parameter` cung cấp phương thức riêng. Với các method, `Method.isBridge()` còn kiểm tra một tính chất khác: phương thức có phải *bridge method* hay không.

Để quan sát các phần tử compiler có thể thêm, dùng các API **declared**:

~~~java
Class<?> type = SomeType.class;
var methods = type.getDeclaredMethods();
var fields = type.getDeclaredFields();
var constructors = type.getDeclaredConstructors();

for (var m : methods) {
    System.out.println(m.getName() + ": " + m.isSynthetic());
}
~~~

Đoạn này chỉ minh họa cách sử dụng Reflection (`SomeType` là tên lớp phải thay bằng class có thật); nó **không phải chương trình độc lập**. `getDeclaredMethods()` nhìn các method khai báo trong binary của chính class, bao gồm cả private và synthetic nếu có. `getMethods()` chỉ xét các public method của kiểu và các phương thức public kế thừa, nên có thể bỏ sót method synthetic không public. Tương tự, `getDeclaredFields()` hữu ích hơn `getFields()` khi kiểm tra các field do compiler sinh.

## 3. Ví dụ đầy đủ: bridge method, default constructor, anonymous class

Lưu chương trình Java 17+ dưới đây thành `SyntheticReflectionDemo.java`:

~~~java
import java.lang.reflect.Field;
import java.util.Arrays;
import java.util.Comparator;

public class SyntheticReflectionDemo {
    static class Box<T> {
        T value() {
            return null;
        }
    }

    static class TextBox extends Box<String> {
        @Override
        String value() {
            return "hello";
        }
    }

    static class Outer {
        private int seed = 7;

        class Inner {
            int read() {
                return seed;
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Arrays.stream(TextBox.class.getDeclaredMethods())
                .filter(m -> m.getName().equals("value"))
                .sorted(Comparator.comparing(
                        m -> m.getReturnType().getSimpleName()))
                .forEach(m -> System.out.printf(
                        "return=%s, bridge=%s, synthetic=%s%n",
                        m.getReturnType().getSimpleName(),
                        m.isBridge(), m.isSynthetic()));

        System.out.println("default constructor synthetic: "
                + TextBox.class.getDeclaredConstructor().isSynthetic());

        Class<?> anonymous = new Runnable() {
            @Override
            public void run() { }
        }.getClass();

        System.out.println("anonymous: " + anonymous.isAnonymousClass()
                + ", synthetic: " + anonymous.isSynthetic());

        for (Field field : Outer.Inner.class.getDeclaredFields()) {
            if (field.isSynthetic()) {
                System.out.println("synthetic inner field: " + field.getName());
            }
        }
    }
}
~~~

Biên dịch bằng `javac` và chạy:

~~~bash
javac --release 17 SyntheticReflectionDemo.java
java SyntheticReflectionDemo
~~~

Kết quả quan sát được với `javac` và JDK hỗ trợ Java 17 trở lên (tên field do compiler sinh là chi tiết triển khai, xem bên dưới):

~~~text
return=Object, bridge=true, synthetic=true
return=String, bridge=false, synthetic=false
default constructor synthetic: false
anonymous: true, synthetic: false
synthetic inner field: this$0
~~~

### Phân tích bridge method

`Box<T>.value()` sau khi xóa kiểu generic có mô tả JVM tương ứng với `Object value()`. Trong `TextBox`, phương thức ghi đè mà lập trình viên viết là `String value()`. Để giữ hành vi gọi đa hình tương thích với dạng đã xóa kiểu, `javac` còn phát sinh một phương thức chuyển tiếp gần tương đương ý tưởng sau:

~~~java
// Mô tả ý tưởng ở mức bytecode; KHÔNG phải mã nguồn Java hợp lệ
// để khai báo cùng lớp với String value().
Object value() {
    return value(); // ủy quyền tới phương thức trả String
}
~~~

Phần minh họa trên **không thể dán làm method thứ hai trong Java source**: ngôn ngữ Java không cho hai method cùng tên và danh sách tham số chỉ khác kiểu trả về. JVM phân biệt method descriptor gồm cả kiểu trả về và compiler có thể sinh bridge. Ở binary, phương thức trả `Object` mang các cờ `ACC_BRIDGE` và `ACC_SYNTHETIC`. Do đó Reflection báo `isBridge() == true` và `isSynthetic() == true` cho phương thức chuyển tiếp; method `String value()` vốn khai báo trong source có cả hai kết quả `false`.

**Tác dụng thực tế:** Khi tìm method có thể dùng làm endpoint, handler hoặc mô tả API, đừng mù quáng xem tất cả method từ `getDeclaredMethods()` là những khai báo độc lập trong source. Bridge có thể dẫn đến hai `Method` cùng tên và cùng tham số nhưng kiểu trả về khác nhau. Cần chọn đúng method nghiệp vụ và cân nhắc loại bridge/synthetic nếu bài toán đòi hỏi khai báo do người viết.

### Phân tích constructor và anonymous class

- `TextBox` không khai báo constructor, nhưng compiler tạo constructor mặc định; `getDeclaredConstructor().isSynthetic()` trả `false` trong ví dụ. Điều này cho thấy **compiler-generated không luôn đồng nghĩa synthetic**.
- Cú pháp `new Runnable() { ... }` thật sự khai báo một anonymous class trong mã nguồn. Reflection nhận ra `isAnonymousClass() == true`, còn `isSynthetic() == false` theo chương trình `javac` này. `isAnonymousClass()`, `isLocalClass()`, `isMemberClass()` và `isSynthetic()` trả lời các câu hỏi khác nhau.
- `Outer.Inner` đọc `seed` của outer object, nên `javac` trong ví dụ lưu tham chiếu outer vào một field tổng hợp thường đặt tên `this$0`. Tên và cách triển khai field này **không phải hợp đồng ngôn ngữ**; compiler/JDK khác có thể tạo cấu trúc khác. Từ các bản Java hiện đại, compiler còn có thể bỏ field outer khi không cần giữ tham chiếu. Phải xem `Field.isSynthetic()` thay vì đoán từ tên.

## 4. Những cấu trúc synthetic thường gặp

| Tình huống | Cấu trúc có thể xuất hiện | Cách kiểm tra và lưu ý |
| --- | --- | --- |
| Override phương thức generic sau type erasure | Bridge method | `Method.isBridge()` và `Method.isSynthetic()`; có ví dụ xác định ở trên. |
| Ghi đè với kiểu trả về covariant | Bridge method khi binary cần giữ descriptor gốc | Xét `isBridge()`; không phải mọi override đều cần bridge. |
| Inner/local class dùng trạng thái từ outer hoặc biến cục bộ được capture | Field giữ tham chiếu/giá trị captured | `Field.isSynthetic()`; sự tồn tại và tên field phụ thuộc compiler. |
| Lambda expression | Cấu trúc hỗ trợ do compiler/JVM tạo, ví dụ method bổ trợ hoặc lớp runtime | Không dựa vào tên `lambda$...`, số lượng method hay hình dạng class như giao kèo ổn định. |
| Truy cập private giữa các lớp lồng nhau | Trình biên dịch cũ có thể thêm accessor tổng hợp | Từ Java 11 có cơ chế nest-based access control; không mặc định chờ phương thức `access$...` xuất hiện. |
| Enum và record | Một số member ngầm định, cùng các chi tiết triển khai khác | Member ngầm định hợp lệ ở cấp ngôn ngữ không nhất thiết synthetic; xét từng member cụ thể thay vì gắn nhãn toàn bộ. |

Phân biệt **quy tắc ngôn ngữ** và **chiến lược hiện thực của compiler**. Các tên như `this$0`, `val$...`, `lambda$...`, `$VALUES` phổ biến trong bytecode do `javac` sinh, nhưng không có cam kết rằng mọi JDK hoặc compiler khác đều dùng đúng các tên này.

### Với tham số constructor/method

`Executable.getParameters()` trả các đối tượng `Parameter`. Ba loại cần phân biệt:

1. **Explicit:** tham số được viết rõ trong khai báo nguồn, ví dụ `void send(String text)`.
2. **Implicit (mandated):** tham số ngầm định theo quy tắc ngôn ngữ; kiểm tra `Parameter.isImplicit()`.
3. **Synthetic:** tham số không được khai báo tường minh hay ngầm định ở cấp source; kiểm tra `Parameter.isSynthetic()`.

Ví dụ, một inner class không static thường cần truyền tham chiếu tới đối tượng outer khi khởi tạo. Tham số bổ sung đó là thành phần constructor ở cấp binary, nhưng việc Reflection ghi nhận `isImplicit()`/`isSynthetic()` phụ thuộc metadata và cách compiler sinh class file. Khi cần kiểm tra thông tin tham số, cân nhắc biên dịch với `javac -parameters` để giữ metadata `MethodParameters`; đừng suy ra mọi tham số bổ sung đều synthetic, cũng đừng coi kết quả `false` khi thiếu metadata là bằng chứng về source.

## 5. Liên hệ cờ class file và `Modifier`

JVM class file có cờ `ACC_SYNTHETIC` (giá trị hex `0x1000`) dành cho class/field/method tương ứng, và cờ `ACC_BRIDGE` (`0x0040`) cho method. Class file cũng có thể biểu diễn synthetic bằng thuộc tính `Synthetic` theo quy tắc của phiên bản class file.

Đây là các khái niệm từ **class file format**, không đơn giản là các từ khóa mà có thể viết trong Java source. Thư viện `java.lang.reflect.Modifier` chủ yếu diễn giải những modifier thông thường (public/private/static/final...); API Reflection có `isSynthetic()` và `isBridge()` riêng, nên hãy sử dụng các phương thức đó thay vì tự diễn giải magic bit từ `getModifiers()` để kết luận về synthetic.

Có thể đối chiếu với bytecode của chương trình ví dụ:

~~~bash
javap -v 'SyntheticReflectionDemo$TextBox'
~~~

Dùng dấu nháy quanh tên có `$` để tránh shell thay thế ký tự này (đặc biệt trong Bash). Trong output, tìm hai method tên `value`:

- Phương thức trả `java.lang.String` được viết trong mã nguồn.
- Bridge trả `java.lang.Object` có dòng flags chứa `ACC_BRIDGE, ACC_SYNTHETIC`.

Khi kiểm tra class file thực tế, công cụ `javap -v` giúp xác minh dấu cờ và descriptor, còn Reflection giúp xử lý metadata của class được nạp lúc chạy. Không dùng `getName().contains("$")` để thay cho `isSynthetic()`: tên không phải bộ phân loại đáng tin cậy.

## 6. Dùng `isSynthetic()` khi xây framework/tool

Một tình huống thường gặp là thu thập các method do lập trình viên khai báo để dựng metadata. Có thể bắt đầu bằng bộ lọc sau:

~~~java
import java.lang.reflect.Method;
import java.util.Arrays;
import java.util.List;

static List<Method> userFacingMethods(Class<?> type) {
    return Arrays.stream(type.getDeclaredMethods())
            .filter(m -> !m.isSynthetic())
            .filter(m -> !m.isBridge())
            .toList();
}
~~~

Đây là **đoạn method tiện ích**, cần đặt trong một class Java và có các import tương ứng; `toList()` có từ Java 16. Nó trả về method khai báo trong binary của class đã qua hai tiêu chí lọc, chứ **không khôi phục chính xác tập phương thức có mặt trong mã nguồn**. Method do compiler sinh nhưng không synthetic vẫn có thể lọt qua; method synthetic thực sự cần thiết cho công cụ phân tích bytecode lại bị loại.

Quy trình lựa chọn tùy mục tiêu:

- **Tạo danh sách API nghiệp vụ:** lọc hoặc xử lý riêng bridge/synthetic, rồi xét visibility, annotation, override và quan hệ kế thừa theo yêu cầu thực tế. Không chỉ dựa vào `isSynthetic()`.
- **Phân tích bytecode, debug, profiler, serializer cấp thấp:** có thể **cần giữ** các member synthetic vì chúng thể hiện cấu trúc runtime đang tồn tại.
- **Đối chiếu phương thức sau type erasure:** xem cả `getDeclaredMethods()`, `isBridge()`, `getReturnType()` và signature; đừng suy ra một `Method` Reflection luôn tương ứng một khai báo Java nguồn.

## 7. Lỗi thường gặp và bài tự kiểm tra

1. **“Mọi compiler-generated đều synthetic.”** Sai: constructor mặc định, một số member ngầm định của enum/record và class do cú pháp ngôn ngữ tạo ra là phản ví dụ quan trọng.
2. **“Synthetic nghĩa là không gọi được.”** Sai: bridge synthetic vẫn có vai trò thực thi, có thể được gọi khi JVM điều phối dispatch.
3. **“Tên chứa `$` chắc chắn synthetic.”** Sai: `$` có thể xuất hiện trong tên Java hợp lệ và compiler không bắt buộc giữ quy tắc tên nội bộ.
4. **“Một method source = một method Reflection.”** Không luôn đúng: bridge tạo thêm phần tử trong `getDeclaredMethods()`.
5. **“`getMethods()` đủ để soi các thành phần compiler sinh.”** Không luôn đúng: các thành phần private/package thường cần `getDeclaredMethods()` hoặc `getDeclaredFields()`.
6. **“Mọi phiên bản javac sinh cùng accessor/field/lambda method.”** Không có bảo đảm: kiến trúc nestmates, phiên bản class file và tối ưu hóa của compiler có thể làm kết quả khác.
7. **“`isSynthetic() == false` khẳng định member xuất hiện tường minh trong source.”** Sai: đó chỉ là thiếu chỉ dấu synthetic, không chứng minh nguồn gốc.

**Tự kiểm tra:** Thay `TextBox extends Box<String>` thành `TextBox extends Box<Integer>` và override `Integer value()`; dự đoán các method `value()` Reflective sẽ có kiểu trả về nào và method nào là bridge. Sau đó thử loại `isBridge()` trong bộ lọc để thấy method `Object value()` trở lại danh sách.

**Tài liệu chuẩn:**
- [Java SE 17 — `Class.isSynthetic()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isSynthetic())
- [Java SE 17 — `Method.isBridge()` và `Method.isSynthetic()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html)
- [Java SE 17 — `Parameter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Parameter.html)
- [JLS 17 §13.1 — The Form of a Binary](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html#jls-13.1)
- [JVMS 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html)
