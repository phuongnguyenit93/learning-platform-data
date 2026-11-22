# Nhãn mũi tên và nhãn dấu hai chấm trong switch expression của Java 17

Trong Java 17, `switch` có thể được viết dưới **hai dạng nhãn nhánh**:

- **Nhãn mũi tên:** `case ... ->` — mỗi nhánh có ranh giới rõ ràng; **không tự chạy tiếp sang nhánh sau** (*fall-through*).
- **Nhãn dấu hai chấm:** `case ...:` — nhóm câu lệnh theo cách truyền thống; có thể **chạy tiếp** sang nhóm nhãn sau nếu luồng điều khiển chưa kết thúc.

Cả hai dạng đều có thể xuất hiện trong **switch statement** (câu lệnh `switch`) và **switch expression** (biểu thức `switch`), nhưng cách **trả về giá trị**, **thoát nhánh**, và **xử lý fall-through** khác nhau. Khi học switch expression, cần đặc biệt phân biệt:

```java
// Mũi tên: biểu thức đứng sau -> tự tạo ra giá trị cho switch expression.
String text = switch (code) {
    case 1 -> "Một";
    case 2 -> "Hai";
    default -> "Khác";
};
```

với:

```java
// Dấu hai chấm: dùng yield để cung cấp giá trị cho switch expression.
String text = switch (code) {
    case 1:
        yield "Một";
    case 2:
        yield "Hai";
    default:
        yield "Khác";
};
```

**Cả hai đoạn đều hợp lệ trên Java 17**, miễn là biến `code` đã được khai báo với kiểu tương thích, chẳng hạn `int`. Switch expression là tính năng **chính thức từ Java 14** và dùng ổn định ở Java 17, không cần `--enable-preview`. Bài học này chỉ dùng cú pháp đã được chuẩn hóa trong Java 17.

## 1. Trước hết: switch statement khác switch expression thế nào?

Hai cấu trúc cùng sử dụng từ khóa `switch` và các nhãn `case`, nhưng có mục đích khác nhau.

### 1.1. Switch statement: thực hiện hành động

```java
static void printStatus(int status) {
    switch (status) {
        case 200 -> System.out.println("Thành công");
        case 404 -> System.out.println("Không tìm thấy");
        default -> System.out.println("Trạng thái khác");
    }
}
```

Đây là một **câu lệnh**: các nhánh thực hiện hành động, không tạo ra giá trị chung để gán cho biến. Không có dấu `;` sau dấu `}` để kết thúc một biểu thức `switch`, vì đây là câu lệnh `switch` hoàn chỉnh.

### 1.2. Switch expression: tính ra một giá trị

```java
static String statusText(int status) {
    return switch (status) {
        case 200 -> "Thành công";
        case 404 -> "Không tìm thấy";
        default -> "Trạng thái khác";
    };
}
```

Ở đây, **toàn bộ `switch (...) { ... }` là một biểu thức**. Kết quả của nhánh được chọn trở thành kết quả của biểu thức, nên có thể dùng trong `return` hoặc ở bên phải phép gán:

```java
String message = switch (status) {
    case 200 -> "OK";
    case 404 -> "Not found";
    default -> "Other";
};
```

Dấu `;` sau `}` thuộc câu lệnh gán hoặc `return` chứa switch expression.

| Đặc điểm | Switch statement | Switch expression |
| --- | --- | --- |
| Mục đích chính | Thực hiện câu lệnh hoặc tác dụng phụ. | Tạo một giá trị dùng trong biểu thức khác. |
| Có thể dùng `->`? | Có. | Có. |
| Có thể dùng `:`? | Có. | Có. |
| Có bắt buộc bao phủ các khả năng của selector? | Không, trong trường hợp thông thường. | **Có**: mọi giá trị hợp lệ của selector phải có nhánh xử lý. |
| Nhánh kết thúc bằng `break`? | Có thể dùng, đặc biệt với nhãn `:`. | Không dùng `break` để trả giá trị. |
| Nhánh nhiều lệnh muốn tạo giá trị | Không áp dụng; đây là statement. | Dùng `yield giáTrị;` trong nhánh dạng block hoặc nhóm nhãn `:`. |

