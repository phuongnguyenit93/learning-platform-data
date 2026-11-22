# Phân biệt tương thích mã nguồn, nhị phân và hành vi trong Java 17

**Chủ đề:** Java 17  
**Chương:** Biên dịch và tài liệu  
**Bài học:** Phân biệt tương thích mã nguồn, nhị phân và hành vi

Khi phát hành một phiên bản mới của thư viện Java, câu hỏi “có tương thích ngược không?” chưa đủ cụ thể. Một thay đổi có thể khiến source code cũ không biên dịch được, khiến file `.class` đã biên dịch không chạy được, hoặc vẫn biên dịch và chạy nhưng cho kết quả khác trước.

Để đánh giá một thay đổi API, cần tách ba khái niệm:

- **Tương thích mã nguồn (source compatibility):** source code của client cũ có thể được biên dịch lại với phiên bản thư viện mới mà không cần sửa hay không.
- **Tương thích nhị phân (binary compatibility):** client đã biên dịch với phiên bản thư viện cũ có thể liên kết và chạy với phiên bản thư viện mới mà không gặp lỗi liên kết do thay đổi API hay không.
- **Tương thích hành vi (behavioral compatibility):** chương trình dùng phiên bản mới có tiếp tục thể hiện hành vi mà client được quyền kỳ vọng theo hợp đồng API hay không.

Ba tiêu chí này độc lập. Một thay đổi có thể giữ tương thích nhị phân nhưng phá tương thích mã nguồn; có thể giữ cả hai nhưng đổi hành vi; hoặc có thể làm hỏng cả ba.

Trong Java 17, cần hiểu cả quy tắc ngôn ngữ Java, cấu trúc bytecode và hợp đồng API. Bài học này dùng ví dụ về method, field, interface, exception, generic và hằng compile-time để chỉ ra cách đánh giá một thay đổi trước khi phát hành.

## 1. Ba loại tương thích là ba câu hỏi khác nhau

Giả sử một thư viện cung cấp API:

```java
package com.example;

public class Greeting {
    public String message(String name) {
        return "Hello, " + name;
    }
}
```

Client sử dụng API:

```java
import com.example.Greeting;

public class App {
    public static void main(String[] args) {
        Greeting greeting = new Greeting();
        String text = greeting.message("Lan");
        System.out.println(text);
    }
}
```

Khi thư viện được nâng cấp, hãy đặt ba câu hỏi riêng.

### 1.1. Source compatibility

Lấy source code `App.java` cũ, đặt trên classpath/module path với thư viện mới và biên dịch lại. Nếu source vẫn biên dịch mà không phải chỉnh sửa, thay đổi giữ tương thích mã nguồn cho client đó.

Điều này không nói gì về file `App.class` đã biên dịch trước đó. Một thay đổi có thể buộc client biên dịch lại nhưng source vẫn hợp lệ.

### 1.2. Binary compatibility

Giữ nguyên file `App.class` đã biên dịch với phiên bản thư viện cũ, thay JAR cũ bằng JAR mới rồi chạy. Nếu JVM vẫn tìm và liên kết được các class, field, method mà bytecode tham chiếu, thay đổi giữ tương thích nhị phân trong tình huống đó.

Binary compatibility quan tâm đến hợp đồng ở cấp class file và liên kết JVM, không chỉ đến việc source code có thể biên dịch lại.

### 1.3. Behavioral compatibility

Ngay cả khi source cũ biên dịch và bytecode cũ chạy, kết quả vẫn có thể thay đổi.

Ví dụ method `message("Lan")` trước đây trả về `"Hello, Lan"` nhưng phiên bản mới trả `"Welcome, Lan"`. Chữ ký không đổi, nên source và binary compatibility vẫn được giữ; tuy nhiên client phụ thuộc vào nội dung thông điệp có thể bị ảnh hưởng.

Behavioral compatibility phụ thuộc vào hợp đồng được công bố: giá trị trả về, exception, side effect, thứ tự, quy tắc null, tính thread-safe và các bảo đảm khác.

### 1.4. Bảng phân biệt nhanh

| Tiêu chí | Câu hỏi kiểm tra | Đối tượng kiểm tra |
|---|---|---|
| Source compatibility | Source cũ có biên dịch lại được với API mới? | File `.java` |
| Binary compatibility | Bytecode cũ có liên kết và chạy với API mới? | File `.class`, JAR |
| Behavioral compatibility | Chương trình có tiếp tục đáp ứng hợp đồng cũ? | Kết quả và hành vi lúc chạy |

Một bản phát hành thư viện tốt cần nêu rõ loại tương thích nào được cam kết. Cụm từ “backward compatible” mà không nói rõ source, binary hay behavior rất dễ gây hiểu nhầm.

## 2. Vì sao Java có các loại tương thích khác nhau?

Java source code được compiler chuyển thành bytecode trong file `.class`. Khi biên dịch, compiler ghi vào constant pool các tham chiếu tượng trưng đến class, field và method mà code sử dụng.

Khi chạy, JVM phân giải các tham chiếu đó theo tên class, tên member và descriptor. Descriptor mô tả kiểu tham số và kiểu trả về của method, hoặc kiểu của field.

Ví dụ method:

```java
public String message(String name)
```

có descriptor JVM:

```text
(Ljava/lang/String;)Ljava/lang/String;
```

Trong descriptor:

- `(` bắt đầu danh sách tham số.
- `Ljava/lang/String;` là tham số kiểu `String`.
- `)` kết thúc danh sách tham số.
- `Ljava/lang/String;` sau dấu `)` là kiểu trả về.

Tên method và descriptor cùng xác định method ở cấp bytecode. Do đó, thay đổi kiểu tham số hoặc kiểu trả về có thể làm tham chiếu trong bytecode cũ không còn khớp.

### 2.1. Chữ ký source và descriptor bytecode không giống nhau hoàn toàn

Ở cấp ngôn ngữ Java, method signature chủ yếu dựa trên tên method và kiểu tham số sau khi áp dụng quy tắc generic/erasure. Kiểu trả về không cho phép tạo overload riêng.

Ở cấp JVM, method descriptor có cả kiểu trả về. Đây là lý do thay đổi kiểu trả về có thể làm hỏng binary compatibility dù tên method và danh sách tham số vẫn giữ nguyên.

Ví dụ hai khai báo sau không thể cùng tồn tại như hai overload trong Java:

```java
String find(String key);
Object find(String key); // Không thể overload chỉ bằng kiểu trả về
```

Nhưng nếu thư viện đổi kiểu trả về của method từ `String` sang `Object`, descriptor bytecode thay đổi. Client đã biên dịch có thể vẫn tham chiếu descriptor cũ và gặp `NoSuchMethodError`.

