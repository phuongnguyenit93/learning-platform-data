# Quy ước JavaBeans và sự khác biệt với thiết kế theo hành vi trong Java

Trong Java Core, **đóng gói (encapsulation)** là kiểm soát cách đối tượng được tạo, quan sát và thay đổi trạng thái. Một quy ước rất quen thuộc để công bố dữ liệu là **JavaBeans**: các thuộc tính (*properties*) được biểu diễn qua những phương thức như `getName()`, `setName(...)` hoặc `isActive()`. Quy ước này giúp công cụ, thư viện và framework phát hiện thuộc tính theo tên và sử dụng đối tượng theo cách thống nhất.

Tuy nhiên, **một lớp có đủ getter/setter chưa chắc được đóng gói tốt**. Nếu nghiệp vụ chỉ cho phép “nạp tiền”, “rút tiền” hoặc “đặt lại cả khoảng thời gian”, một setter tổng quát như `setBalance(...)` hoặc hai setter độc lập `setStart(...)`, `setEnd(...)` có thể làm lộ những thay đổi không được phép hoặc gây trạng thái trung gian sai. Thiết kế theo hành vi (*behavior-oriented design*) ưu tiên phương thức diễn đạt **hành động hợp lệ** và tự duy trì các bất biến (*invariants*) của đối tượng.

Bài học giải thích đúng quy ước JavaBeans, cách công cụ introspection tìm property, vai trò của constructor không tham số, cách dùng setter có validation, ưu/nhược điểm của mô hình dữ liệu và thiết kế theo hành vi, mẫu kết hợp hai cách, cùng các chương trình **Java 17+** độc lập có kết quả kiểm chứng được.

## 1. Hai cách nhìn một đối tượng

Giả sử đang mô hình hóa tài khoản với số dư. Hai API dưới đây thể hiện hai cách nhìn khác nhau:

~~~java
// API thiên về dữ liệu: cho bên gọi đặt trực tiếp giá trị.
account.setBalanceCents(900);

// API thiên về hành vi: thể hiện hành động hợp lệ.
account.withdraw(100);
~~~

Đây là các **lời gọi minh họa**, chưa có định nghĩa `account` ở đoạn này. Phương thức `setBalanceCents` trả lời câu hỏi “đặt trường này thành giá trị nào?”. Phương thức `withdraw` trả lời câu hỏi “được phép thực hiện nghiệp vụ nào trên tài khoản này?”.

Trong trường hợp đầu, caller phải tự biết số dư mới hợp lệ, việc giảm tiền có cần kiểm tra đủ tiền hay không, có cần ghi nhận một sự kiện giao dịch hay không. Trong trường hợp sau, lớp có cơ hội giữ những quy tắc này ở một nơi thống nhất.

**Không có kết luận rằng JavaBeans là sai.** JavaBeans hữu ích khi trao đổi dữ liệu, tích hợp với công cụ, cấu hình, biểu mẫu hoặc mô hình thuộc tính đơn giản. Thiết kế theo hành vi hữu ích khi đối tượng có vòng đời, invariant, quy tắc chuyển trạng thái hoặc nghiệp vụ cần được bảo vệ.

## 2. JavaBeans là gì và không phải là gì?

**JavaBeans** là một tập hợp quy ước/đặc tả cho các thành phần Java có thể tái sử dụng và được công cụ phân tích. Một phần nổi bật là **mẫu tên phương thức truy cập thuộc tính**, được hệ thống introspection tiêu chuẩn trong gói `java.beans` nhận diện.

Các quy ước thông dụng:

- Thuộc tính `name` thường có `public String getName()` và `public void setName(String name)`.
- Thuộc tính kiểu `boolean` có thể có `public boolean isActive()`; `getActive()` cũng là dạng getter thông thường được nhận diện tùy chữ ký.
- Setter JavaBeans điển hình có tên `setX`, nhận **một giá trị**, trả `void`.
- Một bean phục vụ nhiều công cụ tạo instance thường có **public constructor không tham số**, sau đó công cụ thiết lập property. Đây là quy ước tương thích quan trọng, nhưng **không phải mọi lớp Java có getter đều phải có no-arg constructor**.
- Đối tượng có thể hỗ trợ sự kiện thay đổi property, thông tin `BeanInfo`, đặc tính bound/constrained hoặc serialization khi có nhu cầu; **không phải mọi bean đều bắt buộc cài đặt tất cả**.

Một Java class chỉ có các field `private` và phương thức công khai **không tự động trở thành một JavaBean đầy đủ theo mọi quy ước công cụ mong đợi**. Ngược lại, một domain entity hợp lệ có thể không muốn phơi ra mọi property theo kiểu setter.

Đừng đánh đồng:

| Thuật ngữ | Ý nghĩa chính |
| --- | --- |
| Java class | Khai báo kiểu và hành vi trong ngôn ngữ Java |
| POJO (*Plain Old Java Object*) | Object Java thông thường, không hàm ý nhất thiết tuân JavaBeans |
| JavaBean | Thành phần tuân những quy ước bean phù hợp, nhất là property/introspection |
| DTO (*Data Transfer Object*) | Kiểu dữ liệu dùng chuyển thông tin qua một ranh giới |
| Domain entity | Đối tượng mô hình hóa thực thể nghiệp vụ, thường có identity/invariant |
| Value object | Đối tượng biểu diễn một giá trị, thường thích hợp với bất biến và so sánh theo giá trị |

**JavaBean, DTO, entity, value object là những khái niệm theo các chiều khác nhau.** Một DTO có thể được viết theo JavaBeans; một entity cũng có thể có JavaBeans accessors; một `record` bất biến có thể làm DTO nhưng không theo mẫu setter JavaBeans cổ điển.

## 3. Quy tắc đặt tên property cơ bản

Bảng dưới giả định các phương thức là **public**, có chữ ký hợp lệ và được một introspector tuân quy ước JavaBeans kiểm tra:

| Phương thức | Thuộc tính được nhận diện | Vai trò |
| --- | --- | --- |
| `String getName()` | `name` | Getter |
| `void setName(String value)` | `name` | Setter |
| `int getStock()` | `stock` | Getter |
| `boolean isActive()` | `active` | Getter boolean |
| `void setActive(boolean value)` | `active` | Setter |
| `long getBalanceCents()` | `balanceCents` | Getter |
| `void receive(int amount)` | Không tự là property `amount` | Phương thức hành vi |
| `String name()` | Không phải getter JavaBeans cổ điển | Accessor theo phong cách khác |

Tên field **không bắt buộc trùng** với tên property:

~~~java
private String internalTitle;

public String getName() {
    return internalTitle;
}

public void setName(String value) {
    internalTitle = value;
}
~~~

Đây là đoạn minh họa đặt trong một lớp. Property công bố cho introspector là `name`, dù tên field là `internalTitle`. Một property còn có thể **được tính toán** mà không cần field tương ứng, ví dụ `getFullName()` nối `firstName` và `lastName`.

