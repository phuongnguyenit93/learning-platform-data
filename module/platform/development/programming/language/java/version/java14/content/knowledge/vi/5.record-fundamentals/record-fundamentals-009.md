# Phân biệt `record` với JavaBean và lớp có danh tính riêng (Java 14 → Java hiện đại)

## 1. Bài toán: cùng chứa dữ liệu, nhưng không cùng vai trò

Ba kiểu thiết kế dưới đây đều có thể biểu diễn thông tin khách hàng, nhưng mang **ngữ nghĩa và hợp đồng sử dụng khác nhau**:

- **`record`**: biểu diễn một nhóm dữ liệu cố định, với các thành phần (*record components*) tạo nên trạng thái và cách so sánh mặc định. Thích hợp cho kết quả truy vấn, DTO, dữ liệu trao đổi hoặc ảnh chụp trạng thái tại một thời điểm.
- **JavaBean**: là **quy ước viết lớp và truy cập thuộc tính** thông qua những phương thức như `getName()`, `setName(...)`, `isActive()`. JavaBean thường có constructor không tham số để công cụ tạo đối tượng rồi gán thuộc tính; mô hình này có thể mutable, nhưng JavaBean không bắt buộc mọi thuộc tính đều phải ghi được.
- **Lớp có danh tính riêng** (thường gọi là *domain entity*): đối tượng đại diện cho **một thực thể có vòng đời và danh tính ổn định**. Các thuộc tính có thể thay đổi mà thực thể vẫn là cùng một khách hàng/tài khoản/đơn hàng. Danh tính có thể được biểu diễn bằng mã ID nghiệp vụ hay khóa định danh, tùy thiết kế hệ thống.

**Hai khái niệm JavaBean và entity không loại trừ nhau.** Một entity có thể được viết theo quy ước JavaBean. Ngược lại, một JavaBean dùng làm DTO không nhất thiết có danh tính nghiệp vụ. `record` là **một loại lớp Java đặc biệt có ngữ nghĩa dữ liệu**, còn JavaBean là **quy ước lập trình**; không nên coi chúng là ba từ đồng nghĩa.

### Liên hệ với Java 14

`record` xuất hiện dưới dạng tính năng **preview trong Java 14**, sau đó được hoàn thiện thành tính năng chuẩn từ **Java 16** và vẫn được hỗ trợ trên các bản Java hiện đại như JDK 17/21. Bài này dùng **cú pháp chuẩn**, biên dịch được với JDK 17 trở lên và không cần `--enable-preview`. Mô tả `record` là preview chỉ đúng khi nói về lịch sử Java 14, không phản ánh trạng thái hiện tại.

## 2. So sánh các đặc điểm thực tế

| Tiêu chí | `record` | JavaBean thông thường | Lớp có danh tính riêng |
| --- | --- | --- | --- |
| Mục đích | Mô hình hóa bộ dữ liệu/giá trị | Thuộc tính theo quy ước getter/setter | Mô hình hóa một thực thể tồn tại qua thời gian |
| Khai báo | `record Point(int x, int y) {}` | `class` với các thuộc tính và phương thức | `class` với định danh và hành vi nghiệp vụ |
| Truy cập dữ liệu | Accessor cùng tên thành phần: `point.x()` | Thường là `getX()`/`isX()` | Theo API thiết kế: `getId()`, `rename(...)`, ... |
| Thay đổi trạng thái | Các trường thành phần mặc định `private final`, không có setter thay thế | Setter thường cho phép cập nhật, có thể chỉ đọc | Có thể cập nhật thuộc tính trong vòng đời |
| `equals` / `hashCode` | Java sinh theo **toàn bộ các thành phần** (trừ khi tự định nghĩa) | Không tự sinh theo thuộc tính; nếu không override thì dùng hành vi `Object` | Thiết kế theo quy tắc danh tính: có thể dùng ID ổn định hoặc tham chiếu, tùy miền |
| `toString` | Được sinh từ tên lớp và thành phần | Thừa hưởng `Object.toString()` nếu không override | Tự quyết định định dạng |
| Kế thừa | `record` ngầm kế thừa `java.lang.Record`, là `final`; có thể triển khai interface | Lớp thường có thể kế thừa nếu không bị giới hạn | Theo yêu cầu miền/framework; không mặc định là `final` |
| Thích hợp | DTO, projection, dữ liệu bất biến nông | Bind thuộc tính, tích hợp công cụ dựa trên JavaBeans | Tài khoản, khách hàng, đơn hàng có vòng đời và identity |