### 2.2. Throws clause không nằm trong method descriptor

Danh sách checked exception trong `throws` không phải một phần của descriptor JVM.

Ví dụ:

```java
public String read() {
    return "data";
}
```

đổi thành:

```java
public String read() throws java.io.IOException {
    return "data";
}
```

Tên method, tham số và kiểu trả về vẫn như cũ nên descriptor không đổi. Binary client cũ vẫn có thể liên kết method. Tuy nhiên source client biên dịch lại có thể phải bắt hoặc khai báo `IOException`.

Đây là ví dụ điển hình cho thấy source compatibility và binary compatibility không đồng nhất.

### 2.3. Generic được xóa kiểu khi tạo bytecode

Java dùng type erasure để thực hiện generic. Ví dụ:

```java
public void addAll(List<String> values)
```

thường có descriptor dùng kiểu `List` đã xóa tham số generic:

```text
(Ljava/util/List;)V
```

Nếu thay `List<String>` thành `List<Object>`, descriptor đã xóa có thể không đổi, nên liên kết nhị phân vẫn thành công. Nhưng source client có thể không biên dịch do quy tắc generic khác đi; metadata generic cũng thay đổi và có thể ảnh hưởng code dùng reflection.

Đừng chỉ so sánh tên method để kết luận binary compatibility. Khi cần kiểm tra, xem descriptor thực tế của class file.

## 3. Tương thích mã nguồn: source cũ có biên dịch lại được không?

Source compatibility đánh giá trải nghiệm của người dùng đang nâng cấp dependency rồi biên dịch lại ứng dụng. Những thay đổi sau thường ảnh hưởng đến source.

### 3.1. Xóa hoặc đổi tên method

Phiên bản 1:

```java
public class UserService {
    public User findById(long id) {
        return load(id);
    }
}
```

Phiên bản 2 xóa `findById` và chỉ cung cấp `find`:

```java
public class UserService {
    public User find(long id) {
        return load(id);
    }
}
```

Source client gọi `findById(10)` không còn biên dịch. Đây là source incompatibility. Bytecode cũ cũng không thể tìm method cũ và sẽ gặp lỗi liên kết nếu đường gọi được thực thi.

Một cách chuyển đổi nhẹ nhàng hơn là giữ method cũ và đánh dấu deprecated trong một giai đoạn:

```java
public class UserService {
    public User find(long id) {
        return load(id);
    }

    @Deprecated(since = "2.0", forRemoval = true)
    public User findById(long id) {
        return find(id);
    }
}
```

Việc giữ method cũ giúp client có thời gian chuyển đổi. Chỉ xóa sau khi chính sách tương thích cho phép.

### 3.2. Thay đổi kiểu tham số

Giả sử phiên bản cũ có:

```java
public User find(long id)
```

và phiên bản mới chỉ còn:

```java
public User find(String id)
```

Source client truyền `long` sẽ không còn biên dịch. Binary descriptor cũng thay đổi, nên bytecode cũ tham chiếu method có tham số `long` không còn tìm được method tương ứng.

Nếu muốn hỗ trợ cả hai dạng trong giai đoạn chuyển đổi, có thể giữ overload cũ và bổ sung overload mới:

```java
public User find(long id) {
    return find(Long.toString(id));
}

public User find(String id) {
    return loadByExternalId(id);
}
```

Tuy nhiên, việc thêm overload cũng cần xem xét ảnh hưởng tới method resolution.

### 3.3. Thêm overload có thể làm source cũ trở nên mơ hồ

Phiên bản cũ:

```java
public void send(String value) {
    // ...
}
```

Client:

```java
sender.send(null);
```

Phiên bản mới bổ sung overload:

```java
public void send(String value) {
    // ...
}

public void send(Integer value) {
    // ...
}
```

Khi biên dịch lại, lời gọi `send(null)` trở nên mơ hồ vì `null` có thể chuyển đổi sang cả `String` và `Integer`, hai kiểu không có quan hệ subtype với nhau. Source client cũ không còn biên dịch.

Bytecode cũ đã chọn method `send(String)` từ lần biên dịch trước vẫn tham chiếu descriptor đó và có thể tiếp tục chạy. Vì vậy, thêm overload có thể phá source compatibility nhưng giữ binary compatibility.

### 3.4. Thêm checked exception có thể phá source compatibility

Phiên bản cũ:

```java
public String load() {
    return readValue();
}
```

Phiên bản mới:

```java
public String load() throws IOException {
    return readValue();
}
```

Source client cũ:

```java
String value = service.load();
```

có thể không biên dịch lại vì caller phải bắt `IOException` hoặc khai báo nó trong `throws`.

Binary descriptor không chứa `throws IOException`, nên bytecode cũ vẫn liên kết được. Nếu method mới thực sự ném `IOException`, exception có thể truyền ra caller cũ lúc runtime dù source caller cũ không khai báo nó; JVM không kiểm tra checked exception ở runtime.

### 3.5. Giảm mức truy cập

Nếu một method public trở thành protected hoặc package-private, source client bên ngoài package có thể không biên dịch. Bytecode cũ nếu vẫn gọi member đó có thể gặp `IllegalAccessError` lúc runtime.

Tăng mức truy cập thường ít gây vấn đề hơn giảm mức truy cập, nhưng vẫn cần xem xét hợp đồng API và xung đột tên/inheritance.

### 3.6. Thay đổi generic có thể làm source không tương thích

Phiên bản cũ:

```java
public List<String> names() {
    return List.of("An", "Bình");
}
```

Phiên bản mới:

```java
public List<Object> names() {
    return List.of("An", "Bình");
}
```

Source client:

```java
List<String> names = service.names();
```

không còn biên dịch vì `List<Object>` không thể gán cho `List<String>`. Do type erasure, descriptor method có thể vẫn là `()Ljava/util/List;`, nên binary linkage có thể không đổi. Tuy nhiên, thay đổi generic metadata và hợp đồng kiểu vẫn có ảnh hưởng đến client.

### 3.7. Thay đổi interface có thể ảnh hưởng implementor

Nếu thêm một abstract method vào interface:

```java
public interface PaymentProvider {
    Receipt pay(Invoice invoice);

    void cancel(Receipt receipt); // Method mới
}
```

Các class source cũ implement `PaymentProvider` mà không định nghĩa `cancel` sẽ không biên dịch lại cho đến khi bổ sung implementation.

Binary cũ vẫn có thể được nạp, nhưng nếu chương trình gọi method mới trên một implementation không cung cấp nó, JVM có thể ném `AbstractMethodError`.

Default method có thể giảm gánh nặng cho implementor:

```java
public interface PaymentProvider {
    Receipt pay(Invoice invoice);

    default void cancel(Receipt receipt) {
        throw new UnsupportedOperationException("Cancellation is not supported");
    }
}
```

Tuy nhiên, thêm default method cũng cần kiểm tra xung đột với method cùng chữ ký từ interface khác hoặc superclass. Trong một số cấu trúc kế thừa, việc thêm default method có thể làm source compile trở nên mơ hồ hoặc gây lỗi liên kết khi lời gọi không còn một implementation mặc định duy nhất.

## 4. Những thay đổi thường giữ source compatibility

Không có quy tắc nào thay thế việc biên dịch source client thật, nhưng các thay đổi sau thường giữ source compatibility nếu không tạo xung đột khác:

- Thêm method mới mà không làm thay đổi overload resolution hiện có.
- Thêm class public mới.
- Thêm overload không làm lời gọi cũ trở nên mơ hồ hoặc chọn overload khác ngoài dự kiến.
- Thêm method static mới không đụng tên với thành viên gây xung đột.
- Sửa implementation bên trong mà không đổi API hoặc quy tắc biên dịch.

“Tường minh” ở đây là điều kiện quan trọng: thêm method mới thường an toàn, nhưng thêm overload có thể thay đổi cách compiler phân giải lời gọi source cũ.

Source compatibility cũng không đảm bảo client không có cảnh báo mới. Ví dụ một method bị đánh dấu `@Deprecated` vẫn có thể biên dịch nhưng tạo warning; nếu build bật `-Werror`, warning mới có thể khiến build thất bại. Đây là ảnh hưởng ở quy trình build cần ghi nhận riêng.


## 5. Tương thích nhị phân: bytecode cũ có chạy với thư viện mới không?

Binary compatibility tập trung vào khả năng JVM phân giải các tham chiếu mà compiler đã ghi vào bytecode cũ. Một client có thể không cần biên dịch lại nếu thư viện mới vẫn cung cấp các class và member với tên, descriptor, quyền truy cập và loại member phù hợp.

### 5.1. Xóa method hoặc đổi descriptor

Phiên bản 1 của thư viện:

```java
public class AccountService {
    public Account find(long id) {
        return load(id);
    }
}
```

Client được biên dịch với method descriptor tương ứng với tham số `long`:

```java
Account account = service.find(42L);
```

Nếu phiên bản 2 chỉ cung cấp:

```java
public Account find(String id) {
    return loadByExternalId(id);
}
```

bytecode cũ vẫn yêu cầu method có descriptor cũ. JVM không tự chuyển `long` thành `String` khi phân giải symbolic reference. Khi lời gọi được thực hiện, client có thể gặp `NoSuchMethodError`.

Đổi tên method, xóa method hoặc thay kiểu tham số thường là thay đổi binary incompatible nếu không giữ lại member cũ.

### 5.2. Thay đổi kiểu trả về cũng thay đổi descriptor

Phiên bản cũ:

```java
public String version() {
    return "1.0";
}
```

Phiên bản mới:

```java
public CharSequence version() {
    return "2.0";
}
```

Source code có thể được điều chỉnh tùy cách sử dụng, nhưng bytecode cũ tham chiếu descriptor có kiểu trả về `String`. JVM tìm method theo descriptor, nên không tìm thấy method cũ và có thể ném `NoSuchMethodError`.

Nếu muốn giữ binary compatibility, hãy giữ method cũ hoặc thiết kế API chuyển tiếp bằng một method khác tên. Java không cho overload chỉ bằng kiểu trả về.

### 5.3. Giảm visibility có thể gây lỗi truy cập

Nếu một method từng public bị giảm xuống protected hoặc package-private, bytecode bên ngoài package vẫn có thể chứa tham chiếu đến method đó. Khi JVM thực hiện truy cập và kiểm tra quyền, có thể phát sinh `IllegalAccessError`.

Tương tự, thay đổi quyền truy cập của class hoặc field cũng cần được đánh giá. Không phải mọi thay đổi visibility đều tạo cùng một lỗi ở cùng thời điểm; lỗi có thể xuất hiện khi class được liên kết hoặc khi đường truy cập thực sự được thực thi.

### 5.4. Chuyển method giữa static và instance

Phiên bản cũ:

```java
public static Config current() {
    return INSTANCE;
}
```

Phiên bản mới đổi thành instance method:

```java
public Config current() {
    return this.config;
}
```

Bytecode gọi static method dùng kiểu lệnh invocation khác với lời gọi instance method. Khi class file mới không còn member tương thích với cách gọi mà bytecode cũ yêu cầu, JVM có thể ném `IncompatibleClassChangeError`.

Thay đổi theo chiều ngược lại (instance thành static) cũng có rủi ro tương tự. Không nên xem việc giữ nguyên tên và tham số là đủ để giữ binary compatibility.

### 5.5. Thay đổi kiểu field

Bytecode tham chiếu field bằng tên và descriptor của field. Nếu field `public int count` đổi thành `public long count`, descriptor thay đổi. Client cũ vẫn yêu cầu field có kiểu `int` và có thể gặp `NoSuchFieldError`.

```java
// Phiên bản 1
public int count;

// Phiên bản 2
public long count;
```

Field public/protected thường là một phần của API nhị phân và nên được thay đổi thận trọng. Với API mới, cân nhắc đóng gói trạng thái bằng private field và accessor để giảm phụ thuộc trực tiếp vào descriptor field.

### 5.6. Thêm abstract method vào interface

Khi thêm abstract method vào interface, class đã biên dịch từ trước có thể vẫn được nạp. Nhưng nếu một lời gọi mới yêu cầu implementation mà class cũ không cung cấp, JVM có thể ném `AbstractMethodError`.

Đây là lý do thêm method vào interface không giống thêm method vào một class cụ thể. Cần xem cả những implementation bên ngoài mà thư viện không kiểm soát.

Nếu method mới có thể có hành vi mặc định hợp lý, default method đôi khi giúp duy trì tương thích. Tuy nhiên, phải kiểm tra xung đột default method trong hệ thống kế thừa thực tế.

### 5.7. Xóa class, đổi class thành interface hoặc thay superclass

Binary compatibility còn phụ thuộc cấu trúc class:

- Xóa class mà client tham chiếu có thể gây `NoClassDefFoundError`.
- Thay đổi class/interface có thể gây `IncompatibleClassChangeError`.
- Thay đổi superclass hoặc interface được triển khai có thể ảnh hưởng đến method resolution, verification và các class con đã biên dịch.
- Thay đổi một member từ instance sang static hoặc ngược lại có thể làm bytecode gọi sai dạng member.

