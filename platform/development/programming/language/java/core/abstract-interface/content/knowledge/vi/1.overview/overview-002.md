# Phân biệt trừu tượng hóa với đóng gói và kế thừa trong Java

## Mục tiêu

Sau bài này, bạn có thể giải thích chính xác ba nguyên lý thường xuất hiện cùng nhau trong lập trình hướng đối tượng (OOP):

- **Trừu tượng hóa (abstraction):** xác định *đối tượng cung cấp khả năng gì* và che bớt chi tiết hiện thực mà người dùng không cần biết.
- **Đóng gói (encapsulation):** quản lý *ai được truy cập hoặc thay đổi trạng thái nội bộ, bằng cách nào* để bảo vệ các quy tắc của đối tượng.
- **Kế thừa (inheritance):** xây dựng một kiểu dựa trên kiểu khác, nhận các thành viên được phép kế thừa và hình thành quan hệ kiểu con–kiểu cha.

Chúng có thể phối hợp trong cùng một thiết kế, nhưng giải quyết ba vấn đề khác nhau. Java có `interface`, `abstract class`, các mức truy cập và `extends`/`implements` để hiện thực chúng; không nên đồng nhất một từ khóa với toàn bộ một nguyên lý.

## 1. So sánh nhanh

| Khía cạnh | Trừu tượng hóa | Đóng gói | Kế thừa |
|---|---|---|---|
| Câu hỏi chính | «Dùng đối tượng này để làm gì?» | «Trạng thái và quy tắc bên trong được bảo vệ ra sao?» | «Kiểu này có quan hệ gì với kiểu khác?» |
| Tập trung vào | Hợp đồng/khả năng quan sát được, bỏ qua chi tiết không thiết yếu | Ranh giới truy cập, kiểm soát thay đổi và bất biến dữ liệu | Quan hệ *is-a*, tái sử dụng hành vi, khả năng thay thế kiểu |
| Công cụ Java thường gặp | `interface`, `abstract class`, phương thức public có chủ đích | `private`, API kiểm soát trạng thái, bất biến, defensive copy | `extends`, `implements`, `super`, `@Override` |
| Ví dụ | `PaymentMethod.pay(amount)` mô tả thao tác thanh toán | `Wallet` giữ `balance` ở `private` và chỉ trừ tiền qua kiểm tra hợp lệ | `GiftWallet extends Wallet` |
| Không bảo đảm điều gì? | Có hợp đồng tốt chưa chắc trạng thái được bảo vệ tốt | Dữ liệu được bảo vệ chưa chắc API đủ đơn giản hoặc có kiểu cha | Có kiểu cha chưa chắc API trừu tượng tốt hoặc đóng gói an toàn |

**Cách nhớ:** trừu tượng hóa chọn điều *cần lộ ra*; đóng gói kiểm soát điều *được phép tác động*; kế thừa xác lập mối quan hệ *kiểu con với kiểu cha*. “Che giấu chi tiết” có mặt ở cả trừu tượng hóa và đóng gói, nhưng mục đích khác nhau.

## 2. Trừu tượng hóa (abstraction): làm việc qua hợp đồng

Giả sử một hệ thống thanh toán có ví quà tặng, thẻ ngân hàng và cổng thanh toán bên ngoài. Phần xử lý đơn hàng chỉ cần biết rằng phương thức thanh toán nhận số tiền và trả kết quả. Nó không cần biết cách gọi API ngân hàng, cách kiểm tra hạn mức hay cách lưu số dư.

```java
interface PaymentMethod {
    String pay(int amount);
}
```

`PaymentMethod` là một **hợp đồng hành vi**: bên gọi phụ thuộc vào `pay` thay vì một lớp hiện thực cụ thể. Các lớp khác nhau có thể hiện thực hợp đồng theo những cách riêng; phía gọi không cần sửa chỉ vì thuật toán thanh toán thay đổi.

