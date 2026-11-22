# NPE do JVM tạo và NPE được tạo tường minh: hiểu đúng thông báo lỗi trong Java

## 1. Hai con đường dẫn đến `NullPointerException`

`java.lang.NullPointerException` (NPE) cho biết mã đã sử dụng một tham chiếu `null` trong thao tác không chấp nhận `null`. Tuy cùng loại ngoại lệ, **nguồn phát sinh** ảnh hưởng đáng kể đến nội dung `getMessage()` và cách chẩn đoán:

1. **NPE do JVM trực tiếp tạo và ném:** thường xuất hiện khi bytecode thực hiện thao tác như gọi phương thức, đọc trường hoặc truy cập mảng thông qua một tham chiếu `null`. Với tính năng **Helpful NullPointerExceptions** (JEP 358), JVM có thể phân tích bytecode để mô tả *thao tác nào thất bại* và *biểu thức nào có giá trị null*.
2. **NPE được mã Java tạo/ném tường minh:** ví dụ `throw new NullPointerException("customer ID is required");`, hoặc kiểm tra đầu vào bằng `Objects.requireNonNull(value, "value")`. Trong trường hợp này, **thông báo được quyết định bởi lời gọi tạo ngoại lệ**, không được tính năng Helpful NPE tự động viết lại thành thông báo mô tả biểu thức null.

Hai cách đều có thể hợp lý: JVM phát hiện lỗi dereference lúc thực thi; mã ứng dụng có thể chủ động kiểm tra đầu vào ngay tại ranh giới API để báo lỗi sớm, dễ hiểu hơn.

**Liên hệ Java 14 và hiện tại:** Helpful NullPointerExceptions xuất hiện ở **Java 14** qua JEP 358; ở Java 14 tùy chọn chi tiết chưa được bật mặc định. Từ **JDK 15**, `ShowCodeDetailsInExceptionMessages` được bật mặc định trên HotSpot và các JDK hiện đại thường có cơ chế này. Các ví dụ sử dụng cú pháp Java 17+ ổn định, không có preview/legacy. Tùy VM, cấu hình và nguồn gốc ngoại lệ, một NPE vẫn có thể có thông báo `null`.

## 2. JVM tạo NPE khi nào?

Ví dụ một đường truy cập lồng nhau:

```java
class Address {
    String city;
}

class Customer {
    Address address;
}

// Trong một phương thức Java:
Customer customer = new Customer();
int length = customer.address.city.length();
```

Đoạn này **cố ý phát sinh ngoại lệ khi chạy**: `customer.address` mặc định là `null`, nên máy ảo không thể đọc trường `city` từ tham chiếu đó. JVM trực tiếp tạo và ném NPE cho thao tác bytecode tương ứng.

Khi Helpful NPE được bật, một thông báo **minh họa** có thể trông giống:

```text
Cannot read field "city" because "customer.address" is null
```

Phần thứ nhất, `Cannot read field "city"`, là thao tác bị lỗi; phần sau `because ... is null` chỉ ra đường biểu thức tạo ra tham chiếu `null`. **Tên biến trong thông báo không được bảo đảm luôn đúng như mã nguồn:** nếu tệp lớp không có thông tin debug tên biến cục bộ, JVM có thể dùng một cách gọi đại diện như `<local1>` hoặc `<parameter1>`. Chữ ký phương thức và cách trình bày có thể khác theo mã biên dịch và VM.

Các hoạt động thường có thể làm JVM tạo NPE gồm:

| Thao tác trên giá trị `null` | Ví dụ minh họa | Điều thất bại |
| --- | --- | --- |
| Gọi phương thức instance | `String s = null; s.length();` | Không thể gọi `String.length()` |
| Đọc trường instance | `customer.address.city` khi `address == null` | Không thể đọc trường `city` |
| Gán trường instance | `customer.address.city = "Hà Nội";` khi `address == null` | Không thể ghi trường `city` |
| Đọc độ dài mảng | `String[] items = null; int n = items.length;` | Không thể lấy độ dài mảng |
| Đọc/ghi phần tử mảng | `items[0]` với `items == null` | Không thể truy cập mảng |
| Tự động unboxing | `Integer n = null; int x = n;` | Không thể gọi phương thức unboxing như `intValue()` trên `null` |
| `synchronized` trên tham chiếu `null` | `synchronized (lock) { ... }` với `lock == null` | Không thể lấy monitor của đối tượng |
| Ném tham chiếu ngoại lệ `null` | `throw (RuntimeException) null;` | Không có đối tượng `Throwable` để ném |

Các ví dụ trong bảng là **mã minh họa từng trường hợp**, không phải một chương trình chạy tuần tự. Không phải lúc nào toàn bộ các tình huống đều có cùng cách trình bày thông báo: cơ chế chi tiết phụ thuộc bytecode và việc VM có thể phân tích nguồn gốc tham chiếu hay không.

**Ranh giới quan trọng:** NPE do JVM trực tiếp tạo khác với một NPE mà một phương thức Java tự tạo bằng `new NullPointerException(...)`, kể cả khi cùng phát sinh sau khi truyền tham chiếu `null` vào phương thức đó.

## 3. NPE được tạo tường minh với `throw new`

Người lập trình có thể kiểm tra điều kiện và ném ngoại lệ chủ động:

```java
static String requireId(String id) {
    if (id == null) {
        throw new NullPointerException("customer ID is required");
    }
    return id;
}
```

Nếu gọi `requireId(null)`, `getMessage()` có giá trị **chính xác** là `"customer ID is required"`. Đây là thông báo được truyền vào constructor của ngoại lệ, không phải do Helpful NPE phân tích chuỗi biểu thức ở nơi lỗi.

Có thể tạo NPE không có thông báo:

```java
throw new NullPointerException();
```

Thông thường `getMessage() == null` trong trường hợp này, kể cả khi bật `-XX:+ShowCodeDetailsInExceptionMessages`. Tính năng Helpful NPE **không tự thêm** đường biểu thức vào NPE mà mã đã chủ động tạo/ném như vậy.

Hai trường hợp còn được phân biệt qua **stack trace**:

- NPE tự động do JVM thường có frame đầu trỏ đến dòng thực hiện thao tác bytecode bị lỗi.
- NPE tạo tường minh thường có frame đầu tại chỗ `throw new ...` (hoặc trong phương thức thư viện chủ động tạo ngoại lệ).
- Frame có tên phương thức, file và số dòng nếu thông tin tương ứng còn trong class file; dùng nó cùng với `getMessage()` để chẩn đoán thay vì chỉ nhìn loại ngoại lệ.

**Không nên lạm dụng NPE:** Theo hợp đồng Java, `NullPointerException` thích hợp để thông báo một tham chiếu bắt buộc không được `null`. Nếu chuỗi không `null` nhưng sai định dạng, tuổi ngoài biên hoặc giá trị không hợp lệ về nghiệp vụ, có thể thích hợp hơn với `IllegalArgumentException` hoặc kiểu lỗi miền đã quy định.

## 4. `Objects.requireNonNull`: kiểm tra đầu vào ngay tại ranh giới

`java.util.Objects.requireNonNull` là công cụ Java SE được dùng rộng rãi để khẳng định tham chiếu phải khác `null`:

```java
import java.util.Objects;

static String normalizeName(String name) {
    return Objects.requireNonNull(name, "name").strip();
}
```

Đây là đoạn nằm trong một lớp; khi `name == null`, phương thức ném NPE với `getMessage()` bằng `"name"`. Khi tên hợp lệ, `requireNonNull` trả lại **chính tham chiếu đó**, sau đó `strip()` được thực hiện.

Có ba dạng thường gặp:

