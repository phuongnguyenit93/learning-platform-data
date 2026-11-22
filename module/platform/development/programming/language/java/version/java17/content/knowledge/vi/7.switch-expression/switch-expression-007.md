# Quy tắc không rơi nhánh của dạng mũi tên trong switch expression — Java 17

Trong Java 17, `switch` hỗ trợ cú pháp mũi tên **`case ... ->`** để chọn một nhánh xử lý. Điểm nổi bật của cú pháp này là **không xảy ra fall-through (rơi nhánh)**: khi một nhánh khớp, chương trình chỉ thực hiện phần mã thuộc nhánh đó, không tự chạy tiếp phần mã của các nhánh `case` phía dưới.

Quy tắc này áp dụng cho cả hai cách dùng:

- **Switch statement**: một câu lệnh thực hiện tác vụ, không nhất thiết trả về một giá trị.
- **Switch expression**: một biểu thức có thể gán vào biến, trả về từ phương thức hoặc dùng làm đối số; các nhánh phải cung cấp kết quả theo quy tắc của biểu thức.

Bài học tập trung vào ý nghĩa **không rơi nhánh của mũi tên** trong Java 17, cách đối chiếu với nhãn `case:`, cách nhóm nhánh, quy tắc `yield` và những lỗi thường gặp.

## 1. “Rơi nhánh” (fall-through) nghĩa là gì?

Trong cú pháp `switch` dạng dấu hai chấm, một nhánh có thể tiếp tục thực hiện những câu lệnh thuộc nhánh kế tiếp nếu không có lệnh chuyển luồng phù hợp, chẳng hạn `break`, `return` hoặc `throw`.

Ví dụ:

```java
public class ColonFallThrough {
    public static void main(String[] args) {
        int level = 1;

        switch (level) {
            case 1:
                System.out.println("Mức 1");
            case 2:
                System.out.println("Mức 2");
            default:
                System.out.println("Mức khác");
        }
    }
}
```

Kết quả:

```text
Mức 1
Mức 2
Mức khác
```

Tại sao lại in ba dòng khi `level == 1`?

1. `case 1:` khớp, nên bắt đầu thực hiện `println("Mức 1")`.
2. Không có lệnh nào chấm dứt nhánh, nên luồng chạy tiếp xuống câu lệnh trong `case 2:`.
3. Tiếp tục xuống `default:` trước khi ra khỏi `switch`.

Điều quan trọng là **các nhãn `case` phía dưới không được kiểm tra lại để quyết định có thực hiện hay không** sau khi luồng đã bắt đầu ở một nhánh. Đây chính là hiệu ứng *fall-through*.

Cú pháp dấu hai chấm vẫn được Java 17 hỗ trợ và có những trường hợp sử dụng hợp lệ. Tuy nhiên, nếu mục tiêu là “mỗi giá trị chỉ đi vào đúng một nhánh”, cú pháp mũi tên biểu đạt ý định đó trực tiếp hơn.

## 2. Dạng mũi tên: chỉ chạy một nhánh khớp

Viết lại chương trình bằng `->`:

```java
public class ArrowNoFallThrough {
    public static void main(String[] args) {
        int level = 1;

        switch (level) {
            case 1 -> System.out.println("Mức 1");
            case 2 -> System.out.println("Mức 2");
            default -> System.out.println("Mức khác");
        }
    }
}
```

Kết quả:

```text
Mức 1
```

Với `level == 1`:

- `case 1 ->` được chọn.
- Lệnh `println("Mức 1")` được thực thi.
- Switch statement kết thúc; **`case 2` và `default` không chạy**.

Không cần thêm `break;` vào cuối nhánh mũi tên.

Có thể hình dung hai cách viết như sau:

```text
Nhánh case:                      Nhánh case ->:

case 1 khớp                      case 1 khớp
     |                                |
     v                                v
Xử lý của case 1                Xử lý của case 1
     |                                |
     v                                v
Thiếu break? ------ Có          Kết thúc switch
     |                                |
     v                                v
Chạy tiếp case 2                Câu lệnh sau switch
     |
     v
Có thể chạy tiếp default
```

**Chú ý:** “Không rơi nhánh” chỉ nói về việc **không chạy sang nhánh `case` tiếp theo**. Sau khi một switch statement hoàn thành, chương trình vẫn chạy những câu lệnh tiếp theo ở phía sau switch như bình thường.

