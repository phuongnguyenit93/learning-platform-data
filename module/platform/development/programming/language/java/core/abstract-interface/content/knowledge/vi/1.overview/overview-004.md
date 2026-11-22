# Vai trò của lớp trừu tượng (abstract class) và interface trong Java

## 1. Bài toán mà hai cơ chế giải quyết

Khi nhiều đối tượng có điểm chung, Java cho phép mô tả **phần ổn định** ở một kiểu trừu tượng và để từng kiểu cụ thể quyết định **phần thay đổi**. Nhờ đó, mã sử dụng có thể làm việc với kiểu chung thay vì biết từng lớp triển khai.

- **Lớp trừu tượng (abstract class)** phù hợp khi các lớp con thực sự thuộc cùng một họ, có trạng thái hoặc cách xử lý chung, nhưng vẫn cần một số bước do lớp con cung cấp.
- **Interface** mô tả một **hợp đồng năng lực/hành vi** mà nhiều lớp, kể cả các lớp không cùng họ kế thừa, có thể thực hiện.
- Cả hai đều hỗ trợ **đa hình**: biến có kiểu cha/interface có thể tham chiếu tới đối tượng thuộc lớp triển khai; lời gọi phương thức instance sẽ chạy phiên bản phù hợp với đối tượng thực tế.

Ví dụ về ý tưởng: nhiều loại thuê bao đều có người đăng ký và quy trình báo phí giống nhau, nên có thể dùng lớp trừu tượng `Subscription`. Việc gửi thông báo có thể thực hiện qua email, console hoặc hệ thống khác, nên có thể mô tả bằng interface `Channel`. Đây là **hai trục thay đổi độc lập**.

## 2. Lớp trừu tượng: chia sẻ nền tảng và quy định khung xử lý

Khai báo một lớp bằng từ khóa `abstract`:

```java
abstract class Vehicle {
    private final String id;

    protected Vehicle(String id) {
        this.id = id;
    }

    public String id() {
        return id;
    }

    public abstract int maxSpeed();
}
```

Đoạn trên là khai báo kiểu, không phải chương trình độc lập có `main`. Nó minh họa rằng lớp trừu tượng có thể chứa cả **dữ liệu instance**, **constructor**, **phương thức đã triển khai** và **phương thức trừu tượng**.

Các đặc điểm cần hiểu:

1. Không thể khởi tạo trực tiếp `new Vehicle("V1")`. Phải tạo đối tượng của một lớp con cụ thể.
2. Constructor của lớp trừu tượng vẫn được gọi như một phần của chuỗi khởi tạo lớp con; nó có thể thiết lập và kiểm tra các bất biến chung.
3. Phương thức `abstract` chỉ khai báo chữ ký, không có thân; lớp con cụ thể phải triển khai những phương thức trừu tượng còn thiếu. Một lớp con chưa triển khai đủ phải tiếp tục là `abstract`.
4. Lớp trừu tượng cũng có thể không khai báo phương thức `abstract` nào: từ khóa `abstract` vẫn ngăn khởi tạo trực tiếp và biểu đạt rằng đây là lớp nền.
5. Có thể dùng `private`, `protected`, `public`, `static`, `final`, phương thức cụ thể và trường instance theo các quy tắc thông thường của lớp Java. Một phương thức không thể đồng thời là `abstract` và `final` vì một bên đòi lớp con triển khai, bên kia cấm ghi đè.
6. Lớp Java chỉ có **một lớp cha trực tiếp** (`extends` một class); lớp trừu tượng không làm thay đổi giới hạn này.

Một cách dùng quan trọng là **Template Method**: lớp cha giữ thứ tự các bước chung, các phương thức trừu tượng tạo điểm mở rộng. Khi quy trình phải thống nhất, có thể đánh dấu phương thức điều phối là `final` và chỉ cho lớp con thay đổi những bước được định nghĩa rõ.

## 3. Interface: hợp đồng để các lớp cộng tác

Ví dụ:

```java
interface Payable {
    int amount();

    default boolean isFree() {
        return amount() == 0;
    }
}
```

`Payable` yêu cầu lớp triển khai cung cấp `amount()`; phương thức `isFree()` là hành vi mặc định dùng chung.

Những quy tắc quan trọng trong Java 17+:

- Phương thức thông thường khai báo trong interface là `public abstract` theo ngầm định. Một lớp triển khai phải dùng phạm vi `public` cho phương thức ghi đè; không được giảm xuống package-private hoặc `protected`.
- Interface có thể có phương thức `default` (có thân và được thừa hưởng), `static` (gọi qua tên interface) và `private`/`private static` (hỗ trợ tái sử dụng logic bên trong interface). Không phải mọi phương thức interface đều trừu tượng.
- Trường khai báo trong interface luôn mang tính `public static final`, tức hằng số; interface **không có trường instance hoặc constructor** để giữ trạng thái riêng của từng đối tượng.
- Một class có thể `implements` **nhiều interface**, trong khi một interface có thể `extends` nhiều interface. Điều này cho phép kết hợp các năng lực độc lập mà không cần đa kế thừa class.
- `default` không biến interface thành nơi lý tưởng để chứa mọi xử lý chung hoặc trạng thái. Nó hữu ích để cung cấp hành vi mặc định có liên quan chặt tới hợp đồng; lớp triển khai vẫn có thể ghi đè.
- Interface có thể là kiểu của tham số, biến, trường hoặc kiểu trả về. Nhờ đó, thành phần nhận `Payable` chỉ cần biết `amount()`, không cần biết lớp cụ thể nào cung cấp.

Ví dụ một lớp có hai năng lực:

```java
interface Printable {
    void print();
}

interface Exportable {
    void export();
}

final class Report implements Printable, Exportable {
    @Override
    public void print() {
        System.out.println("Print report");
    }

    @Override
    public void export() {
        System.out.println("Export report");
    }
}
```

Các khai báo này biên dịch được như một nhóm kiểu, nhưng không có `main` để chạy độc lập. `Report` nhận hai hợp đồng hành vi mà không cần kế thừa hai lớp cha.

## 4. So sánh và quan hệ giữa hai cơ chế

| Tiêu chí | Abstract class | Interface |
| --- | --- | --- |
| Câu hỏi thiết kế | “Các lớp này cùng là một loại gì, và chia sẻ nền tảng nào?” | “Đối tượng này có thể thực hiện năng lực gì?” |
| Quan hệ thường dùng | `extends` một lớp cha | `implements` một hoặc nhiều interface |
| Trạng thái instance | Có thể chứa trường instance và constructor | Không có trường instance hoặc constructor; trường là hằng số |
| Mã xử lý chung | Phương thức cụ thể, `protected`, `final`, template method | `default`, `static`, `private` theo quy tắc interface |
| Điều bắt buộc ở lớp con | Triển khai phương thức trừu tượng còn thiếu | Triển khai phương thức trừu tượng còn thiếu từ các interface |
| Tính linh hoạt | Thích hợp với họ lớp có cấu trúc chung | Hợp tác giữa các họ lớp khác nhau, dễ thay thế implementation |
| Số lượng quan hệ trực tiếp | Một class cha | Nhiều interface |

**Hai cơ chế có thể kết hợp:** một lớp trừu tượng có thể `implements` một hay nhiều interface và để các lớp con hoàn tất hợp đồng. Một lớp cụ thể cũng có thể vừa `extends` một abstract class, vừa `implements` nhiều interface.

Điểm mấu chốt là **chọn theo quan hệ thiết kế**, không dựa vào việc interface “mạnh hơn” hay abstract class “cũ hơn”. Nếu chỉ cần công bố khả năng để người gọi phụ thuộc vào kiểu chung, interface thường là lựa chọn đơn giản. Nếu thực sự cần chia sẻ trạng thái hợp lệ và điều phối vòng đời/hành vi giữa các lớp cùng họ, abstract class có giá trị rõ ràng.

## 5. Ví dụ Java 17+ chạy được: dùng đồng thời abstract class và interface

Lưu mã sau vào **`Demo.java`** (không khai báo `package`):