| Cách gọi | Khi đối số khác `null` | Khi đối số bằng `null` |
| --- | --- | --- |
| `Objects.requireNonNull(value)` | Trả lại `value` | Ném NPE, thông thường không có thông báo |
| `Objects.requireNonNull(value, "field")` | Trả lại `value` | Ném NPE có thông báo `"field"` |
| `Objects.requireNonNull(value, () -> "field must be present")` | Trả lại `value` | Ném NPE, thông báo từ `Supplier<String>` khi cần |

Dạng `Supplier<String>` hữu ích nếu việc tạo thông báo tương đối tốn công và muốn trì hoãn đến nhánh lỗi. Với thông báo đơn giản như `"field"`, overload nhận `String` thường rõ ràng hơn.

**Chú ý bản chất:** `Objects.requireNonNull` kiểm tra `null` và ném ngoại lệ **từ mã của thư viện**. NPE đó không được sinh ra do JVM phát hiện thao tác đọc trường/call trên `null` ở biểu thức của người gọi, vì vậy không được kỳ vọng có thông báo Helpful NPE dạng `Cannot invoke ... because ... is null`. Muốn báo tên trường thì hãy truyền tên trường vào `requireNonNull`.

Một bẫy thường gặp là đánh giá biểu thức **trước** khi gọi `requireNonNull`:

```java
// Có thể lỗi JVM trước khi requireNonNull được gọi:
Objects.requireNonNull(customer.address, "customer.address");
```

Nếu chính `customer == null`, việc đọc `customer.address` đã có thể ném NPE tự động, và chuỗi `"customer.address"` chưa kịp được dùng. Để nhận thông báo rõ cho từng mức:

```java
Objects.requireNonNull(customer, "customer");
Objects.requireNonNull(customer.address, "customer.address");
```

Các dòng trên là minh họa trong phương thức có biến `customer` thuộc kiểu phù hợp. Phân biệt **đối tượng cha null** với **trường con null** giúp kiểm tra đúng ở biên hệ thống.

## 5. Helpful NPE (JEP 358) hoạt động như thế nào?

Trong bytecode Java, thao tác như `getfield`, `invokevirtual`, `arraylength` hoặc các lệnh truy cập mảng thường sử dụng tham chiếu đã được tính trước. Khi tham chiếu ấy là `null`, VM có đủ thông tin để biết bytecode nào không thể tiếp tục.

JEP 358 cho phép VM phân tích các lệnh có liên quan để dựng thông điệp gồm hai phần:

1. **Consequence** — thao tác không thực hiện được, ví dụ `Cannot invoke "String.length()"`.
2. **Reason** — biểu thức trước đó cung cấp tham chiếu `null`, ví dụ `because "user.name" is null` hoặc `because the return value of "getName()" is null`.

Ví dụ:

```java
static int length(String text) {
    return text.length();
}
```

Khi gọi `length(null)`, một NPE tự động có thể mô tả việc không thể gọi `String.length()` do tham số `text` bằng `null`. Đây là **thông điệp chẩn đoán về thao tác gần nơi lỗi**, không nhất thiết xác định được vì sao đầu vào trở thành `null` từ trước đó. Muốn tìm nguyên nhân gốc phải lần theo dữ liệu, các lời gọi liên quan và invariant.

### Khi nào không có mô tả chi tiết?

Không nên xây logic ứng dụng dựa trên việc `getMessage()` bắt buộc luôn chứa “because ... is null”:

- Có thể không bật tùy chọn của VM hoặc đang chạy một VM/cấu hình khác.
- NPE được tạo/ném rõ ràng bởi mã Java hoặc thư viện chứ không phải JVM trực tiếp tạo trong thao tác bytecode.
- Thông tin tên biến cục bộ trong class file không đầy đủ, khiến cách gọi tên trong thông báo thay đổi.
- Một số ngữ cảnh JVM đặc biệt hoặc loại mã được sinh ra không cung cấp đủ thông tin chi tiết cho message.
- Thông báo là thông tin hỗ trợ chẩn đoán, không phải hợp đồng API ổn định để phân tích bằng `split` hoặc regular expression.

