# Vai trò của `toString()`, `getClass()` và `clone()` trong Java

## 1. Bức tranh tổng quan

Mọi đối tượng thuộc kiểu tham chiếu trong Java đều kế thừa các phương thức từ `java.lang.Object` (trực tiếp hoặc gián tiếp). Ba phương thức sau giải quyết ba nhu cầu khác nhau:

| Phương thức | Câu hỏi mà phương thức trả lời | Kết quả chính |
| --- | --- | --- |
| `toString()` | “Biểu diễn đối tượng này thành văn bản như thế nào?” | Một `String` mô tả đối tượng, thường phục vụ đọc hiểu, gỡ lỗi và ghi log. |
| `getClass()` | “Đối tượng này thực sự thuộc lớp nào tại thời điểm chạy?” | Đối tượng `Class<?>` biểu diễn lớp runtime chính xác. |
| `clone()` | “Có thể tạo bản sao của đối tượng này bằng cơ chế `Object.clone()` không?” | Một đối tượng mới, với các trường được sao chép ở mức nông; việc gọi hợp lệ phụ thuộc vào giao ước `Cloneable`. |

Ba phương thức không thay thế cho nhau và cũng không phải ba cách kiểm tra đối tượng “bằng nhau”. Đặc biệt, `clone()` không mặc nhiên tạo một bản sao độc lập hoàn toàn. Khi học *object contract*, cần liên hệ chúng với `equals()` và `hashCode()` nhưng phân biệt rõ trách nhiệm.

Chữ ký đáng chú ý của `Object`:

```java
public String toString();
public final native Class<?> getClass();
protected native Object clone() throws CloneNotSupportedException;
```

Đây là **các khai báo minh họa API trong `java.lang.Object`**, không phải ba phương thức để dán độc lập vào một tệp Java. Từ khóa `native` thể hiện phần triển khai của `getClass()` và `clone()` gắn với JVM; người sử dụng chỉ cần nắm giao ước hành vi.

## 2. `toString()`: biểu diễn đối tượng thành chuỗi

### Hành vi mặc định và lý do ghi đè

`Object.toString()` có thể trả về chuỗi theo dạng:

```text
ten.lop.DayDu@chuoiHex
```

Cách biểu diễn mặc định tương ứng với tên lớp từ `getClass().getName()`, ký tự `@` và dạng thập lục phân của giá trị `hashCode()`. **Không** suy luận phần sau `@` là địa chỉ bộ nhớ, mã định danh duy nhất hay `System.identityHashCode()` trong mọi trường hợp: `hashCode()` có thể đã được ghi đè và các giá trị hash có thể trùng nhau.

Ví dụ một lớp mang dữ liệu nên ghi đè để tạo mô tả có ý nghĩa:

```java
final class Product {
    private final String sku;
    private final int price;

    Product(String sku, int price) {
        this.sku = sku;
        this.price = price;
    }

    @Override
    public String toString() {
        return "Product{sku='" + sku + "', price=" + price + "}";
    }
}
```

*Đây là đoạn định nghĩa lớp minh họa; chương trình hoàn chỉnh có `main` nằm ở mục 5.* Với `new Product("P01", 120)`, khi gọi `toString()` sẽ thu được:

```text
Product{sku='P01', price=120}
```

Các tình huống thường gọi `toString()` gồm `System.out.println(product)`, nối chuỗi `"item=" + product`, và nhiều công cụ debug/log khi chúng cần biểu diễn văn bản của đối tượng. Với biến có thể `null`, `String.valueOf(value)` trả về `"null"` thay vì gọi phương thức trên tham chiếu `null` gây `NullPointerException`. Một hệ thống logging có thể dùng cơ chế định dạng riêng hoặc gọi `toString()` trễ, nên hành vi cụ thể phụ thuộc thư viện.

### Thiết kế `toString()` tốt

