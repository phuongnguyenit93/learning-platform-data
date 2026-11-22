# Phương thức private static và ngữ cảnh gọi trong interface

## Mục tiêu

Sau bài này, bạn có thể:

- Giải thích vì sao interface cần phương thức **private static**.
- Phân biệt phương thức **private static** với phương thức **private** thông thường và phương thức **static** công khai.
- Xác định phương thức nào có thể gọi helper trong từng ngữ cảnh: static, default và instance.
- Hiểu phạm vi truy cập, khả năng kế thừa và dispatch của phương thức private trong interface.
- Viết và chạy một ví dụ Java 17 sử dụng private static helper đúng cách.

## 1. Vì sao interface có private static method?

Từ Java 9, interface được phép khai báo phương thức private, bao gồm cả dạng private static. Khả năng này giúp các phương thức public static và default dùng chung phần xử lý nội bộ mà không phải lặp code hoặc đưa helper thành API công khai.

Một interface có thể cung cấp nhiều điểm gọi:

- Phương thức public static là API được gọi bằng tên interface.
- Phương thức default là hành vi instance mà lớp triển khai nhận được.
- Phương thức private static là helper dùng chung, không phải API bên ngoài.
- Phương thức private instance là helper cần ngữ cảnh của một đối tượng.

Ví dụ, một interface có thể chuẩn hóa chuỗi ở cả phương thức static lẫn phương thức default. Phần kiểm tra null và chuẩn hóa khoảng trắng có thể đặt trong private static method để hai luồng xử lý cùng sử dụng.

## 2. Cú pháp và quy tắc

Cú pháp cơ bản:

~~~java
interface TextPolicy {
    private static String normalizeSpaces(String value) {
        return value.strip().replaceAll("\\s+", " ");
    }
}
~~~

Các quy tắc cần nhớ:

1. **Private interface methods có từ Java 9.** Khi biên dịch, source level phải từ Java 9 trở lên. Ví dụ trong bài dùng Java 17.
2. **Phương thức phải có thân hàm.** Private method trong interface không thể là abstract. Dạng private static cũng phải có phần triển khai.
3. **Private giới hạn quyền truy cập.** Chỉ code bên trong interface khai báo method mới được gọi helper đó. Lớp triển khai, lớp gọi bên ngoài và subinterface không được gọi trực tiếp.
4. **Static gắn method với interface.** Private static method không có đối tượng nhận lời gọi, không dùng được **this** hoặc **super**, và không truy cập trực tiếp thành viên instance.
5. **Không được kế thừa hoặc override.** Private method không được kế thừa bởi class triển khai hay subinterface, vì vậy nó không tham gia dispatch đa hình.
6. **Có thể overload.** Có thể khai báo nhiều private static method cùng tên nếu danh sách tham số khác nhau, theo quy tắc overload thông thường của Java.
7. **Có thể gọi helper từ nhiều method trong cùng interface.** Một private static method có thể được gọi từ public static method, default method, private instance method hoặc private static method khác của chính interface đó.

**private static** kết hợp hai ý nghĩa độc lập:

- **private**: giới hạn nơi được phép gọi.
- **static**: method không cần instance và không có **this**.

Do đó, private static helper phù hợp với xử lý dùng chung nhưng không cần trạng thái của một đối tượng.

## 3. Ngữ cảnh gọi quyết định cách dùng

### 3.1. Từ một static method trong cùng interface

Một static method có thể gọi private static helper trực tiếp:

~~~java
interface TextPolicy {
    static String normalize(String raw) {
        return normalizeSpaces(requireText(raw));
    }

    private static String requireText(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("raw must not be null");
        }
        return raw;
    }

    private static String normalizeSpaces(String value) {
        return value.strip().replaceAll("\\s+", " ");
    }
}
~~~

Ở đây, **normalize** là điểm gọi công khai. Hai method private static chỉ phục vụ quá trình xử lý nội bộ.

Code bên ngoài gọi API bằng tên interface:

~~~java
String result = TextPolicy.normalize("  Java   17  ");
~~~

Kết quả là **Java 17**.

### 3.2. Từ default method hoặc private instance method

Một default method có ngữ cảnh instance nên có thể gọi private instance helper. Private instance helper vẫn có thể gọi private static helper vì static helper không cần receiver.

~~~java
interface TextPolicy {
    default String toDisplayText(String raw) {
        return "[" + clean(raw) + "]";
    }

    private String clean(String raw) {
        return normalizeSpaces(requireText(raw));
    }

    private static String requireText(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("raw must not be null");
        }
        return raw;
    }

    private static String normalizeSpaces(String value) {
        return value.strip().replaceAll("\\s+", " ");
    }
}
~~~

Luồng gọi:

1. Code gọi **toDisplayText** trên một instance triển khai interface.
2. Default method gọi private instance method **clean**.
3. **clean** gọi hai private static helper để kiểm tra và chuẩn hóa dữ liệu.
4. Kết quả được trả về cho default method.

Cách tổ chức này giữ phần xử lý chung trong interface, trong khi helper instance vẫn có thể dùng ngữ cảnh của đối tượng nếu cần.

### 3.3. Từ bên ngoài interface hoặc lớp triển khai

Private static helper không phải thành viên API có thể truy cập từ bên ngoài. Các lời gọi sau không hợp lệ:

~~~java
TextPolicy.requireText("Java");       // Lỗi: method private
BasicTextPolicy.requireText("Java");  // Lỗi: method không được kế thừa
~~~

Lớp triển khai chỉ sử dụng các method mà interface công khai, chẳng hạn default method. Nó không thể gọi hoặc override private helper.