Điểm cốt lõi của trừu tượng hóa **không phải cứ có `interface` là đủ**. Một lớp thông thường với API ít, rõ ràng cũng có thể cung cấp một trừu tượng hữu ích. Ngược lại, một `interface` phơi bày hàng chục chi tiết nội bộ vẫn có thể là thiết kế trừu tượng kém.

Trong Java, thường lựa chọn:

- **`interface`:** diễn tả vai trò/khả năng để nhiều lớp không chung một lớp cha trực tiếp cùng tuân thủ. Ngoài phương thức trừu tượng, Java hiện đại cho phép `default`, `static` và một số phương thức `private` trong interface; trường khai báo trong interface là hằng số `public static final`.
- **`abstract class`:** diễn tả lớp cơ sở chưa hoàn chỉnh, có thể vừa quy định phương thức trừu tượng vừa chia sẻ trạng thái, constructor và cài đặt chung. Không thể khởi tạo trực tiếp lớp `abstract`.

Khi thiết kế trừu tượng tốt, hãy nêu rõ ý nghĩa tham số, kết quả, trường hợp lỗi và quy tắc người gọi có thể trông đợi. Chỉ khai báo tên phương thức mà không xác định hành vi mong đợi thì hợp đồng vẫn mơ hồ.

## 3. Đóng gói (encapsulation): bảo vệ trạng thái và quy tắc

Một ví có số dư không âm. Nếu khai báo `public int balance`, bất kỳ mã nào cũng có thể viết `wallet.balance = -999;` và phá vỡ quy tắc đó. Đóng gói đặt trạng thái sau một ranh giới truy cập, rồi chỉ cho phép thay đổi qua thao tác có kiểm tra.

```java
private int balance;

public int getBalance() {
    return balance;
}

protected boolean deduct(int amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("Số tiền phải dương");
    }
    if (amount > balance) {
        return false;
    }
    balance -= amount;
    return true;
}
```

*Đây là đoạn minh họa các thành viên nằm trong một lớp, chưa phải chương trình Java độc lập.* Ví dụ chạy hoàn chỉnh ở phần 5 có các thành viên tương tự.

Điều quan trọng không đơn thuần là viết `private` và tự động tạo getter/setter cho mọi trường:

- Nếu có `setBalance(int value)` công khai và cho phép giá trị tùy ý, trạng thái vẫn có thể bị sửa sai dù trường là `private`.
- Không cần đưa mọi trường ra thành getter. Chỉ cung cấp các thao tác mà miền nghiệp vụ thực sự cần, ví dụ `deposit` hoặc `withdraw`.
- Với đối tượng mutable như `List` hoặc `Date`, trả trực tiếp tham chiếu nội bộ qua getter có thể làm rò rỉ quyền sửa; cân nhắc bản sao phòng vệ hoặc chế độ xem không sửa được, tùy hợp đồng.
- Trạng thái bất biến (immutable) thường giúp giảm bề mặt lỗi, nhưng cần bảo đảm cả các đối tượng được tham chiếu bên trong không bị bên ngoài sửa ngoài ý muốn.

Đóng gói bảo vệ **bất biến (invariant)**: điều luôn phải đúng đối với đối tượng tại những thời điểm quan sát hợp lệ, chẳng hạn `balance >= 0`. Nó cũng giúp đổi cách lưu trữ nội bộ mà không buộc mã sử dụng phải thay đổi khi API được giữ ổn định.

## 4. Kế thừa (inheritance): quan hệ kiểu con–kiểu cha

Trong Java, `class GiftWallet extends Wallet` nói rằng `GiftWallet` là một dạng `Wallet`. Kiểu con có thể sử dụng các thành viên được phép truy cập từ lớp cha và ghi đè các phương thức có thể override để chuyên biệt hóa hành vi.