Bảng thể hiện **hành vi mặc định**: một JavaBean hoàn toàn có thể tự cài `equals` theo giá trị; một lớp thực thể cũng có thể có getter/setter như JavaBean. Vì vậy **ngữ nghĩa equality là quyết định thiết kế**, còn cú pháp chỉ hỗ trợ thực thi quyết định đó.

## 3. `record`: mô hình dữ liệu và equality theo thành phần

Ví dụ một bản hiển thị thông tin khách hàng:

```java
record CustomerSnapshot(String id, String name) {}
```

Java tạo ra các thành phần cơ bản tương đương về hành vi công khai với:

- Constructor nhận `id` và `name` theo thứ tự đã khai báo.
- Hai accessor `id()` và `name()` (không tự sinh `getId()`, `getName()`).
- Các trường dữ liệu tương ứng là `private final`.
- `equals(Object)` và `hashCode()` dựa trên các thành phần; `toString()` mô tả tên record và từng thành phần.

Ví dụ:

```java
var a = new CustomerSnapshot("C01", "Lan");
var b = new CustomerSnapshot("C01", "Lan");
var c = new CustomerSnapshot("C01", "Mai");

System.out.println(a.equals(b));  // true
System.out.println(a == b);       // false
System.out.println(a.equals(c));  // false
System.out.println(a.name());     // Lan
```

Các đoạn này nằm trong một phương thức; `CustomerSnapshot` đã được khai báo ở ngoài. `a.equals(b)` đúng vì mọi thành phần bằng nhau. `a == b` sai vì đây là **hai đối tượng riêng trong bộ nhớ**. `a.equals(c)` sai dù hai bản cùng `id = "C01"` vì `name` khác nhau.

Vì thế **chỉ thêm thành phần `id` vào record không khiến `equals` trở thành so sánh theo ID**. Mặc định equality của record xem **mọi thành phần** là một phần của giá trị.

### Bất biến nông (*shallow immutability*)

Định nghĩa record không tự tạo **deep immutable object graph**. Nếu một thành phần trỏ đến mảng hay collection có thể sửa, nội dung bên trong vẫn có thể đổi khi giữ tham chiếu đó:

```java
record UnsafeSnapshot(String[] tags) {}

String[] values = {"new"};
var snapshot = new UnsafeSnapshot(values);
values[0] = "changed";
System.out.println(snapshot.tags()[0]); // changed
```

Record ngăn thay thế trường `tags` bằng tham chiếu mới, nhưng **không tự sao chép mảng và không đóng băng phần tử**. Ngoài ra, nếu thành phần là mảng, cách sinh `equals` mặc định xét equality của thành phần mảng theo `equals` của mảng (so sánh tham chiếu), không tự so sánh sâu nội dung mảng.

Nếu cần dữ liệu cố định ở biên hệ thống, có thể phòng vệ bằng collection không sửa được:

```java
import java.util.List;

record Tags(List<String> items) {
    Tags {
        items = List.copyOf(items);
    }
}
```

Đây là đoạn khai báo record độc lập đặt ở mức lớp. Trong **compact constructor**, gán lại tham số `items` cho danh sách sao chép; Java dùng giá trị tham số sau khi khối constructor kết thúc để khởi tạo trường thành phần. `List.copyOf` trả danh sách không sửa được và không chấp nhận phần tử `null`, nhưng vẫn chỉ sao chép **nông**: nếu phần tử là một đối tượng mutable, phần tử đó có thể đổi. Với `String` bất biến như ví dụ, cách này phù hợp.