**Khuyến nghị:** Dùng loại ngoại lệ, vị trí lỗi, hợp đồng đầu vào, dữ liệu kiểm thử và stack trace để phân tích; xem Helpful NPE là một lợi ích bổ sung chứ không phải thay thế validation.

## 6. Chương trình Java 17+ hoàn chỉnh so sánh hai loại NPE

Lưu toàn bộ chương trình sau vào **`Main.java`**. Chương trình cố ý tạo từng lỗi, **bắt riêng** để in kết quả kiểm chứng rồi tiếp tục, tránh một lỗi làm dừng các ca sau.

```java
import java.util.Objects;

public class Main {
    static class Address {
        String city;
        Address(String city) { this.city = city; }
    }
    static class Customer {
        Address address;
        Customer(Address address) { this.address = address; }
    }

    static int readCityLength(Customer customer) {
        return customer.address.city.length();
    }

    static String requireId(String id) {
        if (id == null) {
            throw new NullPointerException("customer ID is required");
        }
        return id;
    }

    static void throwWithoutMessage() {
        throw new NullPointerException();
    }

    static int unbox(Integer score) {
        return score;
    }

    public static void main(String[] args) {
        try {
            readCityLength(new Customer(null));
        } catch (NullPointerException ex) {
            System.out.println("JVM_TYPE=" + ex.getClass().getSimpleName());
            String message = ex.getMessage();
            System.out.println("JVM_HELPFUL=" +
                    (message != null && message.startsWith("Cannot read field \"city\"")
                            && message.contains("because")));
            System.out.println("JVM_TOP_FRAME=" +
                    ex.getStackTrace()[0].getMethodName());
        }

        try {
            requireId(null);
        } catch (NullPointerException ex) {
            System.out.println("EXPLICIT_MESSAGE=" + ex.getMessage());
        }

        try {
            throwWithoutMessage();
        } catch (NullPointerException ex) {
            System.out.println("EXPLICIT_EMPTY=" + (ex.getMessage() == null));
        }

        try {
            Objects.requireNonNull(null, "user.name");
        } catch (NullPointerException ex) {
            System.out.println("REQUIRE_MESSAGE=" + ex.getMessage());
        }

        try {
            Objects.requireNonNull(null);
        } catch (NullPointerException ex) {
            System.out.println("REQUIRE_NO_MESSAGE=" + (ex.getMessage() == null));
        }

        try {
            unbox(null);
        } catch (NullPointerException ex) {
            String message = ex.getMessage();
            System.out.println("UNBOX_HELPFUL=" +
                    (message != null && message.contains("intValue()")));
        }
    }
}
```

**Biên dịch và chạy (JDK 17 trở lên):**

```bash
javac --release 17 -encoding UTF-8 Main.java
java -XX:+ShowCodeDetailsInExceptionMessages Main
```

Tùy chọn `-XX:+ShowCodeDetailsInExceptionMessages` được ghi rõ trong lệnh để phép kiểm tra message có ý nghĩa nhất quán trên HotSpot với Java hiện đại. Trong JDK 15+ thông thường, cấu hình này đã được bật mặc định, nhưng dùng flag giúp ý đồ kiểm thử rõ ràng. Chương trình đã được biên dịch với `--release 17` và chạy thành công.

**Stdout chính xác của chương trình đã kiểm chứng trên JVM hỗ trợ JEP 358:**

```text
JVM_TYPE=NullPointerException
JVM_HELPFUL=true
JVM_TOP_FRAME=readCityLength
EXPLICIT_MESSAGE=customer ID is required
EXPLICIT_EMPTY=true
REQUIRE_MESSAGE=user.name
REQUIRE_NO_MESSAGE=true
UNBOX_HELPFUL=true
```