```java
interface Channel {
    void send(String message);

    default void welcome() {
        send("Welcome!");
    }
}

abstract class Subscription {
    private final String subscriber;

    protected Subscription(String subscriber) {
        if (subscriber == null || subscriber.isBlank()) {
            throw new IllegalArgumentException("Subscriber is required");
        }
        this.subscriber = subscriber;
    }

    public final void report(Channel channel) {
        channel.send(subscriber + ": " + monthlyPrice() + " USD/month");
    }

    protected abstract int monthlyPrice();
}

final class FreeSubscription extends Subscription {
    FreeSubscription(String subscriber) {
        super(subscriber);
    }

    @Override
    protected int monthlyPrice() {
        return 0;
    }
}

final class PremiumSubscription extends Subscription {
    PremiumSubscription(String subscriber) {
        super(subscriber);
    }

    @Override
    protected int monthlyPrice() {
        return 15;
    }
}

final class ConsoleChannel implements Channel {
    @Override
    public void send(String message) {
        System.out.println(message);
    }
}

public class Demo {
    public static void main(String[] args) {
        Channel channel = new ConsoleChannel();
        Subscription[] plans = {
            new FreeSubscription("Lan"),
            new PremiumSubscription("Minh")
        };

        for (Subscription plan : plans) {
            plan.report(channel);
        }
        channel.welcome();
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp (JDK 17 trở lên):

```bash
javac Demo.java
java Demo
```

Kết quả chuẩn trên stdout:

```text
Lan: 0 USD/month
Minh: 15 USD/month
Welcome!
```

Đọc luồng chạy theo từng bước:

1. `new FreeSubscription("Lan")` và `new PremiumSubscription("Minh")` đều đi qua constructor `Subscription`, nên phép kiểm tra tên đăng ký dùng chung không bị lặp ở từng lớp con.
2. Mảng `Subscription[]` giữ nhiều lớp triển khai. Phương thức `report()` là cùng một quy trình chung; lời gọi `monthlyPrice()` được phân phối theo **kiểu thực tế** của phần tử: `0` đối với `FreeSubscription` và `15` đối với `PremiumSubscription`.
3. `report(Channel channel)` chỉ phụ thuộc vào hợp đồng gửi thông báo. Vì vậy có thể thay `ConsoleChannel` bằng implementation khác mà không sửa `Subscription` hoặc hai lớp con.
4. `channel.welcome()` sử dụng phương thức `default` của interface, sau đó gọi `send()` của implementation thực tế để in dòng cuối.
5. `final` trên `report()` giữ nguyên thứ tự xử lý mà lớp nền đã thiết kế; các lớp con chỉ quyết định mức phí qua điểm mở rộng `monthlyPrice()`.

Đây là ví dụ của **đa hình + kế thừa có kiểm soát + lập trình hướng hợp đồng**. Phần phụ thuộc vào cấu trúc chung dùng abstract class; phần giao tiếp với dịch vụ bên ngoài dùng interface.

## 6. Khi nào nên chọn cách nào?

**Chọn abstract class khi:**

- Các lớp con có quan hệ “is-a” rõ ràng, ví dụ các biến thể của một đối tượng miền nghiệp vụ.
- Chúng cần cùng một trạng thái instance được bảo vệ bởi constructor và những bất biến chung.
- Một thuật toán có khung bước ổn định, còn một vài bước có thể được lớp con triển khai khác nhau.
- Bạn có lý do vững chắc để duy trì một lớp nền duy nhất và chấp nhận sự ràng buộc do kế thừa gây ra.

**Chọn interface khi:**

- Cần định nghĩa hợp đồng cho nhiều implementation không cùng một họ lớp, ví dụ `Comparable`, `Runnable` hoặc một interface ứng dụng như `Channel`.
- Mã phía người dùng cần đổi implementation thông qua tham số, dependency injection hoặc kiểm thử với đối tượng giả.
- Một class phải kết hợp nhiều năng lực độc lập (`Printable`, `Exportable`, …).
- Hợp đồng nhỏ, tập trung vào hành vi; không có nhu cầu chia sẻ trạng thái instance.

**Cân nhắc composition (chứa và ủy quyền) khi:** chỉ muốn tái sử dụng cách xử lý, nhưng quan hệ “is-a” không đúng. Ví dụ `OrderService` *có một* `Channel` để gửi sự kiện, không nhất thiết *là một* `Channel`. Kế thừa lớp nền quá sớm khiến việc thay đổi phụ thuộc và phân chia trách nhiệm về sau khó hơn.

Một cách tổ chức hay gặp là **interface làm API cho người dùng, abstract class cung cấp implementation nền tùy chọn**. Ví dụ, có thể có `interface Storage` và `abstract class BaseStorage implements Storage`; một implementation được quyền kế thừa `BaseStorage` hoặc triển khai trực tiếp `Storage`. Lớp nền là tiện ích tùy chọn, không trở thành yêu cầu của hợp đồng.

## 7. Các bẫy hay gặp

**Nhầm `extends` với `implements`.** Class kế thừa class khác bằng `extends`; class thực hiện interface bằng `implements`. Interface mở rộng interface khác bằng `extends`.

**Nghĩ interface luôn hoàn toàn không có implementation.** Kể từ Java 8 có `default`/`static`, từ Java 9 có phương thức `private`. Tuy vậy interface vẫn không có state instance hoặc constructor.

**Nghĩ abstract class không có constructor hoặc mọi phương thức phải abstract.** Cả hai đều sai. Abstract class có thể chứa constructor, trường, phương thức cụ thể và thậm chí không có phương thức abstract nào.

**Thu hẹp visibility khi implement interface.** Nếu `interface Task { void run(); }` thì phương thức tương ứng ở lớp triển khai phải là `public void run()`. Viết `void run()` (package-private) sẽ lỗi biên dịch.

**Dùng kế thừa chỉ để lấy lại vài dòng code.** Nếu hai loại không thật sự thay thế nhau được, quan hệ cha–con có thể vi phạm nguyên tắc thay thế Liskov. Hãy cân nhắc tách logic chung thành một đối tượng cộng tác hoặc một utility phù hợp.

**Tạo interface quá lớn.** Interface buộc mọi implementation gánh các phương thức không liên quan làm hợp đồng khó dùng và khó kiểm thử. Ưu tiên hợp đồng nhỏ, có trách nhiệm rõ ràng (Interface Segregation).

**Hai interface có `default` trùng chữ ký.** Nếu một lớp triển khai cả hai interface cùng đưa ra phương thức mặc định xung đột, lớp đó phải tự override để giải quyết. Chẳng hạn:

```java
interface A {
    default String name() {
        return "A";
    }
}

