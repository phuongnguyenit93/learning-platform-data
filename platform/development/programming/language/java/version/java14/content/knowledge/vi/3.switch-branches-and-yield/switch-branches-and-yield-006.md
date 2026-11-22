# Phạm vi biến của từng khối nhánh `switch` và `yield` (Java 14+)

## 1. Hiểu đúng “phạm vi biến” trong nhánh `switch`

**Phạm vi (scope)** của biến cục bộ là phần mã nguồn mà tên biến có thể được sử dụng hợp lệ. Đối với biến được khai báo trong một **khối `{ ... }`**, phạm vi thường bắt đầu tại chính chỗ khai báo và kết thúc ở dấu `}` đóng khối đó.

Trong Java 14 trở lên, các nhánh `switch` kiểu mũi tên có thể viết:

```java
case A -> expression;
case B -> {
    // Các câu lệnh của nhánh B.
}
case C -> throw new IllegalArgumentException();
```

Đây là **minh họa cú pháp**, không phải chương trình độc lập. Điểm cần phân biệt:

- **`case B -> { ... }` tạo một khối lệnh riêng.** Biến cục bộ khai báo trong khối này chỉ có hiệu lực ở phần còn lại của khối; sang `case` khác hoặc ra khỏi `switch` sẽ không còn truy cập được.
- **`case A -> expression;` không có khối nhánh `{ ... }` để khai báo các biến trung gian.** Nếu cần khai báo nhiều biến, xử lý điều kiện hoặc ghi log, hãy dùng dạng `case A -> { ... }`.
- **`yield value;` trả *giá trị* của một nhánh cho toàn bộ `switch expression`.** Nó không đưa biến cục bộ của nhánh ra ngoài phạm vi khai báo.
- **`case X:` kiểu dấu hai chấm không tự tạo phạm vi mới cho từng nhãn `case`.** Nếu muốn cách ly biến của từng nhánh kiểu này, cần chủ động thêm `{ ... }`.

Dấu `->` dùng được cho cả **switch statement** (thực hiện hành động) và **switch expression** (tạo giá trị). Phạm vi biến phụ thuộc vào **khối lệnh được khai báo**, không phụ thuộc vào việc `switch` có tạo giá trị hay không.

## 2. Ví dụ Java 14+ chạy được: biến cùng tên ở các nhánh độc lập

Tạo tệp **`BranchScopeDemo.java`** với mã hoàn chỉnh:

```java
public class BranchScopeDemo {
    enum Plan { BASIC, PRO, ENTERPRISE }

    // Switch expression: mỗi nhánh có khối riêng và yield giá trị.
    static int calculateFee(Plan plan, int users) {
        if (users <= 0) {
            throw new IllegalArgumentException("users phải dương");
        }

        return switch (plan) {
            case BASIC -> {
                int unitPrice = 10;
                int subtotal = unitPrice * users;
                yield subtotal;
            }
            case PRO -> {
                int unitPrice = 18;
                int subtotal = unitPrice * users;
                int discount = users >= 5 ? 10 : 0;
                yield subtotal - discount;
            }
            case ENTERPRISE -> {
                int unitPrice = 25;
                int subtotal = unitPrice * users;
                int discount = users >= 10 ? 30 : 0;
                yield subtotal - discount;
            }
        };
    }

    // Switch statement: các nhánh thực hiện hành động.
    static void showPlan(Plan plan) {
        switch (plan) {
            case BASIC -> {
                String label = "Gói BASIC";
                System.out.println(label);
            }
            case PRO -> {
                String label = "Gói PRO";
                System.out.println(label);
            }
            case ENTERPRISE -> {
                String label = "Gói ENTERPRISE";
                System.out.println(label);
            }
        }
    }

    // Cú pháp case: vẫn được hỗ trợ; dùng {} để tạo scope riêng.
    static void showColonCase(int code) {
        switch (code) {
            case 1: {
                int value = 100;
                System.out.println("Colon 1: " + value);
                break;
            }
            case 2: {
                int value = 200;
                System.out.println("Colon 2: " + value);
                break;
            }
            default:
                System.out.println("Colon khác");
        }
    }

    public static void main(String[] args) {
        System.out.println("BASIC: " + calculateFee(Plan.BASIC, 3));
        System.out.println("PRO: " + calculateFee(Plan.PRO, 5));
        System.out.println("ENTERPRISE: " + calculateFee(Plan.ENTERPRISE, 10));
        showPlan(Plan.PRO);
        showColonCase(2);
    }
}
```