## 4. JavaBean: hợp đồng truy cập thuộc tính

Một JavaBean quen thuộc thường có các trường riêng tư, constructor không tham số và phương thức truy cập theo quy ước:

```java
public class CustomerBean {
    private String id;
    private String name;

    public CustomerBean() {
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }
}
```

Đây là **lớp `CustomerBean` hoàn chỉnh** nếu đặt trong `CustomerBean.java`. Có thể khởi tạo rỗng, sau đó điền thuộc tính:

```java
CustomerBean bean = new CustomerBean();
bean.setId("C01");
bean.setName("Lan");
System.out.println(bean.getName()); // Lan
bean.setName("Mai");
System.out.println(bean.getName()); // Mai
```

Đoạn sử dụng nằm trong phương thức Java. Cách này có ích khi công cụ đọc tên property và gán giá trị dựa trên getter/setter. Tuy nhiên **JavaBean không tự sinh `equals`/`hashCode` theo thuộc tính**:

```java
var first = new CustomerBean();
first.setId("C01");
first.setName("Lan");

var second = new CustomerBean();
second.setId("C01");
second.setName("Lan");

System.out.println(first.equals(second)); // false nếu không override equals
```

Hai đối tượng có cùng nội dung vẫn không bằng nhau theo `Object.equals` mặc định (so sánh tham chiếu). Muốn so sánh theo giá trị trong JavaBean, phải tự xác định và cài đặt quy tắc `equals`/`hashCode` thích hợp.

**JavaBean không đồng nghĩa bắt buộc mutable:** có thể có property chỉ đọc (getter mà không có setter). Constructor không tham số và setter thường gặp ở các công cụ binding nhưng mức hỗ trợ phụ thuộc framework. `record` không theo quy ước getter JavaBean truyền thống vì accessor là `name()`, mặc dù một số framework hiện đại đã hỗ trợ record trực tiếp.

## 5. Lớp có danh tính riêng: phân biệt thay đổi trạng thái và cùng thực thể

Xét khách hàng có **ID không thay đổi**, nhưng tên hiển thị có thể đổi. Với một lớp domain entity, ta có thể quyết định: hai đối tượng cùng mã ID là hai biểu diễn của **cùng thực thể nghiệp vụ**, dù các thuộc tính khác khác nhau.

```java
import java.util.Objects;

public final class CustomerEntity {
    private final String id;
    private String name;

    public CustomerEntity(String id, String name) {
        this.id = Objects.requireNonNull(id, "id");
        this.name = Objects.requireNonNull(name, "name");
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public void rename(String newName) {
        this.name = Objects.requireNonNull(newName, "newName");
    }

    @Override
    public boolean equals(Object obj) {
        if (this == obj) {
            return true;
        }
        return obj instanceof CustomerEntity other
                && id.equals(other.id);
    }

    @Override
    public int hashCode() {
        return id.hashCode();
    }
}
```

Đây là **lớp Java độc lập**, lưu trong `CustomerEntity.java`. Có thể sử dụng:

```java
var first = new CustomerEntity("C01", "Lan");
var second = new CustomerEntity("C01", "Mai");

System.out.println(first == second);      // false
System.out.println(first.equals(second)); // true
first.rename("Hương");
System.out.println(first.equals(second)); // true
```

Ở đây:

- **Object identity**: `first == second` sai, vì chúng là hai tham chiếu đến hai đối tượng khác nhau.
- **Domain identity**: `first.equals(second)` đúng vì triển khai `equals` dựa trên ID nghiệp vụ `"C01"`.
- **State/attributes**: `name` là thuộc tính thay đổi được; đổi `"Lan"` thành `"Hương"` không thay đổi danh tính nghiệp vụ.

