# Chuyển chuỗi if hoặc switch cũ sang biểu thức rõ ràng trong Java 17

Trong mã Java, một chuỗi if/else hoặc một switch statement thường được dùng để chọn một giá trị kết quả. Cách viết cũ có thể tạo biến tạm, gán giá trị ở nhiều nhánh và lặp lại return hoặc break. Khi mục tiêu của các nhánh chỉ là **tạo ra một giá trị**, Java 17 cho phép dùng **switch expression** để diễn đạt lựa chọn ngay tại nơi giá trị được sử dụng.

Chuyển đổi đúng giúp mã ngắn hơn, thể hiện rõ rằng mọi nhánh đều phải tạo kết quả và giảm nguy cơ quên gán biến. Tuy nhiên, không phải mọi chuỗi if hay switch đều nên đổi thành biểu thức. Cần giữ nguyên điều kiện, thứ tự đánh giá, tác dụng phụ, xử lý null, nhánh mặc định và hành vi fall-through của chương trình ban đầu.

Java 17 hỗ trợ switch expression chính thức từ Java 14. Bài này chỉ sử dụng cú pháp và khả năng đã ổn định trong Java 17; không dùng type-pattern switch, record patterns hoặc case null của các phiên bản Java mới hơn.

## 1. Phân biệt switch statement và switch expression

Hai cấu trúc có cú pháp gần nhau nhưng vai trò khác nhau:

- **Switch statement** là một câu lệnh điều khiển luồng. Nó thực hiện các câu lệnh trong nhánh được chọn, có thể cập nhật biến, gọi phương thức, ghi log hoặc thay đổi trạng thái.
- **Switch expression** là một biểu thức tạo ra một giá trị. Giá trị đó có thể được gán cho biến, truyền vào phương thức, trả về từ phương thức hoặc kết hợp với biểu thức khác.

Ví dụ switch statement:

~~~java
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
        label = "Other";
}

System.out.println(label);
~~~

Ví dụ switch expression:

~~~java
int day = 2;

String label = switch (day) {
    case 1 -> "Monday";
    case 2 -> "Tuesday";
    default -> "Other";
};

System.out.println(label);
~~~

Trong ví dụ thứ hai, switch tự tạo giá trị String. Người đọc thấy ngay mỗi nhánh cung cấp một kết quả, không cần tìm biến được gán ở đâu và break có bị quên hay không.

| Đặc điểm | Switch statement | Switch expression |
| --- | --- | --- |
| Mục đích | Điều khiển thực thi câu lệnh | Tạo một giá trị |
| Có thể gán kết quả trực tiếp | Không phải bản chất của statement; thường gán biến bên ngoài | Có: var x = switch (...) { ... }; |
| Có thể dùng return switch (...) | Không | Có |
| Cần nhánh đầy đủ để tạo giá trị | Không nhất thiết; có thể không làm gì | Có; mọi đường thực thi phải tạo giá trị hoặc không hoàn tất bình thường |
| Arrow rule case ... -> | Có trong Java 17 | Có trong Java 17 |
| Colon label case ...: | Có | Có, với quy tắc yield khi cung cấp giá trị |
| break | Thường kết thúc switch statement | Không dùng để cung cấp giá trị cho switch expression |
| yield | Không dùng để trả giá trị từ switch statement | Cung cấp giá trị cho switch expression |

Một switch expression có thể xuất hiện ở bất kỳ nơi nào Java chấp nhận biểu thức có kiểu tương ứng. Switch statement không thể được dùng thay thế tại những vị trí đó.

## 2. Cú pháp switch expression trong Java 17

### Arrow rule với một biểu thức

Cách viết thường gọn nhất:

~~~java
String category = switch (code) {
    case 200 -> "Success";
    case 400, 422 -> "Client error";
    case 500, 503 -> "Server error";
    default -> "Unknown";
};
~~~

Các điểm cần nhớ:

- Dùng mũi tên để tách nhãn case khỏi rule.
- Nhiều nhãn có thể cùng dùng một nhánh, ví dụ case 400, 422.
- Nhánh có một biểu thức trả về giá trị của biểu thức đó.
- Mỗi arrow rule không tự rơi xuống nhánh tiếp theo.
- Không viết break ở cuối arrow rule chỉ để ngăn fall-through.

### Arrow rule với một block

