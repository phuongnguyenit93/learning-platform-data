# Khối lệnh, `yield` và kiểu của giá trị kết quả trong switch expression (Java 17)

Từ Java 14, Java có **switch expression** chính thức: `switch` không chỉ chọn một nhánh để thực hiện câu lệnh mà còn có thể **tạo ra một giá trị** để gán cho biến, truyền vào phương thức hoặc kết hợp trong một biểu thức khác. Java 17 sử dụng tính năng này ổn định, không cần bật preview.

Khi một nhánh chỉ có một biểu thức, cú pháp mũi tên `->` khá trực tiếp. Nhưng khi nhánh cần nhiều câu lệnh — khai báo biến tạm, ghi log, kiểm tra dữ liệu rồi mới tính kết quả — bạn cần dùng **khối lệnh** và kết thúc bằng `yield`. Đồng thời, kiểu dữ liệu của toàn bộ switch expression phải phù hợp với nơi nhận kết quả.

Bài học tập trung vào ba vấn đề liên kết với nhau:

1. Viết nhánh switch expression dưới dạng khối lệnh.
2. Dùng `yield` để trả giá trị của nhánh.
3. Hiểu kiểu kết quả được xác định và chuyển đổi như thế nào trong Java 17.

## 1. Từ switch statement đến switch expression

### 1.1. switch statement thực hiện hành động

Switch statement truyền thống được dùng để chọn một nhánh câu lệnh:

```java
int day = 2;
String label;

switch (day) {
    case 1:
        label = "Monday";
        break;
    case 2:
        label = "Tuesday";
        break;
    default:
        label = "Other day";
}

System.out.println(label);
```

Ở đây `switch` là một **statement**. Nó điều khiển luồng thực thi; việc gán cho `label` được viết riêng bên trong từng nhánh. Nếu quên `break` trong dạng nhãn `case ...:`, luồng có thể rơi xuống nhánh kế tiếp (*fall-through*).

### 1.2. switch expression tạo ra giá trị

Với switch expression, kết quả của nhánh chính là giá trị của biểu thức:

```java
int day = 2;

String label = switch (day) {
    case 1 -> "Monday";
    case 2 -> "Tuesday";
    default -> "Other day";
};

System.out.println(label);
```

Các điểm khác biệt:

- `switch (...) { ... }` nằm ở vị trí cần một biểu thức có giá trị.
- Mỗi nhánh dùng `->` tạo ra một *switch rule*; không có fall-through giữa các rule.
- Biểu thức switch phải xử lý đủ các trường hợp theo quy tắc của Java.
- Giá trị của nhánh được dùng làm giá trị của toàn bộ switch expression.
- Có dấu `;` sau dấu `}` khi switch expression là phần khởi tạo trong câu lệnh gán ở ví dụ trên.

Switch expression có thể xuất hiện trong biểu thức lớn hơn:

```java
int price = 100_000;
int discountPercent = 10;

int finalPrice = price - switch (discountPercent) {
    case 0 -> 0;
    case 10 -> price / 10;
    case 20 -> price / 5;
    default -> throw new IllegalArgumentException("Unsupported discount");
};
```

Trong ví dụ, switch expression trả về số tiền giảm, còn phép trừ được thực hiện ở biểu thức bên ngoài.

## 2. Khối lệnh trong một switch rule

Khi nhánh chỉ cần một giá trị, có thể viết trực tiếp:

```java
String status = switch (code) {
    case 200 -> "OK";
    case 404 -> "Not found";
    default -> "Unexpected";
};
```

Nếu cần nhiều bước, sau `->` có thể viết một **block**:

```java
String status = switch (code) {
    case 200 -> {
        System.out.println("Request succeeded");
        yield "OK";
    }
    case 404 -> {
        System.out.println("Resource was not found");
        yield "Not found";
    }
    default -> {
        System.out.println("Unexpected response");
        yield "Unexpected";
    }
};
```

Một block có thể chứa các thành phần Java thông thường phù hợp với ngữ cảnh:

- Khai báo biến cục bộ.
- Câu lệnh điều kiện `if`.
- Vòng lặp.
- Gọi phương thức và ghi log.
- Các câu lệnh kiểm tra/chuẩn hóa dữ liệu.
- Một hoặc nhiều đường đi kết thúc bằng `yield` hoặc kết thúc đột ngột bằng `throw`.

**Điểm quan trọng:** block không tự tạo ra giá trị chỉ vì bên trong có biến. Với mọi đường đi kết thúc bình thường của một nhánh biểu thức, phải có giá trị được cung cấp bằng `yield`. Nếu không thể tạo kết quả hợp lệ, nhánh có thể ném ngoại lệ.

## 3. `yield` trả giá trị của nhánh

`yield` là câu lệnh dùng trong switch expression để chỉ ra giá trị mà nhánh hiện tại cung cấp cho biểu thức switch.

Ví dụ:

```java
int score = 85;

String grade = switch (score / 10) {
    case 10, 9 -> "A";
    case 8 -> {
        String message = "Good";
        yield message;
    }
    case 7 -> "B";
    case 6 -> "C";
    default -> "Needs improvement";
};
```

Trong nhánh `case 8`:

1. Khai báo biến cục bộ `message`.
2. Gán giá trị cần trả cho biến đó.
3. Dùng `yield message;` để cung cấp kết quả của nhánh.
4. Giá trị được dùng làm giá trị của toàn bộ switch expression và gán cho `grade`.

`yield` **không trả kết quả ra khỏi phương thức**. Nó kết thúc nhánh của switch expression đang được nhắm tới. Đây là khác biệt với `return`:

| Câu lệnh | Ý nghĩa |
| --- | --- |
| `yield value;` | Cung cấp `value` làm kết quả của switch expression bao quanh. |
| `return value;` | Kết thúc phương thức hiện tại và trả kết quả cho nơi gọi. |
| `break;` | Thoát khỏi cấu trúc lặp hoặc switch statement phù hợp; không phải cách trả giá trị của switch expression. |
| `continue;` | Chuyển sang vòng lặp kế tiếp theo quy tắc của vòng lặp; không trả giá trị switch expression. |

### 3.1. `yield` chỉ cần khi nhánh dùng block

Với expression rule có một biểu thức, không viết `yield`:

```java
int value = switch (mode) {
    case 0 -> 10;
    case 1 -> 20;
    default -> 30;
};
```

Với block rule, dùng `yield`:

```java
int value = switch (mode) {
    case 0 -> {
        int base = 10;
        yield base;
    }
    default -> {
        int base = 20;
        yield base + 10;
    }
};
```

Không viết `case 0 -> { int base = 10; base; }` vì một câu lệnh biểu thức đứng riêng trong block không tự động trở thành kết quả của switch expression.

### 3.2. Mỗi đường đi phải cung cấp kết quả

Ví dụ sai:

```java
String result = switch (code) {
    case 1 -> {
        if (enabled) {
            yield "Enabled";
        }
        // LỖI: nếu enabled là false, block kết thúc bình thường mà không yield.
    }
    default -> "Other";
};
```

Compiler báo lỗi vì nhánh `case 1` có đường đi mà block hoàn tất bình thường nhưng không cung cấp giá trị.

Sửa:

```java
String result = switch (code) {
    case 1 -> {
        if (enabled) {
            yield "Enabled";
        }
        yield "Disabled";
    }
    default -> "Other";
};
```

Hoặc nếu điều kiện không thể tiếp tục hợp lệ, ném ngoại lệ:

```java
String result = switch (code) {
    case 1 -> {
        if (!enabled) {
            throw new IllegalStateException("Feature is disabled");
        }
        yield "Enabled";
    }
    default -> "Other";
};
```

`throw` kết thúc luồng bằng ngoại lệ, vì vậy không cần tạo một giá trị bình thường cho nhánh đó.

### 3.3. Không dùng `break` để thay cho `yield`