- Ưu tiên những trường giúp người đọc nhận ra trạng thái hoặc ý nghĩa của đối tượng; giữ định dạng dễ hiểu và nhất quán.
- Không tiết lộ mật khẩu, token, khóa riêng, dữ liệu cá nhân hoặc thông tin nội bộ nhạy cảm khi log.
- Tránh tác dụng phụ, thay đổi trạng thái, truy vấn mạng/cơ sở dữ liệu hay phép tính nặng chỉ để tạo chuỗi. Chú ý quan hệ tham chiếu vòng: gọi `toString()` đệ quy trên cả hai phía có thể dẫn đến `StackOverflowError`.
- Không xem `toString()` như định dạng truyền dữ liệu chính thức. Nếu cần hợp đồng ổn định cho JSON, CSV, giao thức hoặc persistence, hãy dùng serializer/DTO thích hợp.

**Quan hệ với `equals()/hashCode()`:** Hai đối tượng `equals()` nhau không bị bắt buộc phải có chuỗi `toString()` giống nhau. Ngược lại, hai chuỗi `toString()` giống nhau không chứng minh hai đối tượng bằng nhau. `toString()` phục vụ biểu diễn, không định nghĩa bình đẳng.

## 3. `getClass()`: nhận diện kiểu thực tế lúc chạy

`getClass()` là phương thức `public final` của `Object` nên lớp con không ghi đè được. Nó trả về đối tượng `Class` mô tả **đúng lớp runtime** của đối tượng nhận lời gọi, bất kể kiểu khai báo của biến tham chiếu rộng đến đâu.

```java
Object value = "Hello";

System.out.println(value.getClass().getName());       // java.lang.String
System.out.println(value.getClass().getSimpleName()); // String
System.out.println(value.getClass() == String.class); // true
System.out.println(value instanceof CharSequence);   // true
```

*Đây là các câu lệnh minh họa đặt bên trong một phương thức; các chú thích là kết quả dự kiến.* `value` được khai báo kiểu `Object` nhưng đối tượng đang giữ là `String`. Vì vậy `getClass()` cho biết lớp thực của đối tượng, không trả về `Object.class` chỉ vì kiểu của biến là `Object`.

Các phép kiểm tra không đồng nghĩa:

| Cách kiểm tra | Ý nghĩa |
| --- | --- |
| `obj.getClass() == SomeType.class` | Lớp runtime **chính xác** là `SomeType`, không chấp nhận lớp con. |
| `obj instanceof SomeType` | Đối tượng thuộc `SomeType` hoặc một kiểu con/kiểu triển khai tương ứng. Với `obj == null`, kết quả là `false`. |
| `SomeType.class.isAssignableFrom(obj.getClass())` | `SomeType` có thể nhận đối tượng có lớp runtime đó qua quan hệ kiểu; phải bảo đảm `obj` không `null` trước khi gọi `getClass()`. |

Ứng dụng thường gặp: ghi nhận lớp thực khi chẩn đoán lỗi, chọn chiến lược xử lý theo kiểu, làm việc với reflection (xem tên lớp, phương thức, annotation) và hiểu các đối tượng được tạo bởi framework/proxy. Chẳng hạn trong `equals()`, một số lớp value object dùng `getClass()` để yêu cầu hai đối tượng có đúng cùng lớp runtime; lớp khác dùng `instanceof` để cho phép quan hệ kế thừa. Lựa chọn đó ảnh hưởng tính đối xứng và khả năng tương thích với subclass/proxy, nên phải thiết kế theo giao ước bình đẳng của cả lớp, không thay máy móc mọi `instanceof` bằng `getClass()`.

**Lưu ý:**

- Gọi `null.getClass()` không hợp lệ và gây `NullPointerException`; không tồn tại “lớp runtime của null”.
- `getClass()` không cần ép kiểu hay tạo đối tượng `Class` mới mỗi lần. Hai đối tượng có cùng lớp runtime sẽ nhận cùng đối tượng `Class` tương ứng trong ngữ cảnh nạp lớp của chúng.
- `getClass()` chỉ có trên giá trị tham chiếu đối tượng; với kiểu nguyên thủy, có thể lấy class literal như `int.class` thay vì gọi phương thức trên giá trị `int`.
- `getName()`, `getSimpleName()` và `getCanonicalName()` là các cách lấy tên khác nhau; với lớp lồng, anonymous class và array, kết quả có thể khác trực giác. Không mặc định `getSimpleName()` là khóa định danh ổn định.

