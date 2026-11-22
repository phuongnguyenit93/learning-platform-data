# Giá trị rỗng và đối tượng chưa tồn tại trong Java

Trong Java, một **biến tham chiếu** có thể đang trỏ đến một đối tượng hoặc có giá trị `null`. Khi nó bằng `null`, ta **không có đối tượng nào để truy cập thông qua tham chiếu đó**. Điều này khác với một đối tượng đã tồn tại nhưng có dữ liệu rỗng, và cũng khác với một biến cục bộ chưa được gán giá trị.

Chẳng hạn, trong ứng dụng bán hàng:

- Khách hàng đã tồn tại, nhưng `phoneNumber` chưa được cung cấp: thuộc tính có thể được biểu diễn bằng `null` nếu mô hình cho phép.
- Khách hàng đã tồn tại và `phoneNumber = ""`: một đối tượng `String` có nội dung rỗng, không phải `null`.
- Tra cứu mã khách hàng không thấy kết quả: hệ thống không tìm được thực thể đáp ứng điều kiện; một API có thể biểu diễn điều này bằng `Optional.empty()` hoặc `null`.
- Khai báo `Customer customer;` trong phương thức mà chưa gán: **biến cục bộ chưa được khởi tạo**, không được phép đọc.
- Gán `customer = null` sau khi dùng: chỉ thay đổi biến tham chiếu; đối tượng cũ chưa chắc biến mất vì nơi khác vẫn có thể đang giữ tham chiếu.

Mục tiêu của bài là hiểu đúng **sự vắng mặt**, **vòng đời đối tượng** và **cách viết mã không bị lỗi truy cập `null`**.

## 1. `null` chính xác là gì?

`null` là giá trị đặc biệt của **null type** trong ngôn ngữ Java, có thể gán cho các kiểu tham chiếu thích hợp, chẳng hạn đối tượng, mảng, interface hay wrapper class. `null` không phải một instance được tạo bởi `new`.

~~~java
String title = null;
Customer customer = null;
int[] scores = null;
Runnable task = null;
~~~

Các khai báo trên hợp lệ về mặt kiểu dữ liệu. Không có một đối tượng `String`, `Customer`, mảng hay `Runnable` nào được tạo ra bởi những phép gán `null` này.

Ngược lại, kiểu nguyên thủy (primitive) như `int`, `long`, `double`, `boolean`, `char` không nhận được `null`:

~~~java
int quantity = 0;        // Hợp lệ: số nguyên có giá trị 0.
// int count = null;     // Lỗi biên dịch.
Integer optionalCount = null; // Hợp lệ: Integer là kiểu tham chiếu.
~~~

**Điểm mấu chốt:** `null` là một **giá trị của tham chiếu**, không phải một đối tượng “rỗng” có thể gọi phương thức. Khi viết `customer.getName()`, Java phải lấy đối tượng thông qua `customer`; nếu `customer == null`, phép gọi instance method này sẽ ném `NullPointerException`.

## 2. Bốn tình huống thường bị nhầm

| Tình huống | Ví dụ | Có đối tượng được tạo? | Điều cần hiểu |
|---|---|---|---|
| Biến cục bộ chưa gán | `Customer c;` | Chưa tạo do câu khai báo đó | Không thể đọc `c` cho đến khi được gán hợp lệ trên mọi nhánh cần thiết |
| Biến tham chiếu bằng `null` | `Customer c = null;` | Không tạo bởi phép gán này | `c` hiện không trỏ đến đối tượng |
| Tham chiếu trỏ đến object | `Customer c = new Customer("Lan");` | Có, nếu khởi tạo thành công | Có một instance và `c` tham chiếu tới nó |
| Đối tượng có dữ liệu rỗng | `String s = "";` hoặc `new ArrayList<>()` | Có một đối tượng tương ứng | Đối tượng tồn tại, chỉ nội dung đang rỗng |

Xem ví dụ:

~~~java
String a = null;
String b = "";
String c = " ";

System.out.println(a == null);     // true
System.out.println(b == null);     // false
System.out.println(b.isEmpty());   // true
System.out.println(c.isEmpty());   // false
System.out.println(c.isBlank());   // true (Java 11+)
~~~