## 3. Cú pháp `case ... ->` trong switch expression

Trong **switch expression**, mỗi nhánh mũi tên có thể cung cấp trực tiếp một giá trị:

```java
public class PriorityLabel {
    static String label(int priority) {
        return switch (priority) {
            case 1 -> "Thấp";
            case 2 -> "Trung bình";
            case 3 -> "Cao";
            default -> "Không xác định";
        };
    }

    public static void main(String[] args) {
        System.out.println(label(1));
        System.out.println(label(2));
        System.out.println(label(3));
        System.out.println(label(99));
    }
}
```

Kết quả:

```text
Thấp
Trung bình
Cao
Không xác định
```

Phân tích câu lệnh:

```java
return switch (priority) {
    case 1 -> "Thấp";
    case 2 -> "Trung bình";
    case 3 -> "Cao";
    default -> "Không xác định";
};
```

- `switch (priority)` là **một biểu thức**.
- Mỗi phần `case ... -> "..."` xác định kết quả của **một nhánh**.
- Với giá trị `1`, biểu thức cho ra `"Thấp"`; nó **không đánh giá** nhánh `2` hoặc `3`.
- `return` nằm **bên ngoài switch expression**, trả kết quả của toàn bộ biểu thức về cho người gọi.
- Dấu `;` cuối cùng kết thúc câu lệnh `return switch ...;`.

Khác với cách viết phải gán lại biến ở từng nhánh, switch expression cho phép tập trung trực tiếp vào **giá trị kết quả**.

## 4. Phân biệt switch statement mũi tên và switch expression mũi tên

Hai dạng đều dùng `->` và đều **không fall-through**, nhưng yêu cầu về kết quả khác nhau.

### 4.1. Switch statement: thực hiện hành động

```java
public class ActionDemo {
    static void execute(String action) {
        switch (action) {
            case "SAVE" -> System.out.println("Đang lưu");
            case "DELETE" -> System.out.println("Đang xóa");
            default -> System.out.println("Không hỗ trợ");
        }

        System.out.println("Kết thúc xử lý");
    }

    public static void main(String[] args) {
        execute("SAVE");
    }
}
```

Kết quả:

```text
Đang lưu
Kết thúc xử lý
```

Nhánh `SAVE` kết thúc mà không rơi sang `DELETE` hoặc `default`. Sau đó chương trình **vẫn thực hiện** câu lệnh `System.out.println("Kết thúc xử lý")` ở bên dưới switch.

Switch statement không bắt buộc mỗi nhánh trả ra một giá trị, và với `int`/`String` thông thường có thể không viết `default` nếu không muốn thực hiện gì khi không có nhánh khớp.

### 4.2. Switch expression: phải cho ra kết quả

```java
public class ResultDemo {
    static String message(String action) {
        String result = switch (action) {
            case "SAVE" -> "Đã chọn lưu";
            case "DELETE" -> "Đã chọn xóa";
            default -> "Không hỗ trợ";
        };

        return result;
    }

    public static void main(String[] args) {
        System.out.println(message("SAVE"));
    }
}
```

Kết quả:

```text
Đã chọn lưu
```

Trong switch expression, mỗi nhánh được thực thi bình thường phải cung cấp kết quả; không thể chỉ in thông báo rồi kết thúc nhánh mà không tạo giá trị. Một nhánh cũng có thể **ném ngoại lệ** thay vì trả kết quả, như các phần bên dưới.

| Tiêu chí | Switch statement dạng `->` | Switch expression dạng `->` |
| --- | --- | --- |
| Mục đích | Thực hiện câu lệnh/hành động. | Tính một giá trị. |
| Có fall-through không? | Không. | Không. |
| Có bắt buộc cho ra giá trị không? | Không. | Có, trên mọi đường đi kết thúc bình thường. |
| Có cần `break` để tránh rơi nhánh không? | Không. | Không. |
| Có cần bao phủ mọi giá trị selector không? | Không nhất thiết. | Có, biểu thức phải exhaustive (đầy đủ các trường hợp). |
| Nhánh mũi tên nhiều câu lệnh | Dùng khối `{ ... }`. | Dùng khối `{ ... }` và `yield` giá trị, hoặc ném ngoại lệ. |

## 5. Nhóm nhiều giá trị vào cùng một nhánh với dấu phẩy