Ví dụ sai:

```java
int result = switch (mode) {
    case 1 -> {
        int value = 100;
        break; // LỖI: break không cung cấp giá trị của switch expression.
    }
    default -> 0;
};
```

Sửa thành:

```java
int result = switch (mode) {
    case 1 -> {
        int value = 100;
        yield value;
    }
    default -> 0;
};
```

Nếu mục đích là thoát khỏi phương thức, hãy dùng `return` ở một phương thức có kiểu trả về phù hợp. Nếu mục đích là trả kết quả cho switch expression, dùng `yield`.

## 4. Dùng block với nhiều điều kiện và tính toán

Một tình huống thường gặp là nhánh switch cần tính kết quả theo nhiều bước:

```java
public class ShippingDemo {
    static int shippingFee(String zone, int weight) {
        return switch (zone) {
            case "LOCAL" -> {
                int baseFee = 15_000;
                int extra = Math.max(0, weight - 1) * 2_000;
                yield baseFee + extra;
            }
            case "REGIONAL" -> {
                if (weight <= 0) {
                    throw new IllegalArgumentException("weight must be positive");
                }

                int baseFee = 25_000;
                int extra = Math.max(0, weight - 1) * 5_000;
                yield baseFee + extra;
            }
            case "REMOTE" -> {
                if (weight > 20) {
                    throw new IllegalArgumentException("Package is too heavy");
                }
                yield 50_000 + weight * 8_000;
            }
            default -> throw new IllegalArgumentException(
                    "Unknown shipping zone: " + zone);
        };
    }

    public static void main(String[] args) {
        System.out.println(shippingFee("LOCAL", 3));
        System.out.println(shippingFee("REGIONAL", 2));
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac --release 17 ShippingDemo.java
java ShippingDemo
```

Đầu ra:

```text
19000
30000
```

Ở đây mỗi nhánh có thể:

- Tạo biến tạm có phạm vi cục bộ trong block.
- Kiểm tra dữ liệu đầu vào.
- Ném ngoại lệ nếu điều kiện nghiệp vụ không hợp lệ.
- Dùng `yield` để cung cấp phí vận chuyển cuối cùng.

Giá trị của toàn bộ switch expression có kiểu phù hợp với kiểu trả về `int` của phương thức. Nhờ vậy, phương thức chỉ cần một câu `return switch (...) { ... };` thay vì khai báo biến rồi gán ở từng nhánh.

Lưu ý: ví dụ này minh họa cấu trúc switch expression. Ứng dụng tính phí thực tế còn phải quy định rõ đơn vị cân nặng, làm tròn, tiền tệ, giới hạn và chính sách tính phí.

## 5. Kiểu của giá trị kết quả switch expression

Một switch expression là **một biểu thức có kiểu**. Kiểu đó phải phù hợp với ngữ cảnh sử dụng: kiểu biến nhận, kiểu trả về của phương thức, kiểu tham số được truyền vào hoặc kiểu đích do biểu thức bao ngoài yêu cầu.

Ví dụ đơn giản:

```java
int value = switch (option) {
    case 1 -> 10;
    case 2 -> 20;
    default -> 0;
};
```

Các nhánh cung cấp số nguyên và ngữ cảnh đích là `int`.

### 5.1. Các nhánh nên cung cấp giá trị tương thích

Ví dụ hợp lệ:

```java
Number amount = switch (type) {
    case 1 -> Integer.valueOf(100);
    case 2 -> Double.valueOf(25.5);
    default -> Long.valueOf(0);
};
```

Các kiểu `Integer`, `Double` và `Long` đều có thể chuyển đổi tham chiếu sang `Number`, vì vậy chúng phù hợp với kiểu đích `Number`.

Ví dụ không hợp lệ:

```java
String result = switch (type) {
    case 1 -> "One";
    case 2 -> 2;
    default -> "Other";
};
```

Nhánh `case 2` cung cấp một `int`, không thể chuyển đổi phù hợp sang `String`. Compiler báo lỗi kiểu dữ liệu. Hãy quyết định hợp đồng kết quả rõ ràng:

