# Lỗi biên dịch khi kiểu nguồn đã là subtype của kiểu pattern

## 1. Khi nào type pattern bị xem là luôn khớp?

Trong pattern matching for instanceof, trình biên dịch xét **kiểu tĩnh của biểu thức nguồn** và kiểu được khai báo trong pattern. Nếu kiểu tĩnh nguồn đã là subtype của kiểu pattern, pattern được xem là *unconditional* (luôn khớp theo quan hệ kiểu) và Java từ chối biểu thức type pattern đó.

Ví dụ:

~~~java
String title = "Java";

// Lỗi biên dịch: kiểu nguồn String đã là String.
// if (title instanceof String text) {
//     System.out.println(text);
// }
~~~

Kiểu nguồn và kiểu pattern đều là String. Biến title đã có kiểu tĩnh đủ cụ thể, nên pattern không cung cấp thêm thông tin kiểu nào. Tính năng pattern matching for instanceof được chuẩn hóa từ Java 16 theo JEP 394 và áp dụng quy tắc này trong cú pháp ổn định.

## 2. Không chỉ kiểu giống hệt nhau mới bị từ chối

Lỗi không chỉ xảy ra khi kiểu nguồn trùng với kiểu pattern. Nếu kiểu nguồn là subtype của kiểu pattern, pattern cũng luôn đúng theo quan hệ kiểu và bị từ chối.

~~~java
String title = "Java";

// Lỗi biên dịch: String triển khai CharSequence.
// if (title instanceof CharSequence chars) {
//     System.out.println(chars.length());
// }

// Lỗi biên dịch: mọi String đều là Object.
// if (title instanceof Object object) {
//     System.out.println(object);
// }
~~~

Các quan hệ kiểu trong ví dụ:

- String là chính nó.
- String triển khai CharSequence.
- Mọi String đều là Object.

Do đó, theo quan hệ kiểu, mọi giá trị không null của String title đều thuộc cả ba kiểu. Quy tắc unconditional được xác định từ kiểu tĩnh; trình biên dịch không cho phép dùng type pattern để khai báo lại một kiểu đã được bảo đảm, kể cả khi biến tham chiếu vẫn có thể chứa null. Nếu mục tiêu là kiểm tra null, hãy dùng điều kiện null tường minh.

Một ví dụ khác với lớp con và lớp cha:

~~~java
Integer count = 10;

// Lỗi biên dịch: Integer là subtype của Number.
// if (count instanceof Number number) {
//     System.out.println(number.doubleValue());
// }
~~~

Integer kế thừa Number, nên biến Integer count đã có thể sử dụng các thành viên của Number. Nếu muốn dùng một biến có kiểu Number để truyền vào API hoặc đặt tên khác, hãy khai báo/gán biến thông thường:

~~~java
Number number = count;
System.out.println(number.doubleValue());
~~~

## 3. Hướng quan hệ kiểu quyết định kết quả

Điều quan trọng là xác định kiểu nào là subtype của kiểu nào. Pattern không bị từ chối chỉ vì hai kiểu có liên quan; nó bị từ chối trong trường hợp kiểu nguồn đã là subtype của kiểu pattern.

### 3.1. Nguồn rộng hơn pattern: có thể hợp lệ

~~~java
Object candidate = "Java";

if (candidate instanceof String text) {
    System.out.println(text.toUpperCase());
}
~~~

Kiểu tĩnh nguồn là Object, còn kiểu pattern là String. Một biến Object có thể tham chiếu đến String, nhưng cũng có thể tham chiếu đến các đối tượng không phải chuỗi. Vì vậy, phép kiểm tra có ý nghĩa và được biên dịch; đối tượng thực tế quyết định điều kiện đúng hay sai.

Tương tự, một nguồn kiểu giao diện rộng hơn có thể được kiểm tra với một lớp triển khai:

~~~java
CharSequence input = new StringBuilder("Java");

if (input instanceof String text) {
    System.out.println(text.toUpperCase());
} else {
    System.out.println("Không phải String");
}
~~~

CharSequence có thể được triển khai bởi StringBuilder, StringBuffer và String. Vì vậy, kiểu tĩnh CharSequence không bảo đảm nguồn là String; pattern String text có thể khớp hoặc không khớp khi chạy.