- `null`: không có tham chiếu đến `String`.
- `""`: có chuỗi độ dài bằng 0.
- `" "`: có chuỗi chứa khoảng trắng; nó không rỗng theo `isEmpty()` nhưng được xem là blank theo `isBlank()`.

Tương tự với collection: `List<String> names = null` nghĩa là hiện không có danh sách để dùng qua biến ấy; `List<String> names = List.of()` nghĩa là **có một danh sách, kích thước bằng 0**. Hai trường hợp có ý nghĩa khác nhau và không nên hoán đổi tùy tiện.

## 3. Biến cục bộ chưa khởi tạo khác `null` ra sao?

Biến cục bộ trong phương thức phải được **definitely assigned** trước khi sử dụng. Java kiểm tra điều này lúc biên dịch:

~~~java
void demo() {
    String name;
    // System.out.println(name); // Lỗi: variable name might not have
    //                           // been initialized.
    name = "Lan";
    System.out.println(name);    // Hợp lệ.
}
~~~

Nếu ta gán `name = null;`, biến **đã được khởi tạo về mặt ngôn ngữ** nhưng giá trị tham chiếu của nó là `null`:

~~~java
void demo() {
    String name = null;
    System.out.println(name == null); // true
}
~~~

Với field của object, static field và phần tử mảng, Java cung cấp **giá trị mặc định** nếu chưa có phép gán khác:

| Kiểu dữ liệu | Giá trị mặc định của field/phần tử mảng |
|---|---|
| `byte`, `short`, `int`, `long` | Số 0 tương ứng |
| `float`, `double` | Số 0.0 tương ứng |
| `boolean` | `false` |
| `char` | Ký tự `'\u005Cu0000'` (U+0000) |
| Kiểu tham chiếu như `String`, `Customer`, mảng | `null` |

Ví dụ:

~~~java
class Profile {
    String email; // Mặc định null nếu không được gán.
    int points;   // Mặc định 0.
}

Profile profile = new Profile();
System.out.println(profile.email == null); // true
System.out.println(profile.points);        // 0

String[] labels = new String[2];
System.out.println(labels[0] == null);     // true
~~~

Giá trị mặc định **không áp dụng cho biến cục bộ thông thường**. Nên khởi tạo field có chủ đích qua constructor thay vì chỉ dựa vào mặc định, đặc biệt nếu `null` không phải trạng thái hợp lệ của đối tượng.

## 4. Phân biệt biến tham chiếu với chính đối tượng

Hãy tưởng tượng biến tham chiếu là một “đường dẫn” đến đối tượng. Có thể có nhiều đường dẫn cùng tới một object; bỏ một đường dẫn không tự động xóa object.

~~~java
class Box {
    int value;
}

Box first = new Box();
first.value = 42;

Box alias = first;
first = null;

System.out.println(first == null); // true
System.out.println(alias.value);   // 42
~~~

`new Box()` tạo một object, ban đầu cả `first` và `alias` đều có thể tham chiếu đến nó. Sau `first = null`, `alias` vẫn tham chiếu tới object ấy.

~~~mermaid
flowchart TD
    A["Biến first"] --> N["null<br/>Không trỏ đến object"]
    B["Biến alias"] --> O["Đối tượng Box<br/>value = 42"]
~~~

Sơ đồ biểu diễn tình huống **sau khi gán `first = null`**; không phải sơ đồ địa chỉ bộ nhớ thực tế.

Điều đó giải thích ba câu rất dễ nhầm:

1. **“Biến bằng null”** chỉ nói về giá trị hiện tại của biến tham chiếu ấy.
2. **“Đối tượng đã bị xóa”** không suy ra từ một phép gán `null`. Java không có lệnh `delete object` như cách một số ngôn ngữ quản lý tài nguyên.
3. **“Đối tượng không còn reachable”** là khi không còn đường đi tham chiếu từ các GC roots đến object. Khi ấy object *có thể đủ điều kiện* để garbage collector thu hồi, nhưng thời điểm thu hồi không được bảo đảm.

Đối tượng cũng có thể tồn tại trong bộ nhớ nhưng không còn tham chiếu mà mã chương trình có thể dùng để truy cập. Vì vậy cần phân biệt **khả năng truy cập** và **sự tồn tại vật lý trong bộ nhớ tại một thời điểm**.

## 5. Ví dụ Java hoàn chỉnh: khách hàng có thể tìm thấy hoặc không