```java
String result = switch (type) {
    case 1 -> "One";
    case 2 -> Integer.toString(2);
    default -> "Other";
};
```

### 5.2. Kiểu đích và target typing

Trong Java, một số biểu thức có thể được kiểm tra theo **kiểu đích** (*target type*) do vị trí sử dụng cung cấp. Switch expression có thể là một *poly expression* khi ngữ cảnh cung cấp kiểu đích phù hợp.

Ví dụ:

```java
Number result = switch (code) {
    case 1 -> 10;     // int được boxing thành Integer rồi tham chiếu như Number
    case 2 -> 20.5;   // double được boxing thành Double rồi tham chiếu như Number
    default -> 0L;    // long được boxing thành Long rồi tham chiếu như Number
};
```

Kiểu đích `Number` cho phép các biểu thức nhánh được kiểm tra theo ngữ cảnh đó. Đây là lý do một switch expression có thể kết hợp các giá trị có kiểu cụ thể khác nhau nếu mỗi giá trị đều tương thích với kiểu đích.

Một ví dụ khác với kiểu giao diện:

```java
CharSequence text = switch (kind) {
    case 1 -> "Java";                       // String
    case 2 -> new StringBuilder("17");      // StringBuilder
    default -> new StringBuffer("SE");
};
```

`String`, `StringBuilder` và `StringBuffer` đều triển khai `CharSequence`, nên có thể dùng trong ngữ cảnh đích `CharSequence`.

### 5.3. Khi không có kiểu đích: standalone switch expression

Nếu không có kiểu đích để hướng dẫn, Java phải xác định kiểu của switch expression từ các kiểu kết quả của những nhánh. Khi đó, các quy tắc về kiểu độc lập (*standalone expression*) và kiểu chung phù hợp được áp dụng.

Ví dụ dễ hiểu:

```java
var message = switch (code) {
    case 200 -> "OK";
    case 404 -> "Not found";
    default -> "Other";
};
```

Mọi nhánh đều cho `String`, vì vậy `var` suy luận `message` là `String`.

Nếu các nhánh có kiểu khác nhau, kiểu được suy luận có thể là một kiểu chung rộng hơn hoặc kiểu giao (*intersection type*) theo quy tắc suy luận kiểu Java. Không nên đoán kiểu chỉ từ nhánh đầu tiên. Khi muốn hợp đồng rõ ràng, hãy khai báo kiểu đích cụ thể:

```java
Number value = switch (code) {
    case 1 -> 10;
    default -> 2.5;
};
```

Khi đọc code, phân biệt hai câu hỏi:

- **Kiểu của từng nhánh có chuyển đổi được sang kiểu đích không?**
- **Nếu không có kiểu đích, compiler suy luận kiểu chung của toàn bộ biểu thức là gì?**

### 5.4. Kiểu kết quả không chỉ được quyết định bởi nhánh chạy thực tế

Giả sử:

```java
String result = switch (code) {
    case 1 -> "Success";
    default -> throw new IllegalArgumentException();
};
```

Nhánh `default` không cung cấp giá trị bình thường vì nó luôn ném ngoại lệ. Nhánh còn lại cung cấp `String`, nên biểu thức phù hợp với kiểu đích `String`.

Ngược lại, nếu có một nhánh trả về kiểu không tương thích, việc nhánh đó **không xảy ra trong lần chạy hiện tại** không làm cho chương trình biên dịch được. Compiler phải xét tất cả các nhánh có thể chọn, không chỉ dữ liệu mà bạn dự đoán sẽ xuất hiện.

## 6. Chuyển đổi số, boxing và kiểu kết quả

Khi các nhánh trả về giá trị số, cần chú ý đến kiểu nguyên thủy và wrapper.

### 6.1. Các nhánh cùng kiểu nguyên thủy

```java
int result = switch (level) {
    case 1 -> 100;
    case 2 -> 200;
    default -> 0;
};
```

