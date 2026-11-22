# Thay đổi chữ ký, kiểu trả về và `throws`: ảnh hưởng đến bên sử dụng API Java

Khi API Java thay đổi, mã nguồn thư viện có thể biên dịch thành công nhưng các ứng dụng sử dụng thư viện vẫn có thể không biên dịch, không liên kết được với bytecode mới hoặc chạy với hành vi khác. Cần đánh giá ba khía cạnh: **source compatibility** (tương thích mã nguồn), **binary compatibility** (tương thích nhị phân) và **behavioral compatibility** (tương thích hành vi).

Bài này tập trung vào việc đổi tham số, kiểu trả về và mệnh đề `throws`, đặc biệt đối với phương thức public/protected và interface được dùng giữa các module.

## 1. Kiểm tra tương thích ở ba thời điểm

Đổi API cần ba phép thử riêng: **source compatibility** khi biên dịch lại client, **binary compatibility** khi chạy bytecode client cũ với thư viện mới, và **behavioral compatibility** khi đối chiếu kết quả/ngoại lệ với hợp đồng đã công bố. Ở bài này, khác biệt giữa chữ ký Java, descriptor JVM và mệnh đề `throws` là nguyên nhân khiến ba phép thử có thể cho kết luận khác nhau.

## 2. Chữ ký phương thức gồm những gì?

Trong Java, chữ ký dùng để phân biệt các phương thức dựa trên **tên phương thức, tham số kiểu (nếu có) và kiểu các tham số hình thức**. Tên biến tham số không thuộc chữ ký; kiểu trả về và mệnh đề `throws` không dùng để phân biệt overload.

```java
String find(long id)
String find(String id) // overload hợp lệ: tham số khác kiểu
```

Hai khai báo cùng tên và cùng tham số nhưng khác kiểu trả về không thể cùng tồn tại:

```java
String find(long id)
Product find(long id) // Không thể overload chỉ bằng kiểu trả về
```

Trong bytecode, descriptor của phương thức JVM có chứa kiểu tham số và kiểu trả về, nhưng không chứa mệnh đề `throws`. Điều này giải thích vì sao đổi kiểu trả về có thể khiến bytecode cũ không tìm thấy phương thức, trong khi đổi `throws` thường không làm thay đổi liên kết nhị phân.

## 3. Đổi kiểu tham số

Giả sử API v1 khai báo:

```java
public User findUser(long id)
```

Nếu v2 chỉ còn `findUser(String id)`, client gọi `findUser(42L)` sẽ không biên dịch với API mới. Bytecode cũ cũng yêu cầu descriptor có tham số `long`; nếu descriptor đó biến mất, lời gọi có thể gặp `NoSuchMethodError` khi chạy.

Một lộ trình ít gián đoạn hơn là giữ phương thức cũ làm cầu nối và thêm overload:

```java
public User findUser(long id) {
    return findUser(Long.toString(id));
}

public User findUser(String id) {
    return lookupByTextId(id);
}
```

Đây là ví dụ cấu trúc; `User` và `lookupByTextId` cần được định nghĩa theo ứng dụng. Giữ phương thức cũ cho client hiện tại thời gian di trú, sau đó có thể đánh dấu nó bằng `@Deprecated` và chỉ loại bỏ trong phiên bản có chủ đích.

Thêm overload cũng có thể làm mã nguồn cũ trở nên mơ hồ. Chẳng hạn, thêm overload nhận `Integer` cạnh overload nhận `String` có thể khiến lời gọi `findUser(null)` không còn chọn được duy nhất một phương thức. Khi thay đổi overload, kiểm tra lời gọi có `null`, lambda, method reference và boxing/unboxing.

## 4. Đổi kiểu trả về

Giả sử v1 cung cấp:

```java
public String findName(String id)
```

Nếu đổi trực tiếp thành `public Product findName(String id)`, client đang gán kết quả vào `String` có thể không biên dịch. Java không cho phép giữ hai phương thức cùng tên và cùng tham số chỉ khác kiểu trả về.

Thay đổi này cũng có thể phá tương thích nhị phân: kiểu trả về thuộc descriptor JVM. Bytecode cũ gọi descriptor trả về `String`; descriptor mới trả về `Product` không tự thay thế descriptor cũ. Nếu phương thức cũ không còn, client có thể gặp `NoSuchMethodError`.

Cách migration an toàn hơn là thêm phương thức mới với tên rõ nghĩa, giữ phương thức cũ làm cầu nối và đánh dấu nó deprecated:

```java
@Deprecated(since = "2.0", forRemoval = false)
public String findName(String id) {
    Product product = findProduct(id);
    return product == null ? null : product.name();
}

public Product findProduct(String id) {
    return lookupProduct(id);
}
```