Trước đây, người viết `switch` có thể cố ý dùng các nhãn `case:` kế tiếp nhau để cùng chạy một khối xử lý. Với cú pháp mũi tên, hãy viết **nhiều nhãn trong cùng một `case`**, ngăn cách bằng dấu phẩy.

Ví dụ, phân loại thứ trong tuần:

```java
public class DayType {
    static String classify(int day) {
        return switch (day) {
            case 2, 3, 4, 5, 6 -> "Ngày làm việc";
            case 7, 1 -> "Cuối tuần";
            default -> "Ngày không hợp lệ";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(2));
        System.out.println(classify(7));
        System.out.println(classify(0));
    }
}
```

Kết quả:

```text
Ngày làm việc
Cuối tuần
Ngày không hợp lệ
```

Mã `case 2, 3, 4, 5, 6 ->` nói rằng **bất kỳ giá trị nào trong nhóm** đều chọn cùng một nhánh và tạo cùng kết quả.

### Vì sao không viết các nhãn mũi tên nối tiếp để “chạy chung”?

Xét:

```java
return switch (day) {
    case 2 -> "Ngày làm việc";
    case 3 -> "Ngày làm việc";
    case 4 -> "Ngày làm việc";
    default -> "Khác";
};
```

Cách này **hợp lệ**, nhưng ba nhánh hoạt động độc lập; chúng không chạy nối tiếp và không rơi nhánh. Nếu cùng hành vi, nhóm lại như `case 2, 3, 4 -> "Ngày làm việc";` sẽ ngắn gọn hơn.

**Sai về ý định** là trông chờ `case 2 ->` thực hiện mã ở `case 3 ->`. Với nhánh mũi tên, Java không bao giờ tự chuyển từ nhánh `2` sang nhánh `3`.

### Đối chiếu cùng ý định với dạng dấu hai chấm

Dạng dấu hai chấm cũng có thể nhóm nhãn:

```java
String type;
switch (day) {
    case 2:
    case 3:
    case 4:
        type = "Ngày làm việc";
        break;
    default:
        type = "Khác";
}
```

Với dạng mũi tên, ý định “nhiều giá trị, một kết quả” được biểu diễn trực tiếp:

```java
String type = switch (day) {
    case 2, 3, 4 -> "Ngày làm việc";
    default -> "Khác";
};
```

Dấu phẩy trong `case 2, 3, 4` **không phải fall-through**. Đó là một nhánh duy nhất có nhiều nhãn.

## 6. Nhánh mũi tên chứa nhiều câu lệnh: dùng khối và `yield`

Một switch expression đôi khi phải thực hiện thêm logic trước khi tạo kết quả. Lúc đó nhánh mũi tên cần khối `{ ... }` và lệnh **`yield`**.

```java
public class ShippingFee {
    static int calculateFee(String method, int weightKg) {
        if (weightKg <= 0) {
            throw new IllegalArgumentException("Khối lượng phải dương");
        }

        return switch (method) {
            case "STANDARD" -> 20_000;

            case "EXPRESS" -> {
                int baseFee = 40_000;
                int extraFee = Math.max(0, weightKg - 1) * 5_000;
                yield baseFee + extraFee;
            }

            case "PICKUP" -> 0;

            default -> throw new IllegalArgumentException(
                    "Phương thức giao hàng không được hỗ trợ: " + method
            );
        };
    }

    public static void main(String[] args) {
        System.out.println(calculateFee("STANDARD", 3));
        System.out.println(calculateFee("EXPRESS", 3));
        System.out.println(calculateFee("PICKUP", 3));
    }
}
```

Kết quả:

```text
20000
50000
0
```

Ở nhánh `EXPRESS`:

1. Java chọn nhánh do `method` bằng `"EXPRESS"`.
2. Thực thi các phép tính trong khối.
3. `yield baseFee + extraFee;` cung cấp **giá trị của toàn bộ switch expression**.
4. Các nhánh `PICKUP` và `default` không được thực hiện.

Có ba dạng đáng nhớ khi dùng nhánh mũi tên trong switch expression:

```java
// 1. Một biểu thức tính giá trị:
case "STANDARD" -> 20_000;

// 2. Khối nhiều câu lệnh và yield:
case "EXPRESS" -> {
    int fee = 40_000;
    yield fee;
}

// 3. Ném ngoại lệ thay cho kết quả:
default -> throw new IllegalArgumentException("Sai phương thức");
```

