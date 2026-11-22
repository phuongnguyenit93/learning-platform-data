# Phép gán chắc chắn và biến được khởi tạo trong các nhánh `switch` expression (Java 14+)

> Trọng tâm: hiểu quy tắc **definite assignment** (phép gán chắc chắn) để biết khi nào một biến cục bộ được phép đọc, khi nào có thể khai báo `final`, và cách các nhánh `case`, `yield`, `throw` bảo đảm tính hợp lệ của kết quả `switch` expression. Cú pháp sử dụng là cú pháp chuẩn từ Java 14, vẫn áp dụng với JDK 17+.

## 1. Definite assignment là gì?

Java không cho phép **đọc giá trị của biến cục bộ** khi trình biên dịch chưa thể xác định biến ấy đã được gán trên mọi đường thực thi có thể đi đến điểm đọc. Quy tắc này gọi là **definite assignment (DA)**. Trình biên dịch phân tích **luồng điều khiển tĩnh**, không đoán dựa trên các dữ liệu “thường xuất hiện” lúc chạy.

```java
int amount;
if (isMember) {
    amount = 100;
}
System.out.println(amount); // Lỗi biên dịch: isMember có thể là false.
```

Để sửa, bảo đảm cả hai đường đi đều gán trước khi đọc:

```java
int amount;
if (isMember) {
    amount = 100;
} else {
    amount = 150;
}
System.out.println(amount); // Hợp lệ.
```

Với biến cục bộ `final` **chưa được gán** (blank `final`), Java còn yêu cầu biến được gán không quá một lần trên mỗi đường thực thi hợp lệ. Khi đến phép gán, nó phải ở trạng thái **definitely unassigned (DU)**: chắc chắn chưa được gán trước đó.

```java
final int tax;
if (isPremium) {
    tax = 20;
} else {
    tax = 10;
}
System.out.println(tax); // Hợp lệ: mỗi đường đi gán đúng một lần.
```

**Phạm vi:** quy tắc đọc-trước-khi-gán ở đây nói về **biến cục bộ**. Field của đối tượng hoặc static field có giá trị mặc định theo Java khi không khởi tạo tường minh, nhưng dựa vào giá trị mặc định đó có thể vẫn là lỗi thiết kế. Gán `null` cho biến cục bộ kiểu tham chiếu cũng đáp ứng DA về mặt cú pháp; nó **không** tự bảo đảm an toàn null.

## 2. Với `switch` expression, biến kết quả thường được khởi tạo một lần

`switch` **expression** là một biểu thức tạo ra **một kết quả**, nên cú pháp thông dụng, rõ ràng nhất là khai báo và khởi tạo ngay:

```java
final int fee = switch (service) {
    case "STANDARD" -> 20;
    case "EXPRESS" -> {
        int base = 40;
        int extra = 15;
        yield base + extra;
    }
    default -> throw new IllegalArgumentException("Unknown service: " + service);
};
System.out.println(fee); // Được phép đọc nếu switch kết thúc bình thường.
```

- Nhánh `STANDARD` cung cấp `20`, nhánh `EXPRESS` cung cấp `55` qua `yield`.
- Nhánh `default` từ chối giá trị lạ bằng `throw`: khi nhánh này chạy, câu lệnh gán không hoàn thành bình thường và lệnh in phía sau cũng không chạy.
- Khi chương trình đến được `System.out.println(fee)`, biểu thức `switch` đã tạo kết quả và phép khởi tạo `fee` đã hoàn thành; không có trạng thái “chỉ một số nhánh mới gán `fee`”.
- Kết quả các nhánh phải tương thích với kiểu đích; đây là **kiểm tra kiểu**, khác với kiểm tra DA. Ví dụ `yield "hello";` không tương thích với biến `int fee`.
- `switch` expression phải **exhaustive** (bao phủ mọi trường hợp có thể). Với `String` thường cần `default`; một `enum` đã liệt kê tất cả hằng có thể không cần `default`.

Trong mã mới, biểu thức `final int fee = switch (...) { ... };` thường dễ đọc và dễ kiểm tra hơn việc khai báo một biến rồi sửa nó ở các nhánh của `switch` statement.

## 3. Biến cục bộ khai báo bên trong nhánh: phải được gán trước `yield`

Một nhánh `case ... -> { ... }` có thể có nhiều câu lệnh và các biến tạm; `yield` trả giá trị cho toàn bộ `switch` expression bao ngoài. Nếu `yield` đọc một biến tạm, biến đó phải được gán chắc chắn trên mọi đường đi dẫn tới `yield`.

```java
int points = switch (level) {
    case "SILVER" -> 10;
    case "GOLD" -> {
        final int base;
        if (promotionActive) {
            base = 50;
        } else {
            base = 40;
        }
        yield base + 5; // Hợp lệ: base được gán ở cả hai nhánh if/else.
    }
    default -> 0;
};
```