- `extends` giữa các lớp tạo quan hệ kế thừa lớp; một lớp chỉ có **một lớp cha trực tiếp**.
- `implements` cho phép lớp thực hiện **nhiều interface**, hình thành quan hệ kiểu con theo hợp đồng interface. Một interface cũng có thể `extends` nhiều interface khác.
- `super(...)` gọi constructor lớp cha. Constructor không được kế thừa như phương thức; `private` của lớp cha không trở thành thành viên có thể truy cập trực tiếp từ lớp con.
- `@Override` giúp trình biên dịch kiểm tra việc ghi đè đúng chữ ký. Phương thức `final` không thể bị override; phương thức `static` có thể bị che tên (*hiding*), không tham gia override đa hình như phương thức instance.

Kế thừa phù hợp khi quan hệ **is-a** thực sự đúng và đối tượng kiểu con có thể được dùng ở nơi đòi hỏi kiểu cha mà vẫn đáp ứng hợp đồng đã công bố. Đây là ý của nguyên tắc thay thế Liskov (LSP). Ví dụ một lớp con làm `pay` tự nhiên từ chối mọi số tiền hợp lệ trái với cam kết của kiểu cha thì có thể vi phạm hợp đồng, dù cú pháp Java vẫn hợp lệ.

**Không nên chọn kế thừa chỉ để dùng lại vài dòng code.** Nếu quan hệ đúng là **has-a** (có hoặc sử dụng một thành phần), hãy cân nhắc composition: một `CheckoutService` *giữ tham chiếu đến* `PaymentMethod` để dùng chức năng thanh toán, chứ không `extends PaymentMethod`. Composition thường giảm phụ thuộc vào chi tiết lớp cha và giúp thay thế cộng tác viên dễ hơn.

## 5. Ví dụ Java 17 hoàn chỉnh: cả ba nguyên lý trong một chương trình

Lưu toàn bộ đoạn sau vào tệp **`ConceptsDemo.java`**. Đoạn mã độc lập, sử dụng số nguyên làm đơn vị tiền giả định để tập trung vào OOP; hệ thống tiền tệ thực tế cần mô hình chính xác hơn, chính sách giao dịch và xử lý đồng thời phù hợp.

```java
interface PaymentMethod {
    String pay(int amount);
}

abstract class Wallet implements PaymentMethod {
    private int balance;

    protected Wallet(int initialBalance) {
        if (initialBalance < 0) {
            throw new IllegalArgumentException("Số dư đầu phải không âm");
        }
        this.balance = initialBalance;
    }

    public final int getBalance() {
        return balance;
    }

    protected final boolean deduct(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Số tiền phải dương");
        }
        if (amount > balance) {
            return false;
        }
        balance -= amount;
        return true;
    }
}

final class GiftWallet extends Wallet {
    GiftWallet(int initialBalance) {
        super(initialBalance);
    }

    @Override
    public String pay(int amount) {
        return deduct(amount)
                ? "Đã thanh toán " + amount
                : "Không đủ số dư";
    }
}

public class ConceptsDemo {
    public static void main(String[] args) {
        GiftWallet wallet = new GiftWallet(100);
        PaymentMethod method = wallet;

        System.out.println(method.pay(40));
        System.out.println("Số dư còn lại: " + wallet.getBalance());
        System.out.println(method.pay(100));
        System.out.println("Số dư còn lại: " + wallet.getBalance());
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac -encoding UTF-8 ConceptsDemo.java
java ConceptsDemo
```

Kết quả chuẩn trên stdout:

```text
Đã thanh toán 40
Số dư còn lại: 60
Không đủ số dư
Số dư còn lại: 60
```

**Giải mã thiết kế:**