Các nhánh đều là `int`, nên kết quả tự nhiên là `int`.

### 6.2. Các nhánh trả về wrapper nhưng có kiểu đích là Number

```java
Number result = switch (level) {
    case 1 -> Integer.valueOf(100);
    case 2 -> Double.valueOf(200.5);
    default -> Long.valueOf(0);
};
```

Mỗi wrapper đều là một lớp con của `Number`. Việc sử dụng kiểu đích `Number` tránh buộc caller phải phụ thuộc vào một wrapper cụ thể.

### 6.3. Tránh trộn kiểu không có chủ đích

Ví dụ:

```java
var result = switch (level) {
    case 1 -> 10;
    default -> 20L;
};
```

Compiler phải áp dụng quy tắc kiểu số và kiểu chung của biểu thức độc lập. Nếu logic yêu cầu một kết quả `long`, khai báo rõ:

```java
long result = switch (level) {
    case 1 -> 10;
    default -> 20L;
};
```

Việc chọn kiểu đích rõ ràng làm ý định dễ đọc hơn và tránh để người đọc phải suy luận quy tắc số học/boxing của từng nhánh.

### 6.4. Phân biệt ép kiểu với chọn kiểu hợp đồng

Không nên ép kiểu tùy tiện chỉ để làm compiler hết báo lỗi:

```java
Object result = switch (kind) {
    case 1 -> "Text";
    default -> 100;
};
```

Đoạn này có thể hợp lệ vì cả hai giá trị đều là đối tượng có thể tham chiếu qua `Object`. Tuy nhiên, caller nhận được một kiểu quá rộng và phải phân loại tiếp. Nếu kết quả thực chất chỉ có thể là chuỗi, hãy chuẩn hóa mọi nhánh thành `String`; nếu là một nhóm số, cân nhắc `Number`; nếu là các trạng thái có ý nghĩa khác nhau, cân nhắc một sealed interface hoặc một kiểu kết quả riêng.

Kiểu kết quả là một phần của **hợp đồng API**. Chọn kiểu đủ diễn đạt miền dữ liệu nhưng không rộng hơn cần thiết.

## 7. Dùng switch expression với nhãn dạng dấu hai chấm

Switch expression không bắt buộc mọi nhánh đều dùng mũi tên. Java cũng cho phép nhãn kiểu truyền thống `case ...:`, nhưng cần chú ý fall-through và cách kết thúc bằng `yield`.

Ví dụ:

```java
int result = switch (option) {
    case 1:
        System.out.println("Option 1");
        yield 10;
    case 2:
    case 3:
        System.out.println("Option 2 or 3");
        yield 20;
    default:
        yield 0;
};
```

Ở đây:

- `case 2:` và `case 3:` được nhóm chung, cùng đi vào một đoạn xử lý.
- `yield` kết thúc nhánh và cung cấp giá trị.
- Không được để một đường đi rơi qua nhãn khác mà chưa tạo kết quả phù hợp.

Với dạng colon, nếu không có `yield` hoặc hành vi kết thúc đột ngột, switch expression có thể không biên dịch được. Đây là nơi dễ nhầm với switch statement truyền thống vốn thường dùng `break`.

### 7.1. Không trộn arrow rule và colon label trong cùng một switch block

Không viết:

```java
int result = switch (option) {
    case 1 -> 10;
    case 2: yield 20; // LỖI: không trộn hai kiểu nhãn trong cùng switch block.
    default -> 0;
};
```

Hãy chọn một phong cách thống nhất cho toàn bộ switch block. Trong code Java 17 mới, dạng arrow thường dễ đọc và giảm nguy cơ fall-through hơn.

### 7.2. Khi nào cần dạng colon?

Dạng colon có thể hữu ích khi cần gom nhiều nhãn hoặc duy trì cấu trúc quen thuộc từ mã cũ. Tuy nhiên, nếu không cần fall-through có chủ đích, arrow rule thường là lựa chọn an toàn và rõ ràng hơn.