Dưới đây là một chương trình chạy được với **Java 17+**. Repository lưu sẵn một khách hàng; truy vấn ID tồn tại trả về `Optional<Customer>` chứa khách hàng, ID không tồn tại trả về `Optional.empty()`.

Lưu vào **`Demo.java`**:

~~~java
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public class Demo {
    public static void main(String[] args) {
        CustomerRepository repository = new CustomerRepository();

        Optional<Customer> found = repository.findById("C01");
        Optional<Customer> missing = repository.findById("C99");

        System.out.println("Có C01: " + found.isPresent());
        System.out.println("Có C99: " + missing.isPresent());

        String name = found
                .map(Customer::getName)
                .orElse("Không tìm thấy");

        String absentName = missing
                .map(Customer::getName)
                .orElse("Không tìm thấy");

        System.out.println("Tên C01: " + name);
        System.out.println("Tên C99: " + absentName);

        Customer one = found.orElseThrow();
        Customer alias = one;

        System.out.println("Cùng object: " + (one == alias));
        System.out.println("Địa chỉ giao hàng: "
                + one.getShippingAddress()
                     .orElse("Chưa cung cấp"));

        try {
            repository.findById("C99")
                    .orElseThrow(() -> new IllegalArgumentException(
                            "Không có khách hàng C99"));
        } catch (IllegalArgumentException exception) {
            System.out.println(exception.getMessage());
        }

        // Objects.equals xử lý an toàn khi một hoặc cả hai vế null.
        String inputName = null;
        System.out.println("Tên khớp: "
                + Objects.equals(inputName, one.getName()));
    }

    static final class Customer {
        private final String id;
        private final String name;
        private String shippingAddress;

        Customer(String id, String name) {
            this.id = Objects.requireNonNull(id, "id không được null");
            this.name = Objects.requireNonNull(name, "name không được null");
            if (id.isBlank() || name.isBlank()) {
                throw new IllegalArgumentException(
                        "id và name không được rỗng");
            }
        }

        String getName() {
            return name;
        }

        Optional<String> getShippingAddress() {
            return Optional.ofNullable(shippingAddress);
        }

        void setShippingAddress(String address) {
            if (address != null && address.isBlank()) {
                throw new IllegalArgumentException(
                        "Địa chỉ không được chỉ chứa khoảng trắng");
            }
            this.shippingAddress = address;
        }
    }

    static final class CustomerRepository {
        private final Map<String, Customer> customers =
                Map.of("C01", new Customer("C01", "Lan"));

        Optional<Customer> findById(String id) {
            Objects.requireNonNull(id, "id không được null");
            return Optional.ofNullable(customers.get(id));
        }
    }
}
~~~

Chạy trong terminal:

~~~bash
javac Demo.java
java Demo
~~~

Kết quả:

~~~text
Có C01: true
Có C99: false
Tên C01: Lan
Tên C99: Không tìm thấy
Cùng object: true
Địa chỉ giao hàng: Chưa cung cấp
Không có khách hàng C99
Tên khớp: false
~~~

### Giải thích từng tình huống

**Trường hợp 1 — Khách hàng tồn tại:** repository có đối tượng `Customer("C01", "Lan")` và `findById("C01")` trả về `Optional` chứa tham chiếu đến đối tượng đó. `one` và `alias` được lấy từ cùng tham chiếu nên `one == alias` là `true`.

**Trường hợp 2 — Khách hàng không tìm thấy:** `Map.get("C99")` trả về `null` vì bản đồ không có khóa ấy. `Optional.ofNullable(...)` chuyển nó thành `Optional.empty()`. Không có **kết quả truy vấn phù hợp**; điều này chưa nói gì về việc ở đâu đó trong toàn hệ thống có thể có đối tượng khác cùng thông tin hay không.

**Trường hợp 3 — Khách hàng tồn tại nhưng chưa có địa chỉ:** đối tượng `Customer` vẫn tồn tại đầy đủ, nhưng field `shippingAddress` được phép ở trạng thái `null`. Getter bộc lộ khả năng thiếu dữ liệu bằng `Optional<String>`. Khách hàng “chưa cung cấp địa chỉ” không đồng nghĩa với “khách hàng không tồn tại”.