Nếu cần nhiều câu lệnh trước khi tạo kết quả, dùng block và yield:

~~~java
String description = switch (status) {
    case "PAID" -> {
        audit("Payment completed");
        yield "Đã thanh toán";
    }
    case "PENDING" -> {
        audit("Payment pending");
        yield "Đang chờ";
    }
    default -> "Chưa xác định";
};
~~~

Yield kết thúc nhánh hiện tại của switch expression và cung cấp giá trị cho toàn bộ biểu thức. Nó khác return: return thoát khỏi phương thức đang chạy; yield chỉ trả giá trị của switch expression.

Nếu block có một biểu thức cuối cùng nhưng không có yield, Java không tự coi biểu thức đó là kết quả:

~~~java
// Sai: block không cung cấp giá trị cho switch expression.
String text = switch (status) {
    case 1 -> {
        "One";
    }
    default -> "Other";
};
~~~

Phải viết:

~~~java
String text = switch (status) {
    case 1 -> {
        String value = "One";
        yield value;
    }
    default -> "Other";
};
~~~

### Colon label và yield

Switch expression cũng hỗ trợ cú pháp colon quen thuộc. Khi một nhánh cần cung cấp giá trị, dùng yield:

~~~java
String label = switch (number) {
    case 1:
        yield "One";
    case 2:
        yield "Two";
    default:
        yield "Other";
};
~~~

Các nhãn colon vẫn có thể nhóm chung:

~~~java
String dayType = switch (day) {
    case 6:
    case 7:
        yield "Weekend";
    default:
        yield "Weekday";
};
~~~

Arrow rule thường dễ đọc và tránh nhầm lẫn với fall-through. Colon label hữu ích khi cần giữ cấu trúc cũ hoặc có logic tuần tự giữa các nhãn, nhưng cần hiểu rõ đường đi đến yield.

## 3. Chuyển chuỗi if/else trả về các giá trị cố định

Đây là trường hợp đơn giản và thường có lợi nhất khi chuyển đổi.

### Trước: mỗi nhánh return một giá trị

~~~java
static String roleName(int role) {
    if (role == 1) {
        return "ADMIN";
    } else if (role == 2) {
        return "EDITOR";
    } else if (role == 3) {
        return "VIEWER";
    } else {
        return "GUEST";
    }
}
~~~

### Sau: switch expression trả kết quả

~~~java
static String roleName(int role) {
    return switch (role) {
        case 1 -> "ADMIN";
        case 2 -> "EDITOR";
        case 3 -> "VIEWER";
        default -> "GUEST";
    };
}
~~~

Chuyển đổi phù hợp vì:

1. Các nhánh kiểm tra cùng một biến role.
2. Các điều kiện là phép so sánh bằng với những hằng số.
3. Mỗi nhánh trả về một String.
4. Có một nhánh mặc định tương đương với else.

Nếu các điều kiện là khoảng giá trị, nhiều biến hoặc biểu thức boolean phức tạp, if/else có thể thể hiện ý định tốt hơn. Switch label trong Java 17 không phải cú pháp tổng quát để thay mọi điều kiện boolean.

### Trường hợp có điều kiện phụ

Mã cũ:

~~~java
static String accessLevel(int role, boolean active) {
    if (!active) {
        return "DISABLED";
    }
    if (role == 1) {
        return "ADMIN";
    }
    if (role == 2) {
        return "EDITOR";
    }
    return "GUEST";
}
~~~

Có thể giữ điều kiện ưu tiên bên ngoài rồi dùng switch expression cho phần lựa chọn theo role:

~~~java
static String accessLevel(int role, boolean active) {
    if (!active) {
        return "DISABLED";
    }

    return switch (role) {
        case 1 -> "ADMIN";
        case 2 -> "EDITOR";
        default -> "GUEST";
    };
}
~~~

Không nên ép điều kiện active vào một switch chỉ để gom tất cả vào một biểu thức. Giữ điều kiện ưu tiên ở dạng if giúp người đọc thấy rõ một quy tắc độc lập.

## 4. Chuyển switch statement gán biến kết quả sang switch expression

Đây là một mẫu chuyển đổi phổ biến trong mã cũ: khai báo biến trước, mỗi nhánh gán một giá trị rồi break.

### Trước