Biên dịch/chạy bằng JDK 14 trở lên (mã không cần preview feature):

```bash
javac -encoding UTF-8 BranchScopeDemo.java
java BranchScopeDemo
```

Đầu ra chính xác:

```text
BASIC: 30
PRO: 80
ENTERPRISE: 220
Gói PRO
Colon 2: 200
```

**Tại sao các dòng khai báo cùng tên vẫn hợp lệ?**

- Trong `calculateFee`, `unitPrice` và `subtotal` được khai báo lần lượt trong ba khối `case ... -> { ... }` **khác nhau**. Mỗi biến chỉ sống trong phạm vi từ chỗ khai báo đến dấu `}` của nhánh tương ứng. Ba khai báo không xung đột với nhau.
- `discount` chỉ tồn tại ở nhánh `PRO` và nhánh `ENTERPRISE`; `BASIC` không thể truy cập `discount`.
- `yield subtotal;` hoặc `yield subtotal - discount;` đưa **giá trị `int`** ra khỏi `switch expression`. Sau `yield`, tên `subtotal` vẫn không tồn tại ở các nhánh khác hay trong phần mã sau `switch`.
- Trong `showPlan`, các nhánh statement cũng lần lượt khai báo `String label`. Chúng hợp lệ vì mỗi tên nằm trong một khối riêng, dù statement không dùng `yield`.
- Trong `showColonCase`, `case 1: { ... }` và `case 2: { ... }` có dấu ngoặc nhọn chủ động, nên cả hai dùng được tên `value`. `break` kết thúc switch statement để tránh chạy tiếp nhánh sau.

**Kết luận từ ví dụ:** muốn tái sử dụng tên biến cục bộ giữa những nhánh độc lập, hãy dùng **mỗi nhánh một block**. Việc tên giống nhau không khiến biến hoặc giá trị trong các nhánh trở thành cùng một đối tượng.

## 3. `yield` đưa ra giá trị, không mở rộng phạm vi của biến

Xét đoạn đặt trong phương thức có biến `plan` kiểu `Plan`:

```java
int fee = switch (plan) {
    case BASIC -> {
        int localFee = 10;
        yield localFee;
    }
    case PRO -> 18;
    case ENTERPRISE -> 25;
};

// Hợp lệ: fee đã được khai báo ở phạm vi bên ngoài switch.
System.out.println(fee);

// Không hợp lệ nếu bỏ dấu chú thích:
// System.out.println(localFee);
// error: cannot find symbol - localFee nằm trong block case BASIC.
```

Tại nhánh `BASIC`, biểu thức `yield localFee;` đọc **giá trị** hiện tại của `localFee` rồi hoàn thành `switch expression` với giá trị ấy. Biến `localFee` không “đi theo” giá trị sang dòng sau. Biến bên ngoài nhận kết quả là **`fee`**, được khai báo ngoài khối `case`.

Điều tương tự xảy ra với `yield` ở các khối có thao tác phụ:

```java
// Đặt trong một phương thức nhận int users và boolean member.
int price = switch (users) {
    case 1 -> {
        int base = 100;
        int finalPrice = base;
        if (member) {
            int discount = 20;
            finalPrice -= discount;
        }
        // 'discount' đã hết scope ở dấu } của if.
        yield finalPrice;
    }
    default -> 80 * users;
};
```

Ở đây có **các tầng phạm vi**: khối `case 1` chứa `base` và `finalPrice`; khối `if (member)` nằm bên trong chứa `discount`. Sau khi `if` kết thúc, `discount` hết phạm vi; `finalPrice` vẫn còn trong khối nhánh để `yield`. Sau khi `switch` kết thúc, chỉ biến `price` ở ngoài giữ giá trị tính được.

### Không thể dùng `yield` trong switch statement để “xuất biến”

`yield` dành cho **switch expression**, nơi toàn cấu trúc phải tạo ra giá trị. Với statement chỉ cần thực hiện hành động, dùng câu lệnh trong block:

```java
// Đặt trong phương thức có biến plan kiểu Plan.
switch (plan) {
    case BASIC -> {
        String message = "Gói cơ bản";
        System.out.println(message);
    }
    case PRO, ENTERPRISE -> System.out.println("Gói nâng cao");
}
```

`message` chỉ có phạm vi trong nhánh `BASIC`. Câu lệnh `println` có tác dụng phụ; statement không có giá trị phải `yield`.

## 4. Vì sao `case:` có thể gây xung đột tên biến?

Đây là cú pháp **vẫn hợp lệ và được Java hiện đại hỗ trợ**:

```java
switch (code) {
    case 1:
        int amount = 100;
        System.out.println(amount);
        break;
    case 2:
        // Sai nếu khai báo cùng tên trong switch block:
        // int amount = 200;
        System.out.println("Trường hợp 2");
        break;
    default:
        System.out.println("Khác");
}
```

Không có `{ ... }` bao quanh **riêng từng nhánh**, nên `case 1:` và `case 2:` không tạo hai khối cục bộ tách biệt. Khai báo `int amount` ở nhánh đầu nằm trong phạm vi của **switch block chung**, và việc khai báo lại `int amount` trong cùng phạm vi dẫn đến lỗi biên dịch kiểu “variable amount is already defined”.

**Cách sửa đúng** nếu vẫn cần cú pháp `case:`:

```java
switch (code) {
    case 1: {
        int amount = 100;
        System.out.println(amount);
        break;
    }
    case 2: {
        int amount = 200;
        System.out.println(amount);
        break;
    }
    default:
        System.out.println("Khác");
}
```

Mỗi cặp dấu `{ }` tạo một phạm vi riêng. **Lưu ý:** dấu `{ }` **không thay thế `break`** của cú pháp `case:`. Nếu không có `break` (hoặc lệnh chuyển điều khiển phù hợp khác), chương trình vẫn có thể thực hiện *fall-through* vào phần lệnh tiếp theo. Trong khi đó, `case ... ->` không có fall-through giữa các nhánh.

Một khác biệt khác: theo quy tắc **definite assignment**, trình biên dịch còn phải chứng minh biến được gán trước khi đọc. Biến được khai báo dưới một nhãn `case:` không có nghĩa là mọi đường vào `switch` đều đi qua khai báo và phép gán đó. Đừng dựa vào việc nhãn `case` “cách dòng” để suy luận tính hợp lệ của biến; hãy tách block và khai báo tại nơi thực sự cần dùng.

## 5. Biến khai báo bên ngoài, bên trong và quy tắc che khuất tên

### Biến ngoài `switch` có thể được đọc hoặc cập nhật từ nhánh

Đoạn minh họa sau đặt trong phương thức có `plan` kiểu `Plan`:

```java
int fee;
switch (plan) {
    case BASIC -> fee = 10;
    case PRO -> fee = 18;
    case ENTERPRISE -> fee = 25;
    default -> throw new IllegalStateException("Kế hoạch không hợp lệ");
}
System.out.println(fee);
```

`fee` được khai báo ở **phạm vi ngoài switch**, nên các nhánh có thể gán và dòng sau có thể đọc. `default` ở đây làm đường gán trở nên rõ ràng với trình biên dịch nếu sau này tập trường hợp thay đổi. Để **tính một giá trị duy nhất**, biểu thức ngắn gọn hơn thường là:

```java
int fee = switch (plan) {
    case BASIC -> 10;
    case PRO -> 18;
    case ENTERPRISE -> 25;
};
```

Cả hai là lựa chọn hiện hành. Khác nhau ở cách tổ chức mã: câu lệnh thực thi phép gán lên biến ngoài; biểu thức trực tiếp tạo kết quả để khởi tạo biến.

### Không được khai báo lại một biến cục bộ bên ngoài còn trong phạm vi

Đoạn sau là **ví dụ sai, không biên dịch**:

```java
int fee = 5;
switch (plan) {
    case BASIC -> {
        int fee = 10; // Lỗi: local variable fee đã được định nghĩa.
        System.out.println(fee);
    }
    default -> System.out.println("Khác");
}
```

Dù có block lồng, Java không cho khai báo một biến cục bộ cùng tên với biến cục bộ ở phạm vi bao ngoài đang còn hiệu lực. **Tái sử dụng tên ở những nhánh có block tách rời** (như `subtotal` trong ba nhánh ở ví dụ chính) là hợp lệ; **khai báo trùng với biến local bên ngoài** thì không.

Nếu cần giữ cả hai giá trị, hãy đặt tên khác, chẳng hạn `baseFee` bên ngoài và `branchFee` trong nhánh.

### Nhóm nhiều nhãn trong cùng một nhánh có chung phạm vi

```java
int multiplier = switch (plan) {
    case BASIC -> 1;
    case PRO, ENTERPRISE -> {
        int factor = 2;
        yield factor;
    }
};
```

`PRO` và `ENTERPRISE` cùng đi vào **một** khối `{ ... }`, nên `factor` là một biến cục bộ của khối ấy khi nhánh được chạy. Nó không thể được truy cập từ nhánh `BASIC` hay từ bên ngoài `switch`.