**Trường hợp 4 — Dữ liệu bắt buộc không được null:** constructor gọi `Objects.requireNonNull` để từ chối `id` hay `name` rỗng theo nghĩa `null` ngay từ đầu. Bước `isBlank()` kiểm tra thêm chuỗi rỗng/khoảng trắng. Nhờ đó một object được xây dựng thành công không có trạng thái sai ở hai trường bắt buộc.

Trong ứng dụng thật, repository có thể truy vấn database thay vì `Map`; nguyên tắc biểu diễn dữ liệu vắng mặt vẫn tương tự.

## 6. Vì sao xảy ra `NullPointerException`?

`NullPointerException` (NPE) là lỗi runtime thường gặp khi chương trình cần dùng một giá trị tham chiếu `null` như thể nó trỏ tới đối tượng hợp lệ.

Ví dụ:

~~~java
String title = null;
// System.out.println(title.length()); // NPE nếu bỏ comment.

Customer customer = null;
// customer.getName();                  // NPE nếu gọi.

int[] numbers = null;
// System.out.println(numbers.length);  // NPE nếu truy cập độ dài mảng.
~~~

Ở đây biến **có kiểu hợp lệ** nhưng không có object để truy cập. Compiler thường không chặn được các lời gọi ấy trong Java thông thường; lỗi phát sinh khi chạy đến câu lệnh.

Cần phân biệt với lỗi khác:

| Tình huống | Kết quả |
|---|---|
| Đọc biến cục bộ chưa được gán | Lỗi biên dịch |
| Gọi instance method trên `null` | `NullPointerException` |
| Truy cập field instance qua `null` | `NullPointerException` |
| Đọc phần tử mảng khi tham chiếu mảng là `null` | `NullPointerException` |
| Mảng có thật nhưng dùng chỉ số vượt giới hạn | `ArrayIndexOutOfBoundsException` |
| Gọi `Optional.empty().get()` | `NoSuchElementException` |
| Tự dùng `Objects.requireNonNull(null)` | `NullPointerException` có chủ đích để báo dữ liệu bắt buộc thiếu |

Một NPE không có nghĩa là “object đã bị garbage collector xóa giữa chừng”. Nó chỉ cho biết thao tác hiện tại đã cố sử dụng tham chiếu `null` theo cách không hợp lệ.

### Tự động unboxing cũng có thể gây NPE

Wrapper `Integer` có thể là `null`. Khi Java chuyển `Integer` sang `int` (auto-unboxing), nó cần lấy giá trị từ object:

~~~java
Integer quantity = null;
// int total = quantity + 1; // NPE do unboxing quantity.
~~~

Nếu một số lượng **bắt buộc phải có** thì thường dùng primitive `int` và quy tắc hợp lệ riêng. Nếu dữ liệu có thể vắng mặt, thiết kế cách biểu diễn sự vắng mặt rõ ràng và xử lý trước khi tính toán.

## 7. Các cách phòng tránh `null` đúng mục đích

Không có một cách duy nhất cho mọi bài toán. Trước khi xử lý, cần xác định: **được phép thiếu dữ liệu hay thiếu dữ liệu là một lỗi?**

### Cách 1 — Kiểm tra `null` tường minh

~~~java
String middleName = getMiddleName();

if (middleName != null) {
    System.out.println(middleName.toUpperCase());
} else {
    System.out.println("(không có tên đệm)");
}
~~~

Cách này phù hợp khi API đã định nghĩa giá trị `null` là hợp lệ. Kiểm tra nên đặt gần nơi dereference và cần áp dụng cho đúng biến đang được sử dụng.

Nếu chỉ muốn gọi hành vi khi có đối tượng:

~~~java
if (customer != null) {
    customer.sendWelcomeMessage();
}
~~~

Đoạn `customer.sendWelcomeMessage()` là mã minh họa cho một lớp `Customer` có phương thức tương ứng; nó không thuộc lớp `Customer` trong `Demo.java` ở trên.

### Cách 2 — Kiểm tra bằng `Objects.requireNonNull` cho dữ liệu bắt buộc

~~~java
import java.util.Objects;

class Product {
    private final String sku;

    Product(String sku) {
        this.sku = Objects.requireNonNull(sku, "SKU bắt buộc");
    }
}
~~~

