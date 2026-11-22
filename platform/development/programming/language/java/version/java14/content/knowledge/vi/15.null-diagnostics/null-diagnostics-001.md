# Mục đích của thông báo NullPointerException chi tiết trong Java hiện đại

> **Bối cảnh:** Java 14 → **Chẩn đoán null**. Java 14 đưa vào **Helpful NullPointerExceptions** qua **JEP 358**: khi JVM phát sinh `NullPointerException` (NPE) do một thao tác dùng tham chiếu null, thông báo có thể nêu **thao tác nào thất bại** và **biểu thức nào là null**. Trên HotSpot, cơ chế này được bật mặc định từ **Java 15** và tiếp tục hữu ích trong Java hiện đại. Bài chỉ sử dụng kiến thức còn áp dụng ngày nay, với JDK được cập nhật như JDK 21/25, không cần chạy JDK 14 cũ hay dùng tính năng preview.

## 1. Mục đích học tập

Sau bài này, bạn sẽ:

1. Hiểu vì sao stack trace cho biết dòng lỗi nhưng có thể chưa chỉ ra **tham chiếu null chính xác** trên dòng có nhiều lời gọi.
2. Đọc được cách Helpful NPE bổ sung hai nhóm thông tin: **hành động không thực hiện được** và **tham chiếu null trực tiếp gây ra lỗi**.
3. Nhận diện các trường hợp gọi phương thức, đọc/ghi field, truy cập mảng, unboxing hoặc dùng monitor trên null.
4. Phân biệt NPE **do JVM tự ném** với NPE **được code tự tạo**, bao gồm `Objects.requireNonNull`.
5. Hiểu giới hạn: nguyên văn thông báo phụ thuộc JVM, bytecode và debug metadata; `getMessage()` vẫn có thể trả `null`.
6. Biết tận dụng thông báo để tìm **nguyên nhân gốc trong nghiệp vụ**, thay vì chỉ chặn exception.
7. Thiết kế kiểm thử không phụ thuộc wording của JVM và không làm lộ chi tiết nội bộ qua API/log công khai.

## 2. Tại sao cần thông báo NPE chi tiết?

Giả sử có dòng:

~~~java
int size = order.customer().address().city().length();
~~~

Đây là **mảnh code minh họa** trong một ứng dụng có các kiểu `Order`, `Customer` và `Address`.

Một NPE có thể xảy ra vì:

- `order` là null → không gọi được `customer()`.
- `order.customer()` trả null → không gọi được `address()`.
- `order.customer().address()` trả null → không gọi được `city()`.
- `order.customer().address().city()` trả null → không gọi được `length()`.

**Stack trace** thường chỉ tới một phương thức, tệp và số dòng, nhưng cả bốn phép dereference đều nằm trên một dòng. Nếu chỉ thấy `NullPointerException at Example.java:12`, người sửa lỗi vẫn phải lần từng giá trị.

Helpful NPE được thiết kế để thu hẹp sự mơ hồ đó: thay vì chỉ biết **dòng nào**, kỹ sư có thể biết **bước nào trong biểu thức đã nhận null**. Ví dụ thông điệp minh họa:

~~~text
Cannot invoke "Address.city()" because the return value of "Customer.address()" is null
~~~

Thông điệp này phân biệt rõ: không phải kết quả `city()` null; **chính kết quả `address()` null**, nên lời gọi `city()` chưa thực hiện được. Đây là thông tin giúp định hướng debug, **không tự khẳng định nguyên nhân nghiệp vụ** khiến `address()` trả null.

### Hai câu hỏi khác nhau

| Nguồn thông tin | Trả lời |
| --- | --- |
| Stack trace | Ngoại lệ phát sinh ở phương thức, tệp và dòng nào? Luồng gọi tới đó thế nào? |
| Helpful NPE message | Thao tác nào thất bại vì biểu thức/giá trị tham chiếu nào là null? |
| Kiểm tra code, dữ liệu và contract | **Tại sao** tham chiếu đó có thể null và nên xử lý thế nào? |

Chẩn đoán tốt cần cả ba mức. Thông báo mới đặc biệt có ích khi một dòng có **chuỗi phương thức dài, nhiều field hoặc kết quả tạm**.

## 3. Cấu trúc và cách đọc một thông báo Helpful NPE

Mẫu mô tả đơn giản:

~~~text
Cannot <action> because <null-producing expression> is null
~~~

Dấu `<...>` trong sơ đồ chỉ phần mô tả, **không phải cú pháp Java**. Một số phần thường gặp:

| Thành phần | Cách hiểu |
| --- | --- |
| `Cannot invoke ...` | Không thể gọi instance method được nêu, vì receiver null. |
| `Cannot read field ...` | Không đọc được field instance từ một receiver null. |
| `Cannot assign field ...` | Không gán được field instance trên receiver null. |
| `Cannot load from ... array` | Mảng được truy cập phần tử là null. |
| `Cannot read the array length ...` | Mảng dùng để lấy `length` là null. |
| `because ... is null` | Biểu thức tham chiếu trực tiếp tạo ra null. |
| `because the return value of ... is null` | Giá trị trả về từ phương thức được nêu là null. |

**Không học thuộc nguyên văn từng câu tiếng Anh.** Thông điệp do JVM sinh, việc có mặt và cách diễn đạt là chi tiết triển khai; API Java cho phép `NullPointerException.getMessage()` trả mô tả triển khai hoặc `null`.

Ví dụ hai thông báo minh họa tương ứng với cùng một lỗi:

~~~text
java.lang.NullPointerException
    at Example.main(Example.java:12)
~~~

~~~text
java.lang.NullPointerException: Cannot read field "name" because "user.profile" is null
    at Example.main(Example.java:12)
~~~

Thông báo thứ hai giúp hiểu **`user.profile` là null**, và đọc `name` từ nó là thao tác thất bại. Nếu chỉ đọc tên field `name`, bạn có thể suy luận sai rằng **field `name` có giá trị null**; điều đúng ở đây là **không thể đọc field** vì object chứa field đã null.

## 4. Cơ chế JVM và giới hạn của tên biến

Helpful NPE được tạo chủ yếu từ **phân tích bytecode** tại lệnh JVM thất bại. Điều đó có những hệ quả:

- **Không cần thay đổi Java source syntax** và không phải một ngôn ngữ preview phải bật bằng compiler.
- JVM tìm bytecode tạo tham chiếu null đưa vào phép đọc field, gọi instance method, thao tác mảng, v.v.
- Không phải lúc nào bytecode cũng giữ **đúng nguyên văn biểu thức source**. Compiler có thể biến đổi hoặc tạo biến tạm.
- **Local Variable Table** và thông tin debug trong class file có thể ảnh hưởng tên biến được hiển thị. Nếu tên không có, JVM có thể dùng biểu diễn `<localN>` hoặc `<parameterN>`.
- Chi tiết message là **implementation-specific**; nó không phải định dạng JSON, không phải cơ chế xác thực dữ liệu, và không có cam kết để parse thành một hợp đồng ổn định.
- JVM không tự truy vấn database hoặc suy luận contract của hệ thống. Nó biết thao tác dereference lỗi, **không biết lý do nghiệp vụ sâu hơn**.

Khi cần gỡ lỗi nội bộ trên JDK phù hợp, có thể biên dịch với debug metadata:

~~~bash
javac -g --release 17 HelpfulNpePurposeDemo.java
~~~

`-g` của `javac` phát sinh đầy đủ thông tin debug, bao gồm tên local variable. Đây là lựa chọn build cần cân nhắc riêng; nó **không đảm bảo** mọi JVM sẽ đưa tên biến vào thông điệp, và tên biến cũng có thể là thông tin nội bộ cần bảo vệ.

## 5. Ví dụ độc lập: quan sát ý nghĩa của một tham chiếu null trong chuỗi field

Tạo tệp **`HelpfulNpePurposeDemo.java`**:

~~~java
public class HelpfulNpePurposeDemo {
    static final class Address {
        String city;
    }

    static final class Customer {
        Address address;
    }

    static final class Order {
        Customer customer;
    }