### Phân tích từng kết quả

- **`JVM_TYPE=NullPointerException`:** đọc `customer.address.city` trong `readCityLength` khi `address == null`. NPE phát sinh tự động tại thao tác đọc trường `city`.
- **`JVM_HELPFUL=true`:** thông báo bắt đầu bằng `Cannot read field "city"` và chứa `because`. Chương trình **không so sánh nguyên văn cả chuỗi**, vì tên biểu thức có thể thay đổi theo tùy chọn debug và bytecode.
- **`JVM_TOP_FRAME=readCityLength`:** frame đầu của stack trace là phương thức nơi JVM phát hiện truy cập null, không phải `main` là nơi tạo `Customer(null)`.
- **`EXPLICIT_MESSAGE=customer ID is required`:** mã tự `throw new NullPointerException("...")`; thông báo đến từ chuỗi được cung cấp.
- **`EXPLICIT_EMPTY=true`:** `throw new NullPointerException()` không truyền thông báo; JEP 358 không tự sinh message chi tiết cho ngoại lệ tường minh này.
- **`REQUIRE_MESSAGE=user.name`:** `Objects.requireNonNull(null, "user.name")` sinh NPE với message chủ động chọn.
- **`REQUIRE_NO_MESSAGE=true`:** overload `Objects.requireNonNull(null)` không cung cấp message rõ ràng.
- **`UNBOX_HELPFUL=true`:** việc gán `Integer` null vào `int` khiến bytecode gọi phương thức unboxing như `Integer.intValue()` trên null; đây là NPE do JVM tạo. Chi tiết hiển thị cũng phụ thuộc VM và flag.

**Không nhầm kết quả so sánh `getMessage()` với loại ngoại lệ:** tất cả các ca là `NullPointerException`, nhưng nguồn gốc và thông báo khác nhau. Sự khác biệt được giải thích bằng *nơi và cách ngoại lệ được tạo*, không phải do NPE có các subtype riêng cho Helpful và Explicit.

## 7. Tùy chọn JVM và lịch sử Java 14

Tùy chọn HotSpot:

```bash
java -XX:+ShowCodeDetailsInExceptionMessages Main
```

Bật thông tin chi tiết cho những NPE do VM hỗ trợ. Để tắt phục vụ thử nghiệm so sánh:

```bash
java -XX:-ShowCodeDetailsInExceptionMessages Main
```

Với lệnh tắt, các biểu thức kiểm tra `JVM_HELPFUL` và `UNBOX_HELPFUL` trong `Main.java` trên sẽ có thể in `false`, vì mã đã kiểm tra `message != null`. Trong khi đó, `EXPLICIT_MESSAGE` vẫn là chuỗi do lập trình viên chỉ định và `REQUIRE_MESSAGE` vẫn là `"user.name"` — tùy chọn không viết lại thông báo của NPE được tạo tường minh.

**Mốc phiên bản cần nhớ:**

| Phiên bản | Trạng thái Helpful NPE |
| --- | --- |
| Java 14 | JEP 358 giới thiệu thông báo mô tả NPE do JVM tạo; tùy chọn `ShowCodeDetailsInExceptionMessages` thường **chưa bật mặc định** |
| Java 15 trở đi (HotSpot/JDK phổ biến) | Thông báo chi tiết **được bật mặc định**, vẫn có thể điều chỉnh bằng tùy chọn JVM |
| Java 17/21+ | Cơ chế đã ổn định, hữu ích khi chẩn đoán; không phải tính năng preview cần mở bằng `--enable-preview` |

Với hệ thống triển khai thực tế, kiểm tra JVM và JVM options thực tế thay vì suy ra hoàn toàn từ mức `--release` dùng lúc biên dịch. **`--release 17` quyết định API/ngữ nghĩa biên dịch mục tiêu; tùy chọn Helpful NPE là hành vi runtime của JVM.**