**Property là hợp đồng thông qua phương thức**, không phải quyền trực tiếp truy cập field. Điều đó cho phép validate hoặc tính giá trị khi getter/setter được gọi.

## 4. Một JavaBean có getter, setter và hành vi bổ sung

Tạo tệp độc lập **`JavaBeanIntrospectionDemo.java`**. Chương trình dùng API `Introspector` và `PropertyDescriptor` của Java để hiển thị đúng những property công cụ tiêu chuẩn phát hiện.

~~~java
import java.beans.BeanInfo;
import java.beans.Introspector;
import java.beans.PropertyDescriptor;
import java.util.Map;
import java.util.TreeMap;

public class JavaBeanIntrospectionDemo {
    public static class ProductBean {
        private String name;
        private boolean active;
        private int stock;

        public ProductBean() {
            this.name = "Chưa đặt";
            this.active = true;
            this.stock = 0;
        }

        public String getName() {
            return name;
        }

        public void setName(String name) {
            if (name == null || name.isBlank()) {
                throw new IllegalArgumentException("name không hợp lệ");
            }
            this.name = name.strip();
        }

        public boolean isActive() {
            return active;
        }

        public void setActive(boolean active) {
            this.active = active;
        }

        public int getStock() {
            return stock;
        }

        public void receive(int amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("amount phải dương");
            }
            stock = Math.addExact(stock, amount);
        }
    }

    public static void main(String[] args) throws Exception {
        ProductBean bean = new ProductBean();
        bean.setName("  Bút  ");
        bean.receive(5);

        System.out.println("value=" + bean.getName()
                + ", active=" + bean.isActive()
                + ", stock=" + bean.getStock());

        BeanInfo info = Introspector.getBeanInfo(
                ProductBean.class, Object.class);
        Map<String, String> properties = new TreeMap<>();

        for (PropertyDescriptor descriptor
                : info.getPropertyDescriptors()) {
            String getter = descriptor.getReadMethod() == null
                    ? "-" : descriptor.getReadMethod().getName();
            String setter = descriptor.getWriteMethod() == null
                    ? "-" : descriptor.getWriteMethod().getName();
            properties.put(descriptor.getName(),
                    getter + "/" + setter);
        }

        properties.forEach((name, methods) ->
                System.out.println(name + "=" + methods));
    }
}
~~~

Biên dịch và chạy bằng Java 17+:

~~~bash
javac -encoding UTF-8 JavaBeanIntrospectionDemo.java
java JavaBeanIntrospectionDemo
~~~

**Stdout chính xác:**

~~~text
value=Bút, active=true, stock=5
active=isActive/setActive
name=getName/setName
stock=getStock/-
~~~

### Phân tích kết quả introspection

- `ProductBean` có constructor `public ProductBean()` không tham số, tạo trạng thái ban đầu hợp lệ.
- `name` có cặp `getName/setName`: property **đọc/ghi**.
- `active` có `isActive/setActive`: property boolean **đọc/ghi**.
- `stock` chỉ có `getStock`: property **chỉ đọc qua mẫu JavaBeans**.
- `receive(int)` là hành vi nhập hàng; nó **không** được báo cáo như một property.
- `Introspector.getBeanInfo(ProductBean.class, Object.class)` loại phần method của `Object`, giúp không xuất hiện property `class` từ `getClass()`.
- `TreeMap` sắp xếp tên property theo thứ tự chữ, nên ba dòng cuối có thứ tự cố định: `active`, `name`, `stock`.

Điều quan trọng: lớp vừa có property kiểu JavaBeans để công cụ khám phá, vừa có **phương thức hành vi `receive`**. Hai phong cách có thể **kết hợp** thay vì loại trừ nhau. Việc không có `setStock` là quyết định đóng gói có chủ đích.

## 5. Getter và setter không nhất thiết tương ứng một field

Một property có thể có getter tổng hợp:

~~~java
public String getFullName() {
    return firstName + " " + lastName;
}
~~~

Đây là **phương thức minh họa**, giả định lớp có `firstName` và `lastName`. Một introspector có thể nhận ra property `fullName` chỉ đọc, dù không tồn tại `private String fullName`.

Tương tự, setter có thể áp dụng validation hoặc chuẩn hóa trước khi gán:

~~~java
public void setName(String name) {
    if (name == null || name.isBlank()) {
        throw new IllegalArgumentException("name không hợp lệ");
    }
    this.name = name.strip();
}
~~~

Không có quy tắc JavaBeans nào buộc setter chỉ chứa **một phép gán field trần**. Nhưng công cụ gọi setter có thể gặp exception, nên hợp đồng validation và cách framework xử lý exception vẫn phải được cân nhắc.

Phân biệt bốn loại property:

| Loại | Bộ phương thức | Nhận xét |
| --- | --- | --- |
| Đọc/ghi | `getX()` + `setX(T)` | Thường gặp trong form/config/DTO |
| Chỉ đọc | Chỉ `getX()` hoặc `isX()` | Không công bố setter tương ứng |
| Chỉ ghi | Chỉ `setX(T)` | Hữu ích hạn chế; công cụ không đọc lại giá trị trực tiếp |
| Tính toán | Getter dựng kết quả từ các field khác | Không bắt buộc field cùng tên |

Để giữ invariant, đôi khi không nên mở setter cho property dù công cụ có thể hiển thị nó. “Công cụ nhận diện property” và “caller được phép thay đổi trạng thái” là hai câu hỏi khác nhau.

## 6. Những chi tiết dễ nhầm trong tên JavaBeans

**Với boolean:** kiểu primitive `boolean` thường dùng `isActive()`. Getter `getActive()` cũng mang mẫu `getX`. Với `Boolean` wrapper, đừng mặc nhiên cho rằng mọi introspector sẽ coi `Boolean isActive()` là getter `is` chuẩn: quy tắc JavaBeans truyền thống cho `isX` đòi kiểu trả về primitive `boolean`. Nếu muốn khả năng tương thích rộng cho wrapper có thể null, `getActive()` rõ hơn.

**Với viết hoa:** tên property không chỉ là “lấy ký tự sau get rồi chuyển chữ đầu sang thường” trong mọi trường hợp. `Introspector.decapitalize` giữ nguyên một tên bắt đầu bằng **hai chữ hoa**. Vì vậy `getURL()` thường là property `URL`, còn `getName()` là `name`.

**Với setter có return type khác void:** các API fluent như `Builder setName(String)` hoặc `withName(String)` có thể hữu ích trong code, nhưng không được mọi JavaBeans introspector cổ điển xem là setter tiêu chuẩn. Nếu một công cụ cụ thể nhận diện fluent accessor, đó là **quy ước của công cụ**, không nên nhầm với mọi công cụ JavaBeans.