Trong dạng **biểu thức ngắn**, không cần viết `yield`. Trong dạng **khối nhiều câu lệnh**, dùng `yield` để tạo giá trị khi nhánh hoàn thành bình thường.

### `yield` kết thúc nhánh đang chạy, không đi sang nhánh kế

Ví dụ:

```java
int score = switch (level) {
    case 1 -> {
        System.out.println("Kiểm tra mức 1");
        yield 10;
    }
    case 2 -> {
        System.out.println("Kiểm tra mức 2");
        yield 20;
    }
    default -> 0;
};
```

Nếu `level == 1`, chương trình chỉ in `"Kiểm tra mức 1"` và gán `score = 10`. `yield` hoàn tất switch expression tại nhánh đó.

Không nên hiểu `yield` là “chuyển sang `case` kế tiếp”. Nó là một cơ chế **trả giá trị từ switch expression**.

## 7. Nhánh `throw` cũng không rơi nhánh

Một nhánh switch expression có thể ném ngoại lệ khi đầu vào không hợp lệ:

```java
public class Discount {
    static int percent(String category) {
        return switch (category) {
            case "REGULAR" -> 0;
            case "SILVER" -> 5;
            case "GOLD" -> 10;
            default -> throw new IllegalArgumentException(
                    "Danh mục không hợp lệ: " + category
            );
        };
    }
}
```

Nếu `category == "UNKNOWN"`, nhánh `default` ném `IllegalArgumentException`. Chương trình không tiếp tục xuống nhánh nào khác và cũng không nhận được giá trị bình thường từ biểu thức.

Đối với switch expression, nhánh `throw` là một lựa chọn hữu ích khi không tồn tại kết quả dự phòng hợp lệ. Mọi nhánh **có thể hoàn tất bình thường** vẫn phải cung cấp giá trị; nhánh **luôn ném ngoại lệ** không cần `yield`.

## 8. Không rơi nhánh không đồng nghĩa “đã kết thúc phương thức”

Đây là điểm dễ nhầm khi chuyển từ `switch statement` sang `switch expression`.

### Switch statement: sau nhánh khớp vẫn chạy lệnh kế tiếp

```java
static void process(int action) {
    switch (action) {
        case 1 -> System.out.println("Tạo");
        case 2 -> System.out.println("Sửa");
        default -> System.out.println("Khác");
    }

    System.out.println("Hoàn tất phương thức");
}
```

Gọi `process(1)` cho kết quả:

```text
Tạo
Hoàn tất phương thức
```

Không có fall-through từ `case 1` sang `case 2`, **nhưng câu lệnh sau switch vẫn chạy**.

### Switch expression: biểu thức cung cấp giá trị cho lệnh bao ngoài

```java
static String process(int action) {
    String message = switch (action) {
        case 1 -> "Tạo";
        case 2 -> "Sửa";
        default -> "Khác";
    };

    System.out.println("Đã xác định hành động");
    return message;
}
```

Switch expression hoàn thành với một giá trị; sau đó `println` và `return message` vẫn chạy. Trừ khi nhánh ném ngoại lệ, switch expression không tự chấm dứt phương thức.

Vì thế, cần phân biệt ba thao tác:

| Thao tác | Ý nghĩa |
| --- | --- |
| Kết thúc nhánh mũi tên | Không chạy các nhánh `case` khác. |
| `yield value;` | Cung cấp giá trị và hoàn tất switch expression. |
| `return value;` ở bên ngoài switch expression | Trả giá trị từ phương thức chứa switch. |

## 9. Switch expression phải bao phủ đầy đủ các trường hợp

Quy tắc **không fall-through** độc lập với một quy tắc khác của switch expression: **exhaustiveness** — biểu thức phải xác định được cách xử lý cho mọi giá trị thuộc miền selector có thể xảy ra.

### 9.1. Với `int`, thường dùng `default`

**Sai — thiếu cách xử lý cho giá trị khác `1` và `2`:**

```java
static String label(int level) {
    return switch (level) {
        case 1 -> "Một";
        case 2 -> "Hai";
        // LỖI: switch expression không bao phủ mọi giá trị int.
    };
}
```

**Đúng:**

```java
static String label(int level) {
    return switch (level) {
        case 1 -> "Một";
        case 2 -> "Hai";
        default -> "Khác";
    };
}
```