### Lưu ý an toàn khi log

Helpful NPE có thể đưa vào thông báo những tên trường, tên phương thức, đường truy cập dữ liệu và cấu trúc nội bộ của ứng dụng. Đó là thông tin tốt cho lập trình viên nhưng có thể không thích hợp để trả nguyên văn cho người dùng qua HTTP, giao diện công khai hoặc error response.

- Ghi log exception trong hệ thống quan sát lỗi có phân quyền thích hợp.
- Không phản hồi đầy đủ stack trace hoặc chi tiết cấu trúc nội bộ cho client không tin cậy.
- Tạo thông báo lỗi nghiệp vụ an toàn, có thể kèm mã lỗi/correlation ID để đối chiếu ở backend.
- Không đưa thông tin bí mật hoặc dữ liệu người dùng nhạy cảm vào thông báo NPE tường minh.

Tính năng có ích cho debug không đồng nghĩa thông tin debug nên được công khai.

## 8. Vì sao NPE của thư viện có thể không giống NPE tự động?

Xét hai cách kiểm tra tham số ở phần đầu phương thức:

```java
import java.util.Objects;

static int autoLength(String value) {
    return value.length();
}

static int checkedLength(String value) {
    Objects.requireNonNull(value, "value must not be null");
    return value.length();
}
```

Khi gọi với `null`:

- `autoLength(null)`: việc gọi `length()` trên null dẫn tới **NPE trực tiếp của JVM**; nếu được bật, Helpful NPE có thể giải thích thao tác gọi phương thức và tham chiếu null.
- `checkedLength(null)`: `Objects.requireNonNull` từ chối trước khi gọi `length()`; ngoại lệ mang chuỗi `"value must not be null"` do ta chỉ định.
- Nếu `checkedLength("Java")`: kiểm tra qua được, `length()` trả `4`.

Đây là các **phương thức đặt trong một lớp**; không tự chạy nếu thiếu `main` hoặc mã gọi. Ví dụ cho thấy một chỗ dùng `null` có thể gây các thông điệp khác nhau chỉ vì thứ tự kiểm tra.

Cũng không nên kết luận **mọi** ngoại lệ ném từ thư viện đều có message tường minh. Một phương thức thư viện có thể tự dereference null rồi JVM tạo NPE ngay trong mã thư viện; hoặc thư viện có thể chủ động ném NPE không message. Muốn biết hãy nhìn **stack trace, source hoặc API contract** tương ứng.

## 9. Chẩn đoán khi gặp NPE trong ứng dụng

Quy trình thực tế:

1. **Đọc frame đầu và đường gọi liên quan trong stack trace.** Nó cho biết nơi NPE được ghi nhận, không nhất thiết nơi dữ liệu null được tạo ra.
2. **Đọc `getMessage()` nhưng không parse theo định dạng cố định.** Với JVM-generated NPE, Helpful NPE thường chỉ ra thao tác/đường null; với explicit NPE, thông điệp do mã ném quy định.
3. **Xác định hợp đồng tham số:** tham số có được phép null không? Nếu không, thêm validation ở biên phù hợp bằng `Objects.requireNonNull` và thông báo rõ.
4. **Lần theo nguồn gốc dữ liệu:** constructor, dữ liệu đọc từ database, API, map lookup, parser hoặc nhánh logic nào tạo ra null.
5. **Kiểm thử đúng ca thiếu dữ liệu:** test cả đầu vào không hợp lệ và luồng nghiệp vụ hợp lệ. Nếu thiếu dữ liệu là tình huống hợp lệ, thiết kế API thể hiện rõ bằng kết quả tùy chọn, giá trị mặc định thích hợp hoặc kiểu kết quả riêng thay vì vô tình dereference.
6. **Sửa nguyên nhân, không che triệu chứng:** tránh bắt NPE trên diện rộng để trả về `null`/chuỗi rỗng rồi làm mất dấu lỗi thiết kế.