Trong một `switch` cụ thể, **không trộn nhãn `->` với nhãn `:`**. Hãy chọn một kiểu nhãn thống nhất cho toàn bộ switch block.

## 2. Nhãn mũi tên: `case ... ->`

Dạng mũi tên thường phù hợp nhất khi mỗi trường hợp dẫn tới **một giá trị hoặc một đoạn xử lý độc lập**.

### 2.1. Cú pháp trả về biểu thức trực tiếp

```java
enum AccessLevel {
    GUEST, MEMBER, ADMIN
}

class ArrowLabels {
    static int maxProjects(AccessLevel access) {
        return switch (access) {
            case GUEST -> 1;
            case MEMBER -> 10;
            case ADMIN -> 100;
        };
    }
}
```

Vì ba nhãn bao phủ toàn bộ hằng số của enum `AccessLevel`, compiler nhận ra switch expression có đủ trường hợp cho enum này. Ở dạng mũi tên:

- Sau `->` là **một biểu thức** tạo ra giá trị, ví dụ `1`, `10` hoặc `100`.
- **Không cần `yield`** khi viết biểu thức ngay sau mũi tên.
- **Không cần `break`**: một nhánh không chạy tiếp sang nhánh bên dưới.
- Khi thêm một giá trị mới vào enum và biên dịch lại code này, compiler có thể yêu cầu xử lý giá trị mới để khôi phục tính bao quát.

### 2.2. Gộp nhiều giá trị trong một nhãn

Java 17 cho phép đặt nhiều hằng sau một `case`:

```java
enum DayType {
    MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY,
    SATURDAY, SUNDAY
}

class DayLabels {
    static boolean isWeekend(DayType day) {
        return switch (day) {
            case SATURDAY, SUNDAY -> true;
            case MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY -> false;
        };
    }
}
```

Hai giá trị `SATURDAY` và `SUNDAY` cùng dẫn tới `true`. Đây là **nhiều nhãn cho một nhánh**, hoàn toàn khác với việc các câu lệnh chạy xuyên qua nhiều nhánh.

### 2.3. Khi nhánh có nhiều lệnh, dùng block và `yield`

Nếu cần tính toán nhiều bước, ghi log hoặc kiểm tra điều kiện trước khi trả về giá trị, dùng một **block** sau `->`:

```java
enum Plan {
    FREE, STANDARD, PREMIUM
}

class PriceCalculator {
    static int monthlyPrice(Plan plan, int basePrice) {
        return switch (plan) {
            case FREE -> 0;

            case STANDARD -> {
                int discount = 10;
                int amount = basePrice * (100 - discount) / 100;
                yield amount;
            }

            case PREMIUM -> {
                int supportFee = 50_000;
                int amount = basePrice + supportFee;
                yield amount;
            }
        };
    }
}
```

Quy tắc quan trọng: **block sau `->` không tự biến câu lệnh cuối cùng thành giá trị**. Muốn trả giá trị từ block của switch expression, phải dùng `yield`.

Ví dụ sai:

```java
// Không biên dịch trong Java 17:
// int price = switch (plan) {
//     case FREE -> 0;
//     case STANDARD -> {
//         int amount = 90;
//         amount; // Không phải cách trả giá trị của block.
//     }
//     case PREMIUM -> 150;
// };
```

Sửa bằng `yield amount;`. Có thể coi `yield` là câu lệnh **chuyển giá trị ra ngoài switch expression đang bao quanh**. Nó không đồng nghĩa với `return` của phương thức chứa switch.

### 2.4. Khi nhánh không tạo giá trị mà ném ngoại lệ

Một nhánh của switch expression có thể dùng câu lệnh `throw`:

```java
static int parseLevel(String level) {
    return switch (level) {
        case "LOW" -> 1;
        case "MEDIUM" -> 2;
        case "HIGH" -> 3;
        default -> throw new IllegalArgumentException(
                "Unsupported level: " + level
        );
    };
}
```

Nhánh `default` không tạo giá trị bởi nó kết thúc bằng ngoại lệ. Điều này vẫn phù hợp với yêu cầu switch expression: mọi đường đi phải **tạo một giá trị hoặc kết thúc bất thường** (như ném ngoại lệ).

