# Qualified enum constant trong các switch phù hợp

Java 21 cho phép dùng qualified enum constant trong nhãn `case`, với cú pháp `TenEnum.TEN_HANG`. Cách viết này hữu ích khi kiểu tĩnh của giá trị được switch không phải chính kiểu enum, mà là một kiểu cha hoặc interface mà enum triển khai. Nhờ ghi rõ tên enum, một switch có thể phân biệt các hằng số đến từ nhiều enum cùng thực hiện một hợp đồng.

Trong phạm vi `JAVA_VERSION_JAVA21` (Java 21), qualified enum constant là một phần của Pattern Matching for `switch` đã ổn định trong JEP 441. Tính năng này đặc biệt phù hợp khi một sealed interface có các enum làm kiểu con được phép và mỗi hằng số cần một cách xử lý riêng. Đây là nhãn hằng số enum, không phải type pattern hay record pattern.

## Vì sao cần qualified enum constant?

Khi selector có kiểu enum, cách viết quen thuộc là dùng tên hằng số:

```java
enum OrderStatus {
    NEW, PAID, CANCELLED
}

static String label(OrderStatus status) {
    return switch (status) {
        case NEW -> "Mới tạo";
        case PAID -> "Đã thanh toán";
        case CANCELLED -> "Đã hủy";
    };
}
```

Ở đây kiểu tĩnh của `status` là `OrderStatus`, nên các hằng số `NEW`, `PAID` và `CANCELLED` đã đủ rõ. Nhưng trong một hệ thống có nhiều enum cùng triển khai một interface, selector có thể chỉ được khai báo bằng kiểu interface. Khi đó, tên hằng số cần kèm tên enum để xác định chính xác nguồn gốc.

Ví dụ, một ứng dụng xử lý sự kiện từ nhiều nhóm:

```java
interface ApplicationEvent {}

enum OrderEvent implements ApplicationEvent {
    CREATED, PAID, CANCELLED
}

enum AccountEvent implements ApplicationEvent {
    OPENED, LOCKED, CLOSED
}
```

Nếu một phương thức nhận `ApplicationEvent`, selector có thể là bất kỳ hằng số nào của hai enum trên. Qualified enum constant cho phép viết `OrderEvent.PAID` hoặc `AccountEvent.LOCKED`, tránh nhầm lẫn khi các enum có hằng số trùng tên.

## Cú pháp và điều kiện sử dụng

Qualified enum constant có dạng:

```java
case TenEnum.TEN_HANG -> ...;
```

Điều kiện quan trọng là kiểu enum chứa hằng số phải là subtype của kiểu selector. Ví dụ, nếu selector có kiểu `ApplicationEvent`, enum `OrderEvent` và `AccountEvent` có thể xuất hiện trong nhãn vì cả hai đều triển khai interface đó.

Khi selector có kiểu enum cụ thể, thông thường dùng nhãn enum không cần qualification như `case PAID`. Khi selector có kiểu cha hoặc interface, dùng tên enum để định danh hằng số như `case OrderEvent.PAID`. Qualified enum constant là một nhãn hằng số; nó không tạo biến để bind đối tượng như `case OrderEvent event`.

## Dùng nhiều enum qua một interface mở

Nếu interface được thiết kế để cho phép các module khác bổ sung kiểu triển khai, switch không thể biết trước mọi giá trị có thể xuất hiện. Qualified enum constant vẫn giúp xử lý các hằng số đã biết, còn `default` bao phủ những kiểu hoặc giá trị khác:

```java
interface ApplicationEvent {}

enum OrderEvent implements ApplicationEvent {
    CREATED, PAID, CANCELLED
}

enum AccountEvent implements ApplicationEvent {
    OPENED, LOCKED, CLOSED
}

static String describe(ApplicationEvent event) {
    return switch (event) {
        case null -> "Không có sự kiện";
        case OrderEvent.CREATED -> "Đơn hàng được tạo";
        case OrderEvent.PAID -> "Đơn hàng đã thanh toán";
        case OrderEvent.CANCELLED -> "Đơn hàng đã hủy";
        case AccountEvent.OPENED -> "Tài khoản được mở";
        case AccountEvent.LOCKED -> "Tài khoản bị khóa";
        case AccountEvent.CLOSED -> "Tài khoản đã đóng";
        default -> "Sự kiện chưa được hỗ trợ";
    };
}
```

Mỗi nhãn chỉ khớp đúng một hằng số enum. `default` cần thiết vì `ApplicationEvent` là interface mở: một class khác hoặc một enum khác vẫn có thể triển khai nó trong phạm vi quyền truy cập hợp lệ. `case null` xử lý riêng giá trị rỗng; `default` không bao phủ `null`.

Nếu ứng dụng cần xử lý tất cả hằng số của một enum theo cùng cách, type pattern có thể ngắn hơn:

```java
static String describe(ApplicationEvent event) {
    return switch (event) {
        case null -> "Không có sự kiện";
        case OrderEvent orderEvent -> "Sự kiện đơn hàng: " + orderEvent;
        case AccountEvent accountEvent -> "Sự kiện tài khoản: " + accountEvent;
        default -> "Sự kiện mở rộng: " + event;
    };
}
```

`case OrderEvent orderEvent` là type pattern: nó khớp mọi hằng số của enum `OrderEvent` và bind giá trị vào biến `orderEvent`. Hãy chọn qualified enum constants khi từng hằng số có hành vi riêng; chọn type pattern khi mọi hằng số của một enum có cùng cách xử lý.

## Kết hợp với sealed interface để switch exhaustive

Khi tập hợp kiểu sự kiện thực sự đóng, có thể khai báo interface là `sealed` và liệt kê các enum được phép triển khai trực tiếp. Khi switch liệt kê đủ các hằng số của từng enum được phép, trình biên dịch có thể kiểm tra tính đầy đủ mà không cần `default`.

```java
sealed interface CardClassification permits Suit, Tarot {}

enum Suit implements CardClassification {
    CLUBS, DIAMONDS, HEARTS, SPADES
}

enum Tarot implements CardClassification {
    CUPS, COINS, SWORDS, WANDS
}

static String describe(CardClassification card) {
    return switch (card) {
        case null -> "Không có lá bài";
        case Suit.CLUBS -> "Chuồn";
        case Suit.DIAMONDS -> "Rô";
        case Suit.HEARTS -> "Cơ";
        case Suit.SPADES -> "Bích";
        case Tarot.CUPS -> "Cốc";
        case Tarot.COINS -> "Tiền";
        case Tarot.SWORDS -> "Kiếm";
        case Tarot.WANDS -> "Gậy";
    };
}
```

Ở đây, kiểu selector là `CardClassification`, không phải `Suit` hay `Tarot`. Vì vậy, mỗi hằng số được ghi kèm enum chứa nó. `CardClassification` là sealed và chỉ cho phép `Suit` cùng `Tarot` làm kiểu con trực tiếp. Hai enum đã liệt kê các hằng số cụ thể, và switch xử lý tất cả các hằng số đó. Không cần nhánh `default` cho một biến thể chưa biết.

Nếu thêm một hằng số vào `Suit` hoặc `Tarot`, hoặc thêm một kiểu con được phép mới vào `CardClassification`, switch có thể không còn exhaustive. Biên dịch lại sẽ giúp phát hiện nơi cần bổ sung xử lý. Đây là lợi ích quan trọng khi mô hình đóng phản ánh đúng quy tắc nghiệp vụ.

Một enum thông thường là kiểu con cuối cùng (implicitly final) của interface sealed mà nó triển khai, nên có thể là một kiểu con được phép. Các enum và sealed interface cũng phải tuân thủ quy tắc module/package áp dụng cho sealed hierarchy: cùng named module, hoặc cùng package nếu nằm trong unnamed module.

## Qualified enum constant khác type pattern thế nào?

Hai dạng nhãn có mục đích khác nhau:

| Nhãn | Ví dụ | Giá trị được khớp |
| --- | --- | --- |
| Qualified enum constant | `case OrderEvent.PAID` | Chính xác hằng số `PAID` của enum `OrderEvent` |
| Type pattern | `case OrderEvent event` | Mọi giá trị có kiểu `OrderEvent`, rồi bind vào `event` |
| Default label | `default` | Những giá trị không khớp nhãn khác, ngoại trừ `null` |

Ví dụ, nếu cần xử lý riêng `CREATED` và `PAID`, nhưng gom các hằng số đơn hàng còn lại vào một nhánh:

```java
static String describe(ApplicationEvent event) {
    return switch (event) {
        case null -> "Không có sự kiện";
        case OrderEvent.CREATED -> "Đơn hàng vừa được tạo";
        case OrderEvent.PAID -> "Đơn hàng đã được thanh toán";
        case OrderEvent orderEvent -> "Sự kiện đơn hàng khác: " + orderEvent;
        case AccountEvent accountEvent -> "Sự kiện tài khoản: " + accountEvent;
        default -> "Sự kiện mở rộng: " + event;
    };
}
```

Các hằng số cụ thể được xét trước type pattern `OrderEvent orderEvent`, vì type pattern này khớp mọi hằng số của `OrderEvent`. Nếu đặt type pattern lên trước, những nhãn `OrderEvent.CREATED` và `OrderEvent.PAID` phía sau sẽ bị nhánh rộng bao phủ và không thể được chọn. Đây là quy tắc dominance: một nhãn rộng không được đứng trước nhãn hẹp mà nó bao phủ.