~~~java
static int shippingFee(String zone) {
    int fee;

    switch (zone) {
        case "LOCAL":
            fee = 10;
            break;
        case "REGIONAL":
            fee = 25;
            break;
        case "INTERNATIONAL":
            fee = 80;
            break;
        default:
            fee = 50;
    }

    return fee;
}
~~~

### Sau

~~~java
static int shippingFee(String zone) {
    return switch (zone) {
        case "LOCAL" -> 10;
        case "REGIONAL" -> 25;
        case "INTERNATIONAL" -> 80;
        default -> 50;
    };
}
~~~

Biến tạm fee đã biến mất. Trình biên dịch yêu cầu switch expression tạo ra một giá trị int trên mọi đường đi có thể hoàn tất bình thường.

### Chọn kiểu dữ liệu kết quả nhất quán

Các nhánh của switch expression phải có kiểu tương thích để biểu thức có thể được gán hoặc truyền vào vị trí sử dụng. Ví dụ:

~~~java
int value = switch (kind) {
    case 1 -> 10;
    case 2 -> 20;
    default -> 0;
};
~~~

Khi các nhánh trả về kiểu khác nhau, Java áp dụng quy tắc typing và numeric promotion của biểu thức. Không nên dựa vào chuyển kiểu ngầm phức tạp nếu ý định không rõ. Hãy chọn kiểu kết quả cụ thể hoặc chuyển đổi tường minh:

~~~java
long value = switch (kind) {
    case 1 -> 10L;
    case 2 -> 20L;
    default -> 0L;
};
~~~

## 5. Chuyển switch statement cũ có fall-through

Đây là phần cần cẩn thận nhất. Trong switch statement kiểu colon, nếu không có break, return hoặc một lệnh chuyển điều khiển khác, chương trình có thể tiếp tục chạy vào nhóm case tiếp theo. Hành vi đó gọi là **fall-through**.

### Fall-through chỉ để gom nhiều nhãn

Mã cũ:

~~~java
static String dayType(int day) {
    String result;
    switch (day) {
        case 6:
        case 7:
            result = "Weekend";
            break;
        default:
            result = "Weekday";
    }
    return result;
}
~~~

Ở đây hai nhãn cùng một kết quả, không cần thực thi riêng logic của case 6 rồi mới tới case 7. Chuyển thành một arrow rule với nhiều nhãn:

~~~java
static String dayType(int day) {
    return switch (day) {
        case 6, 7 -> "Weekend";
        default -> "Weekday";
    };
}
~~~

### Fall-through thực sự thực hiện nhiều đoạn logic

Ví dụ switch statement cũ cố ý cộng dồn:

~~~java
static int legacyScore(int level) {
    int score = 0;
    switch (level) {
        case 3:
            score += 30;
            // Cố ý đi tiếp xuống case 2.
        case 2:
            score += 20;
            // Cố ý đi tiếp xuống case 1.
        case 1:
            score += 10;
            break;
        default:
            score = 0;
    }
    return score;
}
~~~

Kết quả:

| level | Kết quả |
| ---: | ---: |
| 1 | 10 |
| 2 | 30 |
| 3 | 60 |
| Giá trị khác | 0 |

Nếu đổi máy móc thành arrow rules:

~~~java
// Sai về hành vi: mỗi rule chỉ chạy riêng, không cộng dồn.
return switch (level) {
    case 3 -> 30;
    case 2 -> 20;
    case 1 -> 10;
    default -> 0;
};
~~~

Kết quả sẽ khác. Có thể biểu đạt giá trị theo công thức:

~~~java
static int score(int level) {
    return switch (level) {
        case 3 -> 60;
        case 2 -> 30;
        case 1 -> 10;
        default -> 0;
    };
}
~~~

Hoặc giữ rõ các bước tích lũy trong block:

~~~java
static int score(int level) {
    return switch (level) {
        case 3 -> {
            int total = 30;
            total += 20;
            total += 10;
            yield total;
        }
        case 2 -> {
            int total = 20;
            total += 10;
            yield total;
        }
        case 1 -> 10;
        default -> 0;
    };
}
~~~

Đoạn thứ hai thể hiện đúng hiệu ứng cũ nhưng có lặp logic. Nếu quy tắc phức tạp, có thể trích thành phương thức có tên rõ ràng hoặc giữ switch statement nếu nó dễ hiểu hơn. **Mục tiêu là giữ ngữ nghĩa**, không phải chuyển đổi bằng mọi giá.