## 3. Nhãn dấu hai chấm: `case ...:`

Dạng dấu hai chấm tạo các **nhóm câu lệnh** (*statement groups*). Trong nhóm, Java thực thi các câu lệnh theo thứ tự. Nếu không có cấu trúc chuyển điều khiển ra khỏi nhóm, luồng chạy có thể tiếp tục sang những nhóm nhãn sau.

### 3.1. Dạng `:` của switch statement dùng `break`

```java
static void printPlan(String plan) {
    switch (plan) {
        case "FREE":
            System.out.println("Gói miễn phí");
            break;

        case "STANDARD":
            System.out.println("Gói tiêu chuẩn");
            break;

        case "PREMIUM":
            System.out.println("Gói cao cấp");
            break;

        default:
            System.out.println("Gói không xác định");
    }
}
```

Ở đây, `break;` **thoát switch statement**. Nếu bỏ `break;` sau `case "FREE":`, chương trình có thể in thêm thông điệp của `STANDARD` và các nhánh bên dưới.

### 3.2. Dạng `:` của switch expression dùng `yield`

Vẫn có thể sử dụng nhãn dấu hai chấm trong switch expression, nhưng phải **cung cấp kết quả** bằng `yield`:

```java
static String planDescription(String plan) {
    return switch (plan) {
        case "FREE":
            yield "Gói miễn phí";

        case "STANDARD":
            yield "Gói tiêu chuẩn";

        case "PREMIUM":
            yield "Gói cao cấp";

        default:
            yield "Gói không xác định";
    };
}
```

Trong một switch expression dùng `:`:

1. Java nhảy tới nhãn phù hợp.
2. Các câu lệnh được thực hiện theo thứ tự.
3. `yield biểuThức;` cung cấp giá trị của **cả switch expression** và kết thúc việc đánh giá biểu thức đó.
4. Nếu luồng điều khiển có thể kết thúc switch expression mà không cung cấp giá trị hoặc ném ngoại lệ, chương trình không hợp lệ.

**Không thay `yield "x";` bằng `break "x";`**: cú pháp `break giáTrị` không phải cơ chế trả giá trị trong Java 17. `break;` dùng để thoát khỏi switch statement hoặc vòng lặp tương ứng, còn `yield` dùng để đưa giá trị ra khỏi switch expression.

## 4. Cùng bài toán, viết hai kiểu nhãn để đối chiếu

Lưu ví dụ hoàn chỉnh vào **`SwitchLabelsDemo.java`**:

```java
enum ShippingMethod {
    STANDARD, EXPRESS, SAME_DAY
}

public class SwitchLabelsDemo {

    static int feeWithArrow(ShippingMethod method) {
        return switch (method) {
            case STANDARD -> 15_000;
            case EXPRESS -> 30_000;
            case SAME_DAY -> 50_000;
        };
    }

    static int feeWithColon(ShippingMethod method) {
        return switch (method) {
            case STANDARD:
                yield 15_000;
            case EXPRESS:
                yield 30_000;
            case SAME_DAY:
                yield 50_000;
        };
    }

    public static void main(String[] args) {
        for (ShippingMethod method : ShippingMethod.values()) {
            int arrowFee = feeWithArrow(method);
            int colonFee = feeWithColon(method);

            System.out.println(
                    method + " -> arrow=" + arrowFee
                    + ", colon=" + colonFee
            );
        }
    }
}
```

Biên dịch và chạy bằng Java 17:

```bash
javac --release 17 SwitchLabelsDemo.java
java SwitchLabelsDemo
```

Kết quả:

```text
STANDARD -> arrow=15000, colon=15000
EXPRESS -> arrow=30000, colon=30000
SAME_DAY -> arrow=50000, colon=50000
```

Cả hai phương thức có kết quả giống nhau nhưng khác ở cách viết và điều khiển luồng:

| Mũi tên | Dấu hai chấm |
| --- | --- |
| `case STANDARD -> 15_000;` | `case STANDARD: yield 15_000;` |
| Viết ít câu lệnh hơn khi giá trị trả về đơn giản. | Có thể chứa nhiều câu lệnh trong nhóm trước `yield`. |
| Không có fall-through giữa các nhánh. | Có thể có fall-through nếu chưa `yield` hoặc chưa kết thúc bất thường. |
| Với nhiều câu lệnh, dùng `-> { ... yield ...; }`. | Có thể viết câu lệnh sau nhãn rồi `yield` trực tiếp. |