## 4. `clone()`: cơ chế sao chép nông và hợp đồng `Cloneable`

### Vì sao `clone()` khác hai phương thức trước?

`Object.clone()` có mức truy cập `protected`, nên mã bên ngoài một lớp thường **không thể** gọi `object.clone()` trực tiếp trên mọi đối tượng. Một lớp muốn cung cấp API sao chép thường:

1. Khai báo `implements Cloneable`.
2. Ghi đè `clone()` thành `public` nếu muốn mã gọi bên ngoài có thể sử dụng.
3. Gọi `super.clone()` bên trong phương thức ghi đè.
4. Xử lý `CloneNotSupportedException` nếu cần và quyết định có sao chép sâu dữ liệu tham chiếu hay không.

`Cloneable` là **marker interface**, không định nghĩa phương thức `clone()`. Chỉ việc viết `implements Cloneable` không tự tạo một phương thức `clone()` công khai. Nếu dùng `Object.clone()` trên một đối tượng không triển khai `Cloneable` (ngoại lệ riêng dành cho array), cơ chế đó ném `CloneNotSupportedException`.

Theo cơ chế chuẩn, `super.clone()` tạo đối tượng mới cùng lớp runtime và chép giá trị từng trường:

- Trường nguyên thủy (`int`, `boolean`, …) được chép giá trị.
- Trường tham chiếu được chép **địa chỉ tham chiếu tới cùng đối tượng con**, không tự dựng bản sao của đối tượng con.
- Constructor của đối tượng đích không được gọi như khi viết `new`. Vì vậy, không dựa vào constructor để “sửa” trạng thái sau khi gọi `super.clone()`.

Hình dung với `Customer` giữ tham chiếu `Address`:

```text
Trước khi sao chép:
original ──> Customer A ──address──> Address X

Sau super.clone() (shallow copy):
original ──> Customer A ──address──┐
                                  ├──> Address X
shallow  ──> Customer B ──address──┘

Sau khi tạo bản sao độc lập cho Address:
original ──> Customer A ──address──> Address X
deep     ──> Customer C ──address──> Address Y
```

Tên `deep` trong sơ đồ chỉ bản sao được tạo chủ động cho *đồ thị đối tượng của ví dụ*. Nó không có nghĩa Java cung cấp một thao tác deep clone tổng quát cho mọi đồ thị đối tượng.

### Vì sao cần cân nhắc sao chép sâu?

Nếu `Customer A` và `Customer B` cùng giữ `Address X` thì thay đổi `Address X.city` thông qua một bản sẽ hiển thị ở bản kia. Nếu các thành phần tham chiếu là bất biến (ví dụ `String`), chia sẻ chúng thường an toàn; với thành phần mutable, cần quyết định rõ có muốn chia sẻ hay không. Một `final` trên trường tham chiếu chỉ ngăn gán lại tham chiếu đó, **không** làm đối tượng được tham chiếu trở thành bất biến.

## 5. Ví dụ Java 17+ chạy được: ba phương thức trong cùng một tình huống

Lưu toàn bộ mã bên dưới vào tệp `ObjectMethodsDemo.java`.

```java
public class ObjectMethodsDemo {

    static final class Address {
        String city;

        Address(String city) {
            this.city = city;
        }
    }

    static final class Customer implements Cloneable {
        private final String name;
        private final Address address;

        Customer(String name, Address address) {
            this.name = name;
            this.address = address;
        }

        @Override
        public String toString() {
            return "Customer{name='" + name + "', city='" + address.city + "'}";
        }

        @Override
        public Customer clone() {
            try {
                return (Customer) super.clone();
            } catch (CloneNotSupportedException ex) {
                // Customer triển khai Cloneable nên nhánh này không được mong đợi.
                throw new AssertionError(ex);
            }
        }

        // Tạo bản sao độc lập cho Address mà không dựa vào Object.clone().
        public Customer copyIndependent() {
            return new Customer(name, new Address(address.city));
        }
    }

    public static void main(String[] args) {
        Customer original = new Customer("An", new Address("Hà Nội"));
        Customer shallow = original.clone();
        Customer independent = original.copyIndependent();

        System.out.println(original); // Gọi toString().
        System.out.println(original.getClass().getSimpleName());
        System.out.println(original == shallow);
        System.out.println(original.address == shallow.address);
        System.out.println(original.address == independent.address);

        shallow.address.city = "Đà Nẵng";

        System.out.println(original.address.city);
        System.out.println(independent.address.city);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac ObjectMethodsDemo.java
java ObjectMethodsDemo
```