Trái lại, đoạn **cố ý sai, không biên dịch được**:

```java
int points = switch (level) {
    case "GOLD" -> {
        int base;
        if (promotionActive) {
            base = 50;
        }
        yield base + 5; // Lỗi: base chưa chắc đã được khởi tạo.
    }
    default -> 0;
};
```

Ngay cả khi chạy thực tế `promotionActive` thường là `true`, trình biên dịch vẫn xét đường đi `false`. Có thể sửa bằng `else { base = 40; }`, khởi tạo biến ngay khi khai báo (`int base = 40;`) hoặc đặt `yield` trong mỗi đường đi đã gán giá trị.

**Phạm vi biến:** biến khai báo trong `{ ... }` của một nhánh chỉ dùng được trong khối đó; không thể sử dụng từ nhánh khác hay bên ngoài `switch`. Mỗi khối độc lập có thể đặt tên biến tạm giống nhau mà không đụng độ.

```java
int score = switch (group) {
    case "A" -> { int local = 10; yield local; }
    case "B" -> { int local = 20; yield local; }
    default -> 0;
};
// Không thể dùng 'local' tại đây: biến nằm ngoài phạm vi.
```

## 4. Biến khai báo **trước** `switch`: gán trên các đường đi hoàn thành bình thường

Đôi khi một biến bên ngoài phải được xác lập ngay trong các nhánh, chẳng hạn cần sử dụng đồng thời **kết quả của switch** và một thuộc tính bổ sung. Để đọc biến ấy sau `switch`, tất cả đường đi có thể đến điểm đọc phải gán nó.

Ví dụ hợp lệ với blank `final`:

```java
final int surcharge;
final String label = switch (shipping) {
    case "STANDARD" -> {
        surcharge = 0;
        yield "standard";
    }
    case "EXPRESS" -> {
        surcharge = 25;
        yield "express";
    }
    default -> throw new IllegalArgumentException("Unsupported shipping");
};
System.out.println(label + ":" + surcharge);
```

Ở đây `surcharge` được gán trên cả hai đường đi **có thể hoàn thành bình thường**. Nhánh `throw` không dẫn đến câu lệnh in nên không bắt buộc phải gán `surcharge`; điều đó khác với một nhánh chỉ `yield` giá trị mà bỏ quên gán biến.

Đoạn sau **cố ý không biên dịch**:

```java
int surcharge;
String label = switch (shipping) {
    case "STANDARD" -> { surcharge = 0; yield "standard"; }
    case "EXPRESS" -> "express"; // Hoàn thành nhưng chưa gán surcharge.
    default -> throw new IllegalArgumentException("Unsupported shipping");
};
System.out.println(surcharge); // Lỗi: surcharge có thể chưa được khởi tạo.
```

Sửa bằng cách gán `surcharge` ở nhánh `EXPRESS` trước khi `yield`, hoặc thiết kế lại để một `switch` expression tạo hẳn kết quả có cấu trúc (record chứa `label` và `surcharge`), tránh sửa nhiều biến ngoài phạm vi biểu thức.

**Trường hợp `final`:** mỗi đường thực thi phải gán đúng một lần trước khi đọc. Hai nhánh loại trừ nhau cùng gán một `final` là hợp lệ; gán lại lần thứ hai trên **cùng một đường đi** là lỗi:

```java
final int surcharge;
String label = switch (shipping) {
    case "EXPRESS" -> {
        surcharge = 25;
        surcharge = 30; // Lỗi biên dịch: biến final đã được gán.
        yield "express";
    }
    default -> { surcharge = 0; yield "other"; }
};
```

**Giới hạn quan trọng:** không phải chỉ cần mỗi nhánh `case` có một phép gán ở đâu đó. Phải xét **đúng các đường đi thực tế tới chỗ đọc**, kể cả các `if`, `else`, `yield` sớm, `throw`, các lời gọi có thể hoàn thành bình thường và phạm vi biến.

## 5. Phân biệt `switch` expression với `switch` statement

Với switch expression, biến nhận kết quả được khởi tạo bởi **toàn bộ biểu thức** khi biểu thức hoàn thành bình thường:

```java
int fee = switch (method) {
    case "STANDARD" -> 0;
    case "EXPRESS" -> 25;
    default -> throw new IllegalArgumentException("Unsupported method");
};
```

Với switch **statement**, mỗi nhánh thực thi lệnh; nó không tự tạo giá trị. Nếu khai báo `int fee;` ngoài statement, các đường đi có thể đi tiếp phải gán `fee` trước khi đọc:

```java
int fee;
switch (method) {
    case "STANDARD" -> fee = 0;
    case "EXPRESS" -> fee = 25;
    default -> throw new IllegalArgumentException("Unsupported method");
}
System.out.println(fee); // Hợp lệ: mọi đường đi tiếp đều đã gán.
```

Nếu bỏ nhánh `default` trong **switch statement thường** trên `String`, trường hợp `method` không khớp `case` nào có thể đi thẳng đến `System.out.println(fee)` mà không gán; Java sẽ báo lỗi DA. Một `default -> { }` rỗng cũng **không** giúp DA. Những switch statement kiểu pattern trong các JDK mới hơn có các quy tắc exhaustive riêng; không suy rộng nhận xét này cho mọi dạng statement.

Khác biệt còn ở ký hiệu: nhánh `case ... -> { ... }` của **switch expression** cần `yield` giá trị hoặc kết thúc bằng `throw`; khối của **switch statement** có thể kết thúc bình thường. `yield` không dùng để tạo giá trị cho một switch statement thông thường.

## 6. Chương trình Java hoàn chỉnh, kiểm tra được

Tạo file `SwitchAssignmentDemo.java` (đúng tên lớp `public`) bằng nội dung sau. Tất cả ví dụ dùng cú pháp có từ Java 14, chạy với JDK 17 trở lên:

```java
public class SwitchAssignmentDemo {
    static String summary(String shipping, int quantity) {
        if (shipping == null) {
            throw new IllegalArgumentException("shipping is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }

        final int surcharge;
        final String label = switch (shipping) {
            case "STANDARD" -> {
                surcharge = 0;
                yield "standard";
            }
            case "EXPRESS" -> {
                surcharge = 25;
                yield "express";
            }
            default -> throw new IllegalArgumentException(
                "Unsupported shipping: " + shipping);
        };

        final int total = 10 * quantity + surcharge;
        return label + ":" + total;
    }

    static int classify(int score) {
        return switch (score / 10) {
            case 10, 9 -> 1;
            case 8 -> {
                int offset;
                if (score == 89) {
                    offset = 2;
                } else {
                    offset = 1;
                }
                yield offset;
            }
            default -> 0;
        };
    }

    static int statementVersion(boolean express) {
        int fee;
        switch (express ? 1 : 0) {
            case 1 -> fee = 25;
            case 0 -> fee = 0;
            default -> throw new IllegalStateException("Unexpected option");
        }
        return fee;
    }

    public static void main(String[] args) {
        System.out.println(summary("STANDARD", 3));
        System.out.println(summary("EXPRESS", 3));
        System.out.println(classify(89));
        System.out.println(classify(80));
        System.out.println(statementVersion(true));
        try {
            summary("OVERNIGHT", 1);
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac -encoding UTF-8 SwitchAssignmentDemo.java
java SwitchAssignmentDemo
```

**Đầu ra chuẩn (stdout):**

```text
standard:30
express:55
2
1
25
Unsupported shipping: OVERNIGHT
```

Diễn giải: `summary` dùng `final int surcharge` chưa gán, nhưng mỗi nhánh hoàn thành bình thường đều gán trước `yield`; `default` ném ngoại lệ. `classify` cho thấy biến `offset` trong nhánh `case 8` được gán bởi cả hai nhánh `if/else` trước khi đọc. `statementVersion` minh họa biến `fee` ngoài switch statement vẫn DA sau switch. Các số lần lượt là `10 * 3 + 0 = 30`, `10 * 3 + 25 = 55`, `offset = 2`, `offset = 1`, và `fee = 25`.

## 7. Các lỗi hay gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `variable x might not have been initialized` tại `yield x;` | Có đường đi trong nhánh chưa gán `x` | Gán trong mọi nhánh `if/else`, hoặc khai báo có giá trị khởi tạo hợp lệ |
| Cùng lỗi khi đọc biến **sau** switch | Một nhánh vẫn có thể hoàn thành bình thường mà không gán biến | Gán ở mọi đường đi tiếp, hoặc chuyển sang `var value = switch (...) { ... };` |
| `variable x might already have been assigned` đối với `final` | Có đường đi gán `final` hai lần | Bảo đảm đúng một lần trên mỗi đường đi; không dùng phép gán lặp |
| `cannot find symbol` với biến tạm | Biến khai báo trong khối một nhánh nhưng sử dụng ngoài phạm vi | Chỉ dùng trong khối, hoặc đưa giá trị ra ngoài thông qua `yield` |
| `switch expression does not cover all possible input values` | Thiếu nhánh bao phủ selector | Bổ sung `default` khi cần; `enum` có thể liệt kê hết hằng |
| Nhánh expression không tạo được giá trị | Một đường đi kết thúc khối mà chưa `yield` hoặc `throw` | Cung cấp giá trị/ngoại lệ trên mọi đường đi của khối |