Với switch expression mới, **nên ưu tiên nhãn mũi tên** nếu các nhánh độc lập. Dạng dấu hai chấm vẫn hoàn toàn hợp lệ và hữu ích khi cần hiểu hoặc duy trì mã dùng statement groups.

## 5. Fall-through: sự khác biệt quan trọng nhất

*Fall-through* là hiện tượng chương trình **tiếp tục chạy vào nhóm câu lệnh của nhãn tiếp theo** sau khi đã đi vào một nhánh, nếu chưa gặp lệnh chuyển điều khiển như `break`, `yield`, `return` hoặc `throw` thích hợp.

### 5.1. Với nhãn mũi tên, không có fall-through

```java
static String category(int code) {
    return switch (code) {
        case 1 -> "One";
        case 2 -> "Two";
        default -> "Other";
    };
}
```

Với `code == 1`, kết quả luôn là `"One"`. Không thể vô tình chạy tiếp biểu thức `"Two"`. Không cần dùng `break` để ngăn điều đó.

### 5.2. Với nhãn dấu hai chấm, có thể fall-through

```java
static String categoryWithFallThrough(int code) {
    return switch (code) {
        case 0:
            System.out.println("Đã gặp số không");
            // Không có yield nên tiếp tục sang case 1.
        case 1:
            yield "Zero or One";
        default:
            yield "Other";
    };
}
```

Nếu `code == 0`, chương trình in `Đã gặp số không` rồi tiếp tục đến `yield "Zero or One";`. Nếu `code == 1`, chương trình đi thẳng tới `yield "Zero or One";`.

Kiểu điều khiển này hợp lệ nhưng dễ gây hiểu nhầm. Khi **nhiều giá trị thực sự dùng chung một kết quả**, không cần cố ý fall-through:

```java
static String categoryClearer(int code) {
    return switch (code) {
        case 0, 1 -> "Zero or One";
        default -> "Other";
    };
}
```

Đây là một lợi thế của cú pháp nhãn mũi tên trên Java 17: ý định gộp trường hợp rõ ràng, giảm nguy cơ bỏ quên `break` hoặc `yield`.

### 5.3. Dạng dấu hai chấm cũng có thể gộp nhãn mà không viết lặp

```java
static String categoryWithGroupedColon(int code) {
    return switch (code) {
        case 0:
        case 1:
            yield "Zero or One";
        default:
            yield "Other";
    };
}
```

Vì `case 0:` không có câu lệnh nào trước `case 1:`, hai nhãn đều dẫn tới cùng câu lệnh `yield`. Với Java 17, còn có thể viết một nhãn nhiều hằng:

```java
static String categoryWithMultiLabelColon(int code) {
    return switch (code) {
        case 0, 1:
            yield "Zero or One";
        default:
            yield "Other";
    };
}
```

Cả hai cách đều hợp lệ, nhưng nếu chỉ có các nhánh trả về giá trị độc lập, phiên bản `case 0, 1 -> "Zero or One";` ngắn gọn hơn.

## 6. `yield`, `break`, `return` và `throw` khác nhau thế nào?

Những từ khóa này đều liên quan đến luồng điều khiển, nhưng không thể hoán đổi tùy ý.

| Từ khóa | Ý nghĩa trong ngữ cảnh đang xét | Ví dụ phù hợp |
| --- | --- | --- |
| `yield value;` | Kết thúc **switch expression** đang bao quanh và đưa ra giá trị. | `case X: yield 10;` hoặc `case X -> { yield 10; }` |
| `break;` | Thoát **switch statement** hoặc vòng lặp nhận `break` tương ứng. | `case X: doWork(); break;` |
| `return value;` | Trả kết quả và kết thúc **phương thức** hiện tại. | `return switch (key) { ... };` |
| `throw exception;` | Ném ngoại lệ, kết thúc luồng bình thường ở nhánh đó. | `default -> throw new IllegalArgumentException();` |

Một nhầm lẫn phổ biến là cố viết:

```java
static int wrong(int code) {
    // SAI: break không phải cách trả kết quả từ switch expression.
    // return switch (code) {
    //     case 1:
    //         break 10;
    //     default:
    //         break 0;
    // };
    return 0;
}
```

Phiên bản đúng:

```java
static int correct(int code) {
    return switch (code) {
        case 1:
            yield 10;
        default:
            yield 0;
    };
}
```

Trong block của nhãn mũi tên cũng không thể dùng `return` để **thay thế** `yield` trong một switch expression. Nếu cần trả về từ phương thức, hãy dùng `return` **ở bên ngoài** biểu thức:

```java
static int amount(int code) {
    return switch (code) {
        case 1 -> {
            int computed = 10 * 2;
            yield computed;
        }
        default -> 0;
    };
}
```

Ngoài ra, switch statement với nhãn mũi tên không có nhu cầu dùng `yield` bởi nó không tạo giá trị của switch expression:

```java
static void announce(int code) {
    switch (code) {
        case 1 -> System.out.println("Đã tạo");
        case 2 -> System.out.println("Đã cập nhật");
        default -> System.out.println("Khác");
    }
}
```

**Nhận biết bằng ngữ cảnh:** nếu toàn bộ `switch` nằm bên phải phép gán hoặc sau `return` để tạo giá trị, đó là switch expression; nếu `switch` đứng như một câu lệnh độc lập để thực hiện hành động, đó là switch statement.

## 7. Kiểu giá trị và tính đầy đủ của switch expression

Vì switch expression luôn được dùng như **một giá trị**, compiler phải có thể xác định rằng tất cả các khả năng của selector đã được xử lý.

### 7.1. Selector kiểu `int` hoặc `String` thường cần `default`

```java
static String mapCode(int code) {
    return switch (code) {
        case 1 -> "Created";
        case 2 -> "Updated";
        default -> "Unknown";
    };
}
```

Nếu bỏ `default` thì switch expression trên `int` này không bao phủ mọi giá trị có thể xảy ra. Cách viết với dấu hai chấm cũng cần đủ các trường hợp:

```java
static String mapCodeWithColon(int code) {
    return switch (code) {
        case 1:
            yield "Created";
        case 2:
            yield "Updated";
        default:
            yield "Unknown";
    };
}
```

Một nhánh có thể `throw` thay vì cung cấp giá trị, miễn các đường đi đều được xử lý.

### 7.2. Với enum, có thể liệt kê đủ mọi constant

```java
enum TrafficLight {
    RED, YELLOW, GREEN
}

static String instruction(TrafficLight light) {
    return switch (light) {
        case RED -> "Stop";
        case YELLOW -> "Slow down";
        case GREEN -> "Go";
    };
}
```

Không bắt buộc `default` nếu switch expression đã bao phủ đủ ba giá trị enum. Điều này có ích vì khi bổ sung một enum constant và biên dịch lại các nơi dùng switch, compiler có thể chỉ ra nơi cần cập nhật logic.

Nếu API phát hành enum thay đổi sau khi chương trình đã được biên dịch, vẫn cần xem xét tương thích nhị phân và xử lý tại runtime; **không thay thế kiểm thử nâng cấp phụ thuộc chỉ bằng việc enum đã có vẻ đầy đủ ở thời điểm viết mã**.

### 7.3. Các nhánh phải cung cấp kết quả có kiểu tương thích

```java
static double discountRatio(String tier) {
    return switch (tier) {
        case "SILVER" -> 0.05;
        case "GOLD" -> 0.10;
        default -> 0.0;
    };
}
```

Kiểu kết quả của từng nhánh phải phù hợp với cách sử dụng switch expression và quy tắc kiểu của Java. Không thể trả về một đối tượng không tương thích với kiểu đích mà không có chuyển đổi hợp lệ.

Nếu trong nhánh `-> { ... }` có những đường đi tiếp tục sau block mà **không `yield` hoặc `throw`**, compiler sẽ từ chối switch expression. Dấu hai chấm cũng chịu cùng yêu cầu giá trị, dù các câu lệnh có thể fall-through từ một nhãn sang nhãn khác.

## 8. Những vấn đề về phạm vi biến và block

### 8.1. Block sau `->` tạo phạm vi biến rõ ràng