Với static method công khai của interface, dùng tên interface:

~~~java
TextPolicy.normalize("  Java   17  ");
~~~

Static method khai báo trong interface không được kế thừa như instance method. Vì vậy, hãy gọi nó qua interface đã khai báo method, không gọi qua tên lớp triển khai.

## 4. Ví dụ hoàn chỉnh có thể chạy

Tạo file **PrivateStaticInterfaceDemo.java**:

~~~java
interface TextPolicy {

    // API công khai ở cấp interface.
    static String normalize(String raw) {
        return normalizeSpaces(requireText(raw));
    }

    // Hành vi instance mà lớp triển khai nhận được.
    default String toDisplayText(String raw) {
        return "[" + clean(raw) + "]";
    }

    // Helper instance: chỉ được gọi bên trong TextPolicy.
    private String clean(String raw) {
        return normalizeSpaces(requireText(raw));
    }

    // Helper static: không phụ thuộc vào instance.
    private static String requireText(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("raw must not be null");
        }
        return raw;
    }

    // Có thể dùng từ cả static và instance method trong interface.
    private static String normalizeSpaces(String value) {
        return value.strip().replaceAll("\\s+", " ");
    }
}

final class BasicTextPolicy implements TextPolicy {
    // Không cần triển khai lại default method.
}

public class PrivateStaticInterfaceDemo {

    public static void main(String[] args) {
        String normalized = TextPolicy.normalize("  Java   9  ");

        TextPolicy policy = new BasicTextPolicy();
        String displayText = policy.toDisplayText("  private   static  ");

        System.out.println(normalized);
        System.out.println(displayText);
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 PrivateStaticInterfaceDemo.java
java PrivateStaticInterfaceDemo
~~~

Output chính xác:

~~~text
Java 9
[private static]
~~~

Điều cần quan sát:

- **TextPolicy.normalize** được gọi qua tên interface và gọi hai private static helper.
- **toDisplayText** là default method, nên được gọi trên instance **policy**.
- **toDisplayText** gọi private instance helper **clean**.
- **clean** tiếp tục gọi private static helper.
- **BasicTextPolicy** không nhìn thấy và không cần triển khai các helper private.

## 5. Phân biệt các loại method

| Loại method | Có instance receiver? | Nơi được gọi | Có được lớp triển khai kế thừa? |
|---|---|---|---|
| **public static** trong interface | Không | Bên ngoài qua tên interface; bên trong interface | Không |
| **private static** trong interface | Không | Chỉ trong interface khai báo nó | Không |
| **default** trong interface | Có | Qua instance; được code trong interface sử dụng | Có |
| **private** instance trong interface | Có | Chỉ trong interface khai báo nó | Không |

Điểm quan trọng là static và private giải quyết hai vấn đề khác nhau. Static xác định method không phụ thuộc instance; private xác định method không được dùng như API bên ngoài.

## 6. Những lỗi dễ gặp

### Gọi private helper từ lớp triển khai

Không thể gọi private static helper bằng tên interface hoặc tên lớp triển khai từ code bên ngoài. Quyền truy cập private vẫn được áp dụng dù method là static.

### Nhầm static method của interface với static method của class

Static method trong interface không được lớp triển khai kế thừa. Nếu API là **TextPolicy.normalize**, hãy gọi **TextPolicy.normalize(...)**. Không giả định rằng **BasicTextPolicy.normalize(...)** tồn tại.

### Gọi private instance method từ static context

Static method không có **this**, nên không thể gọi trực tiếp private instance helper. Nếu xử lý cần dữ liệu instance, hãy để nó trong default/instance method hoặc truyền một đối tượng phù hợp vào helper static.

### Dùng private static cho xử lý cần trạng thái instance

Private static method không thể đọc trực tiếp trạng thái instance. Nếu logic cần gọi method instance hoặc cần ngữ cảnh đối tượng, dùng private instance method.

### Đưa helper thành public chỉ để tái sử dụng nội bộ

Nếu helper chỉ phục vụ các method của một interface, public sẽ mở rộng API không cần thiết. Private static giữ helper ở phạm vi nội bộ và cho phép thay đổi triển khai mà không buộc caller phụ thuộc vào helper đó.

## 7. Khi nào nên dùng?

Dùng **private static** khi:

- Nhiều method trong cùng interface cần chung một đoạn xử lý.
- Logic helper không phụ thuộc vào instance.
- Không muốn công khai helper như một phần API.
- Cần chia nhỏ một static method hoặc default method để code dễ đọc và dễ bảo trì.

Dùng **private instance** khi helper cần ngữ cảnh instance hoặc cần gọi các hành vi instance khác của interface.

Dùng **public static** khi method thực sự là API cấp interface mà code bên ngoài cần gọi.

Không cần tạo private static method cho một biểu thức đơn giản chỉ xuất hiện một lần nếu việc tách method làm code khó đọc hơn. Mục tiêu là đặt đúng ranh giới trách nhiệm và quyền truy cập.

## 8. Checklist

- [ ] Project dùng Java 9 trở lên.
- [ ] Private static method có thân hàm.
- [ ] Helper chỉ được gọi từ bên trong interface khai báo nó.
- [ ] Static helper không dùng **this**, **super** hoặc truy cập trực tiếp instance member.
- [ ] Caller bên ngoài sử dụng public API của interface.
- [ ] Không giả định private/static interface method được lớp triển khai kế thừa.
- [ ] Dùng private instance method khi logic thực sự cần ngữ cảnh instance.