    public static void main(String[] args) {
        Order order = new Order();
        order.customer = new Customer();
        order.customer.address = null;

        try {
            int count = order.customer.address.city.length();
            System.out.println(count);
        } catch (NullPointerException ex) {
            System.out.println("caught: NullPointerException");
            // Chỉ dùng dữ liệu giả trong ví dụ, không ghi message vào API public.
            System.err.println("diagnostic: " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -g --release 17 HelpfulNpePurposeDemo.java
java HelpfulNpePurposeDemo
~~~

**Stdout chính xác:**

~~~text
caught: NullPointerException
~~~

**Stderr minh họa** trên HotSpot có thông báo hữu ích (không cam kết nguyên văn):

~~~text
diagnostic: Cannot read field "city" because "order.customer.address" is null
~~~

Phân tích:

1. `order` đã được tạo → không null.
2. `order.customer` đã được gán một `Customer` → không null.
3. `order.customer.address = null` → field `address` không chứa object.
4. JVM không thể đọc field `city` trên `address` null, nên ném NPE ngay tại phép đọc đó.
5. `city.length()` **chưa được gọi**. Không nên nói NPE này do `city` null; chưa có lần đọc `city` thành công.

Thông báo giúp trả lời **tham chiếu trực tiếp nào null** nhưng chưa trả lời vì sao `address` chưa khởi tạo. Đó là bước điều tra dữ liệu/constructor/contract tiếp theo.

**Vì sao tách stdout và stderr?** Dòng `caught: NullPointerException` do code quyết định và ổn định. Chuỗi `ex.getMessage()` có thể khác hoặc thiếu tùy JVM, flag và metadata. Đừng viết golden test đòi khớp nguyên văn chuỗi tiếng Anh này trên mọi môi trường.

## 6. NPE không chỉ đến từ `obj.method()`

Một tham chiếu null có thể gây lỗi trong nhiều dạng bytecode:

| Mã minh họa | Thao tác cần object | Điểm cần chẩn đoán |
| --- | --- | --- |
| `String s = null; s.length();` | Gọi phương thức instance | Receiver của `length()` là null. |
| `User u = null; String x = u.name;` | Đọc field | Receiver của field `name` là null. |
| `User u = null; u.name = "A";` | Ghi field | Receiver của phép gán là null. |
| `int[] a = null; int n = a.length;` | Đọc kích thước mảng | Tham chiếu mảng là null. |
| `int[] a = null; int n = a[0];` | Lấy phần tử mảng | Không có mảng thật để đọc phần tử. |
| `Integer boxed = null; int n = boxed;` | Auto-unboxing | Phải lấy giá trị `int` từ wrapper null. |
| `Object lock = null; synchronized(lock) {}` | Khóa monitor | Không dùng null làm đối tượng đồng bộ được. |
| `Throwable t = null; throw t;` | Ném Throwable | Không thể ném tham chiếu null như ngoại lệ hợp lệ. |

Mỗi dòng trên chỉ là **mảnh Java minh họa**, không phải chương trình chạy độc lập. Thông báo chi tiết cụ thể phụ thuộc vào bytecode của phép toán thất bại.

### Ví dụ độc lập: kiểm thử các loại lỗi mà không phụ thuộc câu chữ

Tạo tệp **`NpeOperationCasesDemo.java`**:

~~~java
public class NpeOperationCasesDemo {
    static final class User {
        String name;
    }

    static void expectNpe(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected NullPointerException");
        } catch (NullPointerException ex) {
            System.out.println(label + ": NPE");
        }
    }

    public static void main(String[] args) {
        String text = null;
        User user = null;
        int[] numbers = null;
        Integer boxed = null;

        expectNpe("method", () -> {
            int n = text.length();
        });
        expectNpe("field", () -> {
            String n = user.name;
        });
        expectNpe("array", () -> {
            int n = numbers.length;
        });
        expectNpe("unboxing", () -> {
            int n = boxed;
        });
        expectNpe("monitor", () -> {
            synchronized (text) {
                System.out.println("not reached");
            }
        });
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 17 NpeOperationCasesDemo.java
java NpeOperationCasesDemo
~~~

**Stdout chính xác:**

~~~text
method: NPE
field: NPE
array: NPE
unboxing: NPE
monitor: NPE
~~~

Code test **loại exception và đường điều khiển**, không ràng buộc wording tiếng Anh. Khi bạn cần quan sát `getMessage()`, dùng một test chẩn đoán riêng trên JDK/vendor có tên rõ ràng; không dùng câu chữ đó làm business contract.

## 7. Ví dụ với kết quả phương thức null: vì sao rất hữu ích?

Xét:

~~~java
order.customer().address().city().length();
~~~

Nếu `address()` trả null, thao tác thất bại đầu tiên là **gọi `city()` trên kết quả của `address()`**.

Thông báo minh họa:

~~~text
Cannot invoke "Address.city()" because the return value of "Customer.address()" is null
~~~

Thông tin “the return value of...” giúp phân biệt rất rõ với trường hợp `city()` tự trả null rồi lỗi ở `length()`. Mấu chốt của debug là đi tới **phương thức trả giá trị null đầu tiên**, kiểm tra cách nó được tạo và điều kiện nào hợp lệ.

### Ví dụ độc lập: record và chuỗi accessor

Tạo tệp **`NestedAccessDiagnosticDemo.java`**:

~~~java
public class NestedAccessDiagnosticDemo {
    record Address(String city) {}
    record Customer(Address address) {}
    record Order(Customer customer) {}

    public static void main(String[] args) {
        Order order = new Order(new Customer(null));

        try {
            int length =
                    order.customer().address().city().length();
            System.out.println(length);
        } catch (NullPointerException ex) {
            System.out.println("nested access failed");
            System.err.println("internal NPE detail: "
                    + ex.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 NestedAccessDiagnosticDemo.java
java NestedAccessDiagnosticDemo
~~~

**Stdout chính xác:**

~~~text
nested access failed
~~~

`stderr` phụ thuộc JVM và cách biên dịch. Trên HotSpot hỗ trợ, thông báo thường gợi tới **giá trị trả về của `Customer.address()`**, nhưng không được hardcode câu đó làm kết quả bắt buộc của mọi JVM.

Record trong ví dụ đã là tính năng Java chính thức từ Java 16; ở đây record chỉ mô phỏng tập dữ liệu có tên. Nó không phải nguyên nhân hay điều kiện để Helpful NPE hoạt động.

## 8. Phân biệt NPE do JVM tạo và NPE được code chủ động ném

Helpful NPE được tạo khi JVM **có thông tin về lệnh dereference gây lỗi**. Không phải mọi `NullPointerException` đều mang thông tin đó.

**A. JVM tạo NPE tại dereference**

~~~java
String name = null;
int n = name.length();
~~~

Nếu runtime hỗ trợ, `getMessage()` có thể mô tả việc không gọi được `String.length()` vì `name` null.

**B. Lập trình viên chủ động tạo NPE**

~~~java
throw new NullPointerException("name must not be null");
~~~

Message là **`"name must not be null"`** mà code cung cấp, **không bị JVM thay bằng mô tả "Cannot invoke..."**.

**C. NPE không có message do code tạo**

~~~java
throw new NullPointerException();
~~~

Không có đường dereference gắn với đối tượng NPE này; message có thể là `null`. JavaDoc `NullPointerException.getMessage()` cũng nêu thông tin phân tích không sẵn có ở một NPE đã được **deserialize**.

### Ví dụ độc lập: message được code kiểm soát

Tạo tệp **`ManualNpeMessageDemo.java`**:

~~~java
import java.util.Objects;

public class ManualNpeMessageDemo {
    public static void main(String[] args) {
        try {
            throw new NullPointerException("explicit reason");
        } catch (NullPointerException ex) {
            System.out.println(ex.getMessage());
        }

        try {
            throw new NullPointerException();
        } catch (NullPointerException ex) {
            System.out.println(ex.getMessage() == null);
        }

        try {
            Objects.requireNonNull(null, "customer");
        } catch (NullPointerException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 ManualNpeMessageDemo.java
java ManualNpeMessageDemo
~~~

**Stdout chính xác:**

~~~text
explicit reason
true
customer
~~~

Kết quả này giúp thấy ba trường hợp: message tường minh; NPE thủ công không có detail; và `Objects.requireNonNull(..., "customer")` tạo NPE có message do ứng dụng xác định. **Không kỳ vọng tất cả NPE đều có thông báo đầy đủ.**

## 9. Mốc Java 14, Java 15 và hành vi trong JDK hiện đại

| Phiên bản / môi trường | Trạng thái liên quan |
| --- | --- |
| **Java 14** | JEP 358 đưa Helpful NPE vào HotSpot, nhưng mặc định ban đầu **không bật**. Đây là mốc lịch sử. |
| **Java 15 trở lên trên HotSpot** | Flag `ShowCodeDetailsInExceptionMessages` được đổi mặc định thành **true**; thông báo hữu ích thường có sẵn. |
| **JDK 17/21/25 có cập nhật** | Vẫn có cơ chế chẩn đoán này. Không cần một cú pháp Java mới hay bật `--enable-preview`. |
| **JVM khác hoặc cấu hình đặc biệt** | Wording, mức chi tiết và hỗ trợ flag có thể khác; luôn đọc tài liệu vendor/runtime hiện dùng. |
| **NPE do code tạo, message explicit, hoặc deserialize** | Không tự có đường truy cập bytecode cần thiết để sinh Helpful NPE. |

Trên HotSpot, một số lựa chọn cấu hình để hiểu/kiểm tra trong môi trường có kiểm soát:

~~~bash
# Chạy như bình thường trên HotSpot hiện đại:
java HelpfulNpePurposeDemo

# Bật tường minh khi muốn xác minh cấu hình HotSpot:
java -XX:+ShowCodeDetailsInExceptionMessages HelpfulNpePurposeDemo

# Tắt chi tiết trên HotSpot trong một phép thử cấu hình:
java -XX:-ShowCodeDetailsInExceptionMessages HelpfulNpePurposeDemo
~~~

Các lệnh trên **không biên dịch lại class**; cần chạy `javac` trước. `-XX` là tùy chọn JVM nâng cao, không phải chuẩn ngôn ngữ được bảo đảm trên mọi triển khai. **Bật/tắt** cần phù hợp quyền vận hành, nhu cầu debug và bảo mật.

Lựa chọn tốt cho hệ thống production không phải mặc định tắt hết khả năng chẩn đoán, mà là **ngăn chi tiết nội bộ đi đến API công khai**, giữ log cần thiết ở kênh được phân quyền.

## 10. Từ thông báo null tới việc sửa nguyên nhân thật

Ví dụ một repository trả về kết quả có thể thiếu:

~~~java
Customer customer = repository.findById(id);
String name = customer.getName();
~~~

Đây là **mảnh minh họa**, giả định có biến `repository`, `id` và kiểu `Customer`. Nếu `findById` trả null, NPE có thể gợi rằng `customer` là null, nhưng **không thể khẳng định** đó là bug repository.

Những khả năng cần xem:

- Không có dữ liệu là **kết quả nghiệp vụ hợp lệ**, nhưng caller thiếu nhánh xử lý.
- Repository trả null dù contract hứa không null.
- Truy vấn/lọc nhầm điều kiện hoặc sai nguồn dữ liệu.
- Một object chưa được khởi tạo đầy đủ.
- Luồng xử lý bất đồng bộ/cạnh tranh làm trạng thái thay đổi.
- Code gọi API dựa trên giả định chưa được bảo đảm.

**Quy trình sửa đúng:**

1. Chỉ ra **receiver/biểu thức null** trong message, kèm call-site của stack trace.
2. Tìm nơi **giá trị đó được cấp, gán hoặc trả về**.
3. Đọc **hợp đồng**: null được phép hay bị cấm?
4. Nếu null hợp lệ, xử lý rõ (không có dữ liệu, trạng thái lỗi nghiệp vụ, giá trị thay thế được xác định, `Optional` cho return khi thích hợp).
5. Nếu null vi phạm hợp đồng, sửa nguồn sinh dữ liệu hoặc kiểm tra sớm ở boundary có ngữ cảnh.
6. Viết test cho **tình huống thật** trước/sau sửa. Không chỉ test rằng message NPE chứa một tên biến.

Đừng rải `if (x == null) return;` để biến lỗi thành im lặng: điều đó có thể giấu dữ liệu hỏng hoặc khiến hệ thống bỏ dở một hành động quan trọng.

## 11. Phòng ngừa ở ranh giới: `Objects.requireNonNull`

Helpful NPE có ích **khi lỗi đã phát sinh**; nhiều trường hợp còn tốt hơn nếu API phát hiện việc dùng null trái hợp đồng **ngay từ lúc nhận tham số**.

- Với tham số **bắt buộc phải có**, `Objects.requireNonNull(value, "name")` nói rõ biến đầu vào nào vi phạm hợp đồng.
- Với giá trị **được phép thiếu**, cần xử lý trường hợp thiếu; `requireNonNull` không phải giải pháp đúng.
- Với dữ liệu có PII/credential, message nên chứa **tên trường** thay vì nối giá trị đầu vào vào exception.
- Việc kiểm tra sớm không thay thế kiểm thử luồng dữ liệu hoặc cách thiết kế API.

### Ví dụ độc lập: điều kiện đầu vào rõ ràng

Tạo tệp **`NullBoundaryContractDemo.java`**:

~~~java
import java.util.Objects;

public class NullBoundaryContractDemo {
    static String normalize(String input) {
        String checked = Objects.requireNonNull(input, "input");
        return checked.strip();
    }

    public static void main(String[] args) {
        System.out.println(normalize("  Java  "));

        try {
            normalize(null);
        } catch (NullPointerException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 NullBoundaryContractDemo.java
java NullBoundaryContractDemo
~~~

**Stdout chính xác:**

~~~text
Java
input
~~~

Phương thức công bố rằng `input` không thể null. Nếu vi phạm, code ném NPE có message `"input"` **ngay ở boundary**; nếu hợp lệ, `strip()` chạy bình thường. Không in raw input gây rủi ro lộ dữ liệu.

### Biểu thức nhiều tầng khi mỗi tầng đều bắt buộc

~~~java
static String cityName(Customer customer) {
    Objects.requireNonNull(customer, "customer");
    Address address = Objects.requireNonNull(
            customer.address(), "customer.address");
    return Objects.requireNonNull(
            address.city(), "customer.address.city");
}
~~~

Đây là **mảnh phương thức** cần kiểu `Customer`/`Address` đã định nghĩa; không phải file chạy riêng. Chỉ dùng kiểu kiểm tra này khi contract nói `address` và `city` **không được null**. Nếu thiếu địa chỉ là trường hợp bình thường, hãy trả trạng thái “không có địa chỉ” hoặc model hóa rõ ràng, đừng coi mọi trường hợp vắng mặt là lỗi lập trình.

## 12. `NullPointerException.getMessage()` là thông tin chẩn đoán, không phải protocol

Java SE 25 API quy định:

- Khi constructor nhận một chuỗi message khác null, `getMessage()` trả chuỗi đó.
- Khi không có message explicit, phương thức có thể trả **một mô tả tùy triển khai** hoặc **null**.
- Mô tả chi tiết chỉ có thể tạo khi **thông tin nội bộ phù hợp còn tồn tại**; với NPE deserialized, thông tin đó không sẵn có.

Hệ quả thiết kế:

- Không parse tiếng Anh do JVM sinh để quyết định “nếu chứa `Cannot invoke` thì trả HTTP 400”.
- Không dùng exact wording trong snapshot/golden tests portable.
- Không dùng tên biến từ helpful message làm key cho analytics/business logic.
- Không coi thiếu message là bug của JVM: có những NPE hoàn toàn hợp lệ nhưng không có thông tin để dựng lại đường truy cập.
- Không cho rằng `getMessage()` không null chỉ vì đang chạy trên JDK có hỗ trợ JEP 358.

Nếu ứng dụng cần **mã lỗi ổn định**, hãy tạo mã riêng (`INVALID_INPUT`, `NOT_FOUND`, `INTERNAL_ERROR`...), và chỉ dùng NPE detail để điều tra nội bộ.

## 13. Kiểm thử portable: xác minh đúng hành vi, không so nguyên văn câu chữ

Sai lầm thường gặp là:

~~~java
// Minh họa test dễ hỏng: text do JVM sinh không có định dạng ổn định.
assert ex.getMessage().equals(
        "Cannot invoke \"String.length()\" because \"name\" is null");
~~~

Đây là **mảnh code minh họa không nên dùng**: tên được hiển thị và wording có thể thay đổi giữa JDK/JVM/bytecode; `assert` của Java còn có thể bị tắt nếu không chạy `-ea`.

**Kiểm thử nên xác nhận hợp đồng:** thao tác thực sự ném NPE trong điều kiện xác định, handler xử lý đúng, mã lỗi ổn định (nếu do ứng dụng tạo), và trường hợp hợp lệ vẫn chạy.

### Ví dụ độc lập: test không phụ thuộc message

Tạo tệp **`NpeContractTestDemo.java`**:

~~~java
public class NpeContractTestDemo {
    static void expectNpe(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Missing expected NPE");
        } catch (NullPointerException expected) {
            System.out.println(label + ": NPE");
        }
    }

    public static void main(String[] args) {
        String text = null;
        int[] numbers = null;

        expectNpe("method", () -> {
            int length = text.length();
        });
        expectNpe("array", () -> {
            int length = numbers.length;
        });

        System.out.println("tests passed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 NpeContractTestDemo.java
java NpeContractTestDemo
~~~

**Stdout chính xác:**

~~~text
method: NPE
array: NPE
tests passed
~~~

Đây là phép kiểm thử **loại ngoại lệ** và đường xử lý, chạy độc lập với message format. Với test của một thư viện thực tế, dùng framework như JUnit bản phù hợp dự án; hợp đồng vẫn nên tập trung vào đúng hành vi.

### Khi nào kiểm thử message?

- **Message do chính code ứng dụng xác định**, ví dụ `Objects.requireNonNull(input, "input")`: có thể kiểm tra chính xác `"input"` nếu đó là phần contract được duy trì.
- **Helpful NPE của JVM**: nếu công cụ nội bộ buộc kiểm tra cấu hình trên một HotSpot/JDK cụ thể, viết một test riêng có điều kiện môi trường và chỉ kiểm tra các thuộc tính cần thiết. Không đánh đồng nó với test portable.

Chẳng hạn:

~~~java
String detail = caughtNpe.getMessage();
if (detail == null || detail.isBlank()) {
    throw new AssertionError("Helpful NPE detail unavailable");
}
~~~

Đây chỉ là **mảnh test phụ thuộc runtime**, giả định `caughtNpe` là NPE **do JVM tạo** và môi trường test đã yêu cầu tính năng chẩn đoán hoạt động. Không đưa điều kiện này vào mọi bài test NPE.

## 14. Bảo mật: thông báo có ích cho debug cũng có thể tiết lộ cấu trúc

Một message như:

~~~text
Cannot read field "apiKey" because "settings.credentials" is null
~~~

là thông tin **hữu ích nội bộ** nhưng có thể tiết lộ tên field/class/đường truy cập cấu hình cho người không được phép. Đây là mẫu giả, **không phải khóa API thật**. Cơ chế Helpful NPE thường mô tả **đường truy cập**, không chủ động dump toàn bộ giá trị object; tuy vậy đường truy cập cũng có thể nhạy cảm.

| Kênh nhận lỗi | Cách xử lý |
| --- | --- |
| Công cụ chẩn đoán nội bộ có phân quyền | Có thể lưu detail cần thiết theo chính sách; tránh ghi raw credential/PII. |
| API công khai/web client | Trả mã lỗi ổn định và thông điệp chung phù hợp; **không gửi stack trace hoặc Helpful NPE detail nguyên văn**. |
| Hệ thống log tập trung và APM | Xem quyền truy cập, thời gian lưu, redaction và dữ liệu tự động được thu thập. |
| CI/test logs | Dùng dữ liệu giả; không in token, password hoặc payload người dùng thật. |

Ví dụ payload lỗi công khai chỉ để minh họa:

~~~json
{"error":"INTERNAL_ERROR","message":"An unexpected error occurred"}
~~~

Với hệ thống cần truy vết, có thể thêm correlation ID **được thiết kế an toàn** để ánh xạ tới sự kiện trong log nội bộ. Không dùng token truy cập làm ID truy vết.

Oracle JDK 15 release notes lưu ý rằng khi bật thông báo chi tiết mặc định, ứng dụng web cần kiểm tra cách exception được đưa vào response và log. Học cơ chế debug cũng cần học **ranh giới công khai–nội bộ**; không xem tắt tính năng VM là giải pháp duy nhất.

## 15. Troubleshooting khi message không xuất hiện hoặc khác dự kiến

| Triệu chứng | Khả năng thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `getMessage() == null` | NPE tự tạo không có message, thông tin VM thiếu, feature bị tắt/không hỗ trợ, deserialize | Xác định NPE được tạo ở đâu, JavaDoc/JVM đang chạy. |
| Hiển thị `<localN>` thay vì tên biến | Thiếu thông tin debug trong class hoặc compiler sinh bytecode khác | Kiểm tra toolchain, `javac -g` trên bản build thử nghiệm. |
| “return value of...” xuất hiện | Kết quả của phương thức được gọi trước đó là null | Truy hợp đồng của phương thức trả null. |
| Máy dev và CI khác cách diễn đạt | JDK/vendor/options khác, metadata class khác | So `java -version`, `javac -version` và cờ runtime. |
| Có message nhưng người dùng thấy lỗi chung | Exception handler/API gateway đã mapping sang thông điệp công khai | Đây có thể là hành vi bảo mật đúng; xem log nội bộ. |
| NPE phát sinh tại code chủ động `throw` | Message do developer cung cấp hoặc null | Không yêu cầu JVM tái tạo biểu thức dereference. |
| Lỗi cứ lặp lại | Bug/null contract chưa sửa | Truy null source và thêm kiểm thử hồi quy; không chỉ bật log chi tiết hơn. |

Helpful NPE **không ngăn một exception xảy ra**, không khởi tạo object thay cho null và không tự giải quyết vấn đề thiếu dữ liệu.

## 16. Quy trình điều tra NPE trong dự án

1. Xác nhận **đúng build, đúng JDK và call site**. Stack trace của bản deploy khác commit có thể dẫn tới line number khác.
2. Đọc phần **`Cannot ...`**: JVM đang làm phép toán gì tại điểm lỗi?
3. Đọc phần **`because ... is null`**: biểu thức nào là null ngay lúc đó?
4. Truy ngược **nơi tạo/nhận/trả** giá trị null đó.
5. So với **contract**: null hợp lệ hay bị cấm? Có lỗi khởi tạo, mapping, truy vấn hoặc race condition không?
6. Sửa dữ liệu hoặc luồng điều khiển tại nơi phù hợp, **không chỉ thêm catch để nuốt NPE**.
7. Viết test cho trạng thái dẫn đến lỗi và trạng thái hợp lệ; không phụ thuộc nguyên văn message JVM.
8. Rà soát lỗi gửi ra API và hệ thống log để không lộ chi tiết nội bộ.
9. Chạy lại trên JDK mục tiêu và pipeline CI của dự án.

Câu hỏi quan trọng nhất: **“Tham chiếu nào null tại thao tác thất bại, và nó có được phép null theo hợp đồng ứng dụng không?”** Helpful NPE giúp trả lời nửa đầu; kỹ sư phải xác định nửa sau.

## 17. Bài tập thực hành

### Bài 1 — Đọc một Helpful NPE message

Cho:

~~~text
Cannot invoke "java.lang.String.length()" because "customer.name" is null
~~~

Hãy trả lời: (a) thao tác thất bại; (b) tham chiếu null; (c) liệu đã biết nguyên nhân gốc chưa.

**Đáp án:** JVM không gọi được `String.length()`, `customer.name` null, chưa biết vì sao tên bị null.

### Bài 2 — Phân biệt hai điểm null

Với chuỗi:

~~~java
order.customer().address().city().length();
~~~

Nếu message nói kết quả `Customer.address()` là null, **`city()` đã chạy chưa?** Chưa: không thể gọi `city()` trên null. Nếu message nói kết quả `Address.city()` là null, lúc đó `city()` đã chạy và lỗi xảy ra khi cố gọi `String.length()`.

### Bài 3 — Message do developer tạo

~~~java
throw new NullPointerException("customer is missing");
~~~

**Đáp án:** `getMessage()` là `"customer is missing"`, không phải mô tả dereference tự động.

### Bài 4 — Debug nhưng không làm lộ thông tin

Một ứng dụng web gửi `ex.toString()`/stack trace thẳng vào HTTP 500. Hãy đưa về **error code ổn định + mô tả chung + correlation ID an toàn**; giữ thông tin detail ở log nội bộ có quyền truy cập và retention phù hợp.

### Bài 5 — Soạn test đúng mức

Với `String s = null; s.length()`, test rằng NPE phát sinh. **Đừng** hardcode `Cannot invoke "String.length()" ...`. Giải thích vì sao: wording và việc có detail không được bảo đảm trên mọi JVM.

### Bài 6 — Chạy các chương trình độc lập

~~~bash
javac -g --release 17 HelpfulNpePurposeDemo.java
java HelpfulNpePurposeDemo

javac --release 17 NpeOperationCasesDemo.java
java NpeOperationCasesDemo

javac --release 17 NestedAccessDiagnosticDemo.java
java NestedAccessDiagnosticDemo

javac --release 17 ManualNpeMessageDemo.java
java ManualNpeMessageDemo

javac --release 17 NullBoundaryContractDemo.java
java NullBoundaryContractDemo

javac --release 17 NpeContractTestDemo.java
java NpeContractTestDemo
~~~

Tên mỗi file phải khớp `public class`. So với phần **stdout chính xác**; hai chương trình có `System.err.println` chỉ cho **diagnostic minh họa** vì thông điệp JVM không ổn định giữa các môi trường.

## 18. Nguồn kỹ thuật còn áp dụng

1. [OpenJDK JEP 358 — Helpful NullPointerExceptions](https://openjdk.org/jeps/358): mục đích, phân tích bytecode để xác định thao tác thất bại và biểu thức null.
2. [Java SE 25 API — `NullPointerException`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/NullPointerException.html): `getMessage()` có thể là message do code cung cấp, mô tả do triển khai sinh hoặc null; giới hạn với NPE deserialized.
3. [Java SE 25 — `java` command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `ShowCodeDetailsInExceptionMessages` trên HotSpot, khả năng phân tích bytecode và giá trị mặc định.
4. [Oracle JDK 15 Release Notes](https://www.oracle.com/java/technologies/javase/15-relnote-issues.html): bật Helpful NPE mặc định và cảnh báo cần bảo vệ output ứng dụng.
5. [Java SE 25 API — `Objects.requireNonNull`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Objects.html): xác thực tham số theo hợp đồng và cung cấp message rõ ràng.

**Ghi nhớ:** Helpful NullPointerExceptions được giới thiệu trong Java 14 để giúp xác định **thao tác nào đang dùng tham chiếu null**. Chúng giúp gỡ lỗi nhanh hơn, nhưng **không tìm hộ nguyên nhân nghiệp vụ, không sửa lỗi, không cung cấp format ổn định và không nên công khai chi tiết nội bộ**. Hãy dùng thông báo để tìm đúng nguồn sinh null và sửa contract/luồng dữ liệu, rồi kiểm thử hành vi bằng các assertion bền vững.