Đầu ra chính xác:

```text
Customer{name='An', city='Hà Nội'}
Customer
false
true
false
Đà Nẵng
Hà Nội
```

Giải thích tuần tự:

1. `println(original)` dùng `Customer.toString()` nên hiển thị dữ liệu có ý nghĩa thay cho chuỗi mặc định của `Object`.
2. `getClass().getSimpleName()` cho biết lớp runtime của `original` là `Customer`.
3. `original == shallow` là `false`: `clone()` tạo một đối tượng `Customer` mới, không trả về chính đối tượng cũ.
4. `original.address == shallow.address` là `true`: `super.clone()` chỉ chép tham chiếu `address`.
5. `original.address == independent.address` là `false`: `copyIndependent()` đã tạo một `Address` khác bằng `new`.
6. Đổi `shallow.address.city` cũng đổi giá trị quan sát qua `original.address.city` vì hai tham chiếu trỏ tới cùng `Address`. Bản `independent` vẫn lưu “Hà Nội”.

Ở ví dụ này, `name` là `String` bất biến nên có thể chia sẻ tham chiếu an toàn; `Address` mutable nên cần sao chép riêng nếu yêu cầu độc lập. `Customer.address` được khai báo `final` vẫn chia sẻ `Address` sau shallow clone như bình thường.

### Một điểm dễ nhầm: mảng cũng có `clone()`

Array trong Java hỗ trợ `clone()` và bản sao mảng mới có cùng độ dài/kiểu thành phần. Với phần tử tham chiếu, đó vẫn là sao chép nông:

```java
StringBuilder[] a = {new StringBuilder("A")};
StringBuilder[] b = a.clone();

System.out.println(a == b);       // false: hai mảng khác nhau
System.out.println(a[0] == b[0]); // true: cùng phần tử tham chiếu
```

*Đoạn trên là các câu lệnh minh họa bên trong một phương thức.* Chỉnh sửa `b[0].append("!")` cũng khiến `a[0].toString()` trả về `"A!"`. Trong khi đó, thay trực tiếp `b[0] = new StringBuilder("B")` không thay phần tử `a[0]`, vì hai mảng là hai container riêng.

## 6. Khi nào nên dùng cách nào?

| Nhu cầu | Lựa chọn hợp lý | Cảnh báo |
| --- | --- | --- |
| In trạng thái đối tượng cho người đọc hoặc debug | Ghi đè `toString()` | Không đưa dữ liệu bí mật vào chuỗi; không dùng làm định dạng lưu trữ chính thức. |
| Biết chính xác lớp runtime | `obj.getClass()` | Kiểm tra `null` trước; không nhầm với quan hệ đa hình. |
| Kiểm tra đối tượng có thuộc một hệ kiểu | `instanceof` (hoặc `Class.isInstance()` khi biết kiểu lúc chạy) | `getClass() == ...` chỉ nhận một lớp chính xác. |
| Sao chép trạng thái phẳng hoặc dữ liệu bất biến từ lớp đã hỗ trợ `clone()` đúng cách | `clone()` theo giao ước của lớp đó | Vẫn kiểm tra mức độ sao chép và khả năng gọi public. |
| Tạo đối tượng mới có chủ đích, kiểm soát bất biến và thành phần mutable | Copy constructor, factory/copy method hoặc mô hình immutable | Cần xác định rõ trường nào sao chép và trường nào được phép chia sẻ. |

