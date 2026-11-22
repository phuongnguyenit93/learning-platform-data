# Kế thừa kiểu, kế thừa mã và kế thừa trạng thái trong Java

Từ “kế thừa” thường được dùng cho ba ý khác nhau: **quan hệ kiểu** (đối tượng dùng được qua kiểu cha), **tái sử dụng mã** (nhận một implementation có sẵn) và **kế thừa trạng thái** (instance chứa các field do superclass định nghĩa). Phân biệt ba khía cạnh giúp quyết định nên dùng `extends`, `implements`, `default` method hay composition.

## 1. Ba cơ chế không đồng nghĩa

| Khía cạnh | Câu hỏi | Cơ chế điển hình | Giới hạn |
|---|---|---|---|
| **Kế thừa kiểu** | Giá trị có dùng được ở nơi cần kiểu cha không? | `class extends`, `class implements`, `interface extends` | Có subtype không đồng nghĩa với nhận mọi code hoặc state. |
| **Kế thừa mã** | Implementation nào có thể dùng lại? | Concrete method của superclass; `default` method của interface | Không phải mọi method đều được kế thừa hoặc override. |
| **Kế thừa trạng thái** | Field instance nào thuộc object? | Instance field trong chuỗi `extends` | Interface không cung cấp instance field; `static` field không phải state riêng của mỗi object. |

Một khai báo có thể kết hợp nhiều khía cạnh:

- `SavingsAccount extends Account`: quan hệ subtype, có thể kế thừa concrete method và chứa state do `Account` định nghĩa.
- `SavingsAccount implements Named`: tạo quan hệ kiểu với `Named`; có thể nhận `default` method phù hợp nhưng không nhận state instance từ interface.
- `interface Auditable extends Named`: mở rộng hợp đồng và có thể kế thừa `default` method; vẫn không có state instance.
- `abstract class` có thể chứa field, constructor, concrete method và abstract method; mỗi thành viên có quy tắc riêng.

Java chỉ cho một superclass trực tiếp trên mỗi class, nhưng class có thể implement nhiều interface. Nhiều hợp đồng kiểu không đồng nghĩa với nhiều superclass có trạng thái.

## 2. Kế thừa kiểu: có thể thay thế qua hợp đồng nào?

Ví dụ `SavingsAccount extends Account` và `Account implements Named`:

```java
SavingsAccount savings = new SavingsAccount("Lan", 100);
Account asAccount = savings;
Named asNamed = savings;
```

Các biến có kiểu khai báo khác nhau nhưng có thể cùng tham chiếu **một object**. Upcast không tạo bản sao. Kiểu khai báo giới hạn API có thể gọi; implementation của phương thức instance được override được chọn theo đối tượng runtime. Bài **Quan hệ kiểu cha và kiểu con** trình bày riêng về subtype, LSP, generic và cách chọn kiểu cho API.

Quan hệ kiểu do compiler xác nhận không tự bảo đảm hành vi nghiệp vụ. Nếu lớp con phá cam kết của lớp cha, code dùng kiểu cha vẫn có thể hỏng. Hãy thiết kế hợp đồng theo hành vi mà mọi implementation có thể đáp ứng, không chỉ theo tên `extends`.

## 3. Kế thừa mã: concrete method, abstract method và default method

Superclass có thể cung cấp thuật toán chung qua concrete method; subclass có thể dùng trực tiếp hoặc override method instance phù hợp. Abstract method chỉ định nghĩa phần lớp con phải hoàn thiện. Constructor không được kế thừa.

Interface cũng có thể tái sử dụng code qua `default` method:

```java
interface Named {
    String name();

    default String description() {
        return "Định danh: " + name();
    }
}
```

Lớp `implements Named` nhận hợp đồng `name()` và có thể dùng `description()` mà không chép lại code. Lời gọi `name()` trong default method dispatch tới implementation của object. Điều này **không** làm interface thành superclass có state.

Các quy tắc cần nhớ:

1. `@Override` giúp compiler xác nhận method thực sự override; implementation không được giảm mức truy cập và phải tuân thủ kiểu trả về/checked exception.
2. `final` method không thể override; `static` method bị hide theo kiểu khai báo; `private` method của superclass không được subclass override.
3. `super.method()` gọi implementation của superclass khi hợp lệ; nó không tạo một object cha thứ hai.
4. Nếu hai interface không liên quan cung cấp `default` method trùng signature, lớp cụ thể thường phải override để chọn hành vi. Phương thức instance cụ thể phù hợp từ superclass được ưu tiên theo quy tắc Java. Bài **Đơn kế thừa lớp và đa kế thừa interface** đi sâu vào các trường hợp xung đột này.

## 4. Kế thừa trạng thái: field của superclass nằm trong cùng object

Một `SavingsAccount` có thể chứa phần state do `Account` khai báo, ví dụ `owner` và `balance`, cùng với state riêng của subclass. Đây là các phần trong **một instance**, không phải hai object cha/con được lồng độc lập.

```java
abstract class Account {
    private final String owner;
    private long balance;

    protected Account(String owner, long initialBalance) {
        if (initialBalance < 0) {
            throw new IllegalArgumentException("Số dư ban đầu âm");
        }
        this.owner = owner;
        this.balance = initialBalance;
    }

    public final String owner() {
        return owner;
    }

    protected final void add(long amount) {
        balance += amount;
    }

    public long balance() {
        return balance;
    }
}
```

- `private` field vẫn thuộc state của object subclass, nhưng code subclass không thể truy cập trực tiếp bằng tên field. Superclass có thể kiểm soát thao tác qua method.
- `protected` cho subclass quyền truy cập theo quy tắc Java, nhưng `protected` mutable field dễ làm subclass phá invariant. Ưu tiên field `private` cùng API có kiểm soát.
- `static` field thuộc về class, không phải một bản sao trong mỗi object. Field cùng tên ở subclass tạo **field hiding**, tức hai field riêng biệt, không phải override.
- `final` reference field không thể được gán lại sau khởi tạo, nhưng object mà nó trỏ đến vẫn có thể mutable.

Không nên suy luận rằng field `private` “biến mất” khỏi object con: nó vẫn là phần state do superclass quản lý; chỉ quyền truy cập trực tiếp bị giới hạn.

## 5. Ví dụ Java 17+ kết hợp cả ba cơ chế

Lưu chương trình sau thành `InheritanceKindsDemo.java`:

```java
public class InheritanceKindsDemo {
    interface Named {
        String name();

        default String description() {
            return "Định danh: " + name();
        }
    }

    static abstract class Account implements Named {
        private final String owner;
        private long balance;

        protected Account(String owner, long initialBalance) {
            if (initialBalance < 0) {
                throw new IllegalArgumentException("Số dư ban đầu âm");
            }
            this.owner = owner;
            this.balance = initialBalance;
        }

        @Override
        public final String name() {
            return owner;
        }

        protected final void add(long amount) {
            balance += amount;
        }

        protected abstract String kind();

        public String summary() {
            return kind() + " | " + description() + " | số dư=" + balance;
        }
    }

    static final class SavingsAccount extends Account {
        SavingsAccount(String owner, long initialBalance) {
            super(owner, initialBalance);
        }

        void deposit(long amount) {
            if (amount <= 0) {
                throw new IllegalArgumentException("Số tiền phải dương");
            }
            add(amount);
        }

        @Override
        protected String kind() {
            return "Tiết kiệm";
        }
    }

    public static void main(String[] args) {
        SavingsAccount savings = new SavingsAccount("Lan", 100);
        Account asAccount = savings;
        Named asNamed = savings;

        System.out.println(asNamed.description());
        System.out.println(asAccount.summary());
        savings.deposit(50);
        System.out.println(asAccount.summary());
        System.out.println(asNamed == asAccount);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 InheritanceKindsDemo.java
java InheritanceKindsDemo
```

Stdout:

```text
Định danh: Lan
Tiết kiệm | Định danh: Lan | số dư=100
Tiết kiệm | Định danh: Lan | số dư=150
true
```

Trong ví dụ:

- `SavingsAccount extends Account` tạo quan hệ subtype, nhận method `summary()` và chứa state `owner`/`balance` trong cùng instance.
- `Account implements Named`; `name()` đã đáp ứng hợp đồng interface và `description()` là code được kế thừa từ default method.
- `summary()` gọi `kind()`, được subclass cài đặt; phần thuật toán chung vẫn thuộc superclass.
- `add()` kiểm soát cập nhật balance thay vì để subclass sửa field trực tiếp.
- `asNamed == asAccount` in `true`: hai tham chiếu khác kiểu cùng trỏ đến một object.