Đây là các thay đổi ở cấp cấu trúc type, thường có rủi ro cao hơn thay đổi nội bộ method body.

## 6. Những thay đổi thường giữ binary compatibility

Một số thay đổi thường giữ liên kết nhị phân cho client cũ nếu không kéo theo thay đổi khác:

- Thêm class hoặc interface mới.
- Thêm method mới vào class mà không làm thay đổi member cũ.
- Thêm field mới.
- Thêm overload mới, miễn là member cũ vẫn tồn tại với descriptor và quyền truy cập tương thích.
- Thay đổi phần thân method mà không đổi tên, descriptor hoặc khả năng truy cập.
- Thêm checked exception vào `throws` clause, vì checked exception không nằm trong descriptor JVM.

Tuy nhiên, “binary compatible” không có nghĩa mọi client đều chạy đúng. Một method body mới có thể ném exception khác, trả dữ liệu khác hoặc không còn giữ invariant cũ.

### 6.1. Checked exception: binary compatible nhưng vẫn có thể đổi trải nghiệm runtime

Giả sử client đã biên dịch với method không khai báo checked exception:

```java
String value = service.load();
```

Phiên bản thư viện mới khai báo `throws IOException` và trong một số trường hợp thực sự ném exception đó. Bytecode cũ vẫn liên kết vì descriptor không đổi, nhưng exception có thể truyền ra ngoài caller.

JVM không thực thi quy tắc checked exception. Quy tắc bắt hoặc khai báo exception là kiểm tra của compiler trên source code.

Do đó, thêm checked exception thường giữ binary compatibility nhưng có thể phá source compatibility và làm thay đổi hành vi quan sát được của client cũ.

### 6.2. Thay đổi generic metadata

Generic signature thường được lưu trong metadata riêng; JVM liên kết method bằng descriptor đã xóa kiểu. Vì vậy, thay đổi tham số generic nhưng giữ erasure có thể giữ binary linkage.

Tuy nhiên, source client có thể không biên dịch, code reflection đọc generic metadata có thể thấy thay đổi, và caller dùng raw type có thể gặp lỗi kiểu ở runtime. Đừng dùng việc descriptor không đổi làm bằng chứng rằng API generic vẫn tương thích đầy đủ.

## 7. Hằng compile-time và giá trị đã được inline

Một trường `public static final` có kiểu primitive hoặc `String` và được khởi tạo bằng constant expression có thể là *constant variable*. Compiler thường inline giá trị của hằng vào bytecode client.

Phiên bản 1:

```java
public final class Limits {
    public static final int MAX_RETRIES = 3;
}
```

Client:

```java
if (attempt < Limits.MAX_RETRIES) {
    retry();
}
```

Sau khi biên dịch, bytecode client có thể chứa trực tiếp giá trị `3` thay vì đọc field `Limits.MAX_RETRIES` lúc runtime.

Nếu thư viện đổi thành:

```java
public final class Limits {
    public static final int MAX_RETRIES = 5;
}
```

client cũ vẫn có thể dùng giá trị `3` cho đến khi được biên dịch lại. JAR mới không tự thay giá trị đã inline trong file `.class` cũ.

Điều này thường không phải binary incompatibility vì field vẫn tồn tại, nhưng có thể tạo ra khác biệt hành vi giữa client cũ và client biên dịch mới.

Nếu giá trị cần thay đổi theo phiên bản thư viện hoặc cấu hình runtime, hãy cân nhắc accessor:

```java
public final class Limits {
    private Limits() {
    }

    public static int maxRetries() {
        return 5;
    }
}
```

Lời gọi method được thực hiện lúc runtime, nên client cũ có thể nhận giá trị mới mà không cần inline constant.

## 8. Thêm method mới: an toàn đến đâu?

Thêm method vào class thường giữ source và binary compatibility, nhưng vẫn cần xét method resolution và kế thừa.

### 8.1. Thêm overload có thể đổi hành vi sau khi biên dịch lại

Phiên bản cũ chỉ có:

```java
public void log(Object value) {
    System.out.println("object");
}
```

Phiên bản mới bổ sung:

```java
public void log(String value) {
    System.out.println("string");
}
```

Source cũ:

```java
log(null);
```

trước đây gọi `log(Object)`. Sau khi biên dịch lại với phiên bản mới, compiler chọn overload `log(String)` vì `String` cụ thể hơn `Object`. Source vẫn biên dịch nhưng hành vi đã thay đổi.

Bytecode cũ vẫn gọi descriptor của `log(Object)`, nên có thể tiếp tục hành xử như trước. Đây là ví dụ cho thấy thêm overload có thể giữ source compatibility và binary compatibility nhưng thay đổi hành vi sau khi recompile.

### 8.2. Method mới có thể va chạm với method kế thừa

Khi thêm method vào superclass hoặc interface, method đó có thể trở thành method được kế thừa bởi class con mà thư viện không kiểm soát. Điều này có thể:

- Làm thay đổi method được chọn khi gọi trên instance class con.
- Gây xung đột với method có cùng chữ ký nhưng quy tắc static/instance hoặc visibility khác.
- Tạo xung đột default method trong cấu trúc interface.
- Làm source class con không biên dịch lại được hoặc binary cũ gặp lỗi khi gọi.

Vì vậy, trước khi thêm method vào base class/interface công khai, hãy kiểm tra hệ thống kế thừa và implementor phổ biến, không chỉ kiểm tra class thư viện trực tiếp.

## 9. Behavioral compatibility: chương trình vẫn chạy nhưng hợp đồng có thay đổi?

Behavioral compatibility liên quan đến những gì caller có thể quan sát. Một thay đổi có thể không ảnh hưởng đến source hay binary linkage nhưng vẫn phá ứng dụng phụ thuộc vào hợp đồng cũ.

### 9.1. Thay đổi giá trị trả về

Method giữ nguyên chữ ký nhưng trả dữ liệu khác:

```java
public BigDecimal calculateTax(BigDecimal amount) {
    // Phiên bản cũ: dùng mức thuế 8%
    // Phiên bản mới: dùng mức thuế 10%
}
```

Source và binary có thể không đổi, nhưng kết quả nghiệp vụ thay đổi. Nếu mức thuế là một phần hợp đồng đã công bố, đây là behavioral change quan trọng.

### 9.2. Thay đổi exception

Một method trước đây trả về `null` khi không tìm thấy dữ liệu, nhưng phiên bản mới ném `NoSuchElementException`. Chữ ký có thể giữ nguyên; source và binary vẫn chạy, nhưng caller có thể bị lỗi nếu dựa vào hành vi cũ.

Tương tự, thay đổi loại exception, điều kiện ném exception hoặc exception xảy ra sớm hơn đều có thể là behavioral incompatibility.