Nếu `sku == null`, constructor ném NPE với thông báo rõ ràng ngay tại nơi vi phạm hợp đồng. Kiểm tra này **không** từ chối `""` hoặc chuỗi chỉ chứa khoảng trắng; cần quy tắc riêng cho nội dung nếu bài toán yêu cầu.

Có thể dùng `IllegalArgumentException` khi muốn phân loại đầu vào không hợp lệ theo quy ước ứng dụng. Điều quan trọng là hợp đồng đầu vào nhất quán và không để trạng thái bắt buộc bị thiếu đi sâu vào hệ thống.

### Cách 3 — Sử dụng `Optional<T>` để biểu diễn kết quả có thể vắng mặt

~~~java
Optional<Customer> result = repository.findById("C01");

result.ifPresent(c -> System.out.println(c.getName()));

String displayName = result.map(Customer::getName)
                           .orElse("Khách chưa xác định");

Customer required = result.orElseThrow(
        () -> new IllegalStateException("Khách hàng không tồn tại"));
~~~

`Optional<T>` là một object bao ngoài trạng thái **có giá trị** hoặc **không có giá trị**:

| API | Ý nghĩa |
|---|---|
| `Optional.of(value)` | Yêu cầu `value` khác `null`; nếu null sẽ ném NPE |
| `Optional.ofNullable(value)` | Có thể tạo `Optional.empty()` nếu value null |
| `Optional.empty()` | Không có giá trị |
| `map(fn)` | Biến đổi giá trị nếu có; mapper trả null sẽ cho empty |
| `orElse(defaultValue)` | Lấy giá trị hoặc giá trị mặc định |
| `orElseGet(supplier)` | Chỉ tạo giá trị mặc định nếu đang empty |
| `orElseThrow(...)` | Báo lỗi nếu không có giá trị |
| `ifPresent(action)` | Thực hiện hành động nếu có giá trị |

**Bẫy:** `orElse(expensiveCall())` gọi `expensiveCall()` để tính đối số **dù Optional đã có giá trị**. Nếu muốn chỉ gọi khi thiếu, dùng `orElseGet(() -> expensiveCall())`.

Không nên dùng `Optional.get()` thiếu kiểm tra trạng thái: `Optional.empty().get()` ném `NoSuchElementException`. Thường nên ưu tiên `orElse`, `orElseThrow`, `map` hoặc `ifPresent`.

**Thực hành:** `Optional` đặc biệt hữu ích làm **kiểu trả về** cho phương thức có thể không tìm thấy kết quả. Không nhất thiết thay mọi field, tham số, collection hoặc đối tượng bằng `Optional`. Tránh việc phương thức lúc trả `Optional.empty()`, lúc trả **chính `null` thay cho Optional**, vì người gọi lại phải xử lý thêm một tầng thiếu dữ liệu.

### Cách 4 — Trả collection rỗng khi hợp đồng là “có 0 hoặc nhiều phần tử”

~~~java
import java.util.List;

List<String> findTagsForProduct(String productId) {
    return List.of(); // Không có tag; vẫn là List hợp lệ.
}
~~~

Khi trả `List.of()` thay `null`, người gọi có thể xử lý thống nhất:

~~~java
for (String tag : findTagsForProduct("P01")) {
    System.out.println(tag);
}
~~~

Với các API tra cứu nhiều phần tử, danh sách rỗng thường tự nhiên hơn `null`: kết quả tìm kiếm có **0 phần tử**. Tuy nhiên nếu “chưa tải dữ liệu”, “bị lỗi khi tải” và “tải thành công nhưng không có phần tử” là các trạng thái nghiệp vụ khác nhau, cần mô hình rõ chúng thay vì gộp hết thành danh sách rỗng.

### Cách 5 — Viết so sánh chuỗi và đối tượng an toàn

~~~java
import java.util.Objects;

String status = null;

System.out.println("ACTIVE".equals(status)); // false
System.out.println(Objects.equals(status, "ACTIVE")); // false
System.out.println(Objects.equals(null, null)); // true
~~~

`status.equals("ACTIVE")` sẽ ném NPE nếu status null. Đối với so sánh nội dung object, dùng `equals()` theo hợp đồng của kiểu; `==` đối với hai tham chiếu kiểm tra **có cùng object không**, không so sánh nội dung thông thường.

