# Xử lý phần tử null trước khi truy cập thuộc tính trong Java

## 1. Vấn đề: phần tử null và phép truy cập thuộc tính

Khi lọc, chọn hoặc biến đổi phần tử của một danh sách trong Java, ta thường viết lambda hoặc method reference như:

~~~java
List<String> names = employees.stream()
        .map(Employee::name)
        .toList();
~~~

Đây là **đoạn minh họa**, giả định đã có List<Employee>, record/class Employee có phương thức name() và đã import List. Nếu danh sách **chứa một phần tử null**, tại bước **Employee::name** Java cố gọi phương thức trên receiver null và ném **NullPointerException (NPE)**.

Đây là một lỗi thường gặp khi làm functional programming: cú pháp Stream, lambda hay method reference **không tự kiểm tra null**. Việc truy cập `employee.name()`, `Employee::name`, `employee.getName()`, `employee.address().city()` đều cần đối tượng nhận lời gọi tương ứng khác null.

Giải pháp cơ bản khi chính sách cho phép **bỏ qua phần tử null**:

~~~java
List<String> names = employees.stream()
        .filter(Objects::nonNull)
        .map(Employee::name)
        .toList();
~~~

Đoạn minh họa cần import **java.util.Objects**, **java.util.List**. **Objects::nonNull** là method reference tới phương thức static `boolean Objects.nonNull(Object obj)`. Nó trả true nếu đối số khác null. `filter` giữ phần tử khác null; sau đó `map(Employee::name)` không còn gặp **receiver Employee null** từ nguồn dữ liệu.

Nhưng vẫn còn tình huống khác: **employee không null nhưng employee.name() trả null**. Khi đó `map(Employee::name)` có thể tạo một phần tử null ở Stream đầu ra. Nếu bước tiếp theo là `String::strip`, `String::length` hay `String::toUpperCase`, ta vẫn phải xử lý thuộc tính null trước khi truy cập nó.

**Hai loại null cần phân biệt rõ:**

1. **Null ở chính phần tử:** `employee == null` → không được gọi `employee.name()`.
2. **Null ở thuộc tính:** `employee != null` nhưng `employee.name() == null` → không được gọi `employee.name().strip()`.

Bài học này tập trung vào cách bảo vệ đúng từng ranh giới trong pipeline **lọc và chọn phần tử**, thay vì chỉ thêm một phép kiểm tra null rồi mặc định mọi bước tiếp theo đều an toàn.

## 2. Quy tắc quan trọng nhất: kiểm tra trước khi dereference

**Dereference** là hành động sử dụng một tham chiếu để truy cập thành viên của đối tượng: gọi phương thức, đọc trường instance hoặc dùng các phép toán cần mở hộp một wrapper. Nếu tham chiếu null, những thao tác này có thể ném NPE.

Sai:

~~~java
// CÓ THỂ NÉM NPE khi employee == null.
Predicate<Employee> adult = e -> e.age() >= 18;
~~~

Đoạn minh họa giả định `Employee.age()` trả int và đã import Predicate.

Đúng khi muốn trả false với phần tử null:

~~~java
Predicate<Employee> adult = e -> e != null && e.age() >= 18;
~~~

Toán tử **&&** đánh giá ngắn mạch (*short-circuit*). Nếu `e != null` là false, Java **không đánh giá vế sau** và không gọi `e.age()`.

Sai vì thứ tự:

~~~java
// CÓ THỂ NÉM NPE: gọi e.age() trước khi kiểm tra null.
Predicate<Employee> broken = e -> e.age() >= 18 && e != null;
~~~

Đây là ví dụ cố ý nguy hiểm, không phải mẫu nên sử dụng.

Nếu bản thân thuộc tính có thể null (ví dụ `Integer age` thay vì `int age`), cần thêm một bước:

~~~java
Predicate<Employee> adult = e ->
        e != null && e.age() != null && e.age() >= 18;
~~~

Đoạn minh họa này giả định `Employee.age()` trả **Integer** nullable. Trong biểu thức cuối, Java tự **unbox Integer thành int** để so sánh với 18. Nếu age null mà không có guard, việc unboxing cũng gây NPE.

**Quy tắc kiểm tra:** trước bất kỳ lời gọi `x.method()`, `x.field`, `x::method` (bound method reference), hay unboxing nào, hãy biết chắc `x` **không null** theo hợp đồng hoặc đã được bảo vệ trước điểm sử dụng.

## 3. Các cách biểu diễn null guard trong Stream

### 3.1. Dùng filter(Objects::nonNull)

~~~java
Stream<Employee> safe = employees.stream()
        .filter(Objects::nonNull);
~~~