### 9.3. Thay đổi quy tắc null và validation

Ví dụ method trước đây chấp nhận chuỗi rỗng nhưng phiên bản mới từ chối:

```java
public User findByName(String name) {
    Objects.requireNonNull(name);
    if (name.isBlank()) {
        throw new IllegalArgumentException("name must not be blank");
    }
    // ...
}
```

Việc siết validation có thể hợp lý, nhưng caller cũ từng truyền chuỗi rỗng có thể bị ảnh hưởng. Hãy xem quy tắc null/blank có được ghi trong tài liệu API hay chỉ là hành vi tình cờ.

### 9.4. Thay đổi thứ tự hoặc tính ổn định của kết quả

Một API trả danh sách có thể trước đây giữ thứ tự chèn, nhưng phiên bản mới trả thứ tự khác. Nếu hợp đồng không cam kết thứ tự, caller không nên phụ thuộc vào nó; tuy nhiên, thay đổi vẫn có thể làm lộ các giả định ngầm trong ứng dụng.

Nếu thứ tự là bảo đảm, cần ghi rõ trong Javadoc và kiểm thử.

### 9.5. Thay đổi side effect hoặc transaction boundary

Một method trước đây chỉ đọc dữ liệu, nay cập nhật `lastAccessedAt`; hoặc trước đây tự commit transaction, nay để caller quản lý transaction. Chữ ký không đổi nhưng side effect thay đổi, có thể ảnh hưởng logic gọi và khả năng retry.

### 9.6. Thay đổi đồng bộ, thread safety hoặc timing

API trước đây thread-safe nhưng phiên bản mới dùng mutable state không đồng bộ; hoặc callback trước đây được gọi tuần tự nhưng nay chạy trên executor khác. Đây có thể là behavioral incompatibility dù bytecode không đổi.

Các thuộc tính hiệu năng và thời gian phản hồi cũng có thể là một phần hợp đồng vận hành nếu hệ thống có SLA. Không phải mọi khác biệt hiệu năng đều là breaking change, nhưng không nên bỏ qua chúng trong thư viện nền tảng.


## 10. Ma trận ví dụ: một thay đổi ảnh hưởng những trục nào?

Bảng sau là hướng dẫn phân tích ban đầu. Kết quả chính xác còn phụ thuộc vào cấu trúc kế thừa, cách client gọi API và hợp đồng đã công bố.

| Thay đổi | Source compatibility | Binary compatibility | Behavioral compatibility |
|---|---|---|---|
| Sửa phần thân method, giữ nguyên API | Thường giữ | Thường giữ | Có thể thay đổi |
| Xóa method public | Phá | Phá nếu client tham chiếu | Không áp dụng vì client có thể không chạy |
| Đổi kiểu tham số, không giữ overload cũ | Phá | Phá | Có thể thay đổi |
| Đổi kiểu trả về | Có thể phá | Phá do descriptor đổi | Có thể thay đổi |
| Giảm visibility | Phá với caller mất quyền | Có thể phá với bytecode cũ | Có thể thay đổi |
| Thêm overload không mơ hồ | Thường giữ | Thường giữ | Có thể đổi overload được chọn khi recompile |
| Thêm overload gây mơ hồ | Phá với source liên quan | Bytecode cũ thường giữ | Có thể đổi nếu overload mới được chọn |
| Thêm checked exception | Có thể phá | Thường giữ | Có thể phát sinh exception mới |
| Thêm abstract method vào interface | Phá với implementor cần recompile | Có thể lỗi khi method mới được gọi | Có thể thay đổi |
| Đổi generic nhưng giữ erasure | Có thể phá | Thường giữ descriptor | Có thể ảnh hưởng reflection/type safety |
| Đổi giá trị constant compile-time | Thường giữ | Thường giữ | Client cũ có thể tiếp tục dùng giá trị inline |
| Đổi thứ tự kết quả | Giữ | Giữ | Có thể phá hợp đồng |
| Siết validation | Giữ | Giữ | Có thể phá caller cũ |

Không nên dùng bảng như một bộ quy tắc tuyệt đối. Nó giúp xác định câu hỏi cần kiểm tra; kết luận cuối cùng cần dựa vào JLS, bytecode, source client và test hành vi.

## 11. Kiểm thử source compatibility

Source compatibility được kiểm tra bằng cách biên dịch source client đại diện với phiên bản thư viện mới.

Một cách thực hiện có kiểm soát:

1. Lưu source client của phiên bản trước.
2. Thay dependency bằng artifact mới.
3. Biên dịch lại source cũ mà không sửa.
4. Ghi nhận lỗi compiler và warning mới.
5. Kiểm tra thêm build flag thực tế, chẳng hạn `-Werror`, annotation processor và module path.

Ví dụ:

```bash
javac -cp library-v2.jar -d client-classes src/com/example/client/App.java
```

Nếu build thực tế dùng module path:

```bash
javac --module-path mods \
  -d mods/com.example.client \
  src/com.example.client/module-info.java \
  src/com.example.client/com/example/client/App.java
```

Nên duy trì một tập source fixture nhỏ, đại diện cho cách client sử dụng API công khai:

- Gọi method và constructor phổ biến.
- Kế thừa class mở rộng.
- Implement interface.
- Sử dụng overload với `null`, lambda, method reference và generic.
- Bắt checked exception.
- Truy cập field hoặc constant được công khai.
- Dùng reflection nếu thư viện công bố metadata đó là một phần hợp đồng.

### 11.1. Biên dịch lại đúng source cũ

Nếu source fixture đã được sửa để thích nghi với API mới, test đó không còn chứng minh source compatibility. Hãy giữ một bản source baseline không chỉnh sửa và chạy nó như một bài kiểm tra độc lập.

Có thể có một bộ test khác dành cho migration guide, nhưng cần phân biệt:

- **Compatibility compile test:** source cũ phải biên dịch nguyên trạng.
- **Migration test:** source được sửa theo hướng dẫn nâng cấp phải biên dịch và hoạt động.

Hai test trả lời hai câu hỏi khác nhau.

### 11.2. Kiểm tra warning và công cụ build

Một thay đổi có thể không tạo compile error nhưng thêm deprecation warning, unchecked warning hoặc annotation warning. Nếu dự án bật `-Werror`, warning có thể khiến build thất bại.

Cũng cần kiểm tra cấu hình build thực tế: annotation processor, compiler plugin, module path, target release và các cờ lint có thể làm kết quả khác với một lệnh `javac` tối giản.

## 12. Kiểm thử binary compatibility

Binary compatibility cần một client đã biên dịch bằng thư viện cũ. Không biên dịch lại client giữa hai lần chạy.