Tính exhaustive không có nghĩa mỗi nhánh phải dùng `break`; `default` ở đây chỉ cung cấp lựa chọn cho những giá trị chưa được liệt kê.

### 9.2. Với `enum`, có thể liệt kê toàn bộ hằng số

```java
enum TrafficSignal {
    RED, YELLOW, GREEN
}

public class TrafficSignalDemo {
    static String instruction(TrafficSignal signal) {
        return switch (signal) {
            case RED -> "Dừng";
            case YELLOW -> "Chuẩn bị dừng";
            case GREEN -> "Đi";
        };
    }

    public static void main(String[] args) {
        System.out.println(instruction(TrafficSignal.RED));
    }
}
```

Ví dụ này không cần `default` vì ba hằng số `RED`, `YELLOW` và `GREEN` đã được bao phủ đầy đủ. Đây là đặc điểm hữu ích khi miền giá trị được mô tả rõ ràng bằng `enum`.

Nếu thêm hằng số `BLUE` vào chính định nghĩa `TrafficSignal` và biên dịch lại mã nguồn trên mà chưa bổ sung nhánh, trình biên dịch có thể phát hiện switch expression không còn đầy đủ.

Lưu ý: tính exhaustive theo `enum` không biến `null` thành hằng số enum; xử lý `null` là vấn đề riêng.

## 10. `null` không tự rơi vào `default`

Trong Java 17 với cú pháp switch chuẩn không bật tính năng preview, nếu selector nhận `null`, việc đánh giá switch trên tham chiếu đó sẽ ném `NullPointerException`. Nhánh `default` **không phải** là cơ chế xử lý `null`.

Ví dụ:

```java
static String classify(String code) {
    return switch (code) {
        case "A" -> "Nhóm A";
        case "B" -> "Nhóm B";
        default -> "Nhóm khác";
    };
}
```

Gọi `classify(null)` sẽ ném `NullPointerException`; nó không trả về `"Nhóm khác"`.

Nếu nghiệp vụ cho phép `null` và muốn có kết quả dự phòng, kiểm tra trước switch:

```java
static String classify(String code) {
    if (code == null) {
        return "Không có mã";
    }

    return switch (code) {
        case "A" -> "Nhóm A";
        case "B" -> "Nhóm B";
        default -> "Nhóm khác";
    };
}
```

Điều này khác với fall-through: `null` liên quan tới **giá trị selector**, còn fall-through liên quan tới **luồng chạy giữa các nhánh case**.

## 11. Các lỗi thường gặp khi viết nhánh mũi tên

### Lỗi 1: Quên `yield` trong khối nhiều câu lệnh

**Sai:**

```java
static int total(int count) {
    return switch (count) {
        case 1 -> {
            int price = 100;
            System.out.println("Một sản phẩm");
            // LỖI: khối có thể hoàn tất mà không cung cấp giá trị.
        }
        default -> 0;
    };
}
```

**Đúng:**

```java
static int total(int count) {
    return switch (count) {
        case 1 -> {
            int price = 100;
            System.out.println("Một sản phẩm");
            yield price;
        }
        default -> 0;
    };
}
```

Một switch expression phải có giá trị trên mọi đường đi kết thúc bình thường. Nếu dùng khối để thực hiện nhiều câu lệnh, `yield` là cách chuyển kết quả của khối thành kết quả của toàn bộ biểu thức.

### Lỗi 2: Dùng `break` như thể nó trả kết quả của switch expression

**Sai:**

```java
static int score(int level) {
    return switch (level) {
        case 1 -> {
            break; // LỖI khi cố kết thúc nhánh của switch expression bằng break.
        }
        default -> 0;
    };
}
```

**Đúng:**

```java
static int score(int level) {
    return switch (level) {
        case 1 -> {
            yield 10;
        }
        default -> 0;
    };
}
```

`break` không phải cơ chế tạo kết quả của switch expression. Với nhánh mũi tên ngắn, viết `case 1 -> 10;` còn gọn hơn.

### Lỗi 3: Dùng hành động `void` làm kết quả biểu thức

**Sai:**

```java
static String label(int level) {
    return switch (level) {
        case 1 -> System.out.println("Một"); // LỖI: println trả void.
        default -> "Khác";
    };
}
```