Với API mới, **copy constructor hoặc factory method** thường dễ diễn đạt hơn `Cloneable/clone()`, nhất là khi đối tượng chứa tài nguyên, tham chiếu vòng, trường `final` mutable, invariant cần bảo đảm hoặc quan hệ kế thừa phức tạp. Ví dụ `new Customer(old.name, new Address(old.address.city))` làm chính sách sao chép hiển lộ; với cấu trúc sâu hơn phải tiếp tục sao chép các thành phần mutable liên quan. Không có một thuật toán sao chép sâu mặc định đúng cho mọi loại đối tượng.

## 7. Lỗi thường gặp và cách kiểm tra

**Lỗi 1: Dùng chuỗi `toString()` để so sánh đối tượng.** Hai đối tượng có thể hiển thị giống nhau nhưng khác nhau theo `equals()`; hoặc đối tượng bằng nhau có phần mô tả khác. Hãy dùng `equals()` cho bình đẳng logic được lớp định nghĩa, `==` cho đồng nhất tham chiếu và bảo đảm `hashCode()` tương thích khi ghi đè `equals()`.

**Lỗi 2: Coi phần `@...` trong `Object.toString()` là địa chỉ bộ nhớ.** Nó biểu diễn giá trị hash dạng hex, không phải địa chỉ tin cậy hoặc định danh duy nhất.

**Lỗi 3: Dùng `getClass() == Parent.class` khi muốn chấp nhận lớp con.** Phép so sánh đó loại đối tượng là subclass. Dùng `instanceof Parent` khi thật sự muốn chấp nhận quan hệ kế thừa/triển khai interface.

**Lỗi 4: Gọi `clone()` trên mọi `Object`.** `Object.clone()` là `protected`; `Cloneable` không tự cung cấp method public. Phải xem API cụ thể của lớp, quyền truy cập và điều kiện hỗ trợ.

**Lỗi 5: Tưởng `super.clone()` sao chép luôn các đối tượng lồng.** Hãy kiểm tra từng trường mutable; dùng copy method/copy constructor hoặc sao chép chọn lọc khi cần tính độc lập.

**Lỗi 6: Quên rằng constructor không chạy trong thao tác `super.clone()`.** Khi lớp có invariant, khóa, handle tệp, socket hoặc tài nguyên bên ngoài, sao chép từng trường có thể cho trạng thái nguy hiểm hoặc vô nghĩa; chọn cách tạo mới phù hợp với semantics của lớp.

## 8. Tự kiểm tra kiến thức

**Câu 1.** Biến `Object x = new String("Hi")` trả về gì từ `x.getClass() == String.class`?  
**Đáp án:** `true`, vì `getClass()` nhìn lớp runtime thực tế.

**Câu 2.** Hai đối tượng khác nhau in `toString()` giống hệt nhau có nhất thiết `equals()` nhau không?  
**Đáp án:** Không; chuỗi mô tả không phải giao ước bình đẳng.

**Câu 3.** Sau khi shallow clone một object có trường `List<String> items`, thay đổi `clone.items.add("x")` có thể ảnh hưởng bản gốc không?  
**Đáp án:** Có, nếu cả hai cùng giữ một `List` mutable do chép tham chiếu. Muốn container riêng có thể tạo `new ArrayList<>(items)`, nhưng nếu phần tử là object mutable thì đó vẫn chưa phải sao chép sâu phần tử.

**Câu 4.** Một class `implements Cloneable` nhưng không khai báo `public clone()` thì code bên ngoài có tự gọi `instance.clone()` được không?  
**Đáp án:** Không mặc nhiên; `Cloneable` không khai báo `clone()` và phương thức kế thừa từ `Object` là `protected`.

**Câu 5.** Lớp con cần được chấp nhận khi kiểm tra kiểu: nên dùng `getClass() == Base.class` hay `instanceof Base`?  
**Đáp án:** Thường dùng `instanceof Base` để nhận cả subtype. Nếu cần đúng một lớp runtime (ví dụ một chính sách equality cụ thể), mới cân nhắc `getClass() == Base.class`.

Điểm cần nhớ để vận dụng đúng: `toString()` là **biểu diễn**, `getClass()` là **thông tin kiểu runtime chính xác**, còn `clone()` là **cơ chế sao chép nông có điều kiện và giới hạn truy cập**. Thiết kế sao chép độc lập và định nghĩa bình đẳng là những quyết định riêng của lớp.