```java
static int compute(String mode) {
    return switch (mode) {
        case "A" -> {
            int result = 10;
            yield result;
        }
        case "B" -> {
            int result = 20;
            yield result;
        }
        default -> 0;
    };
}
```

Hai biến địa phương cùng tên `result` hợp lệ vì nằm trong **hai block riêng**.

### 8.2. Với `:`, có thể dùng block để tách phạm vi

```java
static int computeWithColon(String mode) {
    return switch (mode) {
        case "A": {
            int result = 10;
            yield result;
        }
        case "B": {
            int result = 20;
            yield result;
        }
        default:
            yield 0;
    };
}
```

Trong switch dùng nhóm câu lệnh dấu hai chấm, các nhãn không tự tạo block độc lập. Khi cần khai báo biến cùng tên trong nhiều nhánh, đặt các câu lệnh của từng nhánh trong `{ ... }` để tránh xung đột phạm vi. Điều này cũng giúp người đọc hiểu rõ các biến chỉ phục vụ nhánh nào.

## 9. Các lỗi cú pháp và logic thường gặp

### Lỗi 1 — Đặt `;` sai sau block của nhãn mũi tên

```java
static int fee(int code) {
    return switch (code) {
        case 1 -> {
            yield 10;
        }
        default -> 0;
    };
}
```

Không cần thêm dấu chấm phẩy **ngay sau `}` của block nhánh**. Dấu `;` kết thúc toàn bộ câu lệnh `return switch (...) { ... };` nằm **sau dấu `}` cuối cùng** của switch expression.

### Lỗi 2 — Viết `case X: expression;` và mong expression tự trả giá trị

```java
// Sai: câu lệnh ở nhánh dấu hai chấm chưa yield giá trị.
// int result = switch (code) {
//     case 1:
//         10;
//     default:
//         0;
// };
```

Sửa thành `case 1: yield 10;` và `default: yield 0;`, hoặc đổi toàn bộ sang nhãn mũi tên.

### Lỗi 3 — Quên `yield` ở một đường đi của block

```java
// Sai: nếu amount <= 0, nhánh không tạo ra giá trị.
// return switch (code) {
//     case 1 -> {
//         if (amount > 0) {
//             yield amount;
//         }
//     }
//     default -> 0;
// };
```

Sửa bằng cách xử lý cả hai đường đi:

```java
static int normalizedAmount(int code, int amount) {
    return switch (code) {
        case 1 -> {
            if (amount > 0) {
                yield amount;
            }
            yield 0;
        }
        default -> 0;
    };
}
```

### Lỗi 4 — Trộn nhãn `->` và `:` trong cùng switch

```java
// Sai: không trộn hai dạng nhãn trong cùng một switch block.
// return switch (code) {
//     case 1 -> "One";
//     default:
//         yield "Other";
// };
```

Chọn thống nhất một trong hai:

```java
static String describe(int code) {
    return switch (code) {
        case 1 -> "One";
        default -> "Other";
    };
}
```

### Lỗi 5 — Nhầm `break` với `yield`

Một switch statement dùng `:` thường cần `break` để tránh chạy tiếp nhánh. Một switch expression dùng `:` cần `yield` để đưa ra kết quả. Không thể chép nguyên cách điều khiển luồng của statement sang expression mà không xét sự khác biệt này.

### Lỗi 6 — Cho rằng `default` luôn xử lý được `null`

```java
static String label(String input) {
    return switch (input) {
        case "A" -> "Alpha";
        default -> "Other";
    };
}
```

Với cú pháp switch thông thường, **selector `null` gây `NullPointerException` trong Java 17**; không tự động đi vào `default`. Nếu đầu vào có thể `null`, hãy xử lý trước:

```java
static String safeLabel(String input) {
    if (input == null) {
        return "Missing";
    }

    return switch (input) {
        case "A" -> "Alpha";
        default -> "Other";
    };
}
```

Không dựa vào các cú pháp pattern matching trong `switch` của những bản Java mới hơn để viết ví dụ chạy mặc định trên Java 17: **pattern matching for switch chỉ là preview trong JDK 17** (JEP 406).

### Lỗi 7 — Dùng `case` như một điều kiện `if` tùy ý