## 6. Lỗi thường gặp khi xác định phạm vi

| Hiểu nhầm / lỗi | Thực tế | Cách tránh |
| --- | --- | --- |
| “Mỗi nhãn `case:` đều tạo scope mới” | Các nhãn không tự sinh khối; biến trong switch block có thể xung đột tên | Dùng `case X: { ... break; }` hoặc `case X -> { ... }` |
| “`yield local;` đưa biến `local` ra ngoài” | `yield` chỉ đưa **giá trị** vào kết quả switch expression | Nhận kết quả bằng biến khai báo ngoài: `var result = switch (...) { ... };` |
| “Có dấu `->` là khai báo biến thoải mái ngay sau mũi tên” | Vế phải `->` là expression, block hoặc `throw` theo ngữ cảnh; `int x = ...;` không phải expression hợp lệ | Mở block `-> { int x = ...; yield x; }` nếu switch expression cần nhiều bước |
| “Đóng ngoặc `}` ở nhánh dấu hai chấm là đủ để tránh fall-through” | Block chỉ cách ly phạm vi, không tự kết thúc switch statement | Cần `break` khi dùng `case:` mà không muốn fall-through |
| “Biến khai báo trong `if` còn dùng được ở cuối block `case`” | Biến chỉ tồn tại trong block `if` tương ứng | Khai báo trước `if` nếu cần dùng về sau |
| “Các nhánh khác nhau không được dùng cùng tên biến” | Được phép nếu khai báo trong **các block riêng không lồng nhau** | Dùng block per branch, đặt tên mô tả mục đích |
| “Block trong nhánh được phép che khuất local của phương thức” | Java cấm khai báo lại local đang có hiệu lực ở phạm vi bao ngoài | Đặt tên khác cho biến trong nhánh |
| “Switch expression có thể có block kết thúc mà không tạo giá trị” | Nhánh phải tạo giá trị qua expression/`yield`, hoặc kết thúc bằng ngoại lệ | Kiểm tra từng đường đi qua `if`, `else` và `yield` |

### Checklist khi đọc hoặc viết một nhánh mới

1. Xác định `switch` là **statement** hay **expression**. Nếu cần trả giá trị, xem nhánh có `yield`/expression/`throw` phù hợp hay chưa.
2. Xác định chính xác cặp `{ ... }` bao quanh khai báo biến. Nhãn `case:` đơn lẻ **không** phải cặp ngoặc.
3. Kiểm tra biến có bị dùng **ngoài block** hay bị khai báo lại ở phạm vi bao ngoài hay không.
4. Nếu dùng `case:` trong statement, kiểm tra `break` và nguy cơ fall-through.
5. Với biến ngoài cần đọc sau switch statement, kiểm tra **definite assignment** trên mọi đường đi có thể thực hiện.
6. Nếu nhiều nhãn dùng chung một nhánh (`case A, B ->`), nhớ rằng chúng dùng **chung một block**, không phải hai block.

## 7. Ghi chú khi học trên các phiên bản Java mới hơn

Quy tắc block và biến cục bộ của ví dụ trên **vẫn áp dụng cho Java hiện đại**. Từ **Java 21**, `switch` còn hỗ trợ pattern matching chính thức, chẳng hạn `case String text -> ...`. Biến pattern `text` chỉ có phạm vi ở phần nhánh (và guard nếu có) mà pattern khớp; không thể dùng ở một nhánh `case` khác. Đây là cú pháp bổ sung của Java 21+, **không** được dùng thay thế khi biên dịch các ví dụ dành cho Java 14. Dù có thêm pattern, nguyên tắc vẫn không đổi: chỉ đọc tên biến ở phạm vi mà ngôn ngữ cho phép, còn `yield` chuyển giá trị của switch expression.

### Tài liệu chính thức

- [Oracle — Java 14: Switch Expressions](https://docs.oracle.com/en/java/javase/14/language/switch-expressions.html): `case ->`, block nhánh, `yield`.
- [OpenJDK — JEP 361: Switch Expressions](https://openjdk.org/jeps/361): thiết kế và việc chuẩn hóa từ Java 14.
- [Oracle — Java SE 26: Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/26/language/switch-expressions-statements.html): cú pháp hiện hành của statement và expression.
- [Oracle — Java SE 25: Pattern Matching with switch](https://docs.oracle.com/en/java/javase/25/language/pattern-matching-switch.html): phạm vi biến pattern ở các phiên bản Java mới.