Nếu chỉ muốn in ra màn hình, dùng **switch statement**:

```java
static void printLabel(int level) {
    switch (level) {
        case 1 -> System.out.println("Một");
        default -> System.out.println("Khác");
    }
}
```

Nếu vừa muốn in vừa muốn có kết quả, dùng **khối và `yield`**:

```java
static String label(int level) {
    return switch (level) {
        case 1 -> {
            System.out.println("Một");
            yield "LEVEL_1";
        }
        default -> "Khác";
    };
}
```

### Lỗi 4: Trộn dấu hai chấm và mũi tên trong cùng một switch block

**Sai:**

```java
static String describe(int value) {
    return switch (value) {
        case 1 -> "Một";
        case 2:
            yield "Hai";  // LỖI: trộn hai kiểu nhãn trong cùng switch.
        default -> "Khác";
    };
}
```

**Đúng — thống nhất mũi tên:**

```java
static String describe(int value) {
    return switch (value) {
        case 1 -> "Một";
        case 2 -> "Hai";
        default -> "Khác";
    };
}
```

Java cho phép **hai kiểu hình thức switch block khác nhau**, nhưng không trộn `case ...:` và `case ... ->` bên trong **cùng một switch block**.

### Lỗi 5: Cho rằng nhánh tiếp theo sẽ thực hiện nốt phần còn thiếu

**Sai về thiết kế:**

```java
static String result(int value) {
    return switch (value) {
        case 1 -> "A";
        case 2 -> "B";
        default -> "C";
    };
}
```

Đoạn mã trên **biên dịch được**, nhưng nếu ai đó trông chờ `value == 1` cho kết quả kết hợp `"AB"` do chạy cả `case 1` và `case 2`, thì đó là hiểu sai. Kết quả chỉ là `"A"`.

Nếu nhiều giá trị phải cùng có kết quả `"AB"`:

```java
static String result(int value) {
    return switch (value) {
        case 1, 2 -> "AB";
        default -> "C";
    };
}
```

Nếu một nhánh cần nhiều thao tác trước khi có kết quả, đặt chúng **bên trong cùng một khối** và kết thúc bằng `yield`.

### Lỗi 6: Mỗi nhánh trả về một kiểu không phù hợp với nơi sử dụng

**Sai:**

```java
static int statusCode(int code) {
    return switch (code) {
        case 1 -> 200;
        case 2 -> "400"; // LỖI: String không thể trả về như int.
        default -> 500;
    };
}
```

**Đúng:**

```java
static int statusCode(int code) {
    return switch (code) {
        case 1 -> 200;
        case 2 -> 400;
        default -> 500;
    };
}
```

Switch expression là một **biểu thức có kiểu**. Các giá trị của nhánh phải phù hợp với kiểu mà biểu thức được dùng trong ngữ cảnh đó. Lỗi kiểu dữ liệu khác với lỗi fall-through nhưng thường xuất hiện khi chuyển switch statement sang switch expression.

### Lỗi 7: Có đường đi không cung cấp `yield`

**Sai:**

```java
static int calculate(int level, boolean premium) {
    return switch (level) {
        case 1 -> {
            if (premium) {
                yield 100;
            }
            // LỖI: premium == false thì khối kết thúc không có giá trị.
        }
        default -> 0;
    };
}
```

**Đúng:**

```java
static int calculate(int level, boolean premium) {
    return switch (level) {
        case 1 -> {
            if (premium) {
                yield 100;
            }
            yield 50;
        }
        default -> 0;
    };
}
```

Khi kiểm tra khả năng kết thúc của một nhánh khối, phải xem **mọi đường đi có thể xảy ra**, không chỉ đường đi phổ biến.

## 12. Ví dụ thực tế: tính trạng thái đơn hàng bằng switch expression

Giả sử ứng dụng có các trạng thái đơn hàng:

```java
enum OrderStatus {
    NEW,
    PROCESSING,
    SHIPPED,
    DELIVERED,
    CANCELLED
}
```

Muốn ánh xạ mỗi trạng thái thành một thông báo ngắn. Một trạng thái có thể cần nhiều câu lệnh tính toán trước khi trả kết quả. Dưới đây là ví dụ đầy đủ, dùng nguyên cú pháp Java 17 chính thức.

Tạo tệp `OrderStatusDemo.java`:

```java
enum OrderStatus {
    NEW,
    PROCESSING,
    SHIPPED,
    DELIVERED,
    CANCELLED
}

public class OrderStatusDemo {

    static String describe(OrderStatus status, int daysInTransit) {
        if (status == null) {
            throw new IllegalArgumentException("status không được null");
        }

        return switch (status) {
            case NEW -> "Đơn mới";
            case PROCESSING -> "Đang xử lý";

            case SHIPPED -> {
                if (daysInTransit < 0) {
                    throw new IllegalArgumentException(
                            "Số ngày vận chuyển không được âm"
                    );
                }

                String suffix = daysInTransit == 0
                        ? "vừa gửi"
                        : "đã đi " + daysInTransit + " ngày";

                yield "Đang giao - " + suffix;
            }

            case DELIVERED -> "Đã giao";
            case CANCELLED -> "Đã hủy";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(OrderStatus.NEW, 0));
        System.out.println(describe(OrderStatus.SHIPPED, 2));
        System.out.println(describe(OrderStatus.DELIVERED, 0));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 OrderStatusDemo.java
java OrderStatusDemo
```

Kết quả dự kiến:

```text
Đơn mới
Đang giao - đã đi 2 ngày
Đã giao
```

Ở đây:

1. `NEW` và `PROCESSING` dùng nhánh biểu thức ngắn.
2. `SHIPPED` dùng khối nhiều câu lệnh và `yield` kết quả cuối cùng.
3. Đường đi lỗi của `SHIPPED` dùng `throw`.
4. `DELIVERED` và `CANCELLED` là các nhánh độc lập; không cần `break`.
5. Toàn bộ hằng số của `OrderStatus` đều được liệt kê nên switch expression exhaustive mà không cần `default`.

Nếu `status == OrderStatus.NEW`, biểu thức trả `"Đơn mới"`; nó **không chạy khối `SHIPPED`** dù khối đó xuất hiện sau trong mã nguồn.

## 13. Khi nào nên dùng nhánh mũi tên thay vì dấu hai chấm?

Cú pháp mũi tên đặc biệt phù hợp khi **mỗi trường hợp có hành vi hoặc kết quả riêng**:

- Ánh xạ một mã số hoặc `enum` thành thông báo.
- Chọn cấu hình, mức ưu tiên, mức phí hoặc hình thức hiển thị.
- Phân loại trạng thái của một quy trình.
- Gọi một hành động riêng cho từng loại lệnh mà không muốn vô tình chạy thêm hành động khác.
- Đơn giản hóa đoạn mã `switch` từng phải gán biến tạm và thêm `break` ở nhiều nhánh.

Cú pháp dấu hai chấm vẫn là một phần của Java 17, kể cả trong switch expression khi tuân thủ các quy tắc về `yield`. Tuy vậy, nếu chỉ cần nhóm nhiều giá trị để cùng xử lý, `case A, B ->` thường diễn đạt ý định tốt hơn việc đặt nhiều nhãn `case:` liên tiếp.

Việc chọn cú pháp phụ thuộc vào ý định, nhưng **đừng trộn hai kiểu nhãn trong cùng switch block**.

## 14. Bài tập tự luyện

### Bài 1 — dự đoán luồng chạy

Đọc đoạn mã:

```java
int code = 2;

switch (code) {
    case 1 -> System.out.println("A");
    case 2 -> System.out.println("B");
    case 3 -> System.out.println("C");
    default -> System.out.println("D");
}

System.out.println("END");
```

Hãy ghi lại các dòng được in ra và giải thích vì sao chương trình không in `"C"` hay `"D"`.

**Đáp án đối chiếu:**

```text
B
END
```

`case 2` khớp và kết thúc switch statement. Dòng `END` thuộc câu lệnh sau switch nên vẫn thực hiện.

### Bài 2 — nhóm nhánh

Viết phương thức:

```java
static String rate(int score) {
    // Dùng switch expression với dạng mũi tên.
}
```

Yêu cầu minh họa:

| `score` | Kết quả |
| --- | --- |
| `1` hoặc `2` | `"Cần cải thiện"` |
| `3` hoặc `4` | `"Đạt"` |
| `5` | `"Tốt"` |
| Khác | `"Không hợp lệ"` |

**Đáp án tham khảo:**