### Ví dụ lỗi không trực tiếp liên quan đến DA nhưng thường bị nhầm

```java
int result = switch (mode) {
    case "A" -> {
        int temp = 10;
        // Có temp, nhưng thiếu yield: switch expression không có kết quả.
    }
    default -> 20;
};
```

Việc biến `temp` đã được gán **không thay thế** nghĩa vụ tạo ra giá trị cho switch expression. Cần `yield temp;` ở cuối khối. Ngược lại, có `yield` **không đảm bảo** rằng tất cả biến được đọc trong biểu thức `yield` đều DA.

## 8. Lưu ý về tính đúng đắn và thiết kế

- **Phân biệt biên dịch với kiểm thử runtime.** Trình biên dịch chứng minh DA theo đường đi cú pháp; chạy thành công một bộ dữ liệu không đủ chứng minh mọi biến đã được gán. Dùng test để kiểm tra thêm giá trị tính toán và ngoại lệ.
- **Kiểu trả về và DA là hai câu hỏi độc lập.** `yield` phải tạo giá trị tương thích với ngữ cảnh kiểu; mọi biến được đọc trong công thức đó vẫn cần DA.
- **Không dựa vào dữ liệu “không thể xảy ra” để lờ đường đi khác.** Nếu một trạng thái không hợp lệ, `throw` ngoại lệ có nghĩa nghiệp vụ phù hợp. Không gán giá trị ngầm `0` hoặc `null` chỉ để vượt qua kiểm tra DA nếu nó che giấu lỗi.
- **`throw` làm dừng đường đi hiện tại.** Khi nhánh ném ngoại lệ trước khi gán biến, đoạn mã chỉ chạy sau khi switch hoàn thành bình thường không được thực thi theo đường đi đó. Tuy nhiên vẫn phải xem liệu phần còn lại có đường đi nào đọc biến chưa khởi tạo hay không.
- **`null` là quy tắc khác với DA.** Trong cú pháp switch của Java 14/JDK 17, selector tham chiếu bằng `null` thường dẫn đến `NullPointerException`; `default` không tự “bắt null”. Với JDK 21+ có thể chủ động xử lý `case null` trong cú pháp hỗ trợ, hoặc kiểm tra `null` trước `switch` như ví dụ.
- **`enum` mở rộng và exhaustive.** Nếu mọi hằng enum đã được bao phủ, switch expression có thể không cần `default`; việc thêm hằng rồi biên dịch lại buộc xem xét nhánh mới. Mã đã biên dịch riêng cũng phải được kiểm tra tương thích khi enum thay đổi.
- **Biến không nhất thiết phải nằm ngoài switch.** Nếu một nhánh cần nhiều thuộc tính đi cùng nhau, cân nhắc trả về một đối tượng/record bất biến qua `yield` thay vì đồng thời gán nhiều biến bên ngoài; cách này giảm sự ràng buộc giữa các đường đi.
- **Tránh gán với tác dụng phụ khó theo dõi.** Một phép gán trong biểu thức `case X -> (outer = value)` có thể hợp lệ, nhưng thường khó đọc hơn một khối `{ outer = value; yield result; }` rõ ràng.

## 9. Checklist để tự kiểm tra

1. Biến cục bộ được **đọc** ở vị trí nào? Có nhánh `if/else`, `case`, `yield` sớm nào dẫn đến đó mà không gán?
2. Biến `final` chưa khởi tạo có được gán **đúng một lần** trên mọi đường đi dẫn đến chỗ đọc?
3. `switch` expression có bao phủ mọi selector và mỗi nhánh hợp lệ có trả giá trị (`-> expression`/`yield`) hoặc ném ngoại lệ?
4. Giá trị của các nhánh có đúng kiểu đích không? Đừng nhầm lỗi kiểu với lỗi DA.
5. Biến khai báo **trong** khối nhánh có bị dùng ngoài phạm vi của nó?
6. Biến được sử dụng sau switch statement có được gán trên tất cả đường đi hoàn thành bình thường?
7. Có test cho nhánh thường, nhánh điều kiện, nhánh `default`/`throw`, đầu vào `null` (nếu thuộc miền đầu vào) và dữ liệu ranh giới không?

## Tài liệu chính thức

- Oracle, *Switch Expressions* (Java 14): https://docs.oracle.com/en/java/javase/14/language/switch-expressions.html
- Oracle Dev.java, *Branching with Switch Expressions*: https://dev.java/learn/branching-with-switch-expressions/
- Java Language Specification, chương 16 *Definite Assignment* (bao gồm quy tắc dành cho switch expression): https://docs.oracle.com/javase/specs/jls/se25/html/jls-16.html
- Java Language Specification, chương 15 về switch expression: https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.28
