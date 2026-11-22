# Vì sao interface không có constructor và thuộc tính instance trong Java?

## 1. Interface công bố hành vi, class sở hữu trạng thái

Interface mô tả những thao tác mà một đối tượng phải cung cấp. Nó không định nghĩa cách dựng một instance cụ thể và không khai báo field instance. Constructor, trạng thái riêng và quy trình khởi tạo thuộc về class hoặc record triển khai.

```java
interface Account {
    String id();
    int balance();
    void deposit(int amount);

    String CURRENCY = "VND";
}

final class Wallet implements Account {
    private final String id;
    private int balance;

    Wallet(String id, int initialBalance) {
        this.id = id;
        this.balance = initialBalance;
    }

    @Override
    public String id() {
        return id;
    }

    @Override
    public int balance() {
        return balance;
    }

    @Override
    public void deposit(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        balance += amount;
    }
}

public class Main {
    public static void main(String[] args) {
        Account first = new Wallet("A", 100);
        Account second = new Wallet("B", 5);
        first.deposit(25);
        System.out.println(first.id() + ": " + first.balance());
        System.out.println(second.id() + ": " + second.balance());
        System.out.println(Account.CURRENCY);
    }
}
```

Kết quả:

```text
A: 125
B: 5
VND
```

`Wallet` có constructor và field instance `id`, `balance`. Hai đối tượng ví giữ trạng thái riêng; việc nạp tiền vào A không làm đổi số dư B. Biến `first` và `second` dùng kiểu interface `Account` ở phía gọi, nhưng đối tượng thực tế vẫn là `Wallet`.

## 2. Vì sao interface không có constructor?

Constructor khởi tạo instance của class cụ thể và tham gia chuỗi gọi `this(...)` / `super(...)` của class. Interface không phải class có thể khởi tạo trực tiếp, nên khai báo constructor trong interface là không hợp lệ:

```java
interface Service {
    Service() {} // Sai cú pháp Java
    void run();
}
```

`new Service()` cũng không hợp lệ. Cú pháp `new Service() { ... }` lại có thể tạo anonymous class triển khai `Service`; constructor thuộc cơ chế tạo lớp ẩn danh, không thuộc interface. Lambda cũng có thể cung cấp implementation cho functional interface.

Abstract class khác ở chỗ nó vẫn là class trong chuỗi kế thừa: dù không thể tạo trực tiếp bằng `new`, nó có thể khai báo constructor và field instance để chia sẻ trạng thái cho các lớp con.

## 3. Vì sao field interface không phải field instance?

Mọi field khai báo trực tiếp trong interface đều ngầm định là `public static final`. Vì vậy:

```java
interface HttpSettings {
    int DEFAULT_PORT = 8080;
}
```

tương đương với khai báo tường minh `public static final int DEFAULT_PORT = 8080;`. Field thuộc về kiểu interface, không phải một bản sao cho từng đối tượng. Field interface phải được khởi tạo và không thể gán lại.

`final` khóa việc gán lại biến tham chiếu hoặc giá trị, nhưng không nhất thiết làm đối tượng được tham chiếu bất biến. Ví dụ, field `public static final List<String> NAMES` vẫn có thể trỏ đến một danh sách mutable; các nơi gọi có thể thay đổi nội dung danh sách. Vì thế không nên dùng field interface để công bố trạng thái mutable dùng chung.

## 4. Phương thức có thân không có nghĩa interface có state

Từ Java 8, interface có thể chứa `default` và `static` method; từ Java 9, có thể chứa `private` helper method. Các method này có thể gọi method khác của hợp đồng, dùng biến cục bộ và xử lý logic. Chúng không tạo field instance cho mỗi đối tượng.

```java
interface Named {
    String name();

    default String displayName() {
        return name().trim();
    }
}
```

`displayName()` lấy dữ liệu qua `name()`, do implementation quyết định. Nếu cần bộ đếm, cache hoặc trạng thái thay đổi riêng theo từng đối tượng, hãy lưu nó trong class triển khai hoặc một thành phần mà class đó sở hữu.

## 5. Chọn đúng cơ chế

| Nhu cầu | Lựa chọn |
| --- | --- |
| Nhiều kiểu khác nhau cùng công bố một hành vi | Interface |
| Mỗi đối tượng cần field riêng và constructor kiểm tra dữ liệu | Class/record triển khai |
| Nhiều subclass cần chung field, constructor và code cơ sở | Có thể dùng abstract class |
| Muốn một method tiện ích gọi qua tên kiểu | Static method phù hợp |
| Muốn chia sẻ logic instance ngắn mà không cần state chung | Có thể dùng default method |

**Tự kiểm tra:** `int count = 0;` khai báo trực tiếp trong interface có thể được tăng bằng `count++` trong default method không? Không; field đó ngầm định `final`. Hãy khai báo trạng thái trong class triển khai và công bố thao tác qua interface.