```java
static String rate(int score) {
    return switch (score) {
        case 1, 2 -> "Cần cải thiện";
        case 3, 4 -> "Đạt";
        case 5 -> "Tốt";
        default -> "Không hợp lệ";
    };
}
```

### Bài 3 — chuyển một nhánh thành khối nhiều câu lệnh

Cho mã:

```java
static int calculate(int category) {
    return switch (category) {
        case 1 -> 100;
        case 2 -> 200;
        default -> 0;
    };
}
```

Hãy sửa `case 2` để:

1. Khai báo `int base = 150;`.
2. Khai báo `int extra = 50;`.
3. Trả về tổng hai biến bằng `yield`.

**Đáp án tham khảo:**

```java
static int calculate(int category) {
    return switch (category) {
        case 1 -> 100;
        case 2 -> {
            int base = 150;
            int extra = 50;
            yield base + extra;
        }
        default -> 0;
    };
}
```

### Bài 4 — phân biệt lỗi của switch statement và switch expression

Xét hai cách viết:

```java
// A: switch statement
switch (value) {
    case 1 -> System.out.println("One");
    default -> System.out.println("Other");
}
```

```java
// B: switch expression
String text = switch (value) {
    case 1 -> System.out.println("One");
    default -> "Other";
};
```

Hãy xác định cách nào phù hợp và giải thích **vì sao dùng `println` ở nhánh mũi tên lại khác nhau giữa hai dạng**. Đề xuất một cách sửa B bằng khối `yield` để vừa in thông báo vừa nhận giá trị `String`.

**Đáp án tham khảo cho B:**

```java
String text = switch (value) {
    case 1 -> {
        System.out.println("One");
        yield "One";
    }
    default -> "Other";
};
```

Switch statement A dùng `println` như hành động, còn switch expression B yêu cầu kết quả `String` từ nhánh được chọn.

### Bài 5 — xử lý null và exhaustive

Viết hàm `String message(String status)`, yêu cầu:

- Nếu `status == null`, trả `"Thiếu trạng thái"` trước khi vào switch.
- Nếu `status` là `"OK"`, trả `"Thành công"`.
- Nếu `status` là `"ERROR"`, trả `"Thất bại"`.
- Các giá trị khác trả `"Không xác định"`.

**Đáp án tham khảo:**

```java
static String message(String status) {
    if (status == null) {
        return "Thiếu trạng thái";
    }

    return switch (status) {
        case "OK" -> "Thành công";
        case "ERROR" -> "Thất bại";
        default -> "Không xác định";
    };
}
```

## 15. Bảng ghi nhớ nhanh

| Tình huống | Cách viết nên dùng | Điểm cần nhớ |
| --- | --- | --- |
| Một nhánh trả ngay giá trị | `case 1 -> "Một";` | Giá trị này là kết quả của switch expression, không cần `yield`. |
| Nhiều giá trị cùng xử lý | `case 1, 2, 3 -> "Nhóm A";` | Các nhãn trong cùng nhánh, không có fall-through. |
| Nhánh cần nhiều câu lệnh | `case 1 -> { ...; yield value; }` | `yield` cung cấp kết quả khi khối hoàn tất bình thường. |
| Nhánh từ chối đầu vào | `default -> throw new IllegalArgumentException(...);` | Ném ngoại lệ; không cần tạo giá trị bình thường. |
| Chỉ thực hiện hành động | `switch (x) { case 1 -> doWork(); ... }` | Đây là switch statement, không nhất thiết tạo giá trị. |
| Cần giá trị cho biến | `String s = switch (x) { ... };` | Đây là switch expression, phải exhaustive. |
| Muốn xử lý `null` với Java 17 chuẩn | Kiểm tra `null` trước switch. | `default` không bắt `null`. |
| Tránh lỗi “rơi nhánh” | Dùng `case ... ->` và không trông chờ chạy sang nhánh sau. | Không cần `break` để chặn fall-through. |

**Nguyên tắc cốt lõi:** Khi viết `case ... ->` trong Java 17, **một lần chọn chỉ thực thi một nhánh**. Với switch expression, nhánh đó tạo giá trị trực tiếp, thực hiện khối có `yield` hoặc ném ngoại lệ. Nhờ quy tắc không rơi nhánh, bạn có thể đọc một switch mũi tên theo đúng ý định “giá trị nào, xử lý đó”, mà không cần lần theo các lệnh `break` để biết nhánh sẽ dừng ở đâu.