## 8. Phát hiện `null` qua cú pháp Java và điều kiện an toàn

### So sánh `== null` / `!= null`

~~~java
if (customer == null) {
    System.out.println("Chưa có khách hàng");
} else {
    System.out.println(customer.getName());
}
~~~

So sánh với `null` bằng `==` là đúng. Không viết `customer.equals(null)`, vì có thể ném NPE khi customer null, và lại diễn tả sai mục đích kiểm tra tham chiếu.

### Toán tử logic short-circuit

Java đánh giá `&&` từ trái sang phải, và dừng khi điều kiện bên trái là `false`:

~~~java
if (customer != null && customer.isActive()) {
    System.out.println("Có khách hàng đang hoạt động");
}
~~~

`customer.isActive()` chỉ được gọi khi `customer != null`. Đây là mã minh họa cho lớp có phương thức `isActive()`.

Đổi chiều điều kiện có thể gây lỗi:

~~~java
// Sai: customer có thể bị dereference trước khi kiểm tra null.
// if (customer.isActive() && customer != null) { ... }
~~~

Tương tự, toán tử `||` dừng khi vế trái đúng, nên `customer == null || customer.isActive()` có thể chạy an toàn về mặt null dereference trong điều kiện đơn luồng và khi tham chiếu không bị thay đổi đồng thời. Tuy nhiên hãy viết điều kiện dễ đọc và tránh tác dụng phụ khi đánh giá.

### `instanceof` khi biến null

~~~java
Object value = null;

System.out.println(value instanceof String); // false
~~~

`instanceof` với toán hạng `null` trả về `false`, không ném NPE. Nhưng điều đó không biến `null` thành đối tượng `String`.

### Java không có toán tử `?.` như một số ngôn ngữ khác

Cú pháp `customer?.getName()` **không phải cú pháp truy cập an toàn hợp lệ trong Java 17**. Cần kiểm tra `null`, dùng Optional, hoặc dùng một API mô hình hóa sự thiếu dữ liệu rõ ràng. Không nhầm cú pháp của Kotlin, C# hoặc JavaScript với Java.

## 9. Khi nào một đối tượng “chưa tồn tại”?

Câu này có ít nhất ba ý nghĩa khác nhau:

| Ngữ cảnh | Ví dụ | Cách hiểu đúng |
|---|---|---|
| Trong mã Java | `User u = null;` | Chưa có object `User` để truy cập bằng `u`; ở nơi khác vẫn có thể có User |
| Trong kết quả truy vấn | `findById("C99")` trả empty | Không tìm thấy bản ghi theo điều kiện tại thời điểm truy vấn |
| Trong quy trình nghiệp vụ | Chưa có đơn hàng cho giỏ hàng | Một đơn hàng có thể chưa được tạo hoặc lưu; cần quy tắc nghiệp vụ xác định |
| Trong bộ nhớ JVM | Object không còn reachable | Có thể được GC thu hồi sau này; không suy ra ngay thời điểm |
| Trong luồng điều khiển | Constructor chưa được gọi | Code hiện tại chưa tạo instance theo con đường ấy |

Ví dụ:

~~~java
Order order = null;

// Sau thao tác hợp lệ nào đó:
order = new Order(); // Tạo một instance nếu constructor thành công.
~~~

Không thể nói từ `order == null` rằng “không tồn tại bất cứ Order nào trong chương trình”. Chỉ có thể nói **biến `order` hiện không trỏ tới một Order**.

Mặt khác, nếu thực thể chưa có trong database, việc tạo `new Order()` trong bộ nhớ cũng **không tự động** tạo bản ghi trong database. Đối tượng Java và sự tồn tại của thực thể trong hệ thống lưu trữ là hai tầng khác nhau.

### Một đối tượng có thật nhưng trạng thái có trường null

~~~java
class Employee {
    final String name;
    String managerName; // null nếu chưa có người quản lý.

    Employee(String name) {
        this.name = java.util.Objects.requireNonNull(name);
    }
}

Employee employee = new Employee("Mai");
System.out.println(employee == null);             // false
System.out.println(employee.managerName == null); // true
~~~

Đây là trường hợp rất thực tế: **đối tượng nhân viên tồn tại**, nhưng thông tin quản lý trực tiếp chưa có. Việc một field bằng `null` không làm toàn bộ object trở thành null.