Đây là đoạn minh họa cần import `Stream` và `Objects`. Khi nguồn Stream chứa nhiều Employee và xen lẫn null, kết quả chỉ giữ Employee không null. Đây là lựa chọn dễ đọc khi muốn loại **null element** trước các thao tác nhận đối tượng.

**Thứ tự rất quan trọng:**

~~~java
// ĐÚNG: bỏ null trước khi gọi name().
employees.stream()
        .filter(Objects::nonNull)
        .map(Employee::name);

// SAI: method reference có thể nhận null trước khi filter.
employees.stream()
        .map(Employee::name)
        .filter(Objects::nonNull);
~~~

Hai pipeline trên là **các đoạn minh họa**, chưa có terminal operation và không phải chương trình độc lập. Pipeline thứ hai chỉ có tác dụng lọc **null được tạo bởi name()**, không thể ngăn NPE khi `Employee::name` cố gọi method trên Employee null.

Một câu hỏi hữu ích cho mỗi bước: **“Ngay trước khi thao tác này chạy, những giá trị nào còn có thể null?”**

### 3.2. Dùng lambda kiểm tra rõ điều kiện

~~~java
employees.stream()
        .filter(e -> e != null)
        .map(Employee::name);
~~~

Đây là đoạn minh họa. Về ý định loại phần tử null, `e -> e != null` và `Objects::nonNull` tương đương. Dùng method reference khi tên method đã diễn đạt ý rõ; dùng lambda khi cần thêm logic.

### 3.3. Lọc cả null element và nullable property

~~~java
List<String> names = employees.stream()
        .filter(Objects::nonNull)
        .map(Employee::name)
        .filter(Objects::nonNull)
        .map(String::strip)
        .filter(name -> !name.isEmpty())
        .toList();
~~~

Đây là đoạn minh họa cần import List và Objects, với `Employee.name()` trả String có thể null:

- `filter(Objects::nonNull)` thứ nhất loại Employee null.
- `map(Employee::name)` có thể trả String null.
- `filter(Objects::nonNull)` thứ hai loại String null.
- `map(String::strip)` được gọi trên String chắc chắn không null.
- `filter(!isEmpty())` loại chuỗi rỗng sau chuẩn hóa.

**Không có một filter(Objects::nonNull) duy nhất nào tự bảo đảm an toàn cho mọi thuộc tính lồng nhiều cấp.** Mỗi lần chuyển sang kiểu giá trị mới bằng `map`, hãy xem xét nó có thể tạo null hay không.

## 4. Java 17 chạy được: lọc phần tử null và thuộc tính null

Tạo tệp **NullSafeFilterDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.function.Predicate;

record Employee(String id, String name, Integer age) {}

public class NullSafeFilterDemo {
    public static void main(String[] args) {
        List<Employee> employees = Arrays.asList(
                new Employee("E1", " Lan ", 20),
                null,
                new Employee("E2", null, 25),
                new Employee("E3", "Minh", 17),
                new Employee("E4", " An ", 22),
                new Employee("E5", "   ", 30),
                new Employee("E6", "Hà", null)
        );

        Predicate<Employee> validAdult = employee ->
                employee != null
                && employee.name() != null
                && !employee.name().isBlank()
                && employee.age() != null
                && employee.age() >= 18;

        List<String> adultNames = employees.stream()
                .filter(validAdult)
                .map(Employee::name)
                .map(String::strip)
                .toList();

        List<String> allPresentNames = employees.stream()
                .filter(Objects::nonNull)
                .map(Employee::name)
                .filter(Objects::nonNull)
                .map(String::strip)
                .filter(name -> !name.isEmpty())
                .toList();

        System.out.println("Adults: " + adultNames);
        System.out.println("Names: " + allPresentNames);
        System.out.println("Source size: " + employees.size());
    }
}
~~~

Chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 NullSafeFilterDemo.java
java NullSafeFilterDemo
~~~

Stdout:

~~~text
Adults: [Lan, An]
Names: [Lan, Minh, An, Hà]
Source size: 7
~~~

**Vì sao kết quả đúng?**

1. Dữ liệu có một phần tử null nằm giữa danh sách: **E1, null, E2, E3, E4, E5, E6**.
2. Predicate `validAdult` kiểm tra **employee khác null**, **name khác null và không blank**, **age khác null**, rồi mới so sánh **age >= 18**. Nhờ short-circuit, không có phép dereference hoặc unboxing nguy hiểm ở những nhánh thất bại.
3. **E1** đủ điều kiện và `" Lan "` được strip thành **"Lan"**; **E4** đủ điều kiện và `" An "` thành **"An"**.
4. **E2** bị loại do name null; **E3** do age dưới 18; **E5** do name blank; **E6** do age null.
5. Pipeline `allPresentNames` chỉ yêu cầu name tồn tại và không blank, không yêu cầu tuổi hợp lệ. Vì thế **Minh** và **Hà** vẫn xuất hiện.
6. `Arrays.asList(...)` **cho phép null element** ở đầu vào. `List.of(...)` của Java **không cho phần tử null** và sẽ ném NPE ngay khi tạo danh sách. Sự khác biệt này quan trọng khi chuẩn bị dữ liệu thử nghiệm.