Quy trình mẫu:

1. Biên dịch thư viện phiên bản 1.
2. Biên dịch client bằng JAR phiên bản 1.
3. Giữ nguyên các file `.class` của client.
4. Thay JAR phiên bản 1 bằng JAR phiên bản 2.
5. Chạy client cũ với JAR phiên bản 2.
6. Xác nhận không có lỗi liên kết do API đã thay đổi.

Ví dụ cấu trúc thư mục:

```text
compat-test/
├── library-v1.jar
├── library-v2.jar
├── client-src/
│   └── App.java
└── client-classes/
    └── App.class
```

Biên dịch client một lần với phiên bản 1:

```bash
javac -cp library-v1.jar -d client-classes client-src/App.java
```

Chạy bytecode cũ với thư viện mới:

```bash
java -cp library-v2.jar:client-classes App
```

Trên Windows, dùng dấu phân cách classpath `;`:

```powershell
java -cp "library-v2.jar;client-classes" App
```

Điểm quan trọng là không chạy lại `javac` sau khi thay JAR. Nếu biên dịch lại, compiler có thể phát hiện API mới và tạo bytecode mới, che mất lỗi binary compatibility.

### 12.1. Các lỗi liên kết nên nhận diện

| Lỗi | Nguyên nhân thường gặp |
|---|---|
| `NoSuchMethodError` | Method được bytecode tham chiếu không còn với descriptor tương ứng |
| `NoSuchFieldError` | Field được tham chiếu đã bị xóa hoặc đổi descriptor |
| `NoClassDefFoundError` | Class cần thiết không có mặt hoặc không thể định nghĩa |
| `IllegalAccessError` | Bytecode truy cập member không còn được phép |
| `IncompatibleClassChangeError` | Loại cấu trúc class/member không còn khớp với cách bytecode gọi |
| `AbstractMethodError` | Lời gọi cần implementation mà class runtime không cung cấp |

Không phải mọi lỗi trên đều chắc chắn do thay đổi API. Dependency thiếu, classpath trùng phiên bản hoặc module configuration sai cũng có thể gây lỗi. Hãy xác định class và member trong thông báo trước khi kết luận.

### 12.2. Kiểm tra nhiều phiên bản client

Một thư viện có thể được dùng bởi client biên dịch với nhiều JDK hoặc nhiều phiên bản thư viện khác nhau. Nếu chính sách hỗ trợ yêu cầu, hãy giữ các binary fixture từ những phiên bản client quan trọng và chạy chúng với artifact mới.

Cần kiểm soát classpath/module path để chắc chắn JVM nạp đúng JAR mới. Có thể in `CodeSource` hoặc dùng class loading diagnostics trong test khi cần điều tra xung đột dependency.

## 13. Kiểm thử behavioral compatibility

Behavioral compatibility cần test theo hợp đồng API. Không thể suy ra nó chỉ từ diff source hoặc diff bytecode.

### 13.1. Duy trì contract tests

Với mỗi API công khai, ghi nhận những điều caller được quyền kỳ vọng:

- Input hợp lệ và không hợp lệ.
- Giá trị trả về và quy tắc null.
- Exception được ném trong từng trường hợp.
- Side effect và transaction boundary.
- Thứ tự phần tử hoặc callback nếu được cam kết.
- Quy tắc đồng bộ và thread safety.
- Quy tắc charset, timezone, rounding hoặc locale nếu có liên quan.

Contract test nên mô tả các bảo đảm này bằng đầu vào và kết quả quan sát được, không phụ thuộc chi tiết triển khai nội bộ.

### 13.2. So sánh kết quả giữa phiên bản cũ và mới

Với API có thể chạy song song trên hai phiên bản, có thể dùng cùng bộ fixture để ghi nhận:

- Kết quả trả về.
- Loại exception.
- Side effect.
- Thứ tự kết quả.
- Thời gian hoặc mức sử dụng tài nguyên nếu đó là một phần SLA.

Không phải mọi output phải giống tuyệt đối. Nếu thay đổi là có chủ ý, hãy xác định trước khác biệt nào được chấp nhận và cập nhật hợp đồng, tài liệu migration cùng test tương ứng.

### 13.3. Kiểm thử trường hợp biên

Behavioral regression thường xuất hiện ở trường hợp biên hơn là happy path:

- `null`, chuỗi rỗng, số âm hoặc giá trị cực đại.
- Collection rỗng và collection có phần tử trùng.
- Input sai định dạng hoặc thiếu field.
- Timeout, retry, cancellation.
- Dữ liệu lớn hoặc đồng thời.
- Locale, timezone và charset khác nhau.

Nếu API thay đổi validation hoặc cách xử lý lỗi, cần có test rõ ràng cho các trường hợp này.

### 13.4. Phân biệt hành vi được cam kết và chi tiết triển khai

Không phải mọi hành vi quan sát được một lần đều trở thành hợp đồng. Ví dụ thứ tự iteration của một collection không cam kết có thể thay đổi mà không vi phạm API contract. Tuy vậy, nếu client thực tế phụ thuộc vào hành vi đó, thay đổi vẫn có thể gây sự cố khi triển khai.

Tài liệu API nên nói rõ phần nào được bảo đảm và phần nào không được bảo đảm. Điều này giúp client tránh phụ thuộc vào chi tiết nội bộ và giúp maintainers có không gian thay đổi implementation an toàn hơn.

## 14. Công cụ kiểm tra API và bytecode

### 14.1. Dùng javap xem descriptor

`javap` đi kèm JDK 17 có thể hiển thị chữ ký và descriptor bytecode:

```bash
javap -classpath library-v1.jar -s -p com.example.AccountService
```

- `-s` hiển thị descriptor.
- `-p` hiển thị cả member không public.
- `-classpath` chọn artifact cần kiểm tra.

Chạy lệnh cho cả phiên bản cũ và mới rồi so sánh descriptor giúp phát hiện method/field đã thay đổi ở cấp bytecode.

`javap` là công cụ quan sát class file; nó không tự đưa ra kết luận đầy đủ về behavioral compatibility hoặc mọi quy tắc source compatibility.

### 14.2. Dùng công cụ API diff

Các công cụ như **Revapi** và **japicmp** có thể so sánh API giữa hai artifact, báo cáo thay đổi class, method, field, visibility và một số dạng binary/source incompatibility.

Chúng hữu ích trong CI để phát hiện thay đổi không mong muốn trước khi publish. Cần cấu hình đúng phạm vi API công khai, module, dependency và mức độ nghiêm trọng; không nên coi mọi thay đổi được công cụ báo là breaking change trong mọi hợp đồng.

### 14.3. Dùng jdeps cho dependency analysis