interface B {
    default String name() {
        return "B";
    }
}

final class C implements A, B {
    @Override
    public String name() {
        return A.super.name() + B.super.name();
    }
}
```

Đoạn này là ví dụ khai báo kiểu, không phải chương trình có `main`. Kết quả gọi `new C().name()` là chuỗi `"AB"`. Không thể chỉ dựa vào thứ tự liệt kê `implements A, B` để Java tự chọn một phương thức mặc định.

**Đưa dữ liệu thay đổi vào field của interface.** Mọi field interface là `public static final`, không phải dữ liệu của mỗi instance. Dữ liệu thuộc riêng từng đối tượng nên đặt trong class hoặc record thích hợp.

## 8. Câu hỏi tự kiểm tra

1. Vì sao `Subscription` cần constructor dù không thể tạo trực tiếp đối tượng `Subscription`?
2. Khi thêm `EmailChannel implements Channel`, có cần sửa `Subscription.report()` không? Tại sao?
3. Nếu `FreeSubscription` không triển khai `monthlyPrice()`, lớp đó phải khai báo như thế nào?
4. Lúc nào việc thêm một abstract class cha chỉ để tái sử dụng code sẽ làm thiết kế kém linh hoạt?
5. Vì sao lớp `C implements A, B` ở ví dụ cuối bắt buộc phải override `name()`?

**Tự đối chiếu:** (1) để thiết lập/kiểm tra trạng thái chung khi lớp con được khởi tạo; (2) không, vì `report()` nhận `Channel`; (3) phải là `abstract` hoặc vẫn sẽ lỗi biên dịch nếu là lớp cụ thể; (4) khi các lớp không có quan hệ is-a/thay thế lẫn nhau hợp lệ; (5) vì hai default method cùng chữ ký gây xung đột.

Nhớ quy tắc chọn thiết kế: **abstract class để chia sẻ nền tảng của một họ lớp; interface để công bố năng lực và làm điểm kết nối giữa các implementation**. Có thể phối hợp cả hai khi mỗi cơ chế thực sự giải quyết một nhu cầu riêng.