Đặc biệt, **switch expression không dùng fall-through để tạo kết quả**. Nếu muốn nhiều nhãn dùng cùng một kết quả, liệt kê nhiều nhãn trên một rule:

```java
String dayType = switch (day) {
    case 1, 7 -> "Weekend";
    case 2, 3, 4, 5, 6 -> "Weekday";
    default -> "Invalid day";
};
```

## 8. Tính đầy đủ của switch expression

Một switch expression phải **exhaustive**: mọi giá trị có thể của selector phải được xử lý theo quy tắc ngôn ngữ.

### 8.1. Với int hoặc String

Các kiểu như `int` và `String` có thể nhận rất nhiều giá trị, nên thường cần `default`:

```java
String category = switch (code) {
    case 200 -> "SUCCESS";
    case 400, 404 -> "CLIENT_ERROR";
    case 500 -> "SERVER_ERROR";
    default -> "OTHER";
};
```

Nếu bỏ `default` và không bao phủ mọi giá trị có thể, compiler báo switch expression không exhaustive.

### 8.2. Với enum

Nếu selector là enum và liệt kê đủ các hằng số enum, có thể không cần `default`:

```java
enum Priority {
    LOW, NORMAL, HIGH
}

String label = switch (priority) {
    case LOW -> "Low";
    case NORMAL -> "Normal";
    case HIGH -> "High";
};
```

Khi thêm hằng số mới vào enum và biên dịch lại cùng mã nguồn, compiler có thể nhắc rằng switch expression cần cập nhật. Điều này hữu ích vì kiểu enum có tập giá trị được khai báo rõ.

Nếu dùng `default`, code có thể tiếp tục biên dịch mà không nhắc đến hằng số mới. Vì vậy, với enum nội bộ mà bạn muốn compiler phát hiện thay đổi, cân nhắc liệt kê đầy đủ các hằng số thay vì thêm default chỉ để phòng xa.

### 8.3. Selector null

Trong Java 17, switch trên một biểu thức tham chiếu có giá trị `null` sẽ ném `NullPointerException` khi đánh giá switch. Cú pháp pattern switch với nhãn `case null` không phải tính năng switch ổn định của Java 17.

Nếu `null` là đầu vào có thể xảy ra, xử lý trước:

```java
String label = value == null
        ? "UNKNOWN"
        : switch (value) {
            case "A" -> "Alpha";
            case "B" -> "Beta";
            default -> "OTHER";
        };
```

Hoặc dùng một bước kiểm tra rõ ràng trước khi đánh giá switch. Đừng giả định `default` sẽ bắt được `null`.

## 9. Switch expression lồng nhau và phạm vi của yield

Một switch expression có thể nằm bên trong block của một switch expression khác. `yield` thuộc về switch expression gần nhất bao quanh nó.

Ví dụ:

```java
String message = switch (role) {
    case "ADMIN" -> {
        String permission = switch (level) {
            case 1 -> "READ";
            case 2 -> "WRITE";
            default -> "FULL";
        };
        yield "ADMIN: " + permission;
    }
    case "USER" -> "USER: READ";
    default -> "GUEST";
};
```

Ở đây:

1. Switch expression bên trong tạo giá trị `permission`.
2. Sau khi switch bên trong kết thúc, block của nhánh `ADMIN` tiếp tục chạy.
3. `yield` bên ngoài trả về chuỗi `"ADMIN: " + permission` cho switch expression bên ngoài.

Khi viết block lồng nhau, hãy đọc từng `yield` theo switch expression gần nhất mà nó thuộc về. Việc đặt tên biến trung gian thường giúp code dễ đọc hơn một biểu thức lồng quá sâu.

## 10. Ví dụ thực hành: chuẩn hóa dữ liệu bằng switch expression

Giả sử ứng dụng nhận mã trạng thái giao hàng và cần trả về một đối tượng kết quả thống nhất. Một số nhánh cần kiểm tra dữ liệu, chuẩn hóa thông tin và ghi log trước khi trả kết quả.