Đây là ví dụ cơ chế, chưa phải mô hình tài chính hoàn chỉnh: hệ thống thật cần xử lý tràn số, đồng thời và kiểu tiền tệ thích hợp.

## 6. Một object, nhiều cách nhìn trạng thái

Với các lớp trong `InheritanceKindsDemo` ở mục 5, đoạn sau có thể đặt trong `main`:

```java
SavingsAccount savings = new SavingsAccount("Lan", 100);
Account asAccount = savings;
savings.deposit(50);
System.out.println(asAccount.summary());
// Tiết kiệm | Định danh: Lan | số dư=150
```

`asAccount` và `savings` cùng trỏ đến một object; cập nhật `balance` qua lớp con được `summary()` của lớp cha nhìn thấy. Thuật toán chung của `summary()` được kế thừa, còn lời gọi `kind()` bên trong dispatch đến implementation của `SavingsAccount`.

Nếu subclass khai báo field **trùng tên** với superclass, đó là hai field khác nhau (field hiding); truy cập field không dispatch động như method được override. Tránh dựa vào hiding để thay đổi hành vi; nên đóng gói state bằng field `private` và method có kiểm soát. Bài **Kiểu tham chiếu và kiểu thực tế của đối tượng** minh họa riêng trường hợp field hiding.

## 7. Constructor và thứ tự khởi tạo

Constructor không được kế thừa. Khi tạo subclass, Java khởi tạo state theo chuỗi superclass rồi mới hoàn tất initializer/constructor của subclass. Constructor con gọi `super(...)` để chọn constructor cha phù hợp; nếu cha không có constructor không tham số khả dụng, lời gọi mặc định không đủ và subclass phải gọi rõ constructor phù hợp.

Tránh gọi method có thể override từ constructor superclass. Dynamic dispatch có thể đi vào subclass khi field của subclass chưa được khởi tạo đầy đủ, dẫn đến kết quả khó đoán hoặc phá invariant.

## 8. Chọn kế thừa hay composition?

| Nhu cầu | Lựa chọn thường phù hợp |
|---|---|
| Một họ object có state, constructor và invariant chung | `abstract class` hoặc superclass được thiết kế ổn định |
| Các class khác họ cần cùng một hợp đồng | `interface` |
| Muốn chia sẻ hành vi mặc định nhỏ, không phụ thuộc state instance | `default` method khi có ý nghĩa |
| Đối tượng “có một” thành phần hoặc cần thay implementation độc lập | Composition/delegation |
| Cần giữ invariant dữ liệu | Field `private` và method có kiểm soát |

Không dùng `extends` chỉ để tiết kiệm vài dòng. `Car` có `Engine` phù hợp với composition hơn `Car extends Engine`; delegation giúp thay thành phần mà không khóa lớp vào một superclass không đúng nghĩa.

## 9. Tự kiểm tra

1. Class implements interface có abstract method và tự cài đặt method đó: có kế thừa kiểu không? **Có**; nó không nhận implementation từ abstract method hay state instance từ interface.
2. Interface có default method: class triển khai nhận gì? **Quan hệ kiểu và khả năng tái sử dụng implementation**, khi không có override/xung đột chi phối; không nhận state instance.
3. Subclass không truy cập trực tiếp field `private` của cha có nghĩa field không thuộc object không? **Không**; field vẫn là phần state của object, chỉ được superclass đóng gói.
4. Khi nào dùng composition? Khi quan hệ “có/dùng một thành phần” đúng hơn “là một”, hoặc hành vi cần thay đổi độc lập.

**Ghi nhớ:** kế thừa kiểu nói về khả năng thay thế, kế thừa mã nói về implementation có thể dùng lại, còn kế thừa trạng thái nói về dữ liệu instance do superclass định nghĩa. `extends class` thường kết hợp các cơ chế này; `implements interface` tạo quan hệ kiểu và đôi khi tái sử dụng default code, nhưng không cung cấp state instance.