### Colon label trong switch expression

Switch expression vẫn có thể dùng colon label cùng yield:

~~~java
static int score(int level) {
    return switch (level) {
        case 3:
            yield 60;
        case 2:
            yield 30;
        case 1:
            yield 10;
        default:
            yield 0;
    };
}
~~~

Đoạn này nêu trực tiếp kết quả tương đương, không mô phỏng từng bước cộng dồn. Với colon labels, nếu một nhóm câu lệnh cố ý rơi xuống nhóm tiếp theo, cần phân tích thứ tự chạy và các yield thực tế. Arrow rules thường an toàn hơn vì không có fall-through ngầm.

## 6. Chuyển đổi khi nhánh cần nhiều câu lệnh

Switch expression không bắt buộc mỗi nhánh chỉ có một biểu thức. Dùng block khi cần tính toán, kiểm tra hoặc ghi nhận trước khi trả giá trị:

~~~java
static String paymentMessage(String status, long amount) {
    return switch (status) {
        case "PAID" -> {
            if (amount < 0) {
                throw new IllegalArgumentException("amount must not be negative");
            }
            yield "Đã thanh toán " + amount;
        }
        case "PENDING" -> {
            auditPending(amount);
            yield "Đang chờ thanh toán";
        }
        case "FAILED" -> "Thanh toán thất bại";
        default -> "Trạng thái chưa xác định";
    };
}

static void auditPending(long amount) {
    // Ghi nhận thông tin theo yêu cầu ứng dụng.
}
~~~

Trong một block:

- Có thể khai báo biến cục bộ.
- Có thể gọi phương thức hoặc thực hiện tác dụng phụ.
- Có thể ném exception.
- Nếu block hoàn tất bình thường như một nhánh của switch expression, phải cung cấp kết quả bằng yield.

Một nhánh chỉ ném exception hoặc không hoàn tất bình thường không cần yield, vì nó không tạo ra đường đi bình thường thiếu giá trị:

~~~java
int result = switch (kind) {
    case 1 -> 10;
    case 2 -> throw new IllegalArgumentException("Unsupported kind");
    default -> 0;
};
~~~

## 7. Dùng switch expression với enum

Enum thường là đối tượng rất phù hợp cho switch expression, vì các hằng số được định nghĩa trong một tập xác định.

~~~java
enum OrderStatus {
    DRAFT,
    CONFIRMED,
    SHIPPED,
    CANCELLED
}

static String label(OrderStatus status) {
    return switch (status) {
        case DRAFT -> "Nháp";
        case CONFIRMED -> "Đã xác nhận";
        case SHIPPED -> "Đã giao";
        case CANCELLED -> "Đã hủy";
    };
}
~~~

Vì tất cả enum constant hiện có đều được liệt kê, switch expression này không cần default. Trình biên dịch kiểm tra tính đầy đủ dựa trên các hằng số của enum trong quá trình biên dịch. Khi thêm một constant vào enum rồi biên dịch lại, những switch expression không còn bao phủ đủ các trường hợp sẽ cần được cập nhật.

Nếu dùng default, mã có thể tiếp tục biên dịch sau khi enum được thêm constant:

~~~java
static String label(OrderStatus status) {
    return switch (status) {
        case DRAFT -> "Nháp";
        case CONFIRMED -> "Đã xác nhận";
        case SHIPPED -> "Đã giao";
        case CANCELLED -> "Đã hủy";
        default -> "Trạng thái khác";
    };
}
~~~

Chọn cách nào tùy hợp đồng:

- Nếu enum thuộc quyền kiểm soát của dự án và mọi giá trị mới cần được xem xét, bỏ default thường giúp phát hiện thay đổi khi biên dịch.
- Nếu cần fallback cho giá trị mới hoặc thư viện enum có thể được cập nhật độc lập, default có thể là lựa chọn chủ đích. Tuy nhiên, fallback chung có thể che việc ứng dụng chưa hiểu một trạng thái mới.

Khi chạy một binary đã biên dịch trước đó với phiên bản thư viện enum mới hơn, không nên cho rằng kiểm tra exhaustiveness lúc biên dịch cũ đã bao phủ constant mới. Cần biên dịch và kiểm thử lại ứng dụng với phiên bản dependency được triển khai.