Các nhãn `case` của Java 17 dùng được với **những dạng hằng phù hợp kiểu selector**, các nhãn enum và các khả năng ngôn ngữ tương ứng. Chúng không phải nơi thay tùy ý bằng điều kiện runtime như `case value > 10 -> ...` trong switch thông thường.

Nếu cần kiểm tra khoảng số như `score >= 90`, có thể dùng `if/else` trước khi áp dụng `switch`, hoặc chuyển thành một nhóm hằng/loại trạng thái rõ ràng phù hợp miền nghiệp vụ.

## 10. Lựa chọn nhãn nào trong code Java 17?

| Tình huống | Cách viết được đề xuất |
| --- | --- |
| Mỗi giá trị dẫn tới một giá trị trả về riêng. | Switch expression với `-> biểuThức`. |
| Nhánh có nhiều bước tính toán rồi tạo ra kết quả. | `case X -> { ... yield result; }`. |
| Nhiều hằng cùng dùng chung một kết quả. | `case A, B, C -> value;`. |
| Muốn thực thi một hành động theo từng trường hợp, không cần giá trị chung. | Switch statement với `-> câuLệnh;` hoặc `-> { ... }`. |
| Đang đọc hoặc bảo trì switch expression sử dụng statement groups. | Hiểu `case X: ... yield value;` và khả năng fall-through. |
| Cần fall-through có chủ ý giữa các nhóm câu lệnh. | Nhãn `:` có thể diễn đạt, nhưng cần giải thích rõ bằng comment và xem có thể thay bằng nhóm nhãn hay không. |
| Dữ liệu đầu vào có thể `null`. | Xử lý `null` trước khi vào switch Java 17 thông thường. |

Đối với code mới, **nhãn mũi tên thường dễ bảo trì hơn** vì loại bỏ fall-through không chủ ý. Dạng dấu hai chấm vẫn là một phần được hỗ trợ của Java 17 và có thể có ý nghĩa khi logic đang cần các nhóm câu lệnh. Trọng tâm là chọn đúng cách điều khiển luồng, không phải ép mọi switch statement thành switch expression.

## 11. Ví dụ tình huống thực tế: phân loại trạng thái đơn hàng

Giả sử hệ thống có enum:

```java
enum OrderStatus {
    CREATED,
    PAID,
    PACKED,
    SHIPPED,
    CANCELLED
}
```

Người dùng cần biết có thể sửa địa chỉ giao hàng hay không. Với switch expression:

```java
static boolean canChangeAddress(OrderStatus status) {
    return switch (status) {
        case CREATED, PAID -> true;
        case PACKED, SHIPPED, CANCELLED -> false;
    };
}
```

Nhãn mũi tên phù hợp vì mỗi tập trạng thái trả một boolean mà không cần tác dụng phụ. Nếu cần thông báo vì sao không sửa được, có thể giữ nhiều bước trong block:

```java
static String addressChangeMessage(OrderStatus status) {
    return switch (status) {
        case CREATED, PAID -> "Có thể sửa địa chỉ";
        case PACKED, SHIPPED -> {
            String stage = status.name();
            yield "Đơn đang xử lý giao hàng: " + stage;
        }
        case CANCELLED -> "Đơn đã hủy";
    };
}
```

Cùng logic viết dưới dạng dấu hai chấm:

```java
static boolean canChangeAddressWithColon(OrderStatus status) {
    return switch (status) {
        case CREATED:
        case PAID:
            yield true;
        case PACKED:
        case SHIPPED:
        case CANCELLED:
            yield false;
    };
}
```

Việc đối chiếu hai phương thức cho thấy:

1. **Tập trạng thái và kết quả không đổi.**
2. Dạng mũi tên bộc lộ việc gộp nhãn ngay trong một dòng và không cần `yield` cho biểu thức đơn.
3. Dạng dấu hai chấm sử dụng các nhãn nối tiếp và một `yield` chung để trả kết quả.
4. Nếu thêm một `OrderStatus` mới, cả hai switch expression có thể cần được cập nhật để bao phủ trường hợp mới khi biên dịch lại.