### 3.2. Nguồn hẹp hơn pattern: bị từ chối

~~~java
String input = "Java";

// Lỗi biên dịch: String là subtype của CharSequence.
// if (input instanceof CharSequence chars) { ... }
~~~

Ở đây hướng quan hệ bị đảo ngược so với ví dụ trước. Nguồn đã là String, một kiểu con của CharSequence. Không cần kiểm tra lại để xác nhận điều mà kiểu tĩnh đã bảo đảm.

### 3.3. Giao diện con và giao diện cha

Quy tắc tương tự áp dụng cho kế thừa giữa các interface:

~~~java
interface Resource {
}

interface ReadableResource extends Resource {
}

class ResourceExample {
    static void inspect(ReadableResource resource) {
        // Lỗi biên dịch: ReadableResource là subtype của Resource.
        // if (resource instanceof Resource parent) { ... }
    }
}
~~~

Mọi ReadableResource đều là Resource. Nếu phương thức nhận một ReadableResource, biến tham số đã có thể dùng ở nơi yêu cầu Resource:

~~~java
interface Resource {
}

interface ReadableResource extends Resource {
}

class ResourceUsageExample {
    static void acceptResource(Resource resource) {
        System.out.println("Đã nhận resource");
    }

    static void useReadable(ReadableResource readable) {
        acceptResource(readable);
    }
}
~~~

### 3.4. Bảng hướng quan hệ

| Kiểu tĩnh nguồn | Kiểu pattern | Kết quả |
| --- | --- | --- |
| Object | String text | Hợp lệ; nguồn rộng hơn pattern |
| CharSequence | String text | Hợp lệ; có thể khớp hoặc không khi chạy |
| String | String text | Lỗi biên dịch; kiểu trùng nhau |
| String | CharSequence chars | Lỗi biên dịch; nguồn là subtype |
| String | Object object | Lỗi biên dịch; nguồn là subtype |
| Number | Integer number | Hợp lệ; có thể là Integer hoặc subtype khác |
| Integer | Number number | Lỗi biên dịch; nguồn là subtype |
| ReadableResource | Resource parent | Lỗi biên dịch; interface nguồn mở rộng interface pattern |

## 4. Phân biệt type pattern với phép instanceof chỉ trả về boolean

Một điểm dễ gây nhầm lẫn là phép kiểm tra instanceof truyền thống không có pattern variable vẫn có thể được dùng khi kiểu nguồn là subtype của kiểu kiểm tra:

~~~java
class InstanceofBooleanDemo {
    static boolean isText(String value) {
        return value instanceof String;
    }

    static boolean isSequence(String value) {
        return value instanceof CharSequence;
    }
}
~~~

Hai phương thức trên hợp lệ. Chúng trả về false nếu value là null và trả về true nếu giá trị là một chuỗi không null.

Nhưng khi thêm pattern variable, biểu thức có quy tắc khác:

~~~java
class InvalidPatternExample {
    static void printText(String value) {
        // Lỗi biên dịch: pattern String text là unconditional với nguồn String.
        // if (value instanceof String text) {
        //     System.out.println(text);
        // }
    }
}
~~~

Lý do là type pattern không chỉ tính một giá trị boolean; nó còn khai báo biến mới có kiểu cụ thể và phạm vi sử dụng được kiểm soát theo luồng điều khiển. Nếu kiểu nguồn đã là subtype của kiểu pattern, biến mới không đem lại thông tin kiểu bổ sung. Quy tắc Java 16 từ chối trường hợp này để tránh pattern binding dư thừa.

Lưu ý: phép kiểm tra value instanceof String vẫn kiểm tra được trường hợp null, còn việc một pattern bị xem là unconditional được xác định theo quan hệ kiểu tĩnh của Java. Không nên suy luận rằng type pattern được phép chỉ vì biến nguồn có thể chứa null.

## 5. Nếu mục tiêu là kiểm tra null, hãy kiểm tra null

Trong nhiều trường hợp, lập trình viên viết pattern dư thừa vì muốn chắc chắn biến có giá trị khác null. Nếu kiểu nguồn đã là String, cách rõ ràng là:

~~~java
class NullCheckDemo {
    static void printText(String value) {
        if (value != null) {
            System.out.println(value.toUpperCase());
        }
    }
}
~~~

Hoặc kết hợp điều kiện nghiệp vụ:

~~~java
class TextValidation {
    static boolean isUsefulText(String value) {
        return value != null
                && !value.isBlank()
                && value.length() <= 100;
    }
}
~~~

Toán tử && đánh giá ngắn mạch. Nếu value == null, các điều kiện tiếp theo không được đánh giá, nên không có lời gọi phương thức trên tham chiếu null.

Nếu cần dùng một interface mà kiểu nguồn đã triển khai, hãy gán hoặc truyền trực tiếp:

~~~java
class InterfaceUseDemo {
    static void write(CharSequence text) {
        System.out.println(text.length());
    }

    static void process(String value) {
        if (value != null) {
            write(value);
        }
    }
}
~~~

String đã triển khai CharSequence; không cần pattern để chứng minh lại quan hệ đó.

## 6. Khi nguồn thực sự có kiểu tổng quát, type pattern vẫn hữu ích

Type pattern phù hợp khi kiểu tĩnh nguồn chưa cho biết kiểu cụ thể:

~~~java
class GenericFormatDemo {
    static String format(Object value) {
        if (value instanceof String text) {
            return text.strip();
        }
        if (value instanceof Number number) {
            return number.toString();
        }
        return "Kiểu khác";
    }
}
~~~

Ở đây value có kiểu Object. Pattern String text và Number number đều có thể kiểm tra các khả năng cụ thể tại runtime.

Nếu dữ liệu ban đầu đã có kiểu String, việc đổi sang Object chỉ để ép trình biên dịch chấp nhận pattern thường làm mã khó hiểu:

~~~java
String value = "Java";
Object candidate = value;

if (candidate instanceof String text) {
    System.out.println(text);
}
~~~

Đoạn này hợp lệ vì kiểu tĩnh của candidate là Object. Tuy nhiên, nếu mục tiêu chỉ là kiểm tra null hoặc sử dụng chuỗi, hãy thao tác trực tiếp trên value. Chỉ giữ kiểu tổng quát khi ranh giới API hoặc mô hình dữ liệu thực sự yêu cầu nó.

## 7. Cách đọc và sửa lỗi compiler

Khi gặp lỗi với pattern variable, hãy kiểm tra theo thứ tự:

1. Xác định kiểu tĩnh của biểu thức ngay bên trái instanceof. Đừng chỉ nhìn giá trị khởi tạo hoặc lớp runtime mà bạn đang kỳ vọng.
2. Xác định kiểu pattern ở bên phải.
3. Kiểm tra quan hệ subtype: nếu kiểu nguồn đã là subtype của kiểu pattern, pattern bị xem là unconditional và không hợp lệ.
4. Nếu chỉ cần loại trừ null, thay pattern bằng điều kiện value != null.
5. Nếu cần hành vi của interface hoặc lớp cha, dùng trực tiếp biến nguồn trong lời gọi hoặc phép gán.
6. Nếu nguồn thực sự là Object hoặc một kiểu tổng quát, giữ pattern để kiểm tra kiểu cụ thể tại runtime.

| Mục tiêu | Cách viết phù hợp |
| --- | --- |
| Xác nhận một Object là chuỗi và lấy biến String | value instanceof String text |
| Kiểm tra một biến String khác null | value != null |
| Gọi hành vi của CharSequence từ String | Truyền trực tiếp String vào tham số CharSequence |
| Chuyển biến Integer sang góc nhìn Number | Number number = integer; |
| Kiểm tra một CharSequence có thực sự là String | value instanceof String text |

**Ghi nhớ:** Type pattern bị từ chối khi kiểu tĩnh của nguồn đã là subtype của kiểu pattern, kể cả khi hai kiểu không giống hệt nhau mà có quan hệ qua lớp cha hoặc interface. Nếu chỉ cần kiểm tra null, hãy kiểm tra null; nếu cần kiểm tra kiểu cụ thể của dữ liệu tổng quát, type pattern vẫn là công cụ phù hợp.