## 10. Lựa chọn cách biểu diễn sự vắng mặt trong thiết kế OOP

Trước khi chọn `null`, hãy đặt câu hỏi **vắng mặt có nghĩa gì với nghiệp vụ?**

~~~mermaid
flowchart TD
    A["Cần biểu diễn dữ liệu có thể vắng mặt"] --> B{"Dữ liệu có bắt buộc không?"}
    B -->|Có| C["Kiểm tra ngay ở constructor / ranh giới API"]
    B -->|Không| D{"Kết quả có nhiều phần tử?"}
    D -->|Có| E["Thường trả collection rỗng khi 0 kết quả"]
    D -->|Không| F{"Là kết quả truy vấn đơn có thể không tìm thấy?"}
    F -->|Có| G["Cân nhắc Optional&lt;T&gt; làm kiểu trả về"]
    F -->|Không| H["Mô hình hóa nullable field hoặc trạng thái nghiệp vụ tường minh"]
~~~

Sơ đồ là gợi ý thiết kế, không phải quy tắc tuyệt đối. Ví dụ nếu `null` có nghĩa “chưa tải”, `List.of()` có nghĩa “đã tải nhưng không có dữ liệu”, thì đổi `null` thành danh sách rỗng làm mất thông tin. Khi có nhiều trạng thái nghiệp vụ, cân nhắc một kiểu riêng:

~~~java
sealed interface LoadResult<T>
        permits Loaded, NotFound, LoadFailed {}

record Loaded<T>(T value) implements LoadResult<T> {}
record NotFound<T>() implements LoadResult<T> {}
record LoadFailed<T>(String reason) implements LoadResult<T> {}
~~~

Các record trên minh họa rằng **“không tìm thấy” khác “không tải được”**. Với Java 17, sealed interface và record được hỗ trợ chính thức. Nếu cần trạng thái bất biến, nên kiểm tra các giá trị bắt buộc trong constructor của record tương ứng.

### Phân biệt lỗi và trường hợp bình thường

- **ID không tìm thấy** có thể là kết quả bình thường: dùng `Optional.empty()` hoặc một kiểu kết quả tường minh.
- **ID null khi hợp đồng yêu cầu bắt buộc** thường là lỗi từ người gọi: kiểm tra ngay, cung cấp thông báo phù hợp.
- **Database kết nối thất bại** không tương đương với “không có khách hàng”: phải báo lỗi, tránh trả `Optional.empty()` làm người gọi hiểu sai.
- **Danh sách tìm kiếm không có kết quả** thường được biểu diễn bằng collection rỗng.
- **Thuộc tính tùy chọn chưa có** có thể cho phép null nội bộ, nhưng API nên thể hiện rõ hợp đồng dùng và tính hợp lệ.

Trong hệ thống lớn, tài liệu API và kiểm thử giúp người dùng API biết khi nào cần xử lý sự vắng mặt.

## 11. Một số lỗi phổ biến cần tránh

| Lỗi | Vấn đề | Cách sửa |
|---|---|---|
| Gọi `obj.method()` khi `obj` có thể null | NPE lúc chạy | Kiểm tra null hoặc thiết kế kiểu trả về an toàn |
| Cho rằng `""` là `null` | Làm sai quy tắc dữ liệu | Phân biệt missing, empty và blank |
| Sử dụng `Integer` có thể null trong biểu thức số học | Auto-unboxing có thể ném NPE | Kiểm tra/đặt mặc định theo nghiệp vụ trước khi tính |
| Trả `null` thay vì danh sách không có phần tử | Người gọi phải phân nhánh ở nhiều nơi | Cân nhắc trả collection rỗng |
| Trả `null` thay cho `Optional<T>` | Vi phạm hợp đồng, làm `Optional` mất ý nghĩa | Trả `Optional.empty()` khi không có kết quả |
| Gọi `Optional.get()` thiếu kiểm tra | Có thể ném `NoSuchElementException` | Dùng `orElseThrow`, `orElse`, `map`… |
| Bắt mọi NPE rồi âm thầm bỏ qua | Che khuất lỗi lập trình hoặc dữ liệu | Sửa nơi tạo/đọc giá trị null, fail fast khi cần |
| Dùng `null` cho mọi trạng thái không rõ | Trộn “chưa nhập”, “không tồn tại”, “lỗi truy vấn” | Mô hình hóa rõ trạng thái nghiệp vụ |
| Gán `x = null` rồi tin đối tượng đã bị hủy | Có thể còn alias hoặc GC chưa thu hồi | Hiểu reachability; quản lý tài nguyên qua cơ chế phù hợp |
| Dùng `null` làm lý do bỏ qua đóng file/kết nối | Lộ tài nguyên bên ngoài heap | Dùng try-with-resources cho tài nguyên `AutoCloseable` |