`jdeps` thuộc JDK, hỗ trợ phân tích phụ thuộc class/package/module của artifact. Nó hữu ích để phát hiện phụ thuộc vào JDK internals hoặc xem module dependency, nhưng không thay thế công cụ API compatibility diff.

### 14.4. Kết hợp công cụ và test

Một quy trình kiểm tra hiệu quả có thể gồm:

- API diff để phát hiện cấu trúc API thay đổi.
- Compile fixture để kiểm tra source compatibility.
- Chạy binary fixture để kiểm tra binary compatibility.
- Contract/regression tests để kiểm tra behavioral compatibility.
- Integration tests để kiểm tra dependency, module path và cấu hình runtime.

Không một công cụ đơn lẻ nào chứng minh được cả ba loại tương thích.


## 15. Quản lý tương thích trong quy trình phát hành

Tương thích nên được xem xét từ lúc thiết kế API và trong mỗi pull request, không đợi đến khi phát hành mới kiểm tra.

### 15.1. Xác định phạm vi API công khai

Trước khi đặt chính sách tương thích, hãy xác định thành phần nào là API được hỗ trợ:

- Public/protected class, interface, method, constructor và field.
- Package được công bố trong tài liệu.
- Module package được export.
- SPI mà bên thứ ba được phép implement.
- Annotation, generic contract và metadata reflection nếu đã được cam kết.
- Định dạng dữ liệu hoặc giao thức được lưu trữ/trao đổi lâu dài.

Không phải mọi class public trong implementation đều nhất thiết là API được hỗ trợ. Có thể dùng package nội bộ hoặc module không export để giữ chi tiết triển khai, nhưng cần ghi rõ ranh giới đó.

### 15.2. Dùng deprecation làm giai đoạn chuyển tiếp

Nếu muốn thay một API đã công bố, có thể giữ API cũ và đánh dấu deprecated:

```java
@Deprecated(since = "3.1", forRemoval = true)
public User findById(long id) {
    return find(longIdToKey(id));
}
```

Javadoc nên chỉ ra API thay thế:

```java
/**
 * Finds a user by its numeric identifier.
 *
 * @deprecated Use {@link #find(String)} instead.
 */
@Deprecated(since = "3.1", forRemoval = true)
public User findById(long id) {
    return find(Long.toString(id));
}
```

Deprecation không tự bảo đảm tương thích mã nguồn hay nhị phân trong mọi trường hợp, nhưng giúp client phát hiện hướng chuyển đổi trong IDE/compiler. Chỉ xóa API khi chính sách phiên bản cho phép và có migration guide phù hợp.

### 15.3. Duy trì API baseline

Với thư viện có nhiều người dùng, lưu artifact phát hành trước đó làm baseline. Mỗi lần build có thể:

1. So sánh public API mới với baseline.
2. Báo thay đổi binary/source đáng chú ý.
3. Yêu cầu maintainer phân loại thay đổi.
4. Chạy compile fixture và binary fixture.
5. Chạy contract tests.
6. Ghi release note và migration note.

Baseline giúp tránh vô tình xóa method hoặc đổi descriptor trong một thay đổi tưởng như nội bộ.

### 15.4. Ghi rõ loại tương thích trong release note

Thay vì chỉ ghi “API compatible”, release note nên nêu cụ thể:

- Source compatibility: có yêu cầu sửa source hoặc xử lý warning mới không?
- Binary compatibility: client đã biên dịch với phiên bản nào còn được hỗ trợ?
- Behavioral compatibility: có thay đổi kết quả, exception, default, ordering hoặc side effect không?
- Migration: nếu có breaking change, cần sửa gì và vì sao?

Nếu một thay đổi cố ý phá tương thích, hãy mô tả đường nâng cấp và thời điểm loại bỏ API cũ.

## 16. SemVer và tương thích trong thư viện Java

Semantic Versioning (SemVer) là một quy ước phổ biến để truyền đạt mức độ thay đổi:

- **PATCH:** sửa lỗi tương thích với hợp đồng hiện tại.
- **MINOR:** bổ sung chức năng theo cách tương thích ngược trong phạm vi API công khai đã cam kết.
- **MAJOR:** có thay đổi không tương thích cần client điều chỉnh.

Tuy nhiên, số phiên bản không tự chứng minh compatibility. Một thay đổi nhỏ cũng có thể vô tình làm source code cũ mơ hồ; một bản major có thể vẫn giữ phần lớn API cũ. Cần có quy tắc cụ thể về public API, module, SPI và behavior mà dự án cam kết.

Với thư viện Java, nên ghi rõ dự án cam kết source compatibility, binary compatibility hay cả hai trong cùng một dòng phiên bản. Nếu hỗ trợ nhiều JDK, nêu rõ phạm vi JDK và module configuration được kiểm thử.

## 17. Quy trình đánh giá một thay đổi API

Khi review một pull request có thay đổi API, có thể đi theo trình tự:

1. **Xác định phạm vi:** member/package/module nào thuộc public API hoặc SPI?
2. **Kiểm tra source:** source client cũ có biên dịch lại không? Overload resolution, generic, checked exception và inheritance có đổi không?
3. **Kiểm tra binary:** tên, descriptor, visibility, static/instance, superclass/interface có thay đổi không?
4. **Kiểm tra hành vi:** giá trị trả về, exception, side effect, thứ tự, null handling, concurrency và timing có đổi không?
5. **Chạy công cụ:** API diff, `javap` và các kiểm tra dependency cần thiết.
6. **Chạy fixture:** compile source cũ, chạy bytecode cũ với artifact mới, chạy contract tests.
7. **Quyết định phiên bản:** xác định đây là thay đổi tương thích hay breaking change theo chính sách dự án.
8. **Cập nhật tài liệu:** Javadoc, migration guide và release note phải phản ánh hợp đồng mới.

Nếu thay đổi chỉ là sửa implementation, vẫn cần test hành vi liên quan. Nếu thay đổi descriptor, cần kiểm tra client đã biên dịch. Nếu thêm overload, cần compile lại source fixture có lời gọi mơ hồ hoặc literal như `null`.

## 18. Những hiểu nhầm thường gặp

### Hiểu nhầm 1. Source compatibility đồng nghĩa binary compatibility

Sai. Source có thể biên dịch lại sau khi API thêm overload, nhưng bytecode cũ có thể cần descriptor không còn tồn tại. Ngược lại, thêm checked exception có thể giữ binary linkage nhưng phá source cũ không biên dịch.

### Hiểu nhầm 2. Binary compatible nghĩa là ứng dụng chạy đúng như trước

Sai. Bytecode có thể liên kết thành công nhưng method trả kết quả khác, ném exception mới hoặc thay side effect.