1. **Trừu tượng hóa:** `PaymentMethod` quy định khả năng `pay` mà người gọi sử dụng. Biến `PaymentMethod method` không cần biết thuật toán trừ tiền bên trong. Lời gọi `method.pay(40)` được điều phối đến hiện thực của `GiftWallet` khi chạy.
2. **Đóng gói:** `Wallet.balance` là `private`; bên ngoài không thể gán trực tiếp. Constructor từ chối số dư âm; `deduct` từ chối số tiền không dương và không làm số dư giảm dưới 0. `getBalance` chỉ cho phép đọc. `protected final deduct` cho phép lớp con sử dụng thao tác có kiểm tra mà không tự sửa trực tiếp trường riêng.
3. **Kế thừa:** `GiftWallet extends Wallet` nhận hành vi quản lý số dư được phép dùng từ lớp cha, gọi `super(initialBalance)` và hiện thực `pay`. Vì `Wallet implements PaymentMethod`, đối tượng `GiftWallet` cũng dùng được tại vị trí cần `PaymentMethod`.
4. **Đa hình (polymorphism), khái niệm liên quan:** biến khai báo kiểu interface `PaymentMethod` tham chiếu đến đối tượng thực `GiftWallet`; Java chọn phương thức instance override tương ứng khi chạy. Đa hình thường được tạo điều kiện bởi trừu tượng hóa và quan hệ kiểu con, nhưng không đồng nghĩa với cả ba nguyên lý trên.

Dòng `method.pay(100)` trả về «Không đủ số dư» vì chỉ còn 60. Sau lời gọi thất bại, số dư vẫn là 60. Đây là một minh chứng kiểm soát thay đổi trạng thái bằng đóng gói. Mẫu ví dụ không xử lý nhiều luồng và không nhằm làm mô hình ví điện tử hoàn chỉnh.

## 6. Ba nguyên lý độc lập nhưng có thể phối hợp

**Có trừu tượng hóa mà thiếu đóng gói:** một lớp triển khai `PaymentMethod` có thể vẫn lộ `public int balance`. Người gọi có hợp đồng thanh toán, nhưng vẫn được phép làm hỏng trạng thái. Sự tồn tại của interface không tự khóa các trường nội bộ.

**Có đóng gói mà không cần kế thừa:** một lớp `final Counter` giữ `private int count` và cung cấp `increment()`, `getCount()` có thể đóng gói tốt mà không cần tự định nghĩa lớp con nào. Mọi lớp Java đều có quan hệ với `Object`, nhưng thiết kế đóng gói này không phụ thuộc vào việc tạo một hệ phân cấp kế thừa nghiệp vụ.

**Có kế thừa mà trừu tượng hóa yếu:** một lớp con có thể `extends` lớp cha phơi bày quá nhiều thao tác không liên quan. Tái sử dụng mã không tự biến API thành một hợp đồng rõ ràng.

**Cả ba kết hợp:** interface mô tả điều người dùng cần; lớp cơ sở giữ và kiểm soát trạng thái; lớp chuyên biệt mở rộng hành vi của lớp cơ sở. Đây là một cách tổ chức hợp lý *khi* thực sự tồn tại quan hệ kiểu con. Không nhất thiết bài toán nào cũng cần đủ ba kỹ thuật.

## 7. Cách quyết định khi thiết kế

| Tình huống | Ưu tiên suy nghĩ về | Vì sao |
|---|---|---|
| Nhiều cách gửi thông báo nhưng bên gọi chỉ cần `send(message)` | Trừu tượng hóa bằng hợp đồng thích hợp | Bên gọi không phụ thuộc SMTP, HTTP hoặc cơ chế cụ thể |
| Số dư, tuổi hoặc trạng thái đơn hàng phải tuân thủ quy tắc | Đóng gói và API chuyển trạng thái | Ngăn mã ngoài đưa đối tượng vào trạng thái không hợp lệ |
| `SavingsAccount` thật sự là một `Account` theo hợp đồng đã nêu | Kế thừa có kiểm tra LSP | Có thể dùng kiểu con tại vị trí đòi hỏi kiểu cha |
| `Car` dùng `Engine` | Composition | Xe **có** động cơ, không **là** động cơ |
| Nhiều lớp chỉ trùng vài hàm tiện ích | Composition hoặc dịch vụ hỗ trợ | Tránh ép thành quan hệ kiểu con giả tạo |