Tạo tệp **`DeliveryStatusDemo.java`**:

```java
public class DeliveryStatusDemo {
    enum StatusCode {
        CREATED, IN_TRANSIT, DELIVERED, FAILED
    }

    record DeliveryStatus(String code, String message, boolean completed) {
    }

    static DeliveryStatus toStatus(StatusCode code, String reference) {
        if (code == null) {
            throw new IllegalArgumentException("code is required");
        }

        return switch (code) {
            case CREATED -> {
                String normalized = normalizeReference(reference);
                yield new DeliveryStatus(
                        "CREATED",
                        "Shipment " + normalized + " was created",
                        false);
            }
            case IN_TRANSIT -> {
                String normalized = normalizeReference(reference);
                System.out.println("Tracking shipment " + normalized);
                yield new DeliveryStatus(
                        "IN_TRANSIT",
                        "Shipment is on the way",
                        false);
            }
            case DELIVERED -> new DeliveryStatus(
                    "DELIVERED",
                    "Shipment delivered",
                    true);
            case FAILED -> new DeliveryStatus(
                    "FAILED",
                    "Delivery failed",
                    true);
        };
    }

    private static String normalizeReference(String reference) {
        if (reference == null || reference.isBlank()) {
            throw new IllegalArgumentException("reference is required");
        }
        return reference.trim().toUpperCase();
    }

    public static void main(String[] args) {
        DeliveryStatus status =
                toStatus(StatusCode.IN_TRANSIT, "  sh-1701 ");
        System.out.println(status);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 DeliveryStatusDemo.java
java DeliveryStatusDemo
```

Đầu ra:

```text
Tracking shipment SH-1701
DeliveryStatus[code=IN_TRANSIT, message=Shipment is on the way, completed=false]
```

Ví dụ thể hiện:

- Kiểu kết quả của switch là `DeliveryStatus`.
- Các nhánh đơn giản trả về record trực tiếp.
- Nhánh cần xử lý nhiều bước dùng block và `yield`.
- Selector là enum; các hằng số được liệt kê đầy đủ nên không cần `default`.
- `null` được kiểm tra trước switch, vì switch Java 17 không coi `null` là một enum constant hay trường hợp default.

Khi mở rộng enum, compiler có thể giúp phát hiện nơi cần cập nhật. Khi mở rộng logic, block chỉ nên chứa các bước liên quan đến việc tạo kết quả của nhánh; nếu xử lý trở nên dài hoặc phụ thuộc nhiều dịch vụ, hãy tách thành phương thức riêng để switch vẫn dễ đọc.

## 11. Những lỗi biên dịch thường gặp

| Cách viết | Vấn đề | Cách sửa |
| --- | --- | --- |
| Block kết thúc mà không `yield` | Có đường đi hoàn tất bình thường nhưng không tạo giá trị | Bổ sung `yield` trên mọi đường đi hoặc ném ngoại lệ |
| Dùng `break` để trả giá trị | `break` không cung cấp kết quả cho switch expression | Dùng `yield value;` |
| Một nhánh trả `String`, nhánh khác trả `int` trong ngữ cảnh `String` | Kiểu kết quả không tương thích | Chuẩn hóa các nhánh thành kiểu đích phù hợp |
| Bỏ sót giá trị selector | Switch expression không exhaustive | Bổ sung case còn thiếu hoặc `default` |
| Trộn `case ->` và `case:` | Một switch block không trộn hai kiểu rule/label | Chọn arrow hoặc colon thống nhất |
| Viết `yield` trong switch statement thông thường | Không có switch expression đích để nhận giá trị | Dùng cấu trúc phù hợp; `yield` dành cho switch expression |
| Nghĩ `default` xử lý được `null` | Switch trên reference null ném `NullPointerException` trong Java 17 | Kiểm tra null trước switch |

### 11.1. Kiểm tra đúng phiên bản Java

Switch expression đã là tính năng chính thức từ Java 14. Với JDK 17:

```bash
javac -version
java -version
```

Có thể biên dịch minh họa hướng tới Java 17:

```bash
javac --release 17 ShippingDemo.java
java ShippingDemo
```

Nếu dùng JDK mới hơn để build ứng dụng Java 17, `--release 17` giúp compiler giới hạn API chuẩn và phiên bản bytecode theo mức Java 17. Nó không thay thế việc kiểm tra các thư viện bên thứ ba và môi trường runtime thực tế.

Không cần bật `--enable-preview` để sử dụng switch expression, block rule hoặc `yield` trong Java 17. Những cú pháp pattern matching for switch từng ở preview của Java 17 là một tính năng khác.

## 12. So sánh nhanh các dạng nhánh

| Dạng nhánh | Cú pháp | Khi dùng |
| --- | --- | --- |
| Arrow expression rule | `case X -> expression;` | Nhánh ngắn, tạo một giá trị trực tiếp. |
| Arrow block rule | `case X -> { statements; yield value; }` | Nhánh cần nhiều bước, biến tạm hoặc điều kiện. |
| Colon labels | `case X: statements; yield value;` | Khi cần cấu trúc nhãn truyền thống; phải kiểm soát fall-through và đường đi. |
| Nhánh ném ngoại lệ | `case X -> throw new ...;` | Trường hợp không thể tạo kết quả hợp lệ. |

Với code mới, ưu tiên arrow rule khi phù hợp vì mỗi nhánh độc lập và không có fall-through. Chuyển sang block khi có nhiều bước thật sự cần thiết, không nên tạo block chỉ để đặt một câu lệnh đơn giản.

## 13. Câu hỏi tự kiểm tra

**1. Vì sao đoạn `case 1 -> { int x = 10; }` không hợp lệ trong switch expression?**  
Vì block kết thúc bình thường mà không cung cấp giá trị. Cần viết `yield x;` hoặc ném ngoại lệ.

**2. `yield` và `return` khác nhau thế nào?**  
`yield` kết thúc nhánh và trả giá trị cho switch expression gần nhất; `return` kết thúc phương thức hiện tại.

**3. Có phải nhánh arrow đơn giản phải dùng `yield` không?**  
Không. `case 1 -> 10;` đã cung cấp trực tiếp giá trị. `yield` dùng trong block của switch expression.

**4. Một nhánh switch expression có thể ném ngoại lệ thay vì trả giá trị không?**  
Có. Nhánh kết thúc đột ngột bằng `throw` không cần cung cấp giá trị bình thường.

**5. Vì sao `String result = switch (...)` không nhận được nhánh trả về `int`?**  
Vì kiểu của nhánh không chuyển đổi được sang kiểu đích `String`. Cần chuẩn hóa giá trị hoặc chọn một kiểu kết quả khác.

**6. Khi nào `var` có thể làm kiểu kết quả khó đoán?**  
Khi các nhánh có kiểu khác nhau. Compiler phải suy luận kiểu chung theo quy tắc Java; khai báo kiểu đích cụ thể thường giúp hợp đồng rõ hơn.

**7. `default` có bắt được `null` trong Java 17 không?**  
Không. Switch trên biểu thức tham chiếu null ném `NullPointerException`; phải xử lý null trước switch.

**8. Có cần preview flag cho switch expression trong Java 17 không?**  
Không. Switch expression đã ổn định từ Java 14. Pattern matching for switch là tính năng preview riêng trong Java 17.

## Tài liệu tham khảo chính thức

- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): switch expression, arrow rule, block và `yield`.
- [Java Language Specification, Java SE 17 — `14.11 The switch Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11): switch statement và switch rule.
- [Java Language Specification, Java SE 17 — `15.28 Switch Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): kiểu, đánh giá và tính đầy đủ của switch expression.
- [Java Language Specification, Java SE 17 — `14.21 The yield Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.21): quy tắc và mục tiêu của `yield`.
- [Java 17 javac Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): compiler và tùy chọn `--release`.