**Với getter có tham số:** `getName(Locale locale)` không phải getter property đơn giản theo mẫu `getName()`. Một property thông thường phải có read method không tham số.

**Với overloaded setters:** nhiều `setValue(...)` nhận các kiểu không thống nhất có thể khiến công cụ introspection không xác định đúng kiểu property. Hãy tránh tập overload mơ hồ, nhất là với JavaBeans dùng để binding tự động.

Ví dụ kiểm chứng phần quy tắc đặt tên:

~~~java
System.out.println(
        java.beans.Introspector.decapitalize("Name")); // name
System.out.println(
        java.beans.Introspector.decapitalize("URL"));  // URL
~~~

Đây là đoạn minh họa đặt trong một phương thức. Một codebase có nhiều công cụ binding nên chọn **một quy ước đặt tên ổn định**, và thử trực tiếp với thư viện tiêu thụ bean thay vì suy từ tên field.

## 7. Constructor không tham số: tiện cho công cụ nhưng có đánh đổi

Nhiều công cụ JavaBeans truyền thống kỳ vọng có thể tạo đối tượng bằng constructor không tham số rồi lần lượt gọi các setter:

~~~java
ProductBean product = new ProductBean();
product.setName("Bút");
product.setActive(true);
~~~

Trong `ProductBean`, constructor tạo trạng thái mặc định **hợp lệ**. Nhưng không phải object nghiệp vụ nào cũng có một trạng thái mặc định có ý nghĩa. Với `BankAccount`, nếu mã tài khoản và số dư ban đầu là dữ liệu bắt buộc, cho phép `new BankAccount()` rồi để `accountId == null` có thể làm hỏng invariant ngay từ lúc tạo.

Hai lựa chọn cần cân nhắc:

1. **JavaBean phục vụ dữ liệu nhập/chuyển đổi:** trạng thái chưa hoàn tất có thể được biểu diễn có chủ đích trong một DTO, rồi xác thực toàn bộ trước khi chuyển thành domain object.
2. **Domain object luôn hợp lệ:** constructor hoặc factory yêu cầu các giá trị bắt buộc ngay từ đầu; không cần tạo no-arg constructor chỉ vì một quy ước tiện lợi nếu nghiệp vụ không cho phép.

Một số framework hiện đại có hỗ trợ constructor binding, factory, records hoặc cách khởi tạo riêng. **Khả năng thực tế tùy framework và cấu hình**, không thể kết luận mọi thư viện đều bắt buộc no-arg constructor hoặc mọi thư viện đều hỗ trợ record.

**Nguyên tắc:** chọn cấu trúc object theo vai trò; nếu cần loại JavaBean mutable để giao tiếp với công cụ, hãy xem nó như mô hình dữ liệu riêng thay vì làm suy yếu invariant của domain object.

## 8. Thiết kế theo hành vi: phương thức biểu đạt một hành động

Đối tượng có nghiệp vụ thường nên cung cấp các thao tác như:

~~~java
account.deposit(250);
account.withdraw(100);
cart.addProduct(product, 2);
reservation.cancel();
~~~

Đây là các lời gọi **minh họa**, không phải chương trình độc lập. Chúng cho người đọc biết **mục đích** của thao tác thay vì cách ghi một field.

Một phương thức hành vi thường chịu trách nhiệm:

- Kiểm tra **tiền điều kiện** của yêu cầu và trạng thái hiện tại.
- Tính trạng thái kết quả có xét invariant, overflow và giới hạn nghiệp vụ.
- Chỉ cập nhật field khi thao tác được phép.
- Nếu cần, tạo một kết quả hoặc sự kiện có ý nghĩa mà caller có thể xử lý.
- Từ chối một lệnh sai bằng cơ chế lỗi được công bố, thay vì âm thầm lưu dữ liệu không hợp lệ.

Thiết kế này đặt quy tắc **gần nơi sở hữu dữ liệu**. Caller không cần tự tính số dư mới rồi gọi setter tổng quát. Từ khóa `private` bảo vệ đường truy cập trực tiếp; **phương thức hành vi** bảo vệ đường thay đổi hợp lệ.

## 9. Ví dụ hoàn chỉnh: tài khoản đóng gói hành vi thay vì công bố setter số dư

Tạo tệp **`AccountBehaviorDemo.java`**:

~~~java
final class LedgerAccount {
    private final String id;
    private long balanceCents;

    LedgerAccount(String id, long initialBalanceCents) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id không hợp lệ");
        }
        if (initialBalanceCents < 0) {
            throw new IllegalArgumentException("số dư âm");
        }
        this.id = id;
        this.balanceCents = initialBalanceCents;
    }

    public String getId() {
        return id;
    }

    public long getBalanceCents() {
        return balanceCents;
    }

    public void deposit(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("số tiền phải dương");
        }
        long next = Math.addExact(balanceCents, amount);
        balanceCents = next;
    }

    public void withdraw(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("số tiền phải dương");
        }
        if (amount > balanceCents) {
            throw new IllegalArgumentException("không đủ số dư");
        }
        balanceCents -= amount;
    }
}