**Lưu ý thiết kế:** Việc liệu một đơn ở trạng thái `PAID` được sửa địa chỉ hay không là quy tắc giả định của ví dụ, không phải quy tắc chung cho mọi hệ thống thương mại điện tử. Nên đặt logic phân quyền theo yêu cầu thực tế của ứng dụng.

## 12. Bài tập thực hành

### Bài 1 — Chuyển `:` sang `->`

Viết lại phương thức sau bằng nhãn mũi tên mà không đổi đầu ra:

```java
static String severityLabel(int level) {
    return switch (level) {
        case 1:
            yield "LOW";
        case 2:
            yield "MEDIUM";
        case 3:
            yield "HIGH";
        default:
            yield "UNKNOWN";
    };
}
```

Gợi ý: với mỗi nhánh chỉ có một `yield`, chuyển trực tiếp thành `case X -> "VALUE";`.

### Bài 2 — Gộp nhiều nhãn

Cho enum:

```java
enum MonthGroup {
    JANUARY, FEBRUARY, MARCH, APRIL, MAY, JUNE,
    JULY, AUGUST, SEPTEMBER, OCTOBER, NOVEMBER, DECEMBER
}
```

Viết `static boolean isSummer(MonthGroup month)` trả `true` cho `JUNE`, `JULY`, `AUGUST`. Dùng switch expression với nhãn mũi tên và **gộp những hằng có cùng kết quả** vào các nhánh thích hợp.

### Bài 3 — Nhánh nhiều câu lệnh

Viết `static int bonus(int level, int baseAmount)`. Khi `level == 1`, trả `0`; khi `level == 2`, tính thêm `baseAmount * 5 / 100`; khi `level == 3`, tính thêm `baseAmount * 10 / 100`. Dùng `-> { ... yield ...; }` cho các nhánh cần nhiều bước.

### Bài 4 — Phân tích fall-through

Đoán kết quả của:

```java
static String inspect(int code) {
    return switch (code) {
        case 0:
            System.out.println("A");
        case 1:
            System.out.println("B");
            yield "X";
        default:
            yield "Y";
    };
}
```

Xét riêng `inspect(0)`, `inspect(1)` và `inspect(2)`. Viết lại với nhãn mũi tên sao cho phần **giá trị trả về** tương đương; nếu muốn giữ cả thông điệp được in ra, hãy sử dụng block và ghi rõ các thao tác in cần thiết cho từng trường hợp.

### Bài 5 — Tìm và sửa lỗi

Đoạn sau có những vấn đề gì khi biên dịch Java 17?

```java
// Đoạn minh họa lỗi:
// String result = switch (code) {
//     case 1 -> "ONE";
//     case 2:
//         yield "TWO";
// };
```

Gợi ý: xem lại **quy tắc không trộn nhãn**, **tính bao quát với kiểu int**, rồi sửa bằng một kiểu nhãn thống nhất và bổ sung trường hợp cần thiết.

## 13. Tài liệu chính thức của Java 17

- [JLS Java SE 17, §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11): switch statement, nhóm câu lệnh, quy tắc nhãn và điều khiển luồng.
- [JLS Java SE 17, §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): switch expression, kiểu kết quả và tính bao quát.
- [JLS Java SE 17, §14.21 — The yield Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.21): cách `yield` chuyển giá trị ra khỏi switch expression.
- [JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): động cơ thiết kế, nhãn mũi tên, chống fall-through ngoài ý muốn và trạng thái chính thức từ JDK 14.
- [Java 17 Language Guide — Switch Expressions](https://docs.oracle.com/en/java/javase/17/language/switch-expressions.html): hướng dẫn cú pháp switch expression trong tài liệu Java 17.
- [JEP 406 — Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406): tài liệu phân biệt các mở rộng preview ở JDK 17 với cú pháp switch expression ổn định.

Khi viết switch expression Java 17, hãy nhớ: **nhãn `->` phù hợp cho nhánh độc lập, trả giá trị trực tiếp; nhãn `:` dùng các nhóm câu lệnh và phải có `yield` để tạo giá trị.** Điểm quan trọng nhất không nằm ở ký hiệu, mà ở việc hiểu rõ **fall-through**, **khả năng tạo giá trị trên mọi đường đi** và sự khác nhau giữa **switch expression** với **switch statement**.