**Không phải mọi entity đều phải override `equals` theo ID.** Đây là chính sách thường hữu ích khi một ID ổn định được cấp ngay khi tạo đối tượng và thực sự đại diện cho danh tính. Có miền chọn identity theo tham chiếu, hoặc phải xử lý ID chưa gán cho entity mới. Nếu khóa định danh có thể `null` hoặc thay đổi sau khi đối tượng đi vào `HashSet`/`HashMap`, `equals`/`hashCode` có thể gây lỗi khó phát hiện. Cần chọn một chính sách nhất quán theo vòng đời và hệ thống lưu trữ thực tế.

**Lưu ý về JPA:** `CustomerEntity` ở ví dụ là một lớp domain thuần Java, **không phải thực thể JPA**. Ví dụ cố ý là `final` để minh họa ID bất biến trong lớp thường. Nếu triển khai entity theo Jakarta Persistence/JPA, phải tuân thủ các yêu cầu riêng (ví dụ lớp entity không được `final` và có constructor không tham số với khả năng truy cập phù hợp). `record` tự thân là `final` và không đáp ứng đầy đủ mô hình entity JPA truyền thống; record thường phù hợp hơn với **DTO hoặc projection** nếu công cụ hỗ trợ. Không đánh đồng mọi lớp domain entity với `@Entity`.

## 6. Chương trình hoàn chỉnh Java 17+: quan sát ba kiểu cùng lúc

Lưu toàn bộ mã dưới đây vào **`Main.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class Main {
    record CustomerSnapshot(String id, String name) {
        CustomerSnapshot {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(name, "name");
        }
    }

    public static class CustomerBean {
        private String id;
        private String name;

        public CustomerBean() {
        }

        public String getId() {
            return id;
        }

        public void setId(String id) {
            this.id = id;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }
    }

    public static final class CustomerEntity {
        private final String id;
        private String name;

        public CustomerEntity(String id, String name) {
            this.id = Objects.requireNonNull(id, "id");
            this.name = Objects.requireNonNull(name, "name");
        }

        public String getId() {
            return id;
        }

        public String getName() {
            return name;
        }

        public void rename(String name) {
            this.name = Objects.requireNonNull(name, "name");
        }

        @Override
        public boolean equals(Object other) {
            return this == other
                    || (other instanceof CustomerEntity that
                        && id.equals(that.id));
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    record Tags(List<String> items) {
        Tags {
            items = List.copyOf(items);
        }
    }

    public static void main(String[] args) {
        var viewA = new CustomerSnapshot("C01", "Lan");
        var viewB = new CustomerSnapshot("C01", "Lan");
        var viewC = new CustomerSnapshot("C01", "Mai");

        System.out.println("record equals: " + viewA.equals(viewB));
        System.out.println("record ==: " + (viewA == viewB));
        System.out.println("record changed field: " + viewA.equals(viewC));
        System.out.println("record accessor: " + viewA.name());

        var beanA = new CustomerBean();
        beanA.setId("C01");
        beanA.setName("Lan");

        var beanB = new CustomerBean();
        beanB.setId("C01");
        beanB.setName("Lan");

        System.out.println("bean equals: " + beanA.equals(beanB));
        beanA.setName("Bình");
        System.out.println("bean getter: " + beanA.getName());

        var entityA = new CustomerEntity("C01", "Lan");
        var entityB = new CustomerEntity("C01", "Mai");

        System.out.println("entity same ID: " + entityA.equals(entityB));
        entityA.rename("Hương");
        System.out.println("entity after rename: " + entityA.equals(entityB));
        System.out.println("entity getter: " + entityA.getName());

        var editableTags = new ArrayList<>(List.of("new"));
        var tags = new Tags(editableTags);
        editableTags.add("changed");
        System.out.println("defensive copy: " + tags.items());
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 Main.java
java Main
```

**Kết quả chuẩn:**