### Hiểu nhầm 3. Giữ nguyên tên method là đủ

Sai. Descriptor bao gồm kiểu tham số và kiểu trả về; cách gọi static/instance và quyền truy cập cũng quan trọng.

### Hiểu nhầm 4. Thêm method luôn an toàn

Không phải lúc nào. Thêm overload có thể làm source cũ mơ hồ hoặc thay đổi overload được chọn sau khi recompile. Thêm method vào interface/base class có thể tác động implementor và class con.

### Hiểu nhầm 5. Thêm checked exception chỉ là thay đổi tài liệu

Sai. `throws` không nằm trong descriptor, nên binary linkage thường giữ; nhưng source client biên dịch lại có thể phải xử lý exception, và client cũ có thể quan sát exception mới lúc runtime.

### Hiểu nhầm 6. Thay đổi generic không ảnh hưởng binary nên hoàn toàn an toàn

Sai. Erasure có thể giữ descriptor, nhưng source type checking, reflection metadata và type safety vẫn có thể thay đổi.

### Hiểu nhầm 7. Công cụ API diff có thể chứng minh behavioral compatibility

Sai. Công cụ phân tích cấu trúc API không thể biết mọi hợp đồng nghiệp vụ. Cần contract tests và kiểm thử tích hợp.

### Hiểu nhầm 8. Nếu source fixture biên dịch thì không cần chạy binary fixture

Sai. Compile test kiểm tra source compatibility. Binary fixture phải được biên dịch với artifact cũ và chạy không biên dịch lại với artifact mới.

### Hiểu nhầm 9. Constant public static final luôn được đọc từ JAR mới

Sai. Constant variable có thể được compiler inline vào bytecode client. Client cũ có thể giữ giá trị cũ cho đến khi recompile.

### Hiểu nhầm 10. Version number tự nói lên compatibility

Sai. Versioning chỉ là cam kết/quy ước của dự án. Cần kiểm tra API, bytecode và behavior để xác nhận thay đổi thực tế.

## 19. Bài tập tự luyện

### Bài 1. Phân loại ba loại tương thích

Một method giữ nguyên tên và descriptor nhưng đổi kết quả từ `"A"` thành `"B"`.

**Đáp án:** Source compatibility và binary compatibility thường được giữ; behavioral compatibility thay đổi nếu caller dựa vào kết quả cũ.

### Bài 2. Thêm overload với null

Thư viện có `send(String)`. Phiên bản mới thêm `send(Integer)`. Client cũ gọi `send(null)`.

**Đáp án:** Source client có thể không biên dịch lại vì lời gọi trở nên mơ hồ. Bytecode cũ vẫn gọi descriptor `send(String)` nếu method cũ còn tồn tại.

### Bài 3. Thêm checked exception

Method `load()` bổ sung `throws IOException` nhưng giữ nguyên tên, tham số và kiểu trả về.

**Đáp án:** Binary descriptor thường không đổi nên binary compatibility được giữ. Source client có thể phải bắt hoặc khai báo exception; hành vi runtime có thể đổi nếu exception thực sự được ném.

### Bài 4. Đổi kiểu trả về

Method đổi từ `String value()` thành `CharSequence value()`.

**Đáp án:** Descriptor đổi vì JVM method descriptor có kiểu trả về. Client bytecode cũ có thể gặp `NoSuchMethodError`; source client cần được kiểm tra lại theo cách sử dụng giá trị trả về.

### Bài 5. Đổi giá trị constant

Một thư viện đổi `public static final int LIMIT = 10` thành `20`.

**Đáp án:** Client cũ có thể vẫn dùng giá trị `10` do compiler inline constant. Đây thường là khác biệt hành vi giữa client cũ và client biên dịch mới, không nhất thiết là binary incompatibility.

### Bài 6. Thêm abstract method vào interface

Một interface được bổ sung method abstract. Class cũ implement interface nhưng không định nghĩa method đó.

**Đáp án:** Source class cũ không biên dịch lại cho đến khi implement method. Binary cũ có thể được nạp, nhưng gọi method mới có thể ném `AbstractMethodError`.

### Bài 7. Kiểm tra binary compatibility

Muốn kiểm tra client đã biên dịch với library v1 có chạy với library v2 không, có nên biên dịch lại client với v2 trước khi chạy?

**Đáp án:** Không. Phải giữ nguyên bytecode được tạo với v1 và chỉ thay thư viện lúc runtime; nếu recompile, test không còn đo binary compatibility.

### Bài 8. Chọn loại test

Một thay đổi chỉ đổi thứ tự phần tử trong kết quả, không đổi chữ ký API.

**Đáp án:** Source và binary test có thể đều pass. Cần contract/behavioral test để xác định thứ tự có được cam kết hay không.

### Bài 9. Chọn công cụ

Muốn xem descriptor method trong JAR Java 17, dùng công cụ nào?

**Đáp án:** `javap -s`, thường kết hợp `-p` và `-classpath` để xem descriptor và member.

### Bài 10. Ghi release note

Một bản phát hành thêm overload mới khiến lời gọi `send(null)` trở nên mơ hồ.

**Đáp án:** Ghi rõ source incompatibility, nêu cách sửa như cast đối số sang kiểu mong muốn hoặc dùng method có tên riêng, và bổ sung compile fixture để tránh tái diễn.

## 20. Tài liệu tham khảo chính thức

- [Java Language Specification 17 — Chapter 13: Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html): các quy tắc tương thích nhị phân khi thay đổi class và interface.
- [Java Language Specification 17 — Chapter 15: Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html): overload resolution, method invocation và biểu thức ở cấp source.
- [Java Virtual Machine Specification 17 — Class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html): constant pool, field/method descriptor và cấu trúc class file.
- [JDK 17 Tool Specifications — javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): công cụ hiển thị thông tin class file và descriptor.
- [JDK 17 Tool Specifications — jdeps](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): phân tích phụ thuộc class, package và module.
- [OpenJDK Revapi](https://revapi.org/): công cụ so sánh API giữa các phiên bản artifact.
- [japicmp](https://siom79.github.io/japicmp/): công cụ so sánh API nhị phân giữa các JAR.

**Ghi nhớ:** Source compatibility hỏi source cũ có biên dịch lại được; binary compatibility hỏi bytecode cũ có liên kết được với thư viện mới; behavioral compatibility hỏi chương trình có tiếp tục giữ hợp đồng quan sát được hay không. Hãy kiểm tra cả ba: compile source fixture, chạy binary fixture được biên dịch từ bản cũ và chạy contract/regression tests. Một thay đổi chỉ an toàn khi nó đáp ứng chính sách tương thích mà thư viện đã cam kết.