**Lưu ý:** garbage collector chỉ quản lý bộ nhớ của các đối tượng Java theo mô hình của JVM; không bảo đảm tự đóng đúng hạn file, socket hay kết nối database. Vì vậy tránh xem phép gán `null` là hành động giải phóng mọi loại tài nguyên.

## 12. Tự luyện tập và kiểm tra

### Bài 1 — Dự đoán kết quả

~~~java
String first = null;
String second = "";
System.out.println(first == null);
System.out.println(second == null);
System.out.println(second.length());
~~~

**Đáp án:**

~~~text
true
false
0
~~~

`second` trỏ đến một chuỗi rỗng, nên `length()` hợp lệ và trả 0.

### Bài 2 — Hai tham chiếu đến một đối tượng

~~~java
class Note {
    String text = "Ban đầu";
}

Note one = new Note();
Note two = one;
one = null;
System.out.println(two.text);
~~~

**Đáp án:** in `Ban đầu`. Phép gán `one = null` không xóa đối tượng mà `two` đang trỏ tới.

### Bài 3 — Lỗi xuất hiện ở giai đoạn nào?

~~~java
String value;
// System.out.println(value);
~~~

**Đáp án:** nếu bỏ comment dòng đọc `value`, xảy ra **lỗi biên dịch**, vì biến cục bộ chưa được gán. Đây không phải NPE.

### Bài 4 — Wrapper và unboxing

~~~java
Integer score = null;
// int doubled = score * 2;
~~~

**Đáp án:** nếu bỏ comment biểu thức tính toán, có thể ném NPE khi Java tự unbox `score` thành `int`.

### Bài 5 — API tìm kiếm

Một phương thức `findUserById(id)` phải phân biệt “không tìm thấy” và “máy chủ database lỗi”. Có nên trả `Optional.empty()` cho cả hai?

**Đáp án:** Không. `Optional.empty()` có thể biểu diễn không tìm thấy. Lỗi truy cập database cần được báo theo hợp đồng API (ví dụ exception hoặc kết quả lỗi tường minh) để không bị hiểu nhầm thành vắng mặt bình thường.

### Bài 6 — Viết một phương thức an toàn

Yêu cầu: nhận `String name`, trả `"(chưa có tên)"` nếu `name` bằng null hoặc toàn khoảng trắng; ngược lại trả chuỗi đã `trim()`.

Gợi ý lời giải:

~~~java
static String displayName(String name) {
    if (name == null || name.isBlank()) {
        return "(chưa có tên)";
    }
    return name.trim();
}
~~~

Vế `name.isBlank()` chỉ được đánh giá nếu `name != null` nhờ cơ chế short-circuit của `||`, nên không gây NPE.

## Ghi nhớ

Trong Java, `null` biểu thị **không có đối tượng được tham chiếu qua giá trị tham chiếu hiện tại**; nó không phải đối tượng rỗng. Biến cục bộ chưa gán là một vấn đề *khởi tạo* được compiler kiểm tra. Chuỗi hoặc danh sách rỗng vẫn là **đối tượng có thật**. Một phép gán `null` không có nghĩa object đã bị hủy, và kết quả truy vấn vắng mặt không phải lúc nào cũng chứng minh thực thể chưa từng tồn tại.

Khi thiết kế lớp và API, hãy xác định dữ liệu **bắt buộc**, **có thể thiếu hợp lệ**, **không tìm thấy** hay **xảy ra lỗi**; từ đó chọn `requireNonNull`, kiểm tra `null`, `Optional`, collection rỗng hoặc kiểu kết quả nghiệp vụ phù hợp. Điều này giúp hạn chế `NullPointerException` và giữ ý nghĩa đối tượng rõ ràng trong thiết kế OOP.