Một quy trình thực hành hiệu quả: (1) xác định khả năng bên ngoài cần dùng; (2) xác định trạng thái, quy tắc và dữ liệu nào phải được bảo vệ; (3) cuối cùng mới quyết định có quan hệ kiểu con thật sự hay nên kết hợp các đối tượng. Các bước này phục vụ thiết kế, không phải một luật bắt buộc áp dụng máy móc cho mọi chương trình.

## 8. Lỗi nhầm lẫn thường gặp

**“Abstraction = `abstract class`, encapsulation = `private`, inheritance = `extends`.”** Đây chỉ là một số công cụ cú pháp. Trừu tượng hóa có thể đến từ interface hoặc public API của lớp thường; đóng gói đòi hỏi kiểm soát hành vi và bất biến; quan hệ kiểu con còn có qua `implements`.

**“Abstraction và encapsulation đều ẩn chi tiết, vậy là một.”** Trừu tượng hóa quyết định *cách người dùng nhìn và sử dụng khả năng*; đóng gói kiểm soát *quyền truy cập, cách trạng thái được sửa và cách bất biến được giữ*. Một API có thể đơn giản nhưng làm lộ mutable state, hoặc bảo vệ state kỹ nhưng vẫn có API rườm rà.

**“Trường `private` + getter/setter cho hết là encapsulation tốt.”** Setter công khai không kiểm tra có thể triệt tiêu lợi ích. Hãy ưu tiên những hành động có ý nghĩa nghiệp vụ và kiểm soát điều kiện trước khi thay đổi.

**“Kế thừa luôn tốt hơn composition vì tái sử dụng code.”** Kế thừa ràng buộc kiểu con vào hợp đồng và hành vi của kiểu cha. Khi chỉ cần dùng chức năng của đối tượng khác, composition thường hợp lý hơn.

**“Override chỉ là viết lại phương thức giống tên.”** Override cần đúng chữ ký và các ràng buộc của Java; quan trọng hơn, hành vi mới phải giữ hợp đồng mà người dùng kiểu cha được quyền kỳ vọng. Nên dùng `@Override` để phát hiện nhầm lẫn lúc biên dịch.

**“Interface chỉ có phương thức trừu tượng, abstract class chỉ có phương thức trừu tượng.”** Sai trong Java hiện đại: interface có thể có phương thức `default`/`static` và phương thức phụ trợ `private`; abstract class có thể chứa dữ liệu, constructor và phương thức đã cài đặt.

## 9. Tự kiểm tra

1. Một `BankAccount` có `private balance` nhưng cho phép `setBalance(-500)`. Có đủ đóng gói tốt chưa? **Chưa**: trạng thái không được bảo vệ bằng quy tắc hợp lệ.
2. `OrderService` nhận tham số `PaymentMethod` thay vì `GiftWallet`. Nguyên lý nào nổi bật? **Trừu tượng hóa**: phụ thuộc hợp đồng chung; đa hình cho phép nhiều hiện thực.
3. `Cat extends Animal` để dùng lại và chuyên biệt hóa hành vi `makeSound()`. Quan hệ nào đang dùng? **Kế thừa**; cần kiểm tra mọi `Cat` có đáp ứng hợp đồng `Animal` hay không.
4. `Car extends Engine` chỉ để gọi `start()` có hợp lý không? **Không**: quan hệ thực tế là *has-a*, nên cân nhắc `Car` giữ một đối tượng `Engine`.
5. Có thể thiết kế lớp đóng gói tốt mà không tạo interface hoặc abstract class riêng không? **Có**: giữ trạng thái riêng, cung cấp thao tác có kiểm soát và duy trì bất biến.

**Ghi nhớ khi đọc code Java:** nhìn vào **API/hợp đồng** để nhận diện trừu tượng hóa; nhìn vào **trạng thái, quyền truy cập và kiểm tra bất biến** để đánh giá đóng gói; nhìn vào **quan hệ `extends`/`implements` và khả năng thay thế** để đánh giá kế thừa/kiểu con.