Đây là ví dụ minh họa; `Product` giả định có accessor `name()` (ví dụ một record), còn `lookupProduct` phải được triển khai thực tế. Hãy xác định rõ hành vi khi không tìm thấy dữ liệu: `null`, `Optional` hay ngoại lệ. Không nên âm thầm thay đổi quy tắc đó trong một bản nâng cấp.

Java cho phép kiểu trả về hiệp biến khi ghi đè (return type mới là kiểu con phù hợp của kiểu cũ); trình biên dịch có thể tạo bridge method để hỗ trợ liên kết. Đây là trường hợp đặc biệt, không có nghĩa mọi thay đổi kiểu trả về đều an toàn. Với generic, thay đổi tham số kiểu nhưng giữ nguyên erasure có thể vẫn liên kết ở bytecode nhưng gây lỗi biên dịch hoặc lỗi ép kiểu lúc chạy.

## 5. Đổi mệnh đề `throws`

Mệnh đề `throws` khai báo các checked exception mà phương thức có thể ném. Nó không thuộc chữ ký dùng để overload và không nằm trong descriptor JVM, nhưng ảnh hưởng đến việc biên dịch mã nguồn.

### Thêm checked exception

Nếu API đổi từ:

```java
public String load(String id)
```

sang:

```java
public String load(String id) throws IOException
```

caller biên dịch lại có thể phải bắt `IOException` hoặc khai báo tiếp nó bằng `throws`. Các lớp triển khai và phương thức override cũng phải được rà soát; override không được khai báo checked exception rộng hơn mức hợp đồng của phương thức cha cho phép.

Vì descriptor không đổi, việc chỉ thêm `throws IOException` thường không phá liên kết nhị phân. Tuy nhiên, nếu phiên bản mới thật sự ném `IOException`, bytecode client cũ chưa xử lý ngoại lệ có thể để nó thoát ra lúc chạy. JVM không thực thi quy tắc checked exception thay cho trình biên dịch.

### Bỏ checked exception hoặc thêm unchecked exception

Bỏ checked exception thường không đổi descriptor, nhưng khi biên dịch lại client, khối `catch` chỉ bắt ngoại lệ đó có thể không còn hợp lệ nếu không còn thao tác nào trong `try` có thể ném nó. Kiểm tra cả caller lẫn các lớp override.

Các ngoại lệ như `IllegalArgumentException` và `IllegalStateException` không cần khai báo trong `throws`. Bắt đầu ném chúng thường không buộc caller sửa mã để biên dịch, nhưng vẫn có thể phá tương thích hành vi nếu client dựa vào kết quả bình thường hoặc loại lỗi khác.

## 6. Ví dụ Java 17+: thêm API mới và giữ API cũ

Ví dụ sau giữ phương thức cũ trả về tên `String`, đồng thời thêm phương thức mặc định trả về `Product` và khai báo `IOException`. Vì phương thức mới là `default`, lớp triển khai cũ không phải lập tức bổ sung một phương thức abstract mới.

Lưu vào `ApiEvolutionDemo.java`:

```java
import java.io.IOException;

public class ApiEvolutionDemo {
    @SuppressWarnings("deprecation")
    public static void main(String[] args) throws IOException {
        CatalogApi api = new InMemoryCatalogApi();

        System.out.println(api.findName("42"));
        System.out.println(api.findProduct("42"));

        try {
            api.findProduct("missing");
        } catch (IOException ex) {
            System.out.println("Lookup failed: " + ex.getMessage());
        }
    }
}

interface CatalogApi {
    @Deprecated(since = "2.0", forRemoval = false)
    String findName(String id);

    @SuppressWarnings("deprecation")
    default Product findProduct(String id) throws IOException {
        String name = findName(id);
        if (name == null) {
            throw new IOException("No product for id " + id);
        }
        return new Product(id, name);
    }
}

record Product(String id, String name) {}

final class InMemoryCatalogApi implements CatalogApi {
    @Override
    public String findName(String id) {
        return "42".equals(id) ? "Keyboard" : null;
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac --release 17 ApiEvolutionDemo.java
java ApiEvolutionDemo
```

Đầu ra của chương trình:

```text
Keyboard
Product[id=42, name=Keyboard]
Lookup failed: No product for id missing
```

Client cũ vẫn có thể gọi `findName`; client mới có thể chuyển sang `findProduct` và xử lý `IOException`. Đây là chiến lược chuyển tiếp minh họa. Trong hệ thống thực tế, nếu dữ liệu cũ không đủ để tạo `Product`, phương thức mặc định không phù hợp; hãy triển khai chiến lược migration dựa trên ngữ nghĩa thật của API.