## Null, default và tính đầy đủ

Khi selector có kiểu interface hoặc class:

- Qualified enum constant chỉ khớp hằng số được chỉ định.
- Type pattern chỉ khớp giá trị không null thuộc kiểu tương ứng.
- `default` không khớp với `null`.
- Nếu selector là `null` mà switch không có `case null`, switch ném `NullPointerException` khi chạy.

Đối với interface mở, thường cần `default` hoặc một pattern bao phủ các kiểu mở rộng. Đối với sealed interface, có thể liệt kê tất cả kiểu con và hằng số enum để switch exhaustive. Không thêm `default` theo thói quen nếu muốn compiler phát hiện khi sealed hierarchy thay đổi.

Nếu hợp đồng của phương thức cấm `null`, có thể kiểm tra trước switch:

```java
static String describeRequired(ApplicationEvent event) {
    java.util.Objects.requireNonNull(event, "event");

    return switch (event) {
        case OrderEvent.CREATED -> "Đơn hàng được tạo";
        case OrderEvent.PAID -> "Đơn hàng đã thanh toán";
        case OrderEvent.CANCELLED -> "Đơn hàng đã hủy";
        case AccountEvent.OPENED -> "Tài khoản được mở";
        case AccountEvent.LOCKED -> "Tài khoản bị khóa";
        case AccountEvent.CLOSED -> "Tài khoản đã đóng";
        default -> "Sự kiện chưa được hỗ trợ";
    };
}
```

Việc kiểm tra trước switch làm rõ hợp đồng đầu vào. Với interface mở, `default` vẫn cần để xử lý các kiểu triển khai khác ngoài hai enum đã biết.

## Khi nào nên dùng qualified enum constant?

| Tình huống | Cách viết nên cân nhắc |
| --- | --- |
| Selector có kiểu enum cụ thể | Dùng enum constant thông thường như `case PAID` |
| Selector có kiểu interface/supertype và cần xử lý từng enum constant riêng | Dùng qualified enum constant như `case OrderEvent.PAID` |
| Mọi hằng số của một enum có cùng hành vi | Dùng type pattern như `case OrderEvent event` |
| Interface mở và còn kiểu triển khai chưa biết | Bổ sung `default` hoặc pattern bao phủ phần mở rộng |
| Sealed interface được triển khai bởi các enum có tập hằng số đã biết | Liệt kê qualified enum constants để switch exhaustive |
| Chỉ phân nhánh theo trạng thái trong cùng một enum | Enum switch thông thường có thể dễ đọc hơn |

Qualified enum constants đặc biệt hữu ích khi nhiều enum cùng triển khai một interface và có thể dùng các tên hằng số giống nhau. Chúng giúp switch thể hiện chính xác enum nào đang được xử lý mà không cần ép kiểu trước hoặc viết chuỗi `if/else` để phân biệt.

Không cần dùng qualified enum constant nếu selector đã có kiểu enum cụ thể. Cũng không cần liệt kê từng hằng số nếu tất cả giá trị của một enum đều được xử lý giống nhau; type pattern có thể diễn đạt ý định đó ngắn gọn hơn.

## Quy trình áp dụng trong dự án Java 21

1. **Kiểm tra kiểu tĩnh của selector.** Nếu selector là chính enum, dùng nhãn enum thông thường; nếu là interface hoặc supertype, cân nhắc qualified enum constant.
2. **Xác định quan hệ kiểu.** Enum được ghi trong nhãn phải là subtype của kiểu selector.
3. **Chọn mức xử lý.** Dùng qualified enum constant cho từng hằng số; dùng type pattern nếu xử lý mọi hằng số của một enum theo cùng cách.
4. **Đánh giá hierarchy.** Nếu interface mở, dự phòng các kiểu triển khai khác; nếu sealed, xác định toàn bộ kiểu con và các hằng số cần bao phủ.
5. **Xử lý null rõ ràng.** Dùng `case null` khi null là đầu vào hợp lệ cần xử lý; nếu không, xác thực trước switch.
6. **Kiểm tra dominance và exhaustiveness.** Đặt hằng số cụ thể trước type pattern rộng; biên dịch lại sau khi thay đổi enum hoặc sealed hierarchy.
7. **Biên dịch theo Java 21.** Qualified enum constant trong switch là cú pháp ổn định của Java 21, không cần `--enable-preview`.

Qualified enum constant giúp switch trên một kiểu cha vẫn phân biệt được từng hằng số của nhiều enum. Kết hợp với sealed interface, nó còn cho phép trình biên dịch kiểm tra switch đã xử lý đủ các trường hợp của mô hình đóng hay chưa. Hãy dùng dạng nhãn này khi kiểu selector là supertype và nghiệp vụ cần phân biệt từng hằng số cụ thể.