## 8. Chọn giữa if và switch theo dạng điều kiện

Switch expression chỉ phù hợp khi các nhánh lựa chọn dựa trên **một selector** và các giá trị case hợp lệ. Java 17 hỗ trợ switch với các kiểu selector như byte, short, char, int, các wrapper tương ứng, String và enum.

Không thể dùng switch thông thường trên long, float, double hoặc boolean. Các nhãn case là hằng số phù hợp với selector; không phải các điều kiện tùy ý như x > 10.

| Dạng điều kiện | Cấu trúc thường rõ hơn | Ví dụ |
| --- | --- | --- |
| So sánh một biến với các giá trị cố định | Switch expression | Mã trạng thái hoặc enum constant |
| Nhiều giá trị cùng kết quả | Switch expression với nhiều nhãn | case 400, 404 |
| Kiểm tra khoảng | If/else | score >= 80 |
| Kết hợp nhiều biến và điều kiện | If/else hoặc phương thức có tên | active && verified && amount > limit |
| Điều kiện ưu tiên trước, sau đó chọn một mã | If rồi switch expression | Kiểm tra active, rồi switch theo role |
| Nhiều thao tác độc lập, không có một giá trị chung | Switch statement | Gọi handler, ghi log, cập nhật trạng thái |

Ví dụ kiểm tra khoảng nên giữ là if:

~~~java
static String grade(int score) {
    if (score < 0 || score > 100) {
        throw new IllegalArgumentException("score must be from 0 to 100");
    }
    if (score >= 90) {
        return "A";
    }
    if (score >= 80) {
        return "B";
    }
    if (score >= 70) {
        return "C";
    }
    return "D";
}
~~~

Các điều kiện là khoảng và có thứ tự ưu tiên. Chuyển chúng sang switch bằng cách tạo hàng loạt case cho từng số nguyên sẽ làm mã dài, khó bảo trì và không biểu đạt đúng ý nghĩa.

## 9. Xử lý String, null và wrapper khi chuyển đổi

### Switch trên String phân biệt hoa/thường

So sánh String trong switch có hành vi phân biệt chữ hoa/chữ thường:

~~~java
static String normalizeStatus(String status) {
    return switch (status) {
        case "paid" -> "PAID";
        case "pending" -> "PENDING";
        default -> "UNKNOWN";
    };
}
~~~

"PAID" không khớp "paid". Nếu mã cũ dùng equalsIgnoreCase, việc đổi sang switch trực tiếp sẽ thay đổi hành vi. Hãy chuẩn hóa trước nếu đó là hợp đồng mong muốn:

~~~java
static String normalizeStatus(String status) {
    if (status == null) {
        return "UNKNOWN";
    }

    return switch (status.toUpperCase(java.util.Locale.ROOT)) {
        case "PAID" -> "PAID";
        case "PENDING" -> "PENDING";
        default -> "UNKNOWN";
    };
}
~~~

Chỉ chuẩn hóa khi miền quy định status không phân biệt hoa/thường. Dùng Locale.ROOT cho mã định danh kỹ thuật tránh phụ thuộc locale mặc định của máy.

### Switch selector null

Trên Java 17, switch thông thường và switch expression **không nhận null như một nhãn case hợp lệ**. Nếu selector là null, việc thực hiện switch ném NullPointerException. Vì vậy, chuyển đổi phải xem lại hành vi của mã cũ:

~~~java
static String label(String status) {
    if (status == null) {
        return "UNKNOWN";
    }

    return switch (status) {
        case "PAID" -> "Đã thanh toán";
        case "PENDING" -> "Đang chờ";
        default -> "Khác";
    };
}
~~~

Không nhầm default với xử lý null: default xử lý selector khác các nhãn đã liệt kê nhưng không làm cho selector null trở nên hợp lệ.

Nếu mã cũ cố ý ném lỗi khi nhận null, có thể kiểm tra tường minh:

~~~java
static String label(String status) {
    java.util.Objects.requireNonNull(status, "status");
    return switch (status) {
        case "PAID" -> "Đã thanh toán";
        case "PENDING" -> "Đang chờ";
        default -> "Khác";
    };
}
~~~

Java 21 bổ sung khả năng xử lý case null trong pattern matching for switch đã được chuẩn hóa. Không đưa cú pháp đó vào mã cần biên dịch với Java 17.

### Switch trên wrapper có thể unbox null