## 7. Phân biệt sửa chữ ký với thêm phương thức mới

Thay đổi kiểu tham số hoặc kiểu trả về của phương thức đã phát hành có thể làm biến mất descriptor mà bytecode cũ tham chiếu. Ngược lại, thêm abstract hoặc default method vẫn giữ descriptor của các phương thức cũ, nhưng có rủi ro riêng: lớp triển khai có thể thiếu implementation, hoặc cây kế thừa phát sinh xung đột. Vì vậy, khi cần tính năng mới hãy đánh giá phương thức bổ sung hoặc interface con trước khi sửa trực tiếp chữ ký cũ.

## 8. Bảng tổng hợp tác động

| Thay đổi | Mã nguồn | Bytecode cũ | Cách giảm rủi ro |
|---|---|---|---|
| Đổi kiểu tham số | Lời gọi cũ có thể không biên dịch | Descriptor cũ có thể biến mất; có thể gặp `NoSuchMethodError` | Giữ phương thức cũ, thêm overload chuyển tiếp |
| Đổi kiểu trả về | Client dùng kiểu cũ có thể không biên dịch | Descriptor gồm kiểu trả về; có thể gặp `NoSuchMethodError` | Thêm phương thức mới có tên rõ nghĩa; deprecate phương thức cũ |
| Thêm checked exception vào `throws` | Caller có thể phải bắt hoặc khai báo ngoại lệ | Descriptor không đổi; thường vẫn liên kết | Cân nhắc API mới, cập nhật hướng dẫn và kiểm thử runtime |
| Bỏ checked exception | Một số `catch` có thể không còn hợp lệ khi biên dịch lại | Descriptor không đổi | Rà soát và cập nhật caller |
| Bắt đầu ném unchecked exception | Thường vẫn biên dịch | Thường vẫn liên kết | Coi là thay đổi hành vi, cập nhật hợp đồng |
| Thêm abstract method vào interface | Implementation có thể phải sửa | Gọi phương thức mới trên implementation cũ có thể lỗi | Dùng default method khi ngữ nghĩa phù hợp hoặc tạo interface mở rộng |
| Thêm overload | Một số lời gọi có thể trở nên mơ hồ | Thường giữ descriptor cũ | Kiểm tra `null`, lambda, method reference và overload resolution |

Đây là hướng dẫn chung. Kết quả cụ thể còn phụ thuộc descriptor trước/sau, erasure của generic, quan hệ kế thừa và bridge method mà trình biên dịch tạo.

## 9. Quy trình kiểm tra trước khi phát hành

1. **Liệt kê hợp đồng bị thay đổi:** phương thức public/protected, interface, tham số, kiểu trả về, checked exception và generic.
2. **Biên dịch lại client mẫu:** bao gồm caller xử lý ngoại lệ, lời gọi overload và các lớp tự triển khai interface.
3. **Kiểm tra nhị phân:** nếu ứng dụng không được biên dịch lại cùng thư viện, chạy smoke test với bytecode từ phiên bản trước và kiểm tra descriptor còn cần thiết.
4. **Kiểm tra hành vi:** xác minh kết quả, trường hợp không tìm thấy, loại ngoại lệ và tình huống biên.
5. **Tạo giai đoạn chuyển tiếp:** giữ phương thức cũ khi có thể, thêm overload hoặc phương thức mới, đánh dấu `@Deprecated`, công bố kế hoạch loại bỏ và hướng dẫn di trú.
6. **Loại bỏ có chủ đích:** trước khi xóa API cũ, tìm cách sử dụng trong repository, xem xét phụ thuộc đã phát hành và ghi rõ thay đổi trong release notes.

## 10. Checklist

- [ ] Thay đổi tham số có làm mất descriptor cũ không?
- [ ] Kiểu trả về có đổi trực tiếp hoặc đổi generic/erasure không?
- [ ] Checked exception mới có làm caller hoặc override phải sửa không?
- [ ] Overload mới có làm lời gọi `null`, lambda hoặc method reference mơ hồ không?
- [ ] Interface có thêm abstract method mà nhiều implementation phải hỗ trợ không?
- [ ] Đã thử cả biên dịch client mới và chạy bytecode cũ chưa?
- [ ] Có phương thức chuyển tiếp, `@Deprecated` và hướng dẫn migration khi cần không?

## Tài liệu tham khảo

- [Java Language Specification 17 — Method Signatures](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.4.2)
- [Java Language Specification 17 — Binary Compatibility](https://docs.oracle.com/javase/specs/jls/se17/html/jls-13.html)
- [Java Virtual Machine Specification 17 — Descriptors](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.3)
