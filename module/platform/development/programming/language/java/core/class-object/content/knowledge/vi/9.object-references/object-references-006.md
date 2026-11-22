# `null` biểu thị không có đối tượng trong Java

Trong Java, một **biến, field, tham số hoặc kết quả phương thức thuộc kiểu tham chiếu (*reference type*)** có thể nhận giá trị **`null`**. Giá trị này nói rằng **tham chiếu hiện tại không trỏ đến một đối tượng hoặc mảng nào**. Nó không phải là một object mang tên `null`, không phải một chuỗi rỗng, không phải con số 0 và cũng không phải một địa chỉ bộ nhớ mà chương trình được phép thao tác trực tiếp.

Đây là một khái niệm nền tảng của lập trình hướng đối tượng: khi dùng `Customer customer`, ta có một **biến tham chiếu kiểu `Customer`**; biến đó có thể trỏ tới một `Customer` thực sự hoặc có thể bằng `null`. Việc khai báo kiểu tham chiếu **không tự tạo ra đối tượng**.

Ví dụ đầu tiên:

~~~java
class Customer {
    String name;
}

class Demo {
    void run() {
        Customer customer = null;        // Hiện chưa tham chiếu object nào
        customer = new Customer();       // Bây giờ có một object Customer
        customer.name = "Lan";          // Truy cập field trên object có thật
        customer = null;                // Biến không trỏ tới object ấy nữa
    }
}
~~~

Đây là **đoạn minh họa khai báo lớp**, chưa phải chương trình chạy độc lập. Khi thực hiện `customer = null` ở cuối, **không có lệnh hủy object ngay lập tức**: nếu còn tham chiếu khác đến `Customer`, object vẫn có thể được sử dụng; nếu không còn khả năng truy cập, JVM có thể thu gom về sau theo cơ chế garbage collection.

Bài này dùng Java 17+ và tập trung vào ý nghĩa của `null` đối với các tham chiếu, cách phát hiện và xử lý không có object, những lỗi thường gặp và cách thiết kế hợp đồng API rõ ràng.

## 1. Nhận diện đúng biến tham chiếu và đối tượng

So sánh:

~~~java
Customer a = null;
Customer b = new Customer();
Customer c = b;
~~~

Trong đoạn fragment này:

- `a` có **kiểu khai báo `Customer`**, nhưng giá trị của nó là `null`: không trỏ tới một object nào.
- `b` có **kiểu khai báo `Customer`** và trỏ tới object vừa được tạo bởi `new Customer()`.
- `c` giữ **bản sao giá trị tham chiếu** của `b`, nên `b` và `c` cùng trỏ tới **một object**.

Sơ đồ khái niệm:

~~~text
a ----------> null                  (không có object đích)

b ------+
        +-----> Customer object     (một đối tượng có thật)
c ------+
~~~

Không có một “object null” nằm sau mũi tên đầu tiên. `null` là trạng thái **không có object được tham chiếu**, chứ không phải object đặc biệt với các field hoặc method.

### 1.1. Reference type không đồng nghĩa object đã được tạo

~~~java
String text = null;         // Không có String object qua text
int[] values = null;        // Không có array object qua values
Runnable task = null;       // Không có implementation object qua task
Object item = null;         // Không có object qua item
~~~

Dù declared type lần lượt là class, array, interface và `Object`, các biến đều có thể nhận null.

Ngược lại:

~~~java
String empty = "";          // Có một String object với độ dài 0
int[] zero = new int[0];    // Có một array object với độ dài 0
Object object = new Object(); // Có một Object thực sự
~~~

`""` và `new int[0]` **không phải null**. Chúng đại diện cho những object có thật dù không mang dữ liệu nội dung hoặc phần tử.

| Biểu thức | Có object được tham chiếu? | Ý nghĩa |
| --- | --- | --- |
| `String s = null;` | Không | Chưa có String qua biến `s` |
| `String s = "";` | Có | String rỗng |
| `int[] a = null;` | Không | Không có mảng |
| `int[] a = new int[0];` | Có | Mảng tồn tại, 0 phần tử |
| `Object o = new Object();` | Có | Object thực |
| `String s = "null";` | Có | Chuỗi gồm bốn chữ `n`, `u`, `l`, `l` |

Đặt tên `s` hoặc loại dữ liệu là gì không biến `null` thành đối tượng. Chỉ những biểu thức tạo/lấy ra tham chiếu hợp lệ mới làm biến trỏ tới object.

## 2. `null` dùng được ở đâu?

Các **reference types** trong Java bao gồm kiểu class, interface và array. Ngoài ra, các kiểu type variable phù hợp cũng thuộc hệ kiểu tham chiếu. Với chúng, `null` có thể là giá trị của biến/tham số/field hoặc kết quả method theo các quy tắc ngôn ngữ.

~~~java
class Account {
    String owner;      // reference field, có thể null
    int[] history;     // reference field, có thể null
}

class Service {
    Account findAccount(boolean found) {
        return found ? new Account() : null;
    }

    void setAccount(Account account) {
        // Caller có thể truyền null nếu API không từ chối
    }
}
~~~

Đây là đoạn minh họa class.

### 2.1. Primitive không thể có giá trị `null` trực tiếp

Java có tám primitive types: `byte`, `short`, `int`, `long`, `float`, `double`, `char` và `boolean`. Các giá trị primitive không phải tham chiếu đến object, nên không thể trực tiếp gán null:

~~~java
// int count = null;       // Lỗi biên dịch
// boolean active = null; // Lỗi biên dịch
// double rate = null;    // Lỗi biên dịch
~~~

Nếu cần một số nguyên có khả năng “chưa biết”, một phương án là `Integer` (reference type) có thể null hoặc `OptionalInt` ở ranh giới phương thức; lựa chọn phụ thuộc hợp đồng API.

### 2.2. `null` là literal đặc biệt, không phải tên class

Bạn có thể viết:

~~~java
Object value = null;
String title = null;
int[] scores = null;
~~~

Nhưng không khai báo biến với “kiểu `null`” như:

~~~java
// null value = null; // Không hợp lệ
~~~

Đặc tả Java nói đến *null type* để mô tả kiểu của null literal, nhưng **`null` không phải một tên kiểu do lập trình viên dùng để khai báo như `String` hoặc `Object`**.

## 3. Giá trị mặc định của field: reference field bắt đầu bằng `null`

Khi tạo object bình thường bằng `new`, những field chưa được khởi tạo tường minh sẽ có giá trị mặc định theo kiểu.

| Loại field | Giá trị mặc định |
| --- | --- |
| Primitive `int` | `0` |
| Primitive `long` | `0L` |
| Primitive `double` | `0.0` |
| Primitive `boolean` | `false` |
| Primitive `char` | Mã ký tự `'\u0000'` |
| Reference `String` | `null` |
| Reference `Customer` | `null` |
| Reference `int[]` | `null` |

Ví dụ:

~~~java
class Order {
    String orderCode;  // null
    Customer buyer;    // null
    int quantity;      // 0
}
~~~

`new Order()` tạo **một object Order có thật**, nhưng bên trong nó, `orderCode` và `buyer` có giá trị null. Đây là hai tầng ý nghĩa khác nhau:

1. Tham chiếu đến **Order object** có thật.
2. Field tham chiếu **buyer** nằm bên trong object ấy có thể không trỏ đến một `Customer` nào.

Sơ đồ:

~~~text
order -----> Order object
             +----------------------+
             | orderCode = null     |
             | buyer = null         |
             | quantity = 0         |
             +----------------------+
~~~

**Đừng suy diễn:** đối tượng `Order` không phải null chỉ vì một hoặc nhiều field của nó đang null.

### 3.1. Biến cục bộ khác field

Khác với instance/static fields, **local variable** trong method không được phép đọc trước khi đã được gán chắc chắn (*definite assignment*):

~~~java
class Example {
    String field; // Mặc định null

    void test() {
        String local;
        // System.out.println(local); // Lỗi compile: chưa khởi tạo local

        local = null;                 // Bây giờ đã được gán
        System.out.println(local == null);
    }
}
~~~

Compiler Java **không tự gán null để bạn đọc** từ một local variable mới khai báo chưa gán. Sau khi bạn gán `local = null` tường minh, phép đọc trở nên hợp lệ về definite assignment.

## 4. `null` trong mảng: null array khác null element

Mảng là object trong Java. Một field/variable có kiểu mảng có thể là null, nhưng **một mảng đã được tạo** vẫn có thể chứa các phần tử null.

~~~java
String[] names = null;             // Không có array object
String[] slots = new String[3];    // Có mảng gồm ba ô tham chiếu
int[] counts = new int[3];        // Có mảng gồm ba giá trị int
~~~

Với `slots`, mỗi phần tử kiểu `String` được khởi tạo mặc định bằng null: `slots[0] == null` là true. Với `counts`, các phần tử primitive `int` được khởi tạo bằng 0.

Khác biệt:

~~~java
// names.length;      // NullPointerException nếu thực thi vì names == null
int size = slots.length;     // 3: array object tồn tại
String first = slots[0];     // null: phần tử tham chiếu chưa có String
int firstCount = counts[0]; // 0: phần tử primitive mặc định
~~~

Một mảng không null **không bảo đảm mọi phần tử tham chiếu đều khác null**. Nếu xử lý `slots[0].length()` ngay, bạn vẫn gặp `NullPointerException` vì `slots[0] == null`.

## 5. Null chỉ gây NPE khi operation cần một object đích

~~~java
String name = null;
System.out.println(name == null); // true, không dereference
// name.length(); // Nếu chạy, ném NullPointerException
~~~

Đây là fragment trong method. `null` không có receiver object cho instance field/method hoặc array access, nhưng **so sánh với null** không dereference nên an toàn. `System.out.println(name)` vẫn có thể in chữ `null`; nó không tạo String object cho biến name.

Nếu null hợp lệ, code có thể dùng `name != null && !name.isBlank()`: toán tử `&&` short-circuit. Nếu null **không được phép** theo contract, hãy validate tại API boundary, chẳng hạn `Objects.requireNonNull(name)`, thay vì âm thầm dùng giá trị rỗng sai nghĩa.

Các tình huống NPE chi tiết gồm nested dereference, nullable array slots, auto-unboxing và bound method references thuộc bài **các tình huống gây NullPointerException**. Bài hiện tại giữ trọng tâm ở nghĩa của `null` như **giá trị tham chiếu không trỏ object**, không phải toàn bộ chiến lược debug NPE.

## 6. Ví dụ hoàn chỉnh: null là không có object, không phải object rỗng

Tạo tệp **`NullReferenceDemo.java`**:

~~~java
import java.util.Objects;

public class NullReferenceDemo {
    static final class Customer {
        private final String name;

        Customer(String name) {
            this.name = Objects.requireNonNull(name, "name");
        }

        String display() {
            return "Customer: " + name;
        }
    }

    static Customer find(boolean found) {
        return found ? new Customer("Lan") : null;
    }

    public static void main(String[] args) {
        Customer present = find(true);
        Customer missing = find(false);

        System.out.println("present = " + present.display());
        System.out.println("missing == null = " + (missing == null));
        System.out.println("missing instanceof Customer = "
                + (missing instanceof Customer));

        System.out.println("same reference = "
                + (present == find(true)));

        Customer alias = present;
        System.out.println("alias == present = "
                + (alias == present));

        try {
            System.out.println(missing.display());
        } catch (NullPointerException ex) {
            System.out.println("NPE from dereference");
        }

        String[] names = new String[2];
        int[] quantities = new int[2];

        System.out.println("array exists = " + (names != null));
        System.out.println("first element null = " + (names[0] == null));
        System.out.println("first primitive = " + quantities[0]);

        Customer saved = present;
        present = null;

        System.out.println("present cleared = " + (present == null));
        System.out.println("saved still works = " + saved.display());
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac -encoding UTF-8 NullReferenceDemo.java
java NullReferenceDemo
~~~

**Stdout chính xác:**

~~~text
present = Customer: Lan
missing == null = true
missing instanceof Customer = false
same reference = false
alias == present = true
NPE from dereference
array exists = true
first element null = true
first primitive = 0
present cleared = true
saved still works = Customer: Lan
~~~

Diễn giải:

1. `find(true)` tạo một object `Customer`; `find(false)` trả null. **Declared return type `Customer`** cho phép cả hai kết quả.
2. `missing == null` là true, còn `missing instanceof Customer` là false vì null không phải instance của class.
3. `present == find(true)` là false: lời gọi `find(true)` thứ hai thực hiện `new Customer("Lan")`, tạo một object khác dù tên cùng `"Lan"`.
4. `alias = present` sao chép tham chiếu đến **cùng Customer**; do đó `alias == present` là true.
5. `missing.display()` gây NPE vì receiver null; ví dụ cố ý bắt lỗi và in một thông báo ổn định, thay vì phụ thuộc wording của exception.
6. `new String[2]` tạo mảng có thật nhưng phần tử String ban đầu là null; `new int[2]` tạo mảng có thật với phần tử int ban đầu là 0.
7. `present = null` chỉ đổi giá trị biến `present`. `saved` vẫn trỏ tới Customer gốc và gọi `display()` được. **Không có thao tác hủy Customer khi gán present thành null**.

Một kiểm tra quan trọng khác: hai object có cùng dữ liệu không nhất thiết có cùng identity. Với kiểu `Customer` ở ví dụ, `==` chỉ hỏi có cùng object hay không; không được dùng nó để tự suy ra nội dung hai khách hàng có giống nhau.

## 7. `null` khác `0`, `false`, chuỗi rỗng và collection rỗng

Một API cần phân biệt **không có đối tượng** với **có đối tượng nhưng không có nội dung**.

| Kết quả | Trạng thái có thể diễn đạt |
| --- | --- |
| `null` | Không có object/kết quả theo hợp đồng |
| `""` | Có String với 0 ký tự |
| `"null"` | Có String gồm chữ “null” |
| `new int[0]` | Có array, độ dài 0 |
| `List.of()` | Có một List không sửa được và đang rỗng |
| `Integer.valueOf(0)` | Có Integer object chứa số 0 |
| `Boolean.FALSE` | Có wrapper Boolean biểu diễn false |

Vì thế, không nên tự động thay `null` bằng `""` nếu “chưa nhập tên” và “đã nhập tên rỗng” mang ý nghĩa nghiệp vụ khác nhau. Tương tự, số lượng bằng 0 có thể là một giá trị hợp lệ và **không tự động tương đương** với “chưa biết số lượng”.

Đối với một method truy vấn danh sách, trả **collection rỗng** thường giúp caller duyệt đơn giản và tránh null-check nếu hợp đồng có nghĩa “không tìm thấy phần tử nào”. Với method tìm **một đối tượng duy nhất**, biểu diễn “không tìm thấy” bằng null hoặc `Optional<T>` cần được cân nhắc theo API.

## 8. Gán `null` không hủy object

Một hiểu lầm phổ biến:

~~~java
Customer first = new Customer("Lan");
Customer second = first;

first = null;
// second vẫn trỏ tới Customer ban đầu
~~~

Gán `first = null` chỉ thay giá trị của **biến first**. Object đang được `second` tham chiếu không vì thế bị xóa hoặc mất dữ liệu.

Các điểm chính:

- Object có thể được tham chiếu từ nhiều biến/field/collection cùng lúc (*aliasing*).
- Gán một biến thành null **không sửa những biến khác** dù chúng trước đó trỏ cùng object.
- Object không còn được truy cập qua bất kỳ đường tham chiếu mạnh thích hợp nào có thể trở thành ứng viên thu gom; **không có cam kết nó bị thu gom ngay** khi câu lệnh gán chạy.
- Garbage collection do JVM quản lý; không dùng `x = null` như cơ chế đóng file/socket/database connection hoặc thay thế `close()` và `try-with-resources`.
- Nếu object còn được giữ trong một static collection hoặc listener registry, gán null cho biến local thường không đủ ngắt đường tham chiếu từ registry đó.

Hãy phân biệt **vòng đời giá trị tham chiếu** với **vòng đời object thực tế** và với **vòng đời tài nguyên bên ngoài JVM**.

## 9. So sánh `null` với `==`, `equals` và `Objects.equals`

### 9.1. `== null` là phép kiểm tra trực tiếp

~~~java
String first = null;
String second = "Java";

System.out.println(first == null);   // true
System.out.println(second == null);  // false
~~~

Đoạn này là fragment bên trong method. Với reference, `==` so sánh **giá trị tham chiếu**, vì vậy kiểm tra `ref == null` hoàn toàn phù hợp.

### 9.2. Không gọi `equals` trên một reference có thể null

~~~java
String name = null;
// name.equals("Lan"); // NPE nếu chạy
~~~

Nếu mục tiêu là kiểm tra nội dung bằng String, có thể viết:

~~~java
boolean match = "Lan".equals(name); // false khi name == null
~~~

Cách đảo receiver trên literal phù hợp khi vế còn lại luôn là một String literal non-null, nhưng đừng coi đó là quy tắc tổng quát cho mọi kiểu hay mọi comparator.

### 9.3. `Objects.equals` xử lý cả hai bên null

~~~java
import java.util.Objects;

class TextCompare {
    static boolean same(String left, String right) {
        return Objects.equals(left, right);
    }
}
~~~

`Objects.equals(null, null)` trả true; `Objects.equals(null, "A")` trả false; `Objects.equals("A", "A")` trả true theo hợp đồng `String.equals`. Nó xử lý null bằng logic: cùng tham chiếu hoặc bên đầu non-null và nội dung `equals` phù hợp.

**Đừng nhầm equality với object identity.** `Objects.equals` dựa vào implementation `equals` của kiểu dữ liệu khi cần; hai object khác nhau nhưng có nội dung bằng nhau có thể cho true. `==` trên hai reference non-null chỉ true nếu chúng cùng trỏ tới một object.

## 10. `null` trong toán tử `instanceof` và pattern matching Java 17

Trong Java 17:

~~~java
Object value = null;

System.out.println(value instanceof String); // false

if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

Vì `value == null`, điều kiện `instanceof` là false và nhánh `if` không chạy. Pattern variable `text` chỉ được dùng tại vị trí hợp lệ khi điều kiện match thành công. Đây là cách kiểm tra kiểu và tham chiếu non-null đồng thời trong những ngữ cảnh phù hợp.

Tuy vậy, `instanceof` không thay thế mọi null-check: nếu bạn chỉ cần biết một reference có object hay không mà không quan tâm runtime type, `value != null` đơn giản hơn và diễn đạt đúng mục đích.

## 11. Tham số null: truyền tham chiếu null không tạo object

Một method khai báo parameter kiểu tham chiếu có thể nhận null:

~~~java
class Greeter {
    static String greeting(String name) {
        if (name == null) {
            return "Chào khách";
        }
        return "Chào " + name;
    }
}
~~~

Lời gọi `Greeter.greeting(null)` hợp lệ, vì `String` là reference type và method đã định nghĩa đường xử lý khi không có tên.

Nhưng có những method **bắt buộc cần đối tượng**. Khi đó nên từ chối null ở ranh giới:

~~~java
import java.util.Objects;

class PaymentRequest {
    private final String accountId;

    PaymentRequest(String accountId) {
        this.accountId = Objects.requireNonNull(
                accountId, "accountId");
        if (accountId.isBlank()) {
            throw new IllegalArgumentException("accountId rỗng");
        }
    }
}
~~~

`Objects.requireNonNull` ném `NullPointerException` khi input null; sau đó constructor kiểm tra blank theo hợp đồng. Đây là ví dụ về **validation**: biết một kiểu tham chiếu có thể null không có nghĩa API bắt buộc phải **chấp nhận** null.

### 11.1. Java truyền đối số theo giá trị, kể cả giá trị null

~~~java
class ReferenceOps {
    static void replace(StringBuilder builder) {
        builder = null; // Chỉ gán lại parameter cục bộ
    }
}
~~~

Nếu caller có một `StringBuilder` object rồi gọi `replace(builder)`, method nhận **bản sao giá trị tham chiếu**. Gán parameter thành null **không** làm biến tham chiếu của caller trở thành null.

Ngược lại, nếu method nhận tham chiếu non-null và gọi `builder.append("!")`, nó sẽ sửa object được cả caller và callee cùng tham chiếu; đó là tác động lên **object**, không phải thay biến của caller.

## 12. Trả `null` từ phương thức

Method trả reference type có thể trả null khi hợp đồng cho phép:

~~~java
class Directory {
    String findName(int id) {
        if (id == 7) {
            return "Lan";
        }
        return null; // Không tìm thấy
    }
}
~~~

Khi caller nhận kết quả:

~~~java
String name = directory.findName(99);

if (name == null) {
    System.out.println("Không tìm thấy");
} else {
    System.out.println(name.toUpperCase());
}
~~~

Đây là fragment trong method có biến `directory` phù hợp. Nếu không kiểm tra mà viết `directory.findName(99).toUpperCase()`, lời gọi `toUpperCase()` có receiver null và ném NPE.

**Return type khai báo `String` không tự cam kết non-null.** Java 17 không có cú pháp kiểu thông thường bắt buộc tách `String?` và `String` như một số ngôn ngữ; một số công cụ phân tích tĩnh sử dụng annotation `@Nullable`/`@NonNull` theo từng hệ sinh thái, nhưng chúng không tự động được compiler Java chuẩn thực thi như một tính năng ngôn ngữ phổ quát.

Với kiểu primitive, `int find() { return null; }` là **lỗi biên dịch**; `null` không chuyển trực tiếp được thành `int`.

## 13. Wrapper và auto-unboxing: null có thể gây NPE dù phép gán biên dịch được

`Integer` là **reference type** tương ứng với primitive `int`, nên biến `Integer` có thể null:

~~~java
Integer count = null;
~~~

Nhưng phép chuyển `Integer` sang `int` (*unboxing*) cần lấy số từ wrapper. Nếu `count == null` thì unboxing gây NPE:

~~~java
Integer count = null;

// int number = count; // Biên dịch được, nhưng ném NPE khi chạy
~~~

Lỗi cũng có thể nằm ở biểu thức toán học:

~~~java
Integer value = null;

// int next = value + 1;    // NPE do unboxing value
// if (value > 0) { }       // NPE do unboxing
~~~

Sự khác nhau rất quan trọng:

| Đoạn code | Kết quả |
| --- | --- |
| `int n = null;` | Lỗi compile |
| `Integer n = null;` | Hợp lệ, n chứa null |
| `Integer n = 5;` | Hợp lệ, boxing |
| `int x = n;` khi n là 5 | Hợp lệ, unboxing ra 5 |
| `int x = n;` khi n null | NPE runtime |
| `n == null` | Hợp lệ với Integer reference |

Nếu một API dùng `Integer` để biểu diễn “chưa có số”, hãy kiểm tra null **trước khi tính toán hoặc unbox**. Không mặc nhiên dùng `0` thay cho “chưa biết” nếu chúng là hai trạng thái khác nhau.

## 14. `Optional<T>`: biểu diễn kết quả vắng mặt một cách tường minh

Java cung cấp `java.util.Optional<T>` để biểu diễn một kết quả tham chiếu **có** hoặc **không có** giá trị, đặc biệt hữu ích ở một số API tìm kiếm/truy vấn.

~~~java
import java.util.Optional;

class UserRepository {
    Optional<String> findName(int userId) {
        if (userId == 7) {
            return Optional.of("Lan");
        }
        return Optional.empty();
    }
}
~~~

Khi caller gọi `findName(99)`, kết quả là **một Optional rỗng**, chứ không phải null. Cách dùng:

~~~java
String name = repository.findName(99).orElse("Khách");
~~~

Fragment này cần biến `repository` phù hợp. `orElse("Khách")` trả fallback khi Optional empty; caller không cần dereference một String null trước khi xử lý trường hợp vắng mặt.

Một số API Optional cần nhớ:

| API | Ý nghĩa |
| --- | --- |
| `Optional.of(value)` | Tạo Optional có giá trị, yêu cầu value non-null |
| `Optional.ofNullable(value)` | Null trở thành Optional rỗng |
| `Optional.empty()` | Trường hợp không có kết quả |
| `isPresent()` / `isEmpty()` | Kiểm tra có/không có giá trị |
| `orElse(defaultValue)` | Lấy giá trị hoặc fallback |
| `orElseGet(supplier)` | Chỉ chạy supplier tạo fallback khi Optional rỗng |
| `orElseThrow()` | Nhận giá trị hoặc ném exception nếu rỗng |
| `map(fn)` | Biến đổi giá trị nếu có, giữ trạng thái rỗng khi không có |

**Đừng trả `null` từ method có return type `Optional<T>`:** caller kỳ vọng một Optional object non-null và có thể gọi `isPresent`/`orElse` ngay. Nếu method trả null thì chính lời gọi này gây NPE, làm mất mục đích thiết kế.

`Optional` cũng là reference type; Java không ngăn được một biến Optional bị gán null từ code sai, nên **hợp đồng code** vẫn quan trọng. Generic `Optional<int>` không hợp lệ vì generic type argument yêu cầu reference type; dùng `OptionalInt` khi phù hợp.

Không nhất thiết mọi biến, field hoặc parameter nullable phải được bọc Optional. Optional thường thích hợp nhất ở **return type**, tùy phong cách API và chi phí/hạn chế tương ứng.

## 15. Ví dụ hoàn chỉnh: API trả null, Optional và unboxing

Tạo tệp **`NullContractDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

public class NullContractDemo {
    record User(String name) {
        User {
            Objects.requireNonNull(name, "name");
            if (name.isBlank()) {
                throw new IllegalArgumentException("Tên rỗng");
            }
        }
    }

    static User findNullable(int id) {
        return id == 7 ? new User("Lan") : null;
    }

    static Optional<User> findUser(int id) {
        return Optional.ofNullable(findNullable(id));
    }

    static String labelOrDefault(String input) {
        return input == null ? "unknown" : input;
    }

    public static void main(String[] args) {
        System.out.println("found = "
                + findUser(7).map(User::name).orElse("N/A"));
        System.out.println("missing = "
                + findUser(8).map(User::name).orElse("N/A"));
        System.out.println("label = " + labelOrDefault(null));

        Integer optionalCount = null;
        try {
            int count = optionalCount; // Unboxing null
            System.out.println(count);
        } catch (NullPointerException ex) {
            System.out.println("unbox null = NPE");
        }

        Map<String, String> values = new HashMap<>();
        values.put("presentNull", null);

        System.out.println("get absent null = "
                + (values.get("missing") == null));
        System.out.println("key exists with null = "
                + values.containsKey("presentNull"));
        System.out.println("key absent = "
                + values.containsKey("missing"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 NullContractDemo.java
java NullContractDemo
~~~

**Stdout chính xác:**

~~~text
found = Lan
missing = N/A
label = unknown
unbox null = NPE
get absent null = true
key exists with null = true
key absent = false
~~~

Giải thích:

1. `findNullable(7)` tạo `User("Lan")`; `findNullable(8)` trả null. `findUser` biến hai kết quả thành Optional có giá trị hoặc Optional rỗng.
2. `map(User::name)` chỉ gọi accessor nếu có User; `orElse("N/A")` xử lý thiếu User bằng fallback.
3. `labelOrDefault(null)` nhận tham số null, nhưng có nhánh xử lý và trả `"unknown"`, không cố truy cập field/method của null.
4. `Integer optionalCount = null` hợp lệ vì Integer là reference type. Lệnh `int count = optionalCount` cố unbox null và ném NPE; ví dụ bắt lỗi để đưa ra stdout ổn định.
5. Với `HashMap`, `get("missing")` trả null khi không có mapping. `get("presentNull")` cũng sẽ trả null vì map cho phép giá trị null, **dù key thật sự tồn tại**. `containsKey` giúp phân biệt hai trường hợp nếu cần.

**Đừng suy rộng quy tắc của HashMap cho mọi Map implementation**: một số map như `ConcurrentHashMap` không cho lưu key hoặc value null. API collection cụ thể có chính sách null riêng; xem hợp đồng của kiểu đang sử dụng.

## 16. `null` trong overload resolution: một lời gọi có thể mơ hồ

Null literal tương thích với nhiều reference parameter types, nên có thể gặp **ambiguous overload**:

~~~java
class Formatter {
    static String describe(String value) {
        return "String";
    }

    static String describe(Integer value) {
        return "Integer";
    }

    static void test() {
        // describe(null); // Lỗi compile: ambiguous overload

        System.out.println(describe((String) null));
        System.out.println(describe((Integer) null));
    }
}
~~~

Đây là khai báo minh họa chưa có `main`. Hai overload **được khai báo hợp lệ** vì tham số khác kiểu, nhưng lời gọi `describe(null)` không thể chọn giữa `String` và `Integer` khi chúng không có quan hệ subtype cho một method rõ ràng hơn.

Dùng cast hoặc một biểu thức tham số đã có kiểu cụ thể có thể xác định overload muốn gọi. Tuy nhiên, **cast null sang String không tạo String object**: `(String) null` vẫn là giá trị null, chỉ có ngữ cảnh kiểu tường minh hơn để chọn overload.

Một overload có tham số `Object` và một overload có tham số `String` thường chọn `String` khi truyền null vì `String` cụ thể hơn `Object` theo quy tắc most-specific. Nhưng không nên thiết kế quá nhiều overload nullable khó hiểu chỉ để caller phải ép kiểu mỗi lần.

## 17. `null` trong String concatenation không tự đồng nghĩa có object chuỗi

Biểu thức:

~~~java
String missing = null;

String result = "name=" + missing;
System.out.println(result); // name=null
~~~

Trong ngữ cảnh nối chuỗi, Java chuyển biểu diễn của giá trị tham chiếu null thành chữ `"null"` trong kết quả. Điều đó **không thay đổi biến `missing`** và không biến nó thành một String object có nội dung `"null"`.

Phân biệt:

~~~java
String first = null;
String second = "null";

System.out.println(first == null);   // true
System.out.println(second == null);  // false
~~~

`first` không trỏ tới object, còn `second` có String object chứa bốn ký tự. Nếu muốn hiển thị nhãn có ý nghĩa thân thiện hơn, đừng dựa vào việc in null thành chữ `"null"`; hãy xử lý bằng fallback hoặc một placeholder theo giao diện, chẳng hạn `"Chưa có tên"`.

## 18. Null và API collection

Không có một quy tắc duy nhất cho mọi collection/map:

- `ArrayList` thường cho phép phần tử null.
- `List.of(...)` không chấp nhận phần tử null; `List.of("A", null)` ném NPE.
- `List.copyOf(collection)` cũng không chấp nhận phần tử null, và trả một List không sửa được.
- `HashMap` cho phép null key và null values theo hợp đồng của nó.
- `ConcurrentHashMap` không cho null key hay null value.
- `Collections.emptyList()` và `List.of()` trả **list rỗng có thật**, không phải null.

Nếu API của class quy định “danh sách không bao giờ null”, constructor nên kiểm tra/copy input và getter nên trả list rỗng khi không có phần tử, thay vì trả null một cách bất ngờ:

~~~java
import java.util.List;

class Playlist {
    private final List<String> songs;

    Playlist(List<String> songs) {
        this.songs = List.copyOf(songs);
    }

    List<String> songs() {
        return songs;
    }
}
~~~

Đây là đoạn minh họa. Với list của String immutable, `List.copyOf` giúp giữ dữ liệu không bị caller sửa cấu trúc. Nếu constructor nhận null hoặc phần tử null, nó sẽ ném NPE thay vì tạo một object ở trạng thái chưa được quy định; đó là hành vi cần đưa vào hợp đồng.

Với list chứa object mutable, `List.copyOf` chỉ tạo snapshot cấu trúc không sửa được, **không tự deep-copy tất cả object con**.

## 19. Khi nào nên dùng null và khi nào nên tránh?

Null là một phần bình thường của Java. Nó không “xấu” trong mọi ngữ cảnh; vấn đề là **hợp đồng không rõ ràng** hoặc **không kiểm tra ở nơi cần dùng**.

| Trường hợp | Lựa chọn thường phù hợp | Cân nhắc |
| --- | --- | --- |
| Field thực sự tùy chọn | Nullable reference, hoặc mô hình dữ liệu khác có hợp đồng | Mọi nơi dùng phải xử lý vắng mặt |
| Constructor cần thông tin bắt buộc | `Objects.requireNonNull` và validation | Từ chối sớm, tránh object sai invariant |
| Truy vấn có thể không tìm thấy một kết quả | `Optional<T>` hoặc nullable `T` theo API | Chọn nhất quán |
| Trả nhiều kết quả nhưng không có item | List/collection rỗng | Caller không cần kiểm tra null để duyệt |
| Không có giá trị nguyên thủy | `OptionalInt`, wrapper hoặc result type | Phân biệt thiếu dữ liệu với số 0 |
| Lỗi nghiệp vụ nghiêm trọng | Exception hoặc result type có trạng thái lỗi | Đừng che lỗi bằng null mơ hồ |
| Đầu vào ngoại vi (JSON/database/form) | Validate tại boundary rồi chuyển thành model hợp lệ | Không cho null bất ngờ lan rộng trong core |
| Dữ liệu cần cache nhưng chưa tạo | Nullable field hoặc lazy initialization được kiểm soát | Phải xét concurrency và cache invalidation |

Một API nên nói rõ: null biểu thị **không tìm thấy**, **chưa tải**, **không áp dụng**, hay **lỗi**? Các ý nghĩa này khác nhau. Nếu chúng đều dùng chung một null, caller rất khó biết phải hành động gì. Có thể dùng enum, sealed hierarchy, record kết quả hoặc exception thích hợp khi cần phân biệt nhiều trạng thái.

## 20. Defensive null checking và nguyên tắc “fail fast”

Nếu một method thật sự yêu cầu object:

~~~java
import java.util.Objects;

class Receipt {
    private final String orderId;

    Receipt(String orderId) {
        this.orderId = Objects.requireNonNull(
                orderId, "orderId");
    }

    String orderId() {
        return orderId;
    }
}
~~~

Constructor thất bại ngay khi input null, thay vì tạo `Receipt` chứa null rồi gây NPE ở một method rất xa nơi tạo. Đây là **fail fast**: phát hiện vi phạm hợp đồng tại ranh giới gần nhất.

Với giá trị có thể thiếu và hợp đồng cho phép:

~~~java
class ReceiptLabel {
    static String display(String customerName) {
        if (customerName == null || customerName.isBlank()) {
            return "Khách";
        }
        return customerName;
    }
}
~~~

Điều kiện dùng `||` short-circuit: nếu tên null, Java không gọi `customerName.isBlank()`. Đây là cách xử lý hợp pháp, vì null có ý nghĩa như một trong các trạng thái input được chấp nhận.

**Không nên bắt `NullPointerException` đại trà để thay cho null-check.** Bắt NPE rất rộng có thể che các lỗi dereference không liên quan, khiến việc tìm bug khó hơn. Chỉ bắt khi thật sự cần xử lý một lỗi theo hợp đồng hoặc minh họa cơ chế như các chương trình trên.

## 21. Một số bẫy nâng cao

### 21.1. `this` trong instance method không phải null

Khi một instance method đang thực thi bình thường trên object có thật, `this` biểu diễn receiver object đó, không phải một null reference. Tuy nhiên, các **field** của object vẫn có thể là null:

~~~java
class Holder {
    String text; // mặc định null

    int length() {
        // this là current Holder object, nhưng this.text vẫn có thể null
        return this.text.length();
    }
}
~~~

Lỗi `this.text.length()` đến từ `this.text == null`, không phải vì `this == null`. Nếu gọi `holder.length()` mà `holder` null, method body thậm chí không được bắt đầu; việc dereference receiver xảy ra ở nơi gọi.

### 21.2. Chuỗi truy cập nhiều tầng

~~~java
customer.getAddress().getCity()
~~~

Có thể NPE nếu `customer` null hoặc `getAddress()` trả null. Điều đó không có nghĩa `getCity()` sai; lỗi có thể xuất hiện ở **một mắt xích tham chiếu trước đó**. Hãy thiết kế domain invariant, nullable contract và API để người dùng biết mắt xích nào được phép thiếu.

### 21.3. Null trong switch

Với cú pháp `switch` phổ biến ở Java 17, `switch` trên một selector reference null thường ném NPE; không nên nghĩ Java tự chuyển null vào nhánh `default`:

~~~java
String status = null;

// switch (status) {
//     default -> System.out.println("Khác");
// }
// Khi thực thi switch trên status null theo cú pháp này: NPE
~~~

Đây là đoạn minh họa không hoàn chỉnh để giải thích hành vi; hãy xử lý null trước `switch` nếu nó là trường hợp hợp lệ của đầu vào. Một số phiên bản Java mới hơn có mở rộng pattern matching cho switch, nhưng không dùng kiến thức của preview/language version khác để suy luận sai về mã Java 17 phổ thông.

### 21.4. Null và generic collections

~~~java
java.util.List<String> names = new java.util.ArrayList<>();
names.add(null);
~~~

Điều này hợp lệ với `ArrayList` dù phần tử được khai báo kiểu `String`. Generics kiểm tra loại giá trị tham chiếu theo kiểu; nó **không mặc định biến mỗi phần tử thành non-null**. Nếu class của bạn cần invariant “không có phần tử null”, hãy kiểm tra hoặc dùng API collection có hợp đồng không chấp nhận null.

### 21.5. Null trong các API đa luồng

Một field tham chiếu được nhiều thread đọc/ghi có thể chuyển từ object sang null hoặc ngược lại. Việc dùng null làm tín hiệu trạng thái không tự đem lại **visibility** hoặc **atomicity** cho một giao thức nhiều bước. Cần `volatile`, atomic reference, lock hoặc công cụ đồng bộ phù hợp tùy yêu cầu.

Ví dụ `volatile Service current` đảm bảo ngữ nghĩa visibility cho thao tác đọc/ghi chính **field tham chiếu** đó, nhưng không tự biến mọi field mutable bên trong `Service` thành thread-safe. Không nên dùng `if (current != null) current.run()` với field có thể bị thread khác gán null giữa hai lần đọc như một lời hứa không NPE; chụp giá trị tham chiếu vào local và thiết kế lifecycle/synchronization thích hợp.

## 22. Những hiểu lầm phổ biến

1. **“Null là một object rỗng.”** Sai. Null biểu thị **không có object được tham chiếu**; object rỗng vẫn là object có thật.
2. **“Khai báo `Customer c;` tự tạo Customer.”** Sai. Field reference chưa khởi tạo có giá trị mặc định null; local variable chưa definite-assigned không được đọc.
3. **“`new String[3]` là null vì cả ba phần tử null.”** Sai. Mảng tồn tại; chỉ các phần tử tham chiếu bên trong ban đầu null.
4. **“`null` và `0` giống nhau.”** Sai. `0` là giá trị primitive, null dành cho reference.
5. **“Gán `x = null` xóa object ngay.”** Sai. Nó chỉ đổi một tham chiếu; object có thể còn alias và GC không cam kết chạy ngay.
6. **“`x == null` gây NPE khi x null.”** Sai. Đây là phép so sánh an toàn.
7. **“`x.equals(y)` an toàn dù x null.”** Sai. Receiver null khiến gọi instance method thất bại.
8. **“String `"null"` là null.”** Sai. Đây là String object có nội dung bốn ký tự.
9. **“Kiểu `Integer` luôn có một số như `int`.”** Sai. Integer là reference, có thể null; unboxing null gây NPE.
10. **“Trả `Optional.empty()` giống trả null.”** Sai ở mức API: Optional rỗng vẫn là giá trị Optional non-null với các method xử lý trường hợp vắng mặt.
11. **“Mọi collection đều chấp nhận phần tử null.”** Sai. Chính sách phụ thuộc implementation/API.
12. **“`ref instanceof Type` với null gây NPE.”** Sai. Biểu thức `instanceof` thông thường trả false khi reference null.
13. **“Nếu `ref != null`, tất cả field bên trong ref đều non-null.”** Sai. Object tồn tại nhưng có thể chứa field null.
14. **“Nếu result type là `String` thì compiler bảo đảm method trả String non-null.”** Sai. Java 17 cho phép `return null` cho reference type.
15. **“Có thể dùng null để thay mọi trạng thái lỗi.”** Không nên: không phân biệt được không tìm thấy, chưa tải, thiếu quyền hay hỏng hệ thống.
16. **“Không cần kiểm tra null sau `Map.get` vì map có key.”** Với map cho phép null values, `get` trả null dù mapping tồn tại; cần hiểu chính sách và dùng `containsKey` khi cần phân biệt.
17. **“Gán null cho tham số bên trong method thay biến caller thành null.”** Sai. Java truyền bản sao giá trị tham chiếu.
18. **“Chỉ thêm `volatile` cho tham chiếu đủ để mọi object con an toàn.”** Sai. Nó không tự đồng bộ các thao tác trên nội dung object.

## 23. Bài tập tự kiểm tra

**Câu 1.** `Customer c = null;` có tạo ra Customer object không?

**Đáp án:** Không. Biến `c` có kiểu `Customer` nhưng giá trị null, không trỏ đến object nào.

**Câu 2.** `Customer c = new Customer();` có thể có `c.name == null` không?

**Đáp án:** Có. Object `Customer` tồn tại, nhưng reference field `name` chưa gán tường minh sẽ mặc định null.

**Câu 3.** `String[] words = new String[2];`. Biểu thức `words == null` và `words[0] == null` lần lượt là gì?

**Đáp án:** False và true. Mảng đã được tạo; phần tử String đầu tiên ban đầu chưa tham chiếu tới String object.

**Câu 4.** `int[] nums = new int[2];` có `nums[0] == null` không?

**Đáp án:** Không thể so sánh một phần tử `int` trực tiếp với null. Phần tử `nums[0]` có giá trị nguyên thủy 0.

**Câu 5.** Tại sao `Integer boxed = null; int n = boxed;` có thể gây lỗi?

**Đáp án:** Boxing wrapper `Integer` là reference và cho phép null; phép gán sang `int` yêu cầu unboxing, không thể unbox null nên gây NPE.

**Câu 6.** `String s = null; if (s != null && s.length() > 0) ...` có gọi `length()` không?

**Đáp án:** Không. `&&` short-circuit, vế thứ hai không chạy khi `s != null` là false.

**Câu 7.** `String s = "null";` có làm `s == null` thành true không?

**Đáp án:** Không. `s` trỏ đến một String object thực sự chứa văn bản `"null"`.

**Câu 8.** Gán `first = null` trong khi `second == first` trước đó có làm `second` cũng null không?

**Đáp án:** Không. Nếu ban đầu `second` và `first` cùng trỏ tới object, gán lại `first` chỉ đổi giá trị biến `first`; `second` giữ tham chiếu cũ.

**Câu 9.** Phương thức khai báo `Optional<String> find()` nên trả gì khi không tìm thấy?

**Đáp án:** `Optional.empty()`, không phải null, để bảo toàn hợp đồng Optional.

**Câu 10.** Tại sao `describe(null)` có thể ambiguous khi có overload `describe(String)` và `describe(Integer)`?

**Đáp án:** Null literal tương thích với cả hai reference parameter types, mà hai kiểu này không xác định một overload cụ thể hơn theo thứ tự subtype liên quan; compiler không chọn được duy nhất.

**Câu 11.** Vì sao `map.get("missing") == null` chưa chắc cho biết key không tồn tại?

**Đáp án:** Map implementation có thể cho phép mapping key tới null value. Với `HashMap`, dùng `containsKey` nếu cần phân biệt absent key và present-null mapping.

**Câu 12.** `String text = null; System.out.println("text=" + text);` có làm `text` trở thành String `"null"` không?

**Đáp án:** Không. Chuỗi kết quả chứa chữ `"null"` để hiển thị, nhưng biến `text` vẫn là null.

## 24. Checklist khi thiết kế và sử dụng tham chiếu nullable

1. **Xác định kiểu:** đây là primitive hay reference? Chỉ reference mới có thể chứa null trực tiếp.
2. **Xác định trạng thái vắng mặt:** null có ý nghĩa nghiệp vụ gì, hay là dữ liệu đầu vào sai phải từ chối?
3. **Phân biệt object và field của nó:** object không null không chứng minh mọi field/element cũng non-null.
4. **Kiểm tra trước khi dereference:** đặc biệt ở chain `a.getB().getC()` và các wrapper unboxing.
5. **Sử dụng short-circuit đúng:** `&&` và `||` giúp bảo vệ các nhánh gọi method khi điều kiện được viết đúng.
6. **Đừng dùng sentinel mơ hồ:** `0`, `""`, collection rỗng và null là những trạng thái khác nhau.
7. **Đặt hợp đồng API rõ ràng:** phương thức nào có thể trả null, phương thức nào trả Optional, phương thức nào cam kết non-null?
8. **Bảo vệ invariant tại constructor:** dùng validation như `Objects.requireNonNull` cho field bắt buộc.
9. **Với collection, xem hợp đồng cụ thể:** `HashMap`, `List.of`, `ArrayList` không có chính sách null giống nhau.
10. **Với aliasing, nhớ null không hủy object:** gán lại một tham chiếu không thay đổi các tham chiếu còn lại.
11. **Với concurrency, không dùng null làm tín hiệu nếu thiếu đồng bộ thích hợp.**
12. **Kiểm thử nhánh có và không có object:** không chỉ thử trường hợp non-null; kiểm tra cả array null, null element, unboxing và kết quả thiếu.

**Kết luận:** `null` là **giá trị tham chiếu biểu thị “không có đối tượng được trỏ tới”**. Nó không phải một object rỗng hay một số 0. Viết Java an toàn đòi hỏi phân biệt **biến tham chiếu**, **object được tham chiếu** và **field/element bên trong object**, đồng thời diễn đạt rõ trong API khi nào sự vắng mặt là hợp lệ và khi nào phải từ chối. Khi đã hiểu điều này, các thao tác tạo object, truyền/nhận tham chiếu và xử lý `NullPointerException` sẽ dễ dự đoán và kiểm soát hơn.