public class AccountBehaviorDemo {
    public static void main(String[] args) {
        LedgerAccount account = new LedgerAccount("A-01", 1000);
        System.out.println("start=" + account.getBalanceCents());

        account.deposit(250);
        System.out.println("after deposit=" + account.getBalanceCents());

        try {
            account.withdraw(2000);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject=" + ex.getMessage());
        }
        System.out.println("after reject=" + account.getBalanceCents());

        account.withdraw(500);
        System.out.println("after withdraw=" + account.getBalanceCents());

        try {
            account.deposit(Long.MAX_VALUE);
        } catch (ArithmeticException ex) {
            System.out.println("reject overflow");
        }
        System.out.println("final=" + account.getBalanceCents());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 AccountBehaviorDemo.java
java AccountBehaviorDemo
~~~

**Stdout chính xác:**

~~~text
start=1000
after deposit=1250
reject=không đủ số dư
after reject=1250
after withdraw=750
reject overflow
final=750
~~~

### Vì sao API này không có `setBalanceCents`?

Nếu cho caller `account.setBalanceCents(-50)`, người viết lớp phải bảo vệ điều kiện không âm. Nhưng kể cả setter có kiểm tra không âm, caller vẫn có thể bỏ qua ý nghĩa nghiệp vụ: ví dụ đặt từ 1000 sang 500 mà không có một thao tác “rút 500” rõ ràng.

Ở ví dụ:

- `deposit(amount)` kiểm tra số nạp dương, dùng `Math.addExact` để phát hiện overflow **trước khi gán field**.
- `withdraw(amount)` kiểm tra yêu cầu hợp lệ và đủ tiền, rồi mới giảm số dư.
- `getBalanceCents()` là **getter đọc trạng thái**, không tạo quyền cập nhật số dư.
- `id` là `final`, được cung cấp khi tạo và không có setter đổi mã tài khoản.
- Khi `withdraw(2000)` hoặc `deposit(Long.MAX_VALUE)` thất bại, giá trị cũ vẫn giữ nguyên theo logic cụ thể của chương trình.

Trong mô hình này, getters kiểu JavaBeans vẫn hữu ích cho **đọc**, nhưng thao tác ghi là hành vi có tên và hợp đồng riêng. Đây là ví dụ đào tạo về domain object trong bộ nhớ, **không phải hệ thống ngân hàng giao dịch đồng thời hoặc bền vững**.

## 10. Setter dù có validation vẫn có thể quá rộng

Xét một setter:

~~~java
public void setBalanceCents(long amount) {
    if (amount < 0) {
        throw new IllegalArgumentException("balance âm");
    }
    balanceCents = amount;
}
~~~

Đây là phương thức minh họa trong lớp có field `balanceCents`. Setter này giúp ngăn số âm, nhưng không bảo đảm những ràng buộc nghiệp vụ khác như:

- Việc giảm tiền có được phép diễn ra nếu chưa xác thực một lệnh rút?
- Đặt số dư mới có cần ghi nhận nguồn thay đổi hay không?
- Có giới hạn số tiền mỗi giao dịch hoặc trạng thái tài khoản bị khóa?
- Có cần bảo đảm thay đổi này gắn với một giao dịch lưu trữ?

Khi nghiệp vụ yêu cầu những hành vi có nghĩa, chỉ kiểm tra miền của **giá trị kết quả** có thể chưa đủ. Nên biểu đạt `deposit`/`withdraw` (và các hành vi cần thiết khác) để mỗi thao tác có precondition/postcondition rõ.

Ngược lại, với DTO cho biểu mẫu, `setBalanceCents` đôi khi chỉ nhằm nhận dữ liệu thô để hiển thị hoặc xử lý ở bước sau. **Vai trò của class** quyết định setter có phù hợp không, không phải tên setter tự nó tốt hay xấu.

## 11. Invariant liên trường: hai setter độc lập gây vấn đề về thứ tự

Giả sử một khoảng số nguyên phải thỏa `0 <= start <= end`. Hai setter độc lập có thể hợp lệ **riêng từng bước** nhưng buộc caller phải nhớ **đúng thứ tự cập nhật**, thậm chí làm một chuyển đổi hợp lệ trở nên khó dùng.

Tạo tệp hoàn chỉnh **`WindowDesignDemo.java`**:

~~~java
class WindowBean {
    private int start = 2;
    private int end = 5;

    public int getStart() {
        return start;
    }

    public int getEnd() {
        return end;
    }

    public void setStart(int start) {
        if (start < 0 || start > end) {
            throw new IllegalArgumentException("window không hợp lệ");
        }
        this.start = start;
    }

    public void setEnd(int end) {
        if (end < start) {
            throw new IllegalArgumentException("window không hợp lệ");
        }
        this.end = end;
    }

    public String describe() {
        return "[" + start + "," + end + "]";
    }
}

final class Window {
    private int start;
    private int end;

    Window(int start, int end) {
        validate(start, end);
        this.start = start;
        this.end = end;
    }

    private static void validate(int start, int end) {
        if (start < 0 || end < start) {
            throw new IllegalArgumentException("window không hợp lệ");
        }
    }

    public void moveTo(int newStart, int newEnd) {
        validate(newStart, newEnd);
        start = newStart;
        end = newEnd;
    }

    public String describe() {
        return "[" + start + "," + end + "]";
    }
}

public class WindowDesignDemo {
    public static void main(String[] args) {
        WindowBean bean = new WindowBean();
        System.out.println("bean=" + bean.describe());

        try {
            bean.setStart(7);
        } catch (IllegalArgumentException ex) {
            System.out.println("setter blocked=" + ex.getMessage());
        }

        bean.setEnd(9);
        bean.setStart(7);
        System.out.println("bean after ordered setters="
                + bean.describe());

        Window window = new Window(2, 5);
        window.moveTo(7, 9);
        System.out.println("window=" + window.describe());

        try {
            window.moveTo(10, 8);
        } catch (IllegalArgumentException ex) {
            System.out.println("window rejected=" + ex.getMessage());
        }
        System.out.println("window after reject="
                + window.describe());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 WindowDesignDemo.java
java WindowDesignDemo
~~~

**Stdout:**

~~~text
bean=[2,5]
setter blocked=window không hợp lệ
bean after ordered setters=[7,9]
window=[7,9]
window rejected=window không hợp lệ
window after reject=[7,9]
~~~

`WindowBean` là lớp có getter/setter theo mẫu JavaBeans nhưng cập nhật `start` trước `end` từ `[2,5]` sang `[7,9]` bị từ chối, vì `start=7` tạm thời vượt `end=5`. Caller buộc phải gọi `setEnd(9)` rồi mới `setStart(7)`.

Trong `Window`, phương thức `moveTo(7,9)` nhận **cả trạng thái đích**, kiểm tra điều kiện liên trường **một lần** rồi cập nhật. Khi `moveTo(10,8)` thất bại, cả hai field giữ nguyên.

**Lưu ý về đa luồng:** hai phép gán `start = ...; end = ...;` trong `moveTo` không tự trở thành một giao dịch nguyên tử khi có nhiều luồng. Nếu object chia sẻ giữa các luồng, cần đồng bộ hóa việc đọc/cập nhật, hoặc một representation bất biến được công bố nguyên tử phù hợp.

## 12. Nên giữ getter/setter ở đâu và tránh ở đâu?

Một bảng định hướng:

| Bối cảnh | Getter | Setter | Phương thức hành vi |
| --- | --- | --- | --- |
| DTO nhập/xuất đơn giản | Hữu ích cho công cụ binding | Có thể phù hợp | Thường không có nhiều nghiệp vụ |
| Bean cấu hình | Hữu ích cho công cụ quản trị | Phù hợp nếu cần điều chỉnh | Có thể cần `reload`, `validate` |
| Domain entity với invariant mạnh | Getter chọn lọc | Hạn chế setter tổng quát | Ưu tiên hành vi hợp lệ |
| Value object bất biến | Truy vấn trạng thái | Thường không có setter | `withX`/trả giá trị mới |
| Object quản lý tài nguyên | Getter trạng thái giới hạn | Tránh setter tùy tiện | `open`, `close`, `start`, `stop` |
| Model hiển thị form | Cần đọc/ghi dữ liệu biểu mẫu | Có thể phù hợp | Validation tổng thể trước khi áp dụng |

Một domain object vẫn có thể là **nguồn dữ liệu để hiển thị** nhờ getter hoặc một DTO projection, nhưng không cần công bố mọi setter. Một DTO có thể giữ dữ liệu chưa hợp lệ trong lúc người dùng nhập và chỉ chuyển thành domain object khi validation thành công.

Chọn theo **nhiệm vụ của lớp**, không nên tự động áp một bộ quy tắc lên tất cả class của ứng dụng.

## 13. Dùng JavaBean làm dữ liệu đầu vào rồi tạo domain object hợp lệ

Tách dữ liệu nhận từ bên ngoài và domain object có thể giúp vừa tương thích với công cụ JavaBeans vừa bảo vệ invariant của nghiệp vụ.

Ví dụ một bean phục vụ dữ liệu nhập:

~~~java
public class AccountFormBean {
    private String id;
    private Long initialBalanceCents;

    public AccountFormBean() {
    }

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public Long getInitialBalanceCents() {
        return initialBalanceCents;
    }

    public void setInitialBalanceCents(Long initialBalanceCents) {
        this.initialBalanceCents = initialBalanceCents;
    }
}
~~~

Đây là **định nghĩa lớp hợp lệ** nếu lưu thành `AccountFormBean.java`. `Long` thay vì `long` có thể biểu diễn tình huống biểu mẫu **chưa có giá trị** (`null`). Bean có constructor không tham số và các getter/setter công khai nên phù hợp với nhiều công cụ binding kiểu JavaBeans.

Tại ranh giới chuyển đổi, logic ứng dụng cần kiểm tra cả `id`, `initialBalanceCents` trước khi gọi:

~~~java
if (form.getInitialBalanceCents() == null) {
    throw new IllegalArgumentException("thiếu số dư");
}
LedgerAccount account = new LedgerAccount(
        form.getId(), form.getInitialBalanceCents());
~~~

Đoạn này là **mã sử dụng minh họa**, với `form` là instance `AccountFormBean` và `LedgerAccount` ở mục 9. Constructor của domain object vẫn kiểm tra `id` hợp lệ và số dư không âm. Nếu thiếu số dư, việc kiểm tra null ở ranh giới tránh unboxing gây `NullPointerException` khó hiểu.

Ưu điểm của cách tách: người dùng hoặc framework có thể từng bước điền biểu mẫu, nhưng domain object **không bao giờ cần được công bố ở trạng thái khởi tạo thiếu trường bắt buộc**.

**Đánh đổi:** có thêm phép chuyển đổi và hai kiểu dữ liệu. Với ứng dụng rất nhỏ, có thể không cần cả hai loại; nhưng khi binding và invariant có mục tiêu khác nhau, sự tách biệt làm hợp đồng rõ hơn.

## 14. `final`, immutable object và record không phải JavaBean setter truyền thống

Một class có field `final` và không có setter là cách biểu diễn object khó bị gán lại trạng thái sau khởi tạo. Java 17 có `record`:

~~~java
record ProductView(String sku, String name, long priceCents) {
    ProductView {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku sai");
        }
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name sai");
        }
        if (priceCents <= 0) {
            throw new IllegalArgumentException("price sai");
        }
    }

    ProductView withPrice(long newPriceCents) {
        return new ProductView(sku, name, newPriceCents);
    }
}
~~~

Đây là **định nghĩa record hợp lệ**, không có `main`. Accessor được sinh ra mang tên `sku()`, `name()`, `priceCents()` chứ không phải `getSku()`, `getName()`, `getPriceCents()` theo mẫu JavaBeans cổ điển. Record **không có setter thông thường** và các component của record không thể gán lại.

Việc một framework hỗ trợ record để serialize/bind hay không tùy khả năng/phiên bản của framework; đừng mặc định rằng `java.beans.Introspector` truyền thống nhận accessor record như property getter JavaBeans.

Phương thức `withPrice` tạo và trả một **record mới**, khiến constructor kiểm tra lại invariant. Caller muốn áp dụng kết quả phải viết:

~~~java
ProductView current = new ProductView("P1", "Bút", 5000);
current = current.withPrice(7000);
~~~

Không dùng getter/setter không đồng nghĩa mất khả năng đóng gói: với value object, **bất biến và kiểm tra từ lúc tạo** thường bảo vệ trạng thái hiệu quả hơn nhiều setter.

## 15. Đừng để getter làm lộ dữ liệu mutable

Ngay cả khi chỉ có getter, đóng gói vẫn có thể bị phá nếu getter trả trực tiếp một collection hoặc mảng có thể sửa.

~~~java
class LeakyBean {
    private final java.util.List<String> tags =
            new java.util.ArrayList<>();

    public java.util.List<String> getTags() {
        return tags;
    }
}
~~~

Đây là lớp minh họa hợp lệ. Caller gọi `bean.getTags().add(null)` có thể thay đổi list **nội bộ** dù không có `setTags` và field là `private final`.

Để bảo vệ invariant:

- Sao chép dữ liệu mutable **khi nhận** vào constructor/setter.
- Cân nhắc trả một **snapshot không hỗ trợ sửa** khi đọc.
- Với mảng primitive, có thể clone/copy ở cả hai chiều.
- Với list chứa object mutable, sao chép list chỉ là **shallow copy**; vẫn phải xét quyền sở hữu đối tượng phần tử.
- Không nhầm `Collections.unmodifiableList(list)` (view trên list nguồn) với một snapshot độc lập trong mọi tình huống.

Điều này đúng cho cả JavaBean, domain entity hay record. **Getter không tự bảo đảm read-only theo nghĩa toàn bộ object graph.**

## 16. Ví dụ chạy được: bean có collection nhưng không làm lộ alias

Tạo tệp **`SafeCollectionBeanDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;

public class SafeCollectionBeanDemo {
    public static class TagsBean {
        private List<String> tags = List.of();

        public TagsBean() {
        }

        public List<String> getTags() {
            return tags;
        }

        public void setTags(List<String> tags) {
            this.tags = List.copyOf(tags);
        }
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>();
        source.add("java");

        TagsBean bean = new TagsBean();
        bean.setTags(source);
        source.add("oop");

        System.out.println("source=" + source);
        System.out.println("bean=" + bean.getTags());

        try {
            bean.getTags().add("unsafe");
        } catch (UnsupportedOperationException ex) {
            System.out.println("getter blocks mutation");
        }

        try {
            bean.setTags(java.util.Arrays.asList("java", null));
        } catch (NullPointerException ex) {
            System.out.println("reject null element");
        }

        System.out.println("final=" + bean.getTags());
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 SafeCollectionBeanDemo.java
java SafeCollectionBeanDemo
~~~

**Stdout:**

~~~text
source=[java, oop]
bean=[java]
getter blocks mutation
reject null element
final=[java]
~~~

`List.copyOf(source)` cung cấp một danh sách **không cho sửa qua API**, không bị thay đổi khi caller thêm phần tử vào `source`. Khi cố đưa phần tử null vào `List.copyOf`, phương thức ném `NullPointerException` trước khi phép gán `this.tags = ...` hoàn tất, nên `tags` vẫn giữ dữ liệu trước đó.

**Giới hạn:** `List.copyOf` không deep-copy từng phần tử. Ví dụ dùng `String` bất biến nên các thay đổi từ bên ngoài không thể sửa nội dung một phần tử tại chỗ. Với `List<MutableItem>`, phải cân nhắc tiếp tính bất biến/sao chép của `MutableItem`.

## 17. Bound property và thông báo thay đổi trong JavaBeans

Ngoài getter/setter, JavaBeans còn hỗ trợ ý niệm **bound property**: khi giá trị thuộc tính đổi, đối tượng có thể phát sự kiện `PropertyChangeEvent` cho những listener đã đăng ký. Thư viện tiêu chuẩn cung cấp `PropertyChangeSupport`.

Tạo tệp **`BeanChangeNotificationDemo.java`**:

~~~java
import java.beans.PropertyChangeListener;
import java.beans.PropertyChangeSupport;

public class BeanChangeNotificationDemo {
    public static class SettingsBean {
        private final PropertyChangeSupport changes =
                new PropertyChangeSupport(this);
        private int volume = 50;

        public SettingsBean() {
        }

        public int getVolume() {
            return volume;
        }

        public void setVolume(int next) {
            if (next < 0 || next > 100) {
                throw new IllegalArgumentException("volume ngoài 0..100");
            }
            int old = volume;
            if (old == next) {
                return;
            }
            volume = next;
            changes.firePropertyChange("volume", old, next);
        }

        public void addPropertyChangeListener(
                PropertyChangeListener listener) {
            changes.addPropertyChangeListener(listener);
        }

        public void removePropertyChangeListener(
                PropertyChangeListener listener) {
            changes.removePropertyChangeListener(listener);
        }
    }

    public static void main(String[] args) {
        SettingsBean bean = new SettingsBean();
        bean.addPropertyChangeListener(event ->
                System.out.println(event.getPropertyName()
                        + ": " + event.getOldValue()
                        + "->" + event.getNewValue()));

        bean.setVolume(70);
        bean.setVolume(70);

        try {
            bean.setVolume(150);
        } catch (IllegalArgumentException ex) {
            System.out.println("reject=" + ex.getMessage());
        }
        System.out.println("volume=" + bean.getVolume());
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 BeanChangeNotificationDemo.java
java BeanChangeNotificationDemo
~~~

**Stdout:**

~~~text
volume: 50->70
reject=volume ngoài 0..100
volume=70
~~~

Trong ví dụ, `setVolume(70)` hợp lệ: field được cập nhật rồi listener nhận một sự kiện mô tả `50 -> 70`. Lời gọi thứ hai đặt `70` khi đã là `70` nên method tự bỏ qua và không phát sự kiện. `setVolume(150)` bị validation từ chối **trước khi sửa field**.

**Không phải mọi JavaBean đều phải có `PropertyChangeSupport`.** Đây là khả năng bổ sung khi ứng dụng cần quan sát thay đổi, ví dụ công cụ quản trị hoặc giao diện. Một biến thể nâng cao là **constrained property** có `VetoableChangeListener` để người nghe có thể từ chối thay đổi theo hợp đồng JavaBeans.

**Lưu ý quan trọng:** `firePropertyChange` có thể gọi listener trong ngữ cảnh lời gọi của setter. Nếu listener ném unchecked exception, một thay đổi field đã thực hiện **không tự rollback**. Nếu có nhiều luồng, phải thiết kế bảo vệ cả field, trình tự sự kiện và listener phù hợp; sự có mặt của `PropertyChangeSupport` không tự làm mọi phương thức của bean thread-safe.

## 18. Framework và công cụ tự động dùng JavaBeans như thế nào?

Một số công cụ dùng **reflection** hoặc **introspection** để xác định thuộc tính rồi đọc/ghi:

~~~text
Thông tin từ form / cấu hình / dữ liệu được giải mã
                  |
                  v
  Xác định tên property: "name", "active", ...
                  |
                  v
  Tìm read/write method phù hợp
                  |
                  v
     Gọi setter / constructor / factory
                  |
                  v
      Đối tượng dữ liệu trong ứng dụng
~~~

Sơ đồ trên là mô hình khái niệm. **Mỗi thư viện có chính sách khác nhau**: có nơi dùng getter/setter, có nơi dùng field, annotation, record component, constructor binding hoặc kết hợp. Không thể suy luận rằng mọi thư viện serialization, ORM hay UI luôn tuân đúng một cơ chế JavaBeans.

Khi một framework cần setter để *bind* một DTO, **đừng vì thế mở setter công khai cho mọi domain entity**. Có thể dùng lớp dữ liệu biên với quy ước mà công cụ mong muốn, rồi chuyển đổi dữ liệu đã kiểm tra sang domain object có hành vi.

Các câu hỏi khi chọn giải pháp tích hợp:

1. Công cụ dùng field, JavaBeans getter/setter hay constructor?
2. Có cần constructor không tham số không?
3. Có gọi setter riêng lẻ làm object ở trạng thái trung gian chưa hợp lệ không?
4. Nếu setter ném `IllegalArgumentException`, framework biến lỗi đó thành thông báo gì?
5. Có hỗ trợ immutable object/`record` không?
6. Thực sự cần để lộ property nào ra bên ngoài?
7. Những ràng buộc liên trường được kiểm tra tại đâu và khi nào?

Đọc tài liệu đúng phiên bản framework đang dùng là cách chắc chắn hơn việc suy từ tên “Bean”.

## 19. Kiểm tra ở điểm tạo và điểm cập nhật: quy tắc áp dụng cho cả hai mô hình

Dù thiết kế JavaBeans hay theo hành vi, một domain object đã công bố là **hợp lệ** vẫn cần bảo vệ các invariant:

~~~text
TẠO:
  Kiểm tra dữ liệu bắt buộc
  -> chuẩn hóa theo hợp đồng
  -> gán state hợp lệ

CẬP NHẬT:
  Kiểm tra yêu cầu
  -> kiểm tra state hiện tại
  -> tính state kết quả
  -> xác nhận mọi invariant
  -> cập nhật

THẤT BẠI:
  Nếu hứa "lỗi không đổi state", tránh sửa field trước khi lỗi phát sinh
~~~

Với setter `setName`, validation đơn giản theo field có thể đủ. Với thao tác `withdraw`, còn phải biết số dư hiện tại. Với hai field liên hệ `start/end`, cần kiểm tra chúng **cùng nhau**.

Một thao tác thay đổi nhiều field nên tính các giá trị đã xác thực trước khi gán:

~~~java
public void updateDetails(String nextName, long nextPrice) {
    String checkedName = validateName(nextName);
    long checkedPrice = validatePrice(nextPrice);
    this.name = checkedName;
    this.priceCents = checkedPrice;
}
~~~

Đây là **phương thức minh họa** thuộc lớp giả định có các hàm `validateName`, `validatePrice` đã được định nghĩa và có field phù hợp. Đoạn này chỉ mô tả cách tập trung kiểm tra; không phải một chương trình độc lập.

**Đừng nhầm validation tuần tự với transaction đa luồng.** Ngay cả khi kiểm tra trước rồi gán, một object chia sẻ giữa thread khác nhau vẫn có thể cần lock, atomic update hoặc mô hình ownership phù hợp.

## 20. Tác dụng phụ, quyền sở hữu dữ liệu và đóng gói

Thiết kế theo hành vi thường đi kèm câu hỏi **ai sở hữu trạng thái mutable**. Lớp kiểm soát field nhưng nếu trả trực tiếp `Map`, `List` hoặc mảng mutable, caller có thể bỏ qua phương thức hành vi bằng cách sửa dữ liệu thông qua alias.

Một API đáng tin cần phân biệt:

- **Đọc dữ liệu:** getter trả scalar bất biến, copy hoặc view theo hợp đồng.
- **Cập nhật có kiểm soát:** phương thức hành vi bảo đảm invariant trước/sau.
- **Đầu vào mutable:** có lưu tham chiếu caller truyền vào hay sao chép?
- **Đầu ra mutable:** trả object nội bộ hay snapshot?
- **Callback/sự kiện:** có gọi external code ngay khi cập nhật không, và nếu listener lỗi thì sao?
- **Đa luồng:** state có được chia sẻ không? Các thao tác cập nhật có nguyên tử/visibility phù hợp không?

Một setter JavaBeans có validation tốt vẫn có thể là API đúng cho cấu hình. Một phương thức tên rất “nghiệp vụ” nhưng bỏ qua invariant vẫn là API kém. **Tên phương thức gợi ý ý định; implementation phải thực sự giữ hợp đồng.**

## 21. Hướng dẫn chọn thiết kế trong một dự án

Tự trả lời các câu hỏi sau:

| Câu hỏi | Nếu câu trả lời là “có” | Hướng thường phù hợp |
| --- | --- | --- |
| Đối tượng là form/DTO để công cụ tạo và điền từng thuộc tính? | Có | JavaBeans properties hoặc binding model đúng công cụ |
| Object có invariant mạnh và không được tồn tại thiếu dữ liệu? | Có | Constructor/factory kiểm tra đầu vào bắt buộc |
| Thay đổi cần nhìn trạng thái cũ và kiểm tra điều kiện nghiệp vụ? | Có | Phương thức hành vi thay vì setter tổng quát |
| Nhiều field phải thay cùng nhau để giữ invariant? | Có | Một thao tác cập nhật theo nhóm |
| Muốn giữ nhiều phiên bản dữ liệu trước/sau? | Có | Immutable value object, record hoặc `withX` |
| Cần thông báo UI khi một property thay đổi? | Có | Bound property/event support theo hợp đồng |
| Có mutable list/array được chia sẻ? | Có | Defensive copy và ownership rõ ràng |
| API được truy cập đồng thời? | Có | Thiết kế synchronization/atomic update riêng |

**Gợi ý thực tế:** không nhất thiết phải biến tất cả lớp thành JavaBeans cũng không cần biến tất cả getter thành phương thức hành vi. Có thể có `OrderFormBean` cho màn hình, `Order` bảo vệ thao tác `place/cancel`, và `OrderView`/record cho kết quả chỉ đọc. Sự phân chia này có thêm lớp và phép chuyển đổi, nên cân nhắc theo độ phức tạp dự án.

## 22. Những lỗi thường gặp

| Sai lầm | Vì sao rủi ro | Cách cải thiện |
| --- | --- | --- |
| Nghĩ JavaBean là mọi class có `getX/setX` | Bỏ qua ngữ nghĩa property, introspection và vai trò bean | Hiểu quy ước và công cụ sử dụng |
| Tự sinh getter/setter cho mọi field domain | Mở khả năng chuyển trạng thái trái nghiệp vụ | Chỉ công bố thao tác cần thiết |
| Coi field `private` là đã đóng gói đầy đủ | Setter hoặc getter lộ alias vẫn phá invariant | Kiểm soát mọi đường cập nhật |
| Cho `setBalance` dù nghiệp vụ chỉ cho deposit/withdraw | Caller tự đặt state mà bỏ qua ý nghĩa nghiệp vụ | `deposit`/`withdraw` |
| Dùng hai setter khi invariant phụ thuộc hai field | Phải biết thứ tự cập nhật; dễ tạo state trung gian sai | Một phương thức `moveTo(start,end)` |
| Chỉ dùng getter để suy ra class bất biến | Getter có thể trả list/mảng mutable nội bộ | Defensive copy/immutable component |
| Cho rằng `final List` làm phần tử bất biến | `final` chỉ ngăn gán lại tham chiếu field | Bảo vệ object bên trong |
| Dùng `Boolean isActive()` và giả định mọi công cụ nhận diện | `isX` truyền thống kỳ vọng primitive boolean | `getActive()` với wrapper khi cần |
| Cho rằng `getURL()` sinh tên `uRL` | Quy tắc decap đặc biệt khi hai chữ đầu viết hoa | Kiểm tra qua `Introspector` |
| Dùng fluent setter rồi mong mọi bean tool nhận ra | Quy ước setter cổ điển thường dùng `void` | Tuân chữ ký công cụ yêu cầu |
| Đặt no-arg constructor tạo domain object không hợp lệ | Domain object tồn tại với state bắt buộc chưa có | Dùng DTO riêng hoặc constructor có tham số |
| Chỉ validate từng setter mà bỏ qua quan hệ các field | Có thể tạo invariant liên trường sai | Xác thực cả trạng thái kết quả |
| Cho rằng PropertyChangeSupport tự rollback | Listener có thể lỗi sau khi field đã sửa | Định nghĩa thứ tự cập nhật và xử lý lỗi |
| Nghĩ record tự động là JavaBean setter cổ điển | Accessor `name()` khác `getName()`, không có setter | Dùng binding hỗ trợ record hoặc DTO tương thích |
| Nghĩ `private`/JavaBeans tự đảm bảo thread safety | Nhiều thread vẫn có thể gọi setter/hành vi đồng thời | Bảo vệ toàn bộ thao tác đọc–tính–ghi |

## 23. Kiểm thử: kiểm tra cả quy ước lẫn invariant

Với `JavaBeanIntrospectionDemo`, cần phân biệt hai loại kiểm thử.

**Kiểm thử quy ước JavaBeans:**

- Có getter `getName`, setter `setName` với kiểu tham số/return chuẩn.
- Có `isActive` cho boolean và `setActive`.
- Property `stock` là chỉ đọc theo `Introspector`.
- Tên property sau introspection đúng quy ước, không nhầm `getURL` với `getName`.
- Constructor public không tham số tạo bean trong trạng thái được phép.

**Kiểm thử hợp đồng đối tượng:**

- `setName(null)` hoặc chuỗi trắng bị từ chối.
- `receive(5)` tăng stock đúng 5.
- `receive(-1)` và thao tác gây overflow bị từ chối trước khi thay stock.
- Getter không trả mutable alias khi hợp đồng yêu cầu snapshot.
- Nếu có bound property, chỉ phát sự kiện ở thay đổi được chấp nhận theo thiết kế.

Với `LedgerAccount`, cần kiểm thử rằng `withdraw` không cho rút quá số dư, `deposit` không chấp nhận giá trị không dương, trạng thái không âm sau các thao tác; **không** cần bài kiểm tra “setBalance có hoạt động không” vì API **cố ý không có setter**.

Với `Window`, cần kiểm tra `moveTo(7,9)` hợp lệ và `moveTo(10,8)` bị từ chối **mà không đổi cả hai field**.

Một số bug không được phát hiện bằng “phương thức gọi không ném exception”. Hãy xác nhận **đúng trạng thái sau lời gọi**, **ngoại lệ thích hợp**, và **trạng thái sau thất bại**.

## 24. Bài tập tự luyện

**Bài 1.** `public boolean isAvailable()` và `public void setAvailable(boolean v)` được JavaBeans introspector nhìn nhận thành property nào? Nếu chỉ có `getCount()` mà không có setter thì property đó thuộc loại gì?

**Bài 2.** Lớp có field `private String title` nhưng công bố `getName()` và `setName(...)`. Tên property JavaBeans là `title` hay `name`? Vì sao?

**Bài 3.** Một lớp cấu hình có `public Settings()`, `getTimeout()`, `setTimeout(int)`. Khi nào kiểu API này hợp lý hơn phương thức hành vi?

**Bài 4.** Một tài khoản có `setBalance(long)` công khai. Vì sao chỉ từ chối số âm vẫn chưa bảo vệ đầy đủ ý nghĩa rút/nạp tiền?

**Bài 5.** Từ khoảng `[2,5]` muốn sang `[7,9]`. Vì sao `setStart(7)` trước `setEnd(9)` có thể bị từ chối trong lớp kiểm tra invariant? Đề xuất phương thức thay thế.

**Bài 6.** Một getter `getTags()` trả nguyên `ArrayList` nội bộ. `private final` ở field có ngăn caller thay đổi list không? Nên làm gì?

**Bài 7.** Trong một hệ thống nhận dữ liệu từ form, có nên dùng một JavaBean cho trạng thái nhập chưa đủ rồi chuyển thành domain object qua validation không? Trình bày đánh đổi.

**Bài 8.** `getURL()` thường sinh property `URL` hay `uRL`? `getName()` sinh gì? Cơ chế nào xác định?

**Bài 9.** Với `Boolean getReady()` và `Boolean isReady()`, dạng nào là getter JavaBeans an toàn hơn cho wrapper có thể null trong công cụ truyền thống?

**Bài 10.** Lớp `SettingsBean` phát `PropertyChangeEvent` trong `setVolume`. Nếu listener ném lỗi sau khi field đã được cập nhật, Java tự đảo lại `volume` không?

**Bài 11.** Một `record PersonView(String name)` có accessor `name()`. Vì sao không nên mặc định rằng một công cụ chỉ hiểu `getName()` sẽ tự nhận ra property record?

**Bài 12.** Hai luồng cùng gọi `withdraw` trên một object được chia sẻ. Field `private` và getter/setter đặt tên chuẩn có tự tránh mất cập nhật không? Cần quan tâm gì thêm?

### Đáp án tham khảo

1. Property `available` đọc/ghi qua `isAvailable/setAvailable`; `count` chỉ đọc.
2. `name`; introspection nhận diện theo accessor công khai phù hợp, không nhất thiết theo tên field.
3. Phù hợp khi nhiệm vụ là trao đổi/cấu hình các property độc lập, không có invariant nghiệp vụ phức tạp; vẫn kiểm tra miền hợp lệ của `timeout`.
4. Setter tổng quát không diễn đạt lý do chuyển trạng thái, giới hạn số tiền, quyền hoặc quy tắc giao dịch; `deposit/withdraw` thích hợp hơn khi có nghiệp vụ.
5. `start=7` vượt `end=5` ở bước trung gian; dùng `moveTo(7,9)` kiểm tra cả cặp trước khi gán.
6. Không. `final` không khóa nội dung list; cần snapshot/copy hoặc API truy vấn đúng hợp đồng.
7. Có thể; DTO hỗ trợ công cụ điền dữ liệu từng bước, domain object chỉ được tạo khi đủ hợp lệ; đánh đổi là thêm model và chuyển đổi.
8. `URL` và `name`, theo quy tắc decap property trong JavaBeans/Introspector.
9. `getReady()` với kiểu `Boolean`; không trông chờ `isReady()` wrapper được mọi JavaBeans introspector cổ điển nhận diện.
10. Không. Một exception từ listener không tự hoàn tác phép gán đã xảy ra; cần thiết kế rõ thứ tự và cam kết lỗi.
11. Accessor record theo tên component, không theo mẫu `getX` cổ điển; hỗ trợ record tùy công cụ.
12. Không. Cần đồng bộ/atomic update/ownership phù hợp với thao tác kiểm tra và ghi trạng thái.

## 25. Tài liệu tham khảo

- [Java SE 17 — JavaBeans Introspector](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/Introspector.html): cách phân tích bean và quy tắc đặt tên property.
- [Java SE 17 — PropertyDescriptor](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/PropertyDescriptor.html): read/write methods của một property.
- [Java SE 17 — BeanInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/BeanInfo.html): thông tin về property, event và method cho công cụ.
- [Java SE 17 — PropertyChangeSupport](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/PropertyChangeSupport.html): hỗ trợ sự kiện bound property.
- [Java SE 17 — Introspector.decapitalize](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/beans/Introspector.html#decapitalize(java.lang.String)): quy tắc biến tên phương thức thành tên property.
- [Java Language Specification 17, §8 — Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html): class, field, method và constructor.
- [Java Language Specification 17, §8.10 — Record Classes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.10): record và accessor của component.

**Ghi nhớ:** quy ước JavaBeans chuẩn hóa **cách công bố và khám phá thuộc tính**; thiết kế theo hành vi bảo vệ **ý nghĩa của những chuyển trạng thái được phép**. Hai cách có thể phối hợp: getter cho quan sát, setter có kiểm tra cho thuộc tính thật sự được phép đặt, và phương thức `deposit`, `withdraw`, `moveTo`, `receive` cho nghiệp vụ. Mục tiêu sau cùng không phải có thật nhiều setter, mà là **giữ invariant qua mọi đường tạo, đọc và cập nhật trạng thái**.