**Đây là một ví dụ chính sách:** bỏ qua nhân viên thiếu dữ liệu, không báo lỗi. Nếu miền nghiệp vụ xem Employee thiếu name hoặc age là bản ghi hỏng **cần báo**, không nên âm thầm filter; hãy xác thực đầu vào và báo lỗi ở ranh giới thích hợp.

## 5. Hai vị trí khác nhau của filter: trước hay sau map?

Một pipeline có thể dùng nhiều filter vì giá trị đã **thay đổi kiểu** qua map.

~~~text
Stream<Employee>
    │
    ├─ filter(Objects::nonNull)   → Employee không null
    │
    ├─ map(Employee::name)        → Stream<String>, có thể chứa null
    │
    ├─ filter(Objects::nonNull)   → String không null
    │
    ├─ map(String::strip)         → String đã chuẩn hóa
    │
    └─ filter(s -> !s.isEmpty())  → chỉ chuỗi không rỗng
~~~

Trong trường hợp này, **filter trước map** bảo vệ receiver Employee. **Filter sau map** bảo vệ receiver String cho bước kế tiếp. Chúng không thay thế nhau.

Khi cả hai điều kiện đơn giản, có thể viết trực tiếp:

~~~java
employees.stream()
        .filter(e -> e != null && e.name() != null)
        .map(Employee::name)
        .map(String::strip);
~~~

Đây là đoạn minh họa. Nó an toàn trước null element và null name, nhưng **không tự loại chuỗi blank**. Nếu cần kiểm tra `name.isBlank()`, phải thêm điều kiện hoặc filter phù hợp.

**Một lưu ý:** Việc gọi `e.name()` hai lần trong cùng pipeline có thể ổn với accessor bất biến như record, nhưng với getter có side effect hoặc dữ liệu mutable thay đổi đồng thời, hai lần đọc có thể không tương đương. Chuyển sang String bằng `map(Employee::name)` rồi xử lý String ở các bước sau giúp tránh đọc lại getter không cần thiết.

## 6. Null element khác null nested property

Một đối tượng có thể tồn tại nhưng một đối tượng con của nó lại null.

Ví dụ:

~~~java
record Address(String city) {}
record Customer(String id, Address address) {}
~~~

Hai record trên là **khai báo kiểu minh họa**. Với `Customer customer` khác null, biểu thức dưới đây vẫn có nguy cơ NPE nếu `customer.address() == null`:

~~~java
String city = customer.address().city();
~~~

Guard cần bảo vệ từng tầng:

~~~java
if (customer != null && customer.address() != null
        && customer.address().city() != null) {
    String city = customer.address().city();
    // Dùng city ở đây.
}
~~~

Đây là đoạn minh họa bên trong một phương thức. Trong Stream, cách rõ ràng hơn thường là chia các tầng thành các `map` và `filter` riêng:

~~~java
List<String> cities = customers.stream()
        .filter(Objects::nonNull)
        .map(Customer::address)
        .filter(Objects::nonNull)
        .map(Address::city)
        .filter(Objects::nonNull)
        .toList();
~~~

Cần import List, Objects và có biến customers phù hợp. Đầu tiên loại Customer null, rồi loại Address null, cuối cùng loại city null. Nếu cần loại thành phố rỗng, thêm `filter(city -> !city.isBlank())` sau bước city không null.

**Điều quan trọng:** `Objects::nonNull` không “đi sâu” tự động vào các trường; nó chỉ kiểm tra **đối tượng chính đang được truyền cho Predicate tại thời điểm đó**.

## 7. Java 17 chạy được: thuộc tính lồng nhau và Optional

Tạo tệp **NullablePropertyDemo.java**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

record Address(String city) {}
record Customer(String id, Address address) {}

public class NullablePropertyDemo {
    static Optional<String> cityOf(Customer customer) {
        return Optional.ofNullable(customer)
                .map(Customer::address)
                .map(Address::city)
                .filter(city -> !city.isBlank());
    }