Selector kiểu Integer, Short, Byte hoặc Character có thể được unbox khi thực hiện switch. Nếu wrapper là null, chương trình ném NullPointerException. Nếu mã cũ xử lý null bằng một nhánh if, giữ bước kiểm tra trước switch.

## 10. Khác biệt giữa break, yield và return

Khi chuyển switch statement sang expression, không thể thay break bằng yield theo kiểu tìm-thay toàn bộ. Mỗi từ khóa có mục đích riêng:

| Từ khóa | Ý nghĩa |
| --- | --- |
| break | Thoát khỏi switch statement hoặc vòng lặp gần nhất phù hợp; không cung cấp giá trị cho switch expression |
| yield value | Cung cấp giá trị và kết thúc nhánh của switch expression |
| return value | Thoát khỏi phương thức hiện tại và trả kết quả của phương thức |
| continue | Chuyển sang vòng lặp tiếp theo theo quy tắc của vòng lặp bao ngoài |
| throw | Kết thúc đường thực thi bằng exception, không tạo giá trị bình thường |

Ví dụ:

~~~java
static int toCode(String name) {
    return switch (name) {
        case "A" -> 1;
        case "B" -> {
            int code = 2;
            yield code;
        }
        default -> throw new IllegalArgumentException("Unknown name");
    };
}
~~~

Ở đây yield trả giá trị 2 cho switch expression, rồi return bên ngoài trả kết quả đó từ phương thức toCode.

Nếu nhánh cũ dùng return sớm, đừng tự động đổi thành yield mà không xét ý nghĩa. Trong switch expression nằm trong return, có thể dùng yield để kết thúc biểu thức rồi phương thức trả kết quả; nhưng return trong một nhánh có thể thoát khỏi phương thức sớm và bỏ qua các thao tác sau switch. Cần giữ đúng luồng điều khiển.

## 11. Không phải mọi switch statement đều nên chuyển thành expression

Giữ switch statement nếu mục tiêu chính là **thực hiện hành động** thay vì tạo một giá trị:

~~~java
static void handle(String event) {
    switch (event) {
        case "CREATED" -> sendCreatedNotification();
        case "DELETED" -> removeSearchIndex();
        case "UPDATED" -> refreshCache();
        default -> logUnknownEvent(event);
    }
}
~~~

Đoạn trên đã dùng arrow labels của Java 17 trong switch statement. Không cần tạo một biểu thức giả chỉ để gom các lời gọi phương thức thành giá trị.

Giữ statement hoặc dùng if rõ ràng khi:

- Mỗi nhánh có tác dụng phụ độc lập, không có một kết quả chung.
- Nhánh thực hiện break, continue hoặc return để thay đổi luồng bao ngoài.
- Logic phụ thuộc vào nhiều điều kiện phức tạp hơn một selector.
- Chuyển đổi sẽ tạo nhiều yield hoặc block lồng nhau khiến ý định khó hiểu hơn.
- Cần bảo toàn fall-through tuần tự phức tạp.

Switch expression là một công cụ diễn đạt **lựa chọn giá trị**, không phải mục tiêu thay thế mọi câu lệnh điều khiển.

## 12. Quy trình chuyển đổi an toàn từ mã cũ

Trước khi sửa một chuỗi if hoặc switch, nên làm rõ hành vi hiện tại theo trình tự:

1. **Xác định selector hoặc biến điều kiện.** Các nhánh có thật sự cùng phân loại một giá trị không? Nếu không, giữ if hoặc tách quy tắc.
2. **Liệt kê mọi nhánh và thứ tự ưu tiên.** Ghi nhận else cuối, default, nhánh null và những trường hợp không được xử lý.
3. **Xác định kết quả cần tạo.** Mỗi nhánh trả về/gán kiểu gì? Có nhánh nào chỉ thực hiện tác dụng phụ hoặc thoát phương thức không?
4. **Đọc kỹ break/fall-through.** Phân biệt nhãn được gom chung với việc cố ý thực hiện nhiều nhóm case.
5. **Kiểm tra thứ tự đánh giá và tác dụng phụ.** Một lời gọi phương thức, phép tăng biến hoặc ghi log có thể đang chạy trước/sau điều kiện; đừng thay đổi thứ tự vô tình.
6. **Quyết định null và giá trị mặc định.** Default không xử lý null; xác định rõ mã cũ trả fallback hay ném exception.
7. **Chọn arrow rule hay colon label.** Ưu tiên arrow khi mỗi nhánh độc lập; dùng block và yield khi cần nhiều câu lệnh.
8. **Biên dịch với đúng Java 17 và kiểm thử các nhánh.** Không dựa vào việc mã biên dịch trên JDK mới hơn rồi suy ra tương thích Java 17.