```text
record equals: true
record ==: false
record changed field: false
record accessor: Lan
bean equals: false
bean getter: Bình
entity same ID: true
entity after rename: true
entity getter: Hương
defensive copy: [new]
```

**Vì sao ra kết quả này?**

1. Hai `CustomerSnapshot` đầu có các thành phần bằng nhau nên `record equals: true`, nhưng vẫn là hai đối tượng độc lập nên `record ==: false`. `viewC` khác trường `name` nên equality theo record là `false`.
2. `CustomerBean` cung cấp getter/setter, nhưng không override `equals`: hai instance khác nhau vẫn không bằng nhau, dù các thuộc tính ban đầu giống nhau. Setter cho phép `beanA` đổi tên.
3. `CustomerEntity` tự định nghĩa equality theo `id`: tên ban đầu khác nhau và sau đó được đổi tiếp, kết quả vẫn là `true` nếu ID giữ nguyên.
4. `Tags` tạo bản sao `List.copyOf` trong compact constructor. Khi danh sách nguồn thêm `"changed"`, danh sách được record giữ vẫn là `[new]`.

Mã sử dụng những tính năng Java ổn định (record chuẩn, `instanceof` pattern, `List.copyOf`) và không yêu cầu bật preview.

## 7. Ba câu hỏi để chọn mô hình phù hợp

**Câu hỏi 1: Hai dữ liệu có cùng mọi thành phần có được coi là tương đương không?**

Nếu **có**, và đối tượng nhằm vận chuyển/hiển thị dữ liệu, `record` thường là lựa chọn rõ ràng:

```java
record PriceQuote(String currency, long amountInMinorUnits) {}
```

`new PriceQuote("VND", 1000)` tương đương về giá trị với một instance khác có hai thành phần giống hệt. Nó là một **bản kết quả/báo giá**, không nhất thiết đại diện cho một thực thể với vòng đời và identity duy nhất.

**Câu hỏi 2: Công cụ cần tạo object rỗng và gán property bằng setter hay tuân theo API JavaBeans?**

Nếu **có**, lớp với getter/setter và constructor thích hợp có thể là lựa chọn tương thích. Cần kiểm tra framework cụ thể vì nhiều công cụ hiện đại đã hỗ trợ constructor binding/record, nhưng cũng có công cụ vẫn dựa trên JavaBeans. Sử dụng JavaBean theo yêu cầu tích hợp hiện tại, không coi nó là mặc định cho mọi DTO.

**Câu hỏi 3: Đối tượng có một danh tính tồn tại qua nhiều lần thay đổi dữ liệu không?**

Nếu **có**, dùng lớp domain biểu diễn ID và hành vi nghiệp vụ. Ví dụ một đơn hàng vẫn là **đơn hàng `ORD-01`** sau khi chuyển trạng thái từ `NEW` sang `SHIPPED`; hai bản ghi mô tả các trạng thái khác nhau có thể thuộc **cùng entity**. Nếu đóng gói trạng thái đơn hàng thành `record OrderView(String id, String status)`, hai view cùng ID nhưng khác status sẽ **không bằng nhau theo equality mặc định của record**.

## 8. Các lỗi hiểu sai thường gặp

| Ngộ nhận | Sửa lại cho đúng |
| --- | --- |
| "`record` là JavaBean viết ngắn hơn" | Record có accessor `componentName()` và equality theo thành phần; không tự có constructor rỗng hay setter JavaBean. |
| "`record` luôn bất biến hoàn toàn" | Trường thành phần final nhưng đối tượng tham chiếu bên trong có thể mutable; cần defensive copy và đánh giá từng loại phần tử. |
| "`record` không có object identity" | Record vẫn là đối tượng tham chiếu thông thường; `==` có thể khác `equals`. |
| "Có trường ID thì record chỉ so sánh ID" | Equality mặc định của record dựa trên **tất cả components**, kể cả trường tên/trạng thái nếu khai báo. |
| "JavaBean tự so sánh nội dung getter" | JavaBean convention không tự sinh equals/hashCode theo thuộc tính. |
| "Cùng ID thì mọi đối tượng Java đều bằng nhau" | Chỉ đúng nếu quy tắc equality đã được cài/định nghĩa như vậy; `==` vẫn kiểm tra cùng một tham chiếu. |
| "Mọi lớp có identity đều là JPA entity" | Domain entity là khái niệm mô hình; `@Entity` là cấu hình persistence có quy tắc riêng. |
| "Dùng record làm JPA entity thay lớp thường" | Record là final và không có constructor rỗng theo mô hình JPA entity thông thường; thường dùng cho DTO/projection phù hợp hơn. |
| "Đổi tên trong entity phải đổi ID" | Đổi thuộc tính không nhất thiết đổi danh tính; ID nên ổn định theo vòng đời nếu dùng ID làm khóa equality. |

### Không nhầm record với một thực thể "chỉ đọc"

Một thực thể nghiệp vụ có thể **không cung cấp setter công khai** nhưng vẫn có identity và vòng đời; ví dụ chuyển trạng thái qua phương thức `approve()` bảo đảm quy tắc nghiệp vụ. Ngược lại, một record có thể chứa component là đối tượng mutable. Vì vậy tiêu chí quan trọng là **ngữ nghĩa giá trị hay danh tính**, không chỉ đếm setter.

### Không nhầm generated `toString()` với định dạng trao đổi an toàn

Record tự sinh `toString()` rất tiện để quan sát dữ liệu, nhưng không phải hợp đồng JSON, không đảm bảo bảo mật thông tin nhạy cảm, và không thay thế serializer. Với các component chứa bí mật/token, cần thiết kế cách log an toàn, bất kể chọn record hay class.

### Duy trì hợp đồng `equals` / `hashCode`

Một khi dùng đối tượng làm khóa của `HashMap` hoặc phần tử của `HashSet`, equality và hash code phải nhất quán. Record sinh hai phương thức dựa theo component, nhưng component có thể mutable và khiến hash thay đổi gián tiếp; entity dùng khóa ID thì phải có chiến lược ID ổn định. Nếu tự override, phải đảm bảo hai đối tượng `equals` thì `hashCode` bằng nhau.

## 9. Bài tập tự kiểm tra

Cho các khai báo đặt cùng một nơi hợp lệ trong Java:

```java
record OrderView(String id, String status) {}

var v1 = new OrderView("ORD-01", "NEW");
var v2 = new OrderView("ORD-01", "SHIPPED");

System.out.println(v1.equals(v2));
```

**Kết quả:** `false`. Dù chung mã `ORD-01`, hai record khác `status`. Đây là hai **giá trị mô tả hai trạng thái**, có thể cùng thuộc một entity đơn hàng.

Nếu một bean có `getStatus()`/`setStatus(...)`, việc gọi `setStatus("SHIPPED")` là thay đổi property trên **chính instance đó**, nhưng getter/setter không quyết định sẵn quy tắc equality. Nếu một class đơn hàng có identity `ORD-01`, domain có thể vẫn coi đó là cùng một đơn hàng khi `status` thay đổi; lớp domain phải thể hiện quy tắc identity và các chuyển trạng thái hợp lệ.

**Ghi nhớ:** Chọn `record` cho **giá trị/bản chụp dữ liệu**, JavaBean khi cần **quy ước truy cập thuộc tính** hoặc tích hợp framework, và lớp có danh tính riêng cho **thực thể có vòng đời, ID và hành vi nghiệp vụ**. Ba lựa chọn không phải ba nhãn thay thế nhau; cần quyết định dựa trên equality, mutability, identity và hợp đồng với hệ thống sử dụng.

### Tài liệu chính thức

- [JEP 395 — Records (tính năng chính thức từ Java 16)](https://openjdk.org/jeps/395).
- [JEP 359 — Records (preview trong Java 14)](https://openjdk.org/jeps/359).
- [Java Language Specification — Record Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10).