    public static void main(String[] args) {
        List<Customer> customers = Arrays.asList(
                new Customer("A", new Address("Hà Nội")),
                null,
                new Customer("B", null),
                new Customer("C", new Address(null)),
                new Customer("D", new Address("Đà Nẵng"))
        );

        List<String> cities = customers.stream()
                .filter(Objects::nonNull)
                .map(Customer::address)
                .filter(Objects::nonNull)
                .map(Address::city)
                .filter(Objects::nonNull)
                .toList();

        System.out.println("Cities: " + cities);
        System.out.println("A: " + cityOf(customers.get(0))
                .orElse("unknown"));
        System.out.println("B: " + cityOf(customers.get(2))
                .orElse("unknown"));
        System.out.println("C: " + cityOf(customers.get(3))
                .orElse("unknown"));
        System.out.println("null: " + cityOf(null).orElse("unknown"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 NullablePropertyDemo.java
java NullablePropertyDemo
~~~

Stdout:

~~~text
Cities: [Hà Nội, Đà Nẵng]
A: Hà Nội
B: unknown
C: unknown
null: unknown
~~~

**Giải thích:**

- Pipeline đầu bỏ Customer null, bỏ Address null, rồi bỏ city null. Do đó chỉ còn hai thành phố **Hà Nội** và **Đà Nẵng**.
- `Optional.ofNullable(customer)` tạo Optional rỗng khi Customer null. `map(Customer::address)` cho Optional.empty() nếu Address null, nên không gọi `Address::city` trên null.
- `Optional.map` chuyển kết quả null của mapper thành Optional.empty(); vì vậy trường city null cũng an toàn trong ví dụ.
- `filter(city -> !city.isBlank())` chỉ thực thi khi Optional chứa city không null.
- `orElse("unknown")` thể hiện **chính sách fallback của ví dụ**. Trong hệ thống thật, thiếu địa chỉ có thể đòi hỏi lỗi xác thực thay vì im lặng thay bằng unknown.

**Optional** thường hữu ích khi phương thức **trả về** một giá trị có thể vắng mặt, như `Optional<String> cityOf(...)`. Không cần thiết phải đặt `Optional<...>` vào mọi field của Customer/Address chỉ để xử lý null trong Stream.

## 8. Chọn phần tử đầu tiên bằng findFirst/findAny

Khi chọn phần tử từ Stream, nhiều người cho rằng **findFirst()** luôn an toàn với null. Thực tế, theo hợp đồng Stream API, **findFirst()** và **findAny()** có thể ném NullPointerException nếu **phần tử được chọn là null**. Chúng trả về **Optional<T>**, mà Optional không thể chứa null.

Vì vậy, khi nguồn có thể chứa null và cần chọn phần tử đầu tiên hợp lệ, hãy lọc trước:

~~~java
Optional<String> first = codes.stream()
        .filter(Objects::nonNull)
        .findFirst();
~~~

Đây là đoạn minh họa cần import `Optional`, `Objects` và một collection `codes` phù hợp. Nếu mọi phần tử đều null hoặc danh sách rỗng, kết quả là Optional.empty().

Tương tự, khi chọn phần tử dựa trên thuộc tính, cần bảo vệ trước khi predicate truy cập thuộc tính:

~~~java
Optional<Employee> firstAdult = employees.stream()
        .filter(Objects::nonNull)
        .filter(e -> e.age() != null && e.age() >= 18)
        .findFirst();
~~~

Đây là đoạn minh họa với Employee.age() trả Integer và đã import Optional, Objects. **findFirst() không bỏ qua null tự động**; chính các bước filter mới bảo đảm phần tử được chọn không null.

### 8.1. findFirst khác findAny

- **findFirst()** trả phần tử đầu tiên theo **encounter order** nếu Stream có thứ tự.
- **findAny()** có thể trả một phần tử bất kỳ, đặc biệt để phù hợp với xử lý song song; không nên dựa vào vị trí cụ thể.
- Cả hai trả **Optional<T>** và đều không hợp lệ khi phần tử thực sự được chọn là null.
- Trường hợp không có phần tử thì trả Optional.empty().

Nếu không quan trọng phần tử nào được chọn, **findAny()** có thể phù hợp; nếu cần kết quả ổn định theo thứ tự danh sách tuần tự, **findFirst()** biểu đạt mục đích tốt hơn.

## 9. Java 17 chạy được: chọn, chuẩn hóa và sắp xếp null-safe

Tạo tệp **NullSafeSelectionDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

record Item(String id, Integer price) {}

public class NullSafeSelectionDemo {
    public static void main(String[] args) {
        List<String> codes =
                Arrays.asList(null, "  ", " ab ", null, " xy ");

        Optional<String> firstCode = codes.stream()
                .filter(Objects::nonNull)
                .map(String::strip)
                .filter(s -> !s.isEmpty())
                .findFirst();

        System.out.println("First: " + firstCode.orElse("(none)"));

        List<Item> items = Arrays.asList(
                new Item("A", 20),
                null,
                new Item("B", null),
                new Item("C", 10)
        );

        Comparator<Item> byPrice =
                Comparator.comparing(
                        Item::price,
                        Comparator.nullsLast(
                                Comparator.naturalOrder()));

        List<String> sortedIds = items.stream()
                .filter(Objects::nonNull)
                .sorted(byPrice)
                .map(Item::id)
                .toList();

        System.out.println("Sorted ids: " + sortedIds);
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 NullSafeSelectionDemo.java
java NullSafeSelectionDemo
~~~

Stdout:

~~~text
First: ab
Sorted ids: [C, A, B]
~~~

**Điểm cần phân biệt:**

1. `codes` có null element, chuỗi blank và chuỗi có khoảng trắng. `Objects::nonNull` loại null **trước** `String::strip`.
2. `strip` biến `"  "` thành `""` và `" ab "` thành `"ab"`; bước `filter(!isEmpty())` loại chuỗi rỗng.
3. `findFirst()` tìm `"ab"`, trả Optional chứa giá trị đó.
4. Danh sách `items` chứa một Item null và một Item hợp lệ có **price null**. `filter(Objects::nonNull)` loại Item null trước khi Comparator đọc `Item::price`.
5. `Comparator.nullsLast(Comparator.naturalOrder())` chỉ xử lý **giá trị price null**, nên Item **B** được xếp cuối, còn **C** giá 10 trước **A** giá 20.
6. **Một Comparator nullsLast ở cấp thuộc tính không tự làm đối tượng Item null trở nên an toàn.** Ở đây ta chủ động loại Item null trước khi sắp xếp.

Trong các bài toán thật, cần xác định sản phẩm thiếu giá có được xếp cuối, loại khỏi danh sách hay báo lỗi. `nullsLast` là **quy tắc sắp xếp**, không phải validation.

## 10. Comparator và truy cập thuộc tính nullable

Khi sắp xếp danh sách đối tượng, expression sau có nguy cơ lỗi:

~~~java
items.stream()
        .sorted(Comparator.comparing(Item::price));
~~~

Đây là đoạn minh họa. Có **hai nguồn NPE**:

1. **Item null:** `Item::price` cố gọi phương thức trên null.
2. **Item.price() null:** Comparator dùng thứ tự tự nhiên trên Integer có thể gặp null và ném NPE.

Giải pháp tùy chính sách:

**Loại Item null và Item thiếu price:**

~~~java
items.stream()
        .filter(Objects::nonNull)
        .filter(item -> item.price() != null)
        .sorted(Comparator.comparing(Item::price));
~~~

**Loại Item null nhưng giữ Item thiếu price, xếp cuối:**

~~~java
items.stream()
        .filter(Objects::nonNull)
        .sorted(Comparator.comparing(
                Item::price,
                Comparator.nullsLast(Comparator.naturalOrder())));
~~~

Đây là hai đoạn minh họa có import Objects và Comparator. **Điều kiện tiền kiểm** phải khớp với cách xử lý dữ liệu thiếu:

- Nếu giá thiếu là bản ghi không hợp lệ: xác thực hoặc loại bỏ.
- Nếu giá thiếu có nghĩa “chưa được định giá” và vẫn phải hiển thị: dùng nullsLast hoặc nullsFirst theo yêu cầu.
- Nếu đối tượng Item null là lỗi cấu trúc dữ liệu nghiêm trọng: báo lỗi sớm thay vì lọc âm thầm.

Cũng có thể dùng **Comparator.nullsLast(itemComparator)** ở mức **đối tượng Item**, nhưng cần đặt tầng xử lý null cho đúng loại: **null của Item** khác **null của price**. Hai tầng cần hai chính sách nếu đều có thể null.

## 11. Các trường hợp NPE dù đã lọc null ban đầu

### 11.1. Unboxing của wrapper nullable

~~~java
// Có thể NPE nếu age() trả Integer null.
Predicate<Employee> adult = employee ->
        employee != null && employee.age() >= 18;
~~~

Cần thêm `employee.age() != null` trước so sánh, vì **Integer** bị unbox thành **int**. Java không tự hiểu rằng receiver khác null thì các trường của nó cũng khác null.

### 11.2. Getter trung gian trả null

~~~java
// Có thể NPE nếu address() trả null.
String city = customer.address().city();
~~~

Kiểm tra `customer != null` chỉ bảo vệ Customer, không bảo vệ Address. Dùng guard riêng hoặc chia pipeline như mục 6.

### 11.3. Method reference truy cập receiver của phần tử

~~~java
// Có thể NPE nếu nguồn chứa null employee.
employees.stream().map(Employee::name);
~~~

Method reference **không** tự bao hàm null guard. Nó chỉ là cách viết gọn cho lời gọi method phù hợp với SAM.

### 11.4. Stream.map có thể tạo null mới

~~~java
employees.stream()
        .filter(Objects::nonNull)
        .map(Employee::name);
~~~

Đây là đoạn minh họa. Pipeline loại Employee null nhưng vẫn có thể tạo String null nếu name() trả null. **Stream.map không bắt buộc kết quả mapper khác null**. Chỉ thêm `filter(Objects::nonNull)` sau map nếu mục tiêu là loại các giá trị thiếu.

### 11.5. API nhận collection có thể cấm null

- **List.of(...)**, **Set.of(...)** và **Map.of(...)** không cho null element/key/value tương ứng.
- **Arrays.asList(...)** có thể chứa null element.
- **Stream.toList()** trong Java 17 có thể chứa null trong kết quả và trả list **không thể sửa**.
- **Collectors.toUnmodifiableList()** không cho các phần tử null: nếu stream có null, collection có thể ném NPE ở terminal operation.

Đây là lý do không nên suy luận từ một lần `toList()` thành công rằng pipeline không chứa null. Hãy làm rõ hợp đồng đầu ra.

## 12. Null guard và đánh giá ngắn mạch với Predicate

Trong functional programming, **Predicate.and()** và **Predicate.or()** cho phép kết hợp điều kiện. **Predicate.and** đánh giá ngắn mạch: nếu predicate bên trái false thì predicate bên phải **không chạy**.

~~~java
Predicate<Employee> present = Objects::nonNull;
Predicate<Employee> hasName = e -> e.name() != null;

Predicate<Employee> safe = present.and(hasName);
~~~

Đây là đoạn minh họa có import Predicate và Objects. **safe.test(null)** trả false mà không gọi `hasName.test(null)`.

Thứ tự đảo lại có thể nguy hiểm:

~~~java
// Có thể ném NPE cho null vì hasName chạy trước.
Predicate<Employee> unsafe = hasName.and(present);
~~~

**Đánh giá ngắn mạch là một thuộc tính của phép kết hợp**, không phải điều Java tự suy ra từ việc có hai Predicate ở đâu đó. Tương tự, `e != null || e.name().isBlank()` là sai nếu muốn bảo vệ dereference: với e=null, vế trái true nên không gọi vế phải, nhưng kết quả logic có thể sai mục đích; với e khác null, vế phải lại chạy. Cần chọn **&&** hay **||** theo ý nghĩa logic mong muốn.

Một ví dụ điều kiện cho phép null hoặc cho phép tên hợp lệ:

~~~java
Predicate<Employee> optionalName = e ->
        e == null || (e.name() != null && !e.name().isBlank());
~~~

Đoạn minh họa này an toàn theo short-circuit, nhưng **trả true cho Employee null**. Điều đó có thể hợp lệ nếu yêu cầu nghiệp vụ thực sự chấp nhận absence, nhưng không thích hợp khi đang **lọc bỏ null element**. Tránh nhầm an toàn về dereference với đúng nghĩa lọc dữ liệu.

## 13. Khi nào không nên bỏ qua phần tử null?

**filter(Objects::nonNull)** thường đúng cho pipeline muốn loại dữ liệu thiếu. Nhưng không phải mọi phần tử null đều nên bị loại âm thầm.

Các trường hợp cần cân nhắc:

- **Bản ghi bắt buộc:** một giao dịch quan trọng thiếu đối tượng có thể cần báo lỗi thay vì bị loại khỏi tổng hợp.
- **Định vị dữ liệu:** nếu vị trí của null có ý nghĩa (ví dụ bản ghi thứ 3 bị thiếu), filter sẽ làm mất vị trí ban đầu.
- **Audit và chất lượng dữ liệu:** loại phần tử giúp pipeline tiếp tục, nhưng nếu cần đếm số bản ghi lỗi phải đo/ghi riêng theo chính sách.
- **API đầu ra:** nếu caller kỳ vọng số phần tử đầu ra bằng đầu vào, filter thay đổi cardinality; có thể cần dùng kiểu kết quả chứa trạng thái thiếu.
- **Dữ liệu domain:** một thuộc tính null có thể đại diện “chưa biết”, “chưa duyệt”, “không áp dụng” — các trạng thái khác nhau không nên bị gộp tùy tiện.

Nếu null vi phạm hợp đồng đầu vào, có thể **fail fast**:

~~~java
List<Employee> checked = employees.stream()
        .map(e -> Objects.requireNonNull(e, "employee"))
        .toList();
~~~

Đoạn minh họa với import Objects và List. **Objects.requireNonNull** ném NPE khi gặp null, thay vì loại bản ghi. `checked` chỉ được tạo thành công nếu mọi phần tử hợp lệ; quy tắc này thích hợp nếu không cho phép thiếu Employee.

Nếu cần phân biệt nhiều loại lỗi hoặc lưu vị trí phần tử gốc, hãy xây dựng một mô hình kết quả kiểm tra riêng (**record ValidationResult(...)**, báo lỗi theo chỉ số, hoặc dạng Result phù hợp) thay vì chỉ lọc để “không bị crash”.

## 14. Stream và null nguồn: không nhầm stream null với phần tử null

Có một khác biệt rất quan trọng:

~~~java
List<String> names = null;
// names.stream() → NPE trước khi tạo Stream.
~~~

Đây là đoạn minh họa. **filter(Objects::nonNull)** chỉ kiểm tra **phần tử trong Stream**, không thể bảo vệ `names.stream()` nếu bản thân biến `names` null.

Một API tốt nên chủ động quy định collection trả về là **không null**; khi không có phần tử, trả **List.of()** hoặc collection rỗng phù hợp. Nếu tích hợp với nguồn legacy có thể trả null, hãy chuẩn hóa tại biên:

~~~java
List<String> source = legacyResult == null
        ? List.of()
        : legacyResult;

List<String> valid = source.stream()
        .filter(Objects::nonNull)
        .toList();
~~~

Đây là đoạn minh họa có biến `legacyResult` kiểu List<String> và import List, Objects. Hai bước có trách nhiệm khác nhau: bước đầu bảo vệ collection reference; bước sau xử lý null element trong collection.

**Không làm điều này một cách tự động** nếu null collection thực ra biểu thị lỗi dữ liệu phải được báo cáo. Đừng chuyển mọi null thành empty vì muốn Stream chạy được.

## 15. Cẩn trọng với hiệu năng, song song và trạng thái thay đổi

### 15.1. filter thường tốt hơn try/catch NPE

Viết `filter(Objects::nonNull)` hoặc guard rõ ràng là cách xử lý dự đoán được. Không nên dùng `catch(NullPointerException)` quanh toàn pipeline để bỏ qua dữ liệu, vì có thể che cả bug không liên quan tới dữ liệu null dự kiến.

Ví dụ phản mẫu:

~~~java
// Phản mẫu minh họa: không nên che mọi NPE.
try {
    return employees.stream()
            .map(Employee::name)
            .toList();
} catch (NullPointerException ignored) {
    return List.of();
}
~~~

Đây là đoạn minh họa bên trong phương thức trả List<String>, không phải chương trình độc lập. Nó trả danh sách rỗng ngay cả khi chỉ một phần tử hỏng, có thể làm mất dữ liệu hợp lệ và che lỗi lập trình.

### 15.2. Predicate không nên dựa vào side effect

Đừng làm thay đổi dữ liệu bên trong `filter` chỉ để “sửa null” rồi mới xử lý. Tốt hơn nên tạo bước biến đổi rõ nghĩa, dùng đối tượng bất biến hoặc validation ở ranh giới. Trong Stream, các side effect có thể khó suy luận, đặc biệt khi pipeline chạy song song.

### 15.3. Concurrent mutation có thể làm null guard không còn đủ

Nếu object có trường mutable và luồng khác thay đổi trường đó giữa hai lần đọc, mã:

~~~java
if (employee.name() != null) {
    System.out.println(employee.name().length());
}
~~~

vẫn có rủi ro khi getter trả các giá trị khác nhau ở hai lần gọi. Với chương trình đa luồng, cần quy tắc đồng bộ hóa, immutable snapshot hoặc đọc vào một local an toàn theo chính sách:

~~~java
String name = employee.name();
if (name != null) {
    System.out.println(name.length());
}
~~~

Đây là các đoạn minh họa trong phương thức và giả định `employee` đã khác null. Đọc local chỉ tránh việc **đọc hai lần cùng một trường**; nó không tự tạo các bảo đảm visibility hoặc thread safety cho toàn bộ chương trình. Trong code domain bất biến (như record chứa String), vấn đề thay đổi trường thường ít xảy ra hơn.

### 15.4. Primitive stream và null wrapper

Pipeline **mapToInt(Employee::age)** với `Integer age` nullable có thể ném NPE do unboxing. Cần lọc `age != null` trước, hoặc dùng bước chuyển đổi có chính sách xử lý thiếu:

~~~java
int sum = employees.stream()
        .filter(Objects::nonNull)
        .map(Employee::age)
        .filter(Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum();
~~~

Đây là đoạn minh họa cần import Objects và giả định employees chứa Employee với Integer age. Bước `mapToInt(Integer::intValue)` chỉ được gọi sau khi Integer null bị loại. Nếu thuộc tính age thiếu là lỗi nghiệp vụ, hãy xác thực và báo thay vì loại khỏi phép tổng hợp.

## 16. Checklist khi viết pipeline lọc và chọn phần tử

Trước khi triển khai một đoạn `stream().filter(...).map(...).findFirst()`, hãy trả lời:

1. **Bản thân collection/stream có thể null không?** Chuẩn hóa hoặc báo lỗi ở boundary.
2. **Các phần tử có thể null không?** Chọn filter(Objects::nonNull) hay fail fast.
3. **Có thuộc tính nullable không?** Đặt guard trước khi gọi phương thức trên thuộc tính đó.
4. **Có thuộc tính lồng nhau không?** Kiểm tra mỗi tầng Customer → Address → City.
5. **Có unboxing từ wrapper không?** `Integer`, `Long`, `Boolean` null đều cần chính sách.
6. **Có chọn bằng findFirst/findAny không?** Không để phần tử được chọn là null.
7. **Có sắp xếp hoặc so sánh thuộc tính không?** Phân biệt null object với null sort key; chọn Comparator.nullsFirst/Last khi phù hợp.
8. **Dữ liệu thiếu phải bị loại, thay thế hay báo lỗi?** Không để cú pháp filter quyết định nghiệp vụ thay mình.
9. **Có thao tác phụ hoặc dữ liệu mutable thay đổi đồng thời không?** Tránh side effect và đọc lại getter không ổn định.
10. **Có kiểm thử null ở mọi vị trí không?** Null element, null field, null nested object, collection null, danh sách toàn null và danh sách rỗng đều đáng thử.

## 17. Bài tập thực hành

### Bài 1: Xác định vị trí NPE

Cho danh sách:

~~~java
List<String> values = Arrays.asList("A", null, "B");
~~~

Đây là đoạn minh họa với import List, Arrays. Dự đoán hành vi của `values.stream().map(String::length).toList()`. Hãy sửa bằng filter(Objects::nonNull) trước map và dự đoán danh sách kết quả **[1, 1]**.

### Bài 2: Null element và nullable field

Cho một List<Employee> có một Employee null, một Employee có name null và một Employee có name `" Linh "`. Viết pipeline chỉ trả **["Linh"]**. Giải thích vì sao cần kiểm tra hai loại null ở hai vị trí khác nhau.

### Bài 3: Nested property

Cho Customer có thể không có Address, Address có thể không có city. Hãy viết một pipeline Stream trả danh sách city không null; sau đó viết phương thức `Optional<String> cityOf(Customer c)` dùng `ofNullable` và `map`.

### Bài 4: Chọn phần tử đầu tiên hợp lệ

Danh sách `[null, "  ", "ab", null, "cd"]` cần chọn mã không blank đầu tiên. Dùng `filter(Objects::nonNull)`, `filter(s -> !s.isBlank())`, rồi `findFirst()`. Giải thích vì sao không dùng findFirst() trước filter.

### Bài 5: Nullable Comparator

Cho Item có trường `Integer price` và danh sách chứa Item null, Item giá null, Item giá 10, Item giá 20. Hãy viết hai phương án: **loại toàn bộ Item thiếu price** và **giữ Item có price null nhưng xếp cuối**. Giải thích vai trò khác nhau của `filter(Objects::nonNull)` và `Comparator.nullsLast`.

### Bài 6: Thiết kế yêu cầu nghiệp vụ

Một báo cáo doanh thu chứa dòng giao dịch null. Có nên dùng filter(Objects::nonNull) rồi cộng doanh thu hay dừng xử lý và báo lỗi? Hãy nêu các điều kiện giúp lựa chọn, nhất là khi dữ liệu thiếu ảnh hưởng độ chính xác tài chính.

## 18. Ghi nhớ

- **Kiểm tra null trước dereference**: `filter(Objects::nonNull)` đặt **trước** `map(Type::getter)` khi phần tử có thể null.
- **Null element khác nullable property**: sau khi map sang một thuộc tính có thể null, cần thêm guard trước khi gọi phương thức trên thuộc tính.
- **&& và Predicate.and() đánh giá ngắn mạch**, nhưng chỉ an toàn khi đặt guard đúng thứ tự.
- **findFirst/findAny không tự bỏ qua null**, Optional không chứa null; loại phần tử null trước khi chọn.
- **Comparator và primitive unboxing** cũng có thể gây NPE dù object gốc không null.
- **Quyết định loại, thay, hoặc báo lỗi phải thuộc về hợp đồng nghiệp vụ**, không chỉ để tránh exception.

Tư duy thực hành: **“Tại bước này, receiver nào sắp bị truy cập, và có bằng chứng nào bảo đảm receiver đó không null?”** Nếu đặt câu hỏi đó ở từng bước lọc, chọn và biến đổi, pipeline Java sẽ dễ đọc, dễ kiểm thử và đáng tin cậy hơn.