### Ví dụ về thứ tự đánh giá

Mã cũ:

~~~java
if (isAllowed(user) && isReady(loadResource())) {
    return "READY";
}
return "WAIT";
~~~

Không thể đổi thành switch expression chỉ vì kết quả là chuỗi. Điều kiện có short-circuit: loadResource() chỉ chạy khi isAllowed(user) đúng. Nếu tạo một biến trung gian hoặc tính trước cả hai điều kiện khi refactor, tác dụng phụ và hiệu năng có thể thay đổi. Giữ if là hợp lý.

### Ví dụ có phép tính dùng chung

Nếu các nhánh đều chọn một hệ số, có thể tách lựa chọn thành switch expression rồi thực hiện phép tính một lần:

~~~java
static long finalPrice(long basePrice, String tier) {
    int discountPercent = switch (tier) {
        case "GOLD" -> 20;
        case "SILVER" -> 10;
        case "BRONZE" -> 5;
        default -> 0;
    };

    return basePrice * (100 - discountPercent) / 100;
}
~~~

Cách này làm rõ phần **chọn chính sách** và phần **áp dụng chính sách**. Tuy nhiên, cần xác định quy tắc làm tròn, tràn số và đơn vị tiền tệ trong ứng dụng thật; ví dụ số học nguyên này chỉ minh họa cấu trúc lựa chọn.

## 13. Ví dụ tổng hợp: refactor bộ phân loại yêu cầu

### Phiên bản cũ với if/else

~~~java
static String describe(int statusCode) {
    String message;

    if (statusCode == 200 || statusCode == 201) {
        message = "Success";
    } else if (statusCode == 400 || statusCode == 404) {
        message = "Client error";
    } else if (statusCode == 500 || statusCode == 503) {
        message = "Server error";
    } else {
        message = "Unknown";
    }

    return message;
}
~~~

### Phiên bản switch expression

~~~java
static String describe(int statusCode) {
    return switch (statusCode) {
        case 200, 201 -> "Success";
        case 400, 404 -> "Client error";
        case 500, 503 -> "Server error";
        default -> "Unknown";
    };
}
~~~

Các nhánh là các giá trị rời rạc của cùng selector, nên switch expression giúp gom các giá trị cùng kết quả. Không thay đổi ý nghĩa của các mã chưa liệt kê: chúng vẫn trả "Unknown".

### Biến thể enum với đầy đủ trường hợp

~~~java
enum HttpOutcome {
    SUCCESS,
    CLIENT_ERROR,
    SERVER_ERROR
}

static String describe(HttpOutcome outcome) {
    return switch (outcome) {
        case SUCCESS -> "Success";
        case CLIENT_ERROR -> "Client error";
        case SERVER_ERROR -> "Server error";
    };
}
~~~

Enum biểu đạt nhóm giá trị hữu hạn tốt hơn các số nguyên tùy ý. Switch expression buộc code liệt kê các constant đang có khi không dùng default, giúp phát hiện thiếu nhánh lúc biên dịch lại sau khi enum thay đổi.

## 14. Biên dịch và kiểm chứng bằng Java 17

Lưu ví dụ độc lập sau thành SwitchRefactorDemo.java:

~~~java
public class SwitchRefactorDemo {

    static String roleName(int role) {
        return switch (role) {
            case 1 -> "ADMIN";
            case 2 -> "EDITOR";
            case 3 -> "VIEWER";
            default -> "GUEST";
        };
    }

    static int shippingFee(String zone) {
        return switch (zone) {
            case "LOCAL" -> 10;
            case "REGIONAL" -> 25;
            case "INTERNATIONAL" -> 80;
            default -> 50;
        };
    }

    static String dayType(int day) {
        return switch (day) {
            case 6, 7 -> "Weekend";
            default -> "Weekday";
        };
    }

    static int score(int level) {
        return switch (level) {
            case 3 -> 60;
            case 2 -> 30;
            case 1 -> 10;
            default -> 0;
        };
    }