Ví dụ một API nhận tên bắt buộc:

```java
static String displayName(String name) {
    return java.util.Objects.requireNonNull(
            name, "name is required"
    ).strip();
}
```

Việc kiểm tra không thể tự bảo đảm chuỗi sau `strip()` khác rỗng. Nếu hợp đồng không chấp nhận chuỗi blank, cần thêm kiểm tra miền và ngoại lệ phù hợp:

```java
static String displayName(String name) {
    name = java.util.Objects.requireNonNull(name, "name is required").strip();
    if (name.isEmpty()) {
        throw new IllegalArgumentException("name must not be blank");
    }
    return name;
}
```

Hai phương thức cùng chữ ký ở trên là **hai phương án thay thế**, không đặt chung vào một lớp. Ví dụ thứ hai thể hiện khác biệt giữa **thiếu tham chiếu null** và **giá trị không đạt quy tắc nghiệp vụ**.

## 10. Kiểm thử NPE nên khẳng định điều gì?

Nếu dự án dùng JUnit Jupiter, một số kiểm tra thích hợp:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class NullChecksTest {
    @Test
    void explicitlyRejectedNullHasMessage() {
        NullPointerException ex = assertThrows(
                NullPointerException.class,
                () -> java.util.Objects.requireNonNull(null, "customer")
        );
        assertEquals("customer", ex.getMessage());
    }

    @Test
    void validInputIsAccepted() {
        String value = java.util.Objects.requireNonNull("Java", "value");
        assertEquals("Java", value);
    }
}
```

Đây là **lớp test** phụ thuộc JUnit Jupiter đã được cấu hình trong dự án, không phải chương trình Java SE độc lập chạy chỉ với `javac`. Với kiểm tra hợp đồng của `Objects.requireNonNull`, việc assert message tường minh có ý nghĩa vì ta tự quyết định thông báo đó.

Ngược lại, **không nên assert nguyên văn toàn bộ Helpful NPE của JVM** trong unit test thông thường. Văn bản chi tiết có thể phụ thuộc compiler, thông tin debug, VM hoặc các tùy chọn. Nếu mục đích kiểm thử là xử lý dữ liệu null đúng đắn, hãy assert loại ngoại lệ hoặc hành vi của API; nếu mục đích là kiểm thử cụ thể tính năng JVM, cấu hình và môi trường chạy phải được kiểm soát chặt.

### Checklist ngắn

| Trường hợp kiểm thử | Điều cần xác minh |
| --- | --- |
| Đối số bắt buộc bằng `null` | Có từ chối rõ, đúng loại ngoại lệ theo API contract |
| Đối số đúng | Không bị từ chối, kết quả và giá trị chuẩn hóa đúng |
| `throw new NullPointerException("...")` | Thông điệp tường minh đúng chuỗi được tạo |
| `throw new NullPointerException()` | Không kỳ vọng Helpful NPE tự tạo message |
| `Objects.requireNonNull(null, "x")` | NPE có message `"x"` |
| Dereference `null` trong môi trường Helpful NPE đã bật | Thông tin chi tiết hỗ trợ chẩn đoán; không phụ thuộc nguyên văn |
| Log lỗi ra ngoài hệ thống | Không làm lộ stack trace hoặc thông tin nhạy cảm cho client |

## 11. Những nhầm lẫn phổ biến

| Nhận định sai | Điều đúng |
| --- | --- |
| “Mọi NPE trên Java 17 đều có message `Cannot ... because ...`” | Chỉ những NPE phù hợp do JVM trực tiếp tạo mới có thể nhận Helpful NPE; explicit NPE dùng message riêng hoặc `null` |
| “`throw new NullPointerException()` sẽ có message tự động khi bật flag” | Không; message không được dựng từ bytecode cho NPE tự tạo/tự ném như vậy |
| “`Objects.requireNonNull` và `someObject.method()` trên null cho message giống nhau” | `requireNonNull` thực hiện kiểm tra chủ động; dereference có thể sinh Helpful NPE |
| “Có message chi tiết là biết ngay lý do dữ liệu bị null” | Nó chỉ ra thao tác/đường biểu thức bị null gần nơi lỗi, chưa phải nguyên nhân đầu nguồn |
| “Bật Helpful NPE sẽ sửa lỗi null” | Đây chỉ là cải thiện chẩn đoán, không tự phòng tránh NPE |
| “Java 14 luôn bật Helpful NPE theo mặc định” | Java 14 giới thiệu tính năng nhưng mặc định chưa bật; Java 15+ bật mặc định trong HotSpot |
| “Có thể dựa vào nội dung `getMessage()` như giao thức API ổn định” | Không nên parse nguyên văn thông điệp VM; dùng contract, loại ngoại lệ và logging |
| “Mọi trường hợp null đều nên ném NPE” | Thiếu tham chiếu bắt buộc có thể dùng NPE; sai định dạng/giá trị miền nên được xử lý theo hợp đồng tương ứng |
| “Có stack trace thì có thể gửi nguyên bản cho client” | Thông tin kỹ thuật có thể tiết lộ nội bộ; cần tách lỗi công khai và log bảo mật |

## 12. Tự kiểm tra

**Câu 1:** Vì sao hai đoạn sau cùng nhận `null` nhưng có thể khác `getMessage()`?

```java
String text = null;
// text.length(); // JVM trực tiếp phát hiện dereference null.
// throw new NullPointerException("text required"); // Mã tạo ngoại lệ.
```

**Đáp án:** Dòng `text.length()` sẽ để JVM tạo NPE cho thao tác invoke trên null, nên có thể có Helpful NPE; dòng `throw new` tạo ngoại lệ tường minh và `getMessage()` bằng `"text required"`. Hai dòng được comment để tránh dừng chương trình ví dụ.

**Câu 2:** `Objects.requireNonNull(null, "email")` trả về gì?

**Đáp án:** Không trả về giá trị; ném `NullPointerException` với message `"email"`.

**Câu 3:** Dùng `-XX:-ShowCodeDetailsInExceptionMessages` có khiến một `new NullPointerException("explicit")` mất message không?

**Đáp án:** Không. Tùy chọn kiểm soát nội dung Helpful NPE do JVM sinh, không xóa thông điệp do constructor của ngoại lệ được cung cấp.

**Câu 4:** Tại sao NPE có message `Cannot invoke ... because ... is null` chưa đủ để sửa triệt để bug?

**Đáp án:** Nó thường cho biết biểu thức nào null tại thao tác gây lỗi, nhưng không giải thích dữ liệu đó bị null do nhánh code, service, database hay hợp đồng đầu vào nào. Cần điều tra nguồn gốc và viết kiểm thử phù hợp.

**Ghi nhớ:** Phân biệt **nơi tạo ngoại lệ** là chìa khóa: NPE do JVM trực tiếp tạo có thể được Helpful NPE phân tích bytecode để tạo thông điệp giàu ngữ cảnh, còn NPE được ném tường minh hoặc bởi `Objects.requireNonNull` sử dụng thông báo do mã chọn. Trên Java hiện đại, dùng Helpful NPE để debug, dùng validation để thể hiện hợp đồng dữ liệu, và không biến văn bản thông báo JVM thành một API bắt buộc.

### Tài liệu chính thức

- [JEP 358 — Helpful NullPointerExceptions](https://openjdk.org/jeps/358).
- [JDK 15 Release Notes — Enable ShowCodeDetailsInExceptionMessages by default](https://www.oracle.com/java/technologies/javase/15-relnote-issues.html).
- [Java SE API — NullPointerException](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/NullPointerException.html).
- [Java SE API — Objects.requireNonNull](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html#requireNonNull(T,java.lang.String)).