    public static void main(String[] args) {
        System.out.println(roleName(2));
        System.out.println(shippingFee("LOCAL"));
        System.out.println(dayType(7));
        System.out.println(score(3));
    }
}
~~~

Biên dịch và chạy với JDK 17:

~~~bash
javac --release 17 SwitchRefactorDemo.java
java SwitchRefactorDemo
~~~

Kết quả:

~~~text
EDITOR
10
Weekend
60
~~~

Tùy chọn --release 17 yêu cầu compiler áp dụng ngôn ngữ, API nền tảng và định dạng bytecode đích Java 17. Nó giúp tránh vô tình sử dụng cú pháp chỉ có ở một bản Java mới hơn khi viết mã dành cho Java 17.

## 15. Các lỗi thường gặp khi chuyển đổi

| Lỗi | Vì sao xảy ra | Cách xử lý |
| --- | --- | --- |
| Quên default ở switch expression trên int hoặc String | Switch expression không bao phủ mọi giá trị selector | Thêm nhánh fallback hoặc ném exception phù hợp |
| Dùng break để trả kết quả | break không cung cấp giá trị cho switch expression | Dùng arrow expression hoặc yield trong block |
| Dùng yield trong switch statement | yield dành cho switch expression | Dùng break hoặc cấu trúc điều khiển phù hợp |
| Chuyển fall-through thành arrow rule độc lập | Arrow rule không tự rơi xuống nhánh sau | Nhóm nhãn nếu chỉ cùng kết quả; mô phỏng rõ các bước nếu fall-through có ý nghĩa |
| Cho rằng default bắt cả null | Selector null ném NullPointerException trên Java 17 | Kiểm tra null trước switch |
| Đổi equalsIgnoreCase thành switch String | Switch String phân biệt hoa/thường | Chuẩn hóa theo quy tắc miền trước switch |
| Dùng switch cho khoảng giá trị | Case label không phải điều kiện tùy ý | Giữ if/else cho khoảng |
| Nhánh block thiếu yield | Block hoàn tất bình thường nhưng không cung cấp kết quả | Thêm yield hoặc thay cấu trúc |
| Thêm default quá rộng cho enum | Constant mới có thể âm thầm rơi vào fallback | Cân nhắc bỏ default để compiler phát hiện khi biên dịch lại |
| Tạo biến kết quả chỉ để gán một lần | Giữ mẫu statement cũ dù chỉ cần giá trị | Trả trực tiếp switch expression |
| Chuyển đổi làm thay đổi thứ tự gọi phương thức | Refactor tính trước các điều kiện hoặc dữ liệu | Bảo toàn short-circuit và thứ tự tác dụng phụ |
| Dùng cú pháp pattern switch của Java 21 | Java 17 chưa hỗ trợ chính thức | Dùng switch expression với constant labels hoặc instanceof pattern đã chính thức |

## 16. Nguyên tắc lựa chọn sau refactor

Sau khi chuyển đổi, hãy nhìn lại cấu trúc:

- Nếu mỗi nhánh **chọn một giá trị**, switch expression thường là lựa chọn rõ ràng.
- Nếu mỗi nhánh **thực hiện một hành động**, switch statement thường phù hợp.
- Nếu điều kiện **không cùng một selector**, if/else thường diễn đạt đúng ý hơn.
- Nếu logic **có thứ tự ưu tiên hoặc kiểm tra khoảng**, giữ if/else hoặc tách thành các phương thức có tên.
- Nếu enum có **tập constant do dự án kiểm soát**, switch expression không default có thể giúp phát hiện trường hợp mới khi biên dịch lại.
- Nếu dữ liệu có thể **null**, xác định rõ hợp đồng null trước khi switch.
- Nếu switch cũ có **fall-through**, chỉ chuyển sau khi hiểu các nhóm case thực sự làm gì.

Mục tiêu của refactor là biến phần lựa chọn thành một biểu thức có kết quả dễ đọc, đồng thời giữ nguyên hành vi của chương trình. Switch expression Java 17 hữu ích nhất khi thay thế các nhánh rời rạc vốn chỉ tính hoặc chọn một giá trị; switch statement và if/else vẫn có vai trò rõ ràng khi mã cần điều khiển luồng hoặc biểu đạt điều kiện phức tạp.
