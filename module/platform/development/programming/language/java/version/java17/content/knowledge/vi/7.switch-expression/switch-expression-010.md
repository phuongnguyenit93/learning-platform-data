# Giới hạn Java 17: không coi pattern switch preview là cú pháp chính thức

Trong Java 17, **switch expression** là tính năng ngôn ngữ **đã chính thức**: bạn có thể dùng `switch` để tạo giá trị, viết nhánh dạng `case ... ->` và dùng `yield` khi một nhánh cần nhiều câu lệnh. Tuy nhiên, **pattern matching for switch** — cho phép các nhánh như `case String s ->` hoặc `case Integer n ->` — mới ở giai đoạn **preview trong Java 17**. Hai tính năng đều liên quan đến `switch` nhưng có trạng thái khác nhau.

Phân biệt đúng điều này giúp bạn viết mã chạy trên Java 17 mặc định, tránh phụ thuộc cờ thử nghiệm và tránh nhầm cú pháp Java 21 hiện đại với cú pháp chính thức của Java 17.

> **Nguyên tắc của bài:** Khi hướng dẫn Java 17 sử dụng trong dự án thông thường, chỉ dùng **switch expression chính thức**; ví dụ pattern switch ở đây được đánh dấu rõ là **preview** và được trình bày để nhận diện ranh giới phiên bản. Nếu muốn dùng pattern matching for switch làm cú pháp chính thức, hãy dùng JDK 21 trở lên với tài liệu tương ứng.

## 1. Hai tính năng có tên gần giống nhưng khác trạng thái

| Đặc điểm | Switch expression | Pattern matching for switch |
|---|---|---|
| JEP đưa đến bản chính thức | [JEP 361](https://openjdk.org/jeps/361) | [JEP 441](https://openjdk.org/jeps/441) |
| Bản Java đầu tiên chính thức | **Java 14** | **Java 21** |
| Trạng thái trong Java 17 | **Chính thức (final)** | **Preview**, theo [JEP 406](https://openjdk.org/jeps/406) |
| Mục đích | Viết biểu thức `switch` tạo ra giá trị và cú pháp nhánh gọn | Khớp kiểu/giá trị theo pattern, ràng buộc biến và mở rộng cách dispatch |
| Ví dụ điển hình | `case "A" -> 10;` | `case String s -> s.length();` |
| Cờ trong JDK 17 | **Không cần** `--enable-preview` | Phải bật `--enable-preview` khi biên dịch và chạy |
| Dùng trong code Java 17 ổn định | Có | Không nên mặc định là cú pháp được hỗ trợ ổn định |

**LTS không thay đổi trạng thái của từng tính năng.** Java 17 là một bản LTS, nhưng điều đó không có nghĩa mọi tính năng được giới thiệu trong JDK 17 đều chính thức. Một JDK có thể đồng thời chứa tính năng đã final và tính năng preview.

Điểm nhận diện quan trọng nhất là **thành phần ngay sau `case`**:

~~~java
// CHÍNH THỨC ở Java 17: khớp hằng String.
case "READY" -> "Sẵn sàng";

// CHÍNH THỨC ở Java 17: gộp các nhãn hằng.
case "NEW", "PENDING" -> "Chưa xử lý";

// PREVIEW trong Java 17: khớp pattern kiểu và tạo biến.
case String text -> text.length();
~~~

Dấu mũi tên `->` **không** làm cú pháp trở thành preview. Chính **type pattern** như `String text` mới là phần thuộc pattern matching for switch.

## 2. Switch expression chính thức có thể làm gì trong Java 17?

Ở Java 17, bạn có thể dùng `switch` như **một biểu thức trả về giá trị**:

~~~java
static String describeStatus(String status) {
    return switch (status) {
        case "NEW" -> "Mới tạo";
        case "PROCESSING" -> "Đang xử lý";
        case "DONE" -> "Hoàn thành";
        default -> "Không xác định";
    };
}
~~~

Mỗi nhánh chọn một biểu thức kết quả. Giá trị do nhánh đó tạo ra trở thành giá trị của cả `switch expression` và được trả về từ phương thức.

### 2.1. Phân biệt switch expression và switch statement

**Switch statement** phục vụ điều khiển luồng và thực hiện hành động:

~~~java
static void printStatus(String status) {
    switch (status) {
        case "NEW" -> System.out.println("Mới tạo");
        case "DONE" -> System.out.println("Hoàn thành");
        default -> System.out.println("Trạng thái khác");
    }
}
~~~

**Switch expression** được sử dụng tại vị trí cần một giá trị:

~~~java
static String statusLabel(String status) {
    String label = switch (status) {
        case "NEW" -> "Mới tạo";
        case "DONE" -> "Hoàn thành";
        default -> "Trạng thái khác";
    };

    return label;
}
~~~

Cả hai đều dùng được nhánh dạng `->` trong Java 17. Điều khác biệt chính là **switch expression phải tạo ra kết quả**; switch statement không cần.

### 2.2. Gộp nhiều hằng ở cùng một nhánh

~~~java
static boolean isWeekend(int dayOfWeek) {
    return switch (dayOfWeek) {
        case 6, 7 -> true;
        case 1, 2, 3, 4, 5 -> false;
        default -> throw new IllegalArgumentException(
                "Ngày trong tuần phải từ 1 đến 7");
    };
}
~~~

Danh sách `case 6, 7` là tập các **nhãn hằng**, không phải pattern matching. Cú pháp này là phần chính thức của switch expression/switch rules ở Java 17.

### 2.3. Dùng `yield` khi một nhánh có nhiều lệnh

Nếu nhánh cần kiểm tra hoặc tính toán trước khi tạo kết quả, dùng block và `yield`:

~~~java
static int shippingFee(String region, int weightKg) {
    return switch (region) {
        case "LOCAL" -> 10_000;

        case "NATIONAL" -> {
            if (weightKg <= 0) {
                throw new IllegalArgumentException(
                        "Khối lượng phải lớn hơn 0");
            }

            int baseFee = 20_000;
            int extraFee = Math.max(0, weightKg - 1) * 5_000;
            yield baseFee + extraFee;
        }

        default -> throw new IllegalArgumentException(
                "Khu vực không được hỗ trợ: " + region);
    };
}
~~~

Trong block của nhánh `"NATIONAL"`, `yield baseFee + extraFee;` **trả giá trị cho biểu thức switch**, không phải thoát khỏi phương thức bao ngoài. `throw` được phép vì nhánh lỗi kết thúc bằng ngoại lệ thay vì trả giá trị.

Cú pháp `yield` đã chính thức trong Java 14 cùng switch expression. Không cần bật preview trong Java 17.

### 2.4. `case ... :` vẫn dùng được trong switch expression

Kiểu nhánh có dấu hai chấm cũng có thể xuất hiện trong switch expression, nhưng bạn phải cung cấp kết quả qua `yield`:

~~~java
static String gradeLabel(char grade) {
    return switch (grade) {
        case 'A':
            yield "Xuất sắc";
        case 'B':
            yield "Khá";
        default:
            yield "Cần cố gắng";
    };
}
~~~

Tuy hợp lệ, dạng `->` thường dễ đọc hơn khi mỗi nhánh tạo ra một kết quả. Trong mã Java hiện đại, hãy ưu tiên `->` trừ khi có lý do rõ ràng dùng nhóm nhánh kiểu `:`.

### 2.5. Những kiểu selector thông thường được hỗ trợ

Với cú pháp **không preview** trên Java 17, biểu thức sau `switch (...)` có thể thuộc các nhóm:

- `byte`, `short`, `char`, `int` cùng các wrapper tương ứng (`Byte`, `Short`, `Character`, `Integer`).
- `String`.
- Một kiểu `enum`.

Ví dụ:

~~~java
enum Priority {
    LOW, MEDIUM, HIGH
}

static int priorityScore(Priority priority) {
    return switch (priority) {
        case LOW -> 1;
        case MEDIUM -> 2;
        case HIGH -> 3;
    };
}
~~~

Trong ví dụ này, không cần `default` vì đã liệt kê đủ mọi hằng của `Priority` tại thời điểm biên dịch. Cách xử lý còn được Java bổ sung cơ chế bảo vệ nếu tập hằng enum khi chạy không khớp với lúc biên dịch.

**Không được giả định rằng selector kiểu `Object` hoặc một interface tùy ý sẽ được hỗ trợ cho switch không preview ở Java 17.** Việc chuyển trên kiểu đối tượng rộng và dùng các type pattern là phần mở rộng của pattern matching for switch.

## 3. Switch expression cần đầy đủ các trường hợp

Vì switch expression phải tạo ra giá trị hoặc kết thúc đột ngột bằng một ngoại lệ, Java cần chứng minh các nhánh **bao phủ mọi giá trị có thể xảy ra** (*exhaustiveness*).

### 3.1. Với `String`, thường cần `default`

~~~java
static int statusCode(String status) {
    return switch (status) {
        case "NEW" -> 1;
        case "DONE" -> 2;
        default -> -1;
    };
}
~~~

Nếu bỏ `default` và chỉ viết hai nhãn hằng, biểu thức không bao phủ vô số giá trị `String` khác có thể xuất hiện, nên biên dịch không thành công.

### 3.2. Với enum, có thể liệt kê đủ các hằng

~~~java
enum TrafficLight {
    RED, YELLOW, GREEN
}

static String action(TrafficLight light) {
    return switch (light) {
        case RED -> "Dừng";
        case YELLOW -> "Chuẩn bị";
        case GREEN -> "Đi";
    };
}
~~~

Đây là trường hợp **switch expression exhaustiveness chính thức** ở Java 17. Không cần pattern matching for switch.

Khi dùng enum, việc không có `default` có thể giúp compiler phát hiện nếu bạn bổ sung hằng enum mới rồi biên dịch lại mã switch nhưng chưa xử lý hằng đó. Ngược lại, nếu tính tương thích với những giá trị không dự kiến là yêu cầu cụ thể, bạn có thể thiết kế nhánh mặc định theo hợp đồng ứng dụng.

### 3.3. Không nhầm exhaustiveness của enum với sealed-pattern switch

**Sealed classes/interfaces đã chính thức trong Java 17**, nhưng cú pháp sau là type pattern trong `switch`, nên **vẫn preview ở Java 17**:

~~~java
// ĐỂ NHẬN DIỆN PREVIEW — không dùng làm ví dụ Java 17 chính thức.
//
// sealed interface Outcome permits Success, Failure {}
// record Success(String data) implements Outcome {}
// record Failure(String reason) implements Outcome {}
//
// static String describe(Outcome outcome) {
//     return switch (outcome) {
//         case Success s -> s.data();
//         case Failure f -> f.reason();
//     };
// }
~~~

Việc Java 17 đã có `sealed` và `record` **không tự biến** pattern switch trên hai kiểu đó thành cú pháp chính thức. Nếu cần xử lý các nhánh kiểu trong code Java 17 thông thường, có thể dùng `instanceof` pattern matching kết hợp `if` như phần tiếp theo.

## 4. Pattern switch ở Java 17 là gì và vì sao phải phân biệt?

**Pattern matching for switch** mở rộng `switch` để kiểm tra kiểu dữ liệu, ràng buộc biến pattern và xử lý các cấu trúc kiểu phức tạp hơn. Cơ chế này xuất hiện dưới dạng **preview lần đầu ở JDK 17** qua [JEP 406](https://openjdk.org/jeps/406).

Ví dụ để **nhận diện cú pháp preview trên Java 17**:

~~~java
// CHỈ MINH HỌA CÚ PHÁP PREVIEW của Java 17.
// Không ghép vào file Java17SwitchDemo ở phần thực hành.
//
// static String describe(Object value) {
//     return switch (value) {
//         case String text -> "Chuỗi: " + text;
//         case Integer number -> "Số: " + number;
//         default -> "Kiểu khác";
//     };
// }
~~~

Trong đoạn trên:

1. `switch` nhận `Object` làm selector. Đây là khả năng mở rộng gắn với pattern matching for switch ở Java 17.
2. `case String text` là **type pattern**: không so sánh với một hằng chuỗi mà kiểm tra giá trị có phải `String` hay không.
3. `case Integer number` tương tự với `Integer`.
4. `text` và `number` là **pattern variables**, chỉ được sử dụng trong nhánh đã khớp.

Đây là ví dụ về **cú pháp có trong bản phân phối JDK 17 nhưng chưa thuộc bộ tính năng chính thức mặc định**. Nếu dùng trong ứng dụng, bạn sẽ phải bật preview khi biên dịch và lúc chạy.

### 4.1. Vì sao không nên dạy ví dụ trên như cú pháp switch expression thông thường?

Nếu người học sao chép trực tiếp vào dự án Java 17 và chỉ chạy:

~~~bash
javac --release 17 SomeFile.java
~~~

thì compiler sẽ từ chối các pattern switch preview. Người học có thể nhầm rằng bản JDK bị cài sai hoặc rằng `switch expression` chưa được hỗ trợ, trong khi nguyên nhân thật sự là **mã dùng một tính năng preview khác**.

Cách giải thích đúng là:

- Java 17 **có switch expression chính thức**, bao gồm `case "VALUE" -> result` và `yield`.
- Java 17 **có pattern matching for switch ở trạng thái preview**, chẳng hạn `case String s -> ...`.
- Một ví dụ có cả `switch expression` và `type pattern` không phải vì dùng `switch` mà là chính thức; phải xét **cú pháp cụ thể của từng nhánh**.

### 4.2. Trạng thái ở các phiên bản Java sau

Pattern matching for switch tiếp tục ở trạng thái preview qua các phiên bản Java 18–20 và được **chính thức trong Java 21** theo [JEP 441](https://openjdk.org/jeps/441).

Do đó, cách viết type pattern như:

~~~java
case String text -> text.length();
~~~

có thể được dùng trong `switch` chính thức của Java 21 khi đặt trong ngữ cảnh và cấu trúc hợp lệ. Tuy nhiên, **đừng hiểu rằng mọi chi tiết của bản preview Java 17 đều được giữ nguyên**: ngôn ngữ đã điều chỉnh một số quy tắc/cú pháp trong quá trình hoàn thiện.

Một ví dụ dễ nhầm là **guarded pattern**: cú pháp điều kiện bảo vệ đã thay đổi trong quá trình preview. Nếu làm việc với Java 21+, phải xem tài liệu ngữ pháp của phiên bản đích; không bê nguyên mọi mẫu preview 17 sang mã mới.

## 5. Phân biệt các kiểu `case` trong Java 17

Cùng dùng dấu `->`, nhưng các nhánh sau có bản chất khác nhau:

| Nhánh | Trạng thái trên Java 17 | Giải thích |
|---|---|---|
| `case 1 -> "Một";` | Chính thức | Khớp hằng số nguyên |
| `case 'A' -> "A";` | Chính thức | Khớp hằng ký tự |
| `case "NEW" -> "Mới";` | Chính thức | Khớp hằng chuỗi |
| `case "NEW", "DRAFT" -> "Chưa hoàn tất";` | Chính thức | Nhiều hằng cùng một nhánh |
| `case HIGH -> 3;` với selector enum | Chính thức | Khớp hằng enum |
| `case String s -> s.length();` | **Preview** | Type pattern, tạo biến `s` |
| `case Integer n -> n.intValue();` | **Preview** | Type pattern, tạo biến `n` |
| `case null -> 0;` | **Preview** | `null` label được đưa vào cùng cơ chế pattern switch preview ở Java 17 |
| `case null, default -> 0;` | **Preview** | Cú pháp mở rộng xử lý null trong pattern switch |
| `default -> "Khác";` | Chính thức | Nhánh mặc định |

Đặc biệt, **`case "hello"` và `case String s` khác nhau hoàn toàn**:

- `case "hello"` so sánh với **một giá trị hằng String**. Dùng được trong Java 17 chính thức.
- `case String s` kiểm tra **kiểu của đối tượng** và đưa biến `s` vào scope của nhánh. Đây là pattern switch preview trong Java 17.

Có thể ghi nhớ:

~~~text
switch expression với case hằng -> chính thức trong Java 17
                          |
                          +--> case "OK" -> 1        [final]
                          +--> case 1, 2 -> 10        [final]
                          +--> case HIGH -> 3         [final, với enum]
                          +--> block { yield ...; }  [final]

pattern matching for switch trong Java 17 -> preview
                          |
                          +--> case String s -> ...   [preview]
                          +--> case Integer n -> ...  [preview]
                          +--> case null -> ...       [preview]
~~~

## 6. Cách xử lý theo kiểu đối tượng **không cần preview** trong Java 17

Nếu yêu cầu nghiệp vụ là **xử lý tùy theo kiểu runtime của đối tượng**, hãy dùng **pattern matching for `instanceof`**, tính năng đã chính thức từ Java 16 (JEP 394).

~~~java
static String describe(Object value) {
    if (value instanceof String text) {
        return "Chuỗi: " + text;
    }
    if (value instanceof Integer number) {
        return "Số nguyên: " + number;
    }
    if (value == null) {
        return "Giá trị null";
    }
    return "Kiểu khác";
}
~~~

Đoạn trên dùng được bằng `javac --release 17` mà không cần bật preview. Nó đưa ra những kết quả tương tự mục tiêu của ví dụ pattern switch nhưng dựa hoàn toàn vào cú pháp chính thức của Java 17.

### 6.1. Nếu kiểu được xác định bởi giá trị enum hoặc hằng String

Trong trường hợp bạn đã biết một tập hằng để phân nhánh, **switch expression** chính thức thường rõ ràng và ngắn hơn:

~~~java
enum ShipmentStatus {
    CREATED, IN_TRANSIT, DELIVERED
}

static String label(ShipmentStatus status) {
    return switch (status) {
        case CREATED -> "Đã tạo";
        case IN_TRANSIT -> "Đang vận chuyển";
        case DELIVERED -> "Đã giao";
    };
}
~~~

Đây là bài toán phân nhánh theo **giá trị hằng enum**, không cần pattern switch.

### 6.2. Nếu bạn có sealed hierarchy

Ví dụ:

~~~java
sealed interface Command permits StartCommand, StopCommand {
}

record StartCommand(String jobId) implements Command {
}

record StopCommand(String jobId) implements Command {
}
~~~

Với Java 17, cách xử lý không phụ thuộc preview là:

~~~java
static String description(Command command) {
    if (command instanceof StartCommand start) {
        return "Bắt đầu " + start.jobId();
    }
    if (command instanceof StopCommand stop) {
        return "Dừng " + stop.jobId();
    }
    throw new IllegalStateException(
            "Loại Command chưa được xử lý: " + command);
}
~~~

Các khai báo `sealed`, `record` và pattern matching for `instanceof` **đều đã chính thức trong Java 17**. Nhưng Java 17 không cung cấp **pattern switch trên kiểu sealed như cú pháp chính thức**. Vì vậy, đoạn `if/instanceof` là lựa chọn phù hợp nếu cần tuân thủ nghiêm ngặt Java 17.

Khi cập nhật các record hoặc nhánh cho phép trong hierarchy, vẫn phải xem xét toàn bộ những nơi xử lý kiểu con. Đừng ngầm coi một chuỗi `if` là được compiler tự kiểm tra đủ trường hợp như một pattern switch exhaustive của Java mới.

## 7. `null` trong `switch` ở Java 17

Đây là một giới hạn cần nhớ rõ vì `null` thường xuất hiện trong dữ liệu thực tế.

**Switch chính thức trên Java 17 không dùng `case null` để xử lý giá trị null**. Với các selector kiểu tham chiếu như `String` hoặc enum, nếu biểu thức chọn là `null`, một switch thông thường sẽ ném `NullPointerException` khi đánh giá. Nhánh `default` **không** đón `null`.

Ví dụ:

~~~java
static String label(String value) {
    return switch (value) {
        case "A" -> "Nhóm A";
        default -> "Nhóm khác";
    };
}
~~~

Lệnh `label(null)` sẽ ném `NullPointerException`; nó không trả về `"Nhóm khác"`.

### 7.1. Cách xử lý null bằng cú pháp chính thức

Nếu null là đầu vào hợp lệ trong bài toán, kiểm tra trước khi dùng switch:

~~~java
static String labelNullable(String value) {
    if (value == null) {
        return "Không có giá trị";
    }

    return switch (value) {
        case "A" -> "Nhóm A";
        case "B" -> "Nhóm B";
        default -> "Nhóm khác";
    };
}
~~~

Nếu null là lỗi lập trình hoặc lỗi hợp đồng API, có thể dùng kiểm tra rõ ràng:

~~~java
import java.util.Objects;

static String labelRequired(String value) {
    Objects.requireNonNull(value, "value");

    return switch (value) {
        case "A" -> "Nhóm A";
        default -> "Nhóm khác";
    };
}
~~~

Việc `case null` được hỗ trợ trong pattern switch preview ở Java 17 **không làm nó trở thành lựa chọn chính thức để giải quyết null trong switch của Java 17**. Khi chuyển lên Java 21+, bạn có thể tham khảo `case null` ở bản đã chính thức.

## 8. Ví dụ thực hành chỉ dùng tính năng chính thức của Java 17

Tạo file **`Java17SwitchDemo.java`**:

~~~java
public class Java17SwitchDemo {

    enum Membership {
        BASIC, PLUS, PREMIUM
    }

    // Switch expression trên enum: chính thức trong Java 17.
    static int discountPercent(Membership membership) {
        return switch (membership) {
            case BASIC -> 0;
            case PLUS -> 5;
            case PREMIUM -> 15;
        };
    }

    // Switch expression trên String, gồm nhiều case hằng và yield.
    static String processStage(String stage) {
        if (stage == null) {
            return "Không có trạng thái";
        }

        return switch (stage) {
            case "NEW", "QUEUED" -> "Chưa bắt đầu";

            case "RUNNING" -> {
                String action = "Đang xử lý";
                yield action + " công việc";
            }

            case "DONE" -> "Đã hoàn tất";
            default -> "Trạng thái lạ";
        };
    }

    // Pattern instanceof: chính thức trong Java 17.
    static String describeInput(Object input) {
        if (input instanceof String text) {
            return "Chuỗi dài " + text.length() + " ký tự";
        }
        if (input instanceof Integer number) {
            return "Số nguyên: " + number;
        }
        if (input == null) {
            return "Đầu vào null";
        }
        return "Kiểu đầu vào khác";
    }

    public static void main(String[] args) {
        System.out.println(discountPercent(Membership.PLUS));
        System.out.println(processStage("QUEUED"));
        System.out.println(processStage("RUNNING"));
        System.out.println(processStage(null));
        System.out.println(describeInput("Java 17"));
        System.out.println(describeInput(17));
        System.out.println(describeInput(null));
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 Java17SwitchDemo.java
java Java17SwitchDemo
~~~

Kết quả mong đợi:

~~~text
5
Chưa bắt đầu
Đang xử lý công việc
Không có trạng thái
Chuỗi dài 7 ký tự
Số nguyên: 17
Đầu vào null
~~~

Tất cả những thành phần ngôn ngữ dùng trong ví dụ trên — `switch expression`, nhánh `->`, `yield`, `enum` và pattern `instanceof` — đều chính thức khi biên dịch với Java 17.

Không có nhánh `case String text`, `case Integer number` hoặc `case null`, vì những nhánh đó thuộc pattern switch preview ở Java 17.

## 9. Khi nào và bằng cách nào có thể thử pattern switch preview trên JDK 17?

Nếu bạn đọc tài liệu nghiên cứu hoặc muốn hiểu lịch sử thiết kế của ngôn ngữ, có thể bắt gặp một ví dụ được đánh dấu **preview Java 17**. Để nhận biết vì sao nó không biên dịch mặc định, cần hiểu hai cờ:

~~~bash
# Chỉ dành cho mã có preview feature của đúng JDK 17.
javac --enable-preview --release 17 PatternSwitchPreview.java
java --enable-preview PatternSwitchPreview
~~~

- `--enable-preview` cho phép `javac` của JDK 17 chấp nhận preview feature của **JDK 17**.
- `--release 17` đặt bản ngôn ngữ/API đích tương ứng lúc biên dịch.
- `java --enable-preview` phải được bật khi thực thi class dùng preview feature.
- Cần dùng **đúng toolchain JDK 17** cho mã preview Java 17. Chỉ thêm `--release 17` ở một `javac` của phiên bản mới hơn không biến bản preview cũ thành cú pháp được hỗ trợ bởi compiler mới.

Ví dụ nhận diện file preview, **không dùng làm mã học switch expression chính thức**:

~~~java
// PatternSwitchPreview.java
// CHỈ CHẠY TRONG JDK 17 KHI BẬT PREVIEW.
public class PatternSwitchPreview {

    static String describe(Object value) {
        return switch (value) {
            case String text -> "String: " + text;
            case Integer number -> "Integer: " + number;
            default -> "Other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(17));
    }
}
~~~

Kết quả khi dùng đúng JDK 17 cùng cờ preview:

~~~text
String: Java
Integer: 17
~~~

Mục đích của phần này là **nhận diện mã preview trong tài liệu hoặc dự án cũ**. Với mã sản xuất vẫn khóa ở Java 17, hãy ưu tiên phương án `if/instanceof` của phần 6. Nếu dự án nâng phiên bản, đánh giá và sử dụng **cú pháp chính thức của bản đích**, chẳng hạn Java 21 trở lên.

### 9.1. Preview không đồng nghĩa lỗi thời vĩnh viễn

Một tính năng có thể đi qua nhiều phiên bản preview và cuối cùng được chuẩn hóa. **Pattern switch đã chính thức từ Java 21**, nên bản thân ý tưởng này hiện nay vẫn hữu ích.

Điều cần tránh là:

- Ghi "Java 17 hỗ trợ chính thức `case String s ->`" — sai về trạng thái ở Java 17.
- Tự động coi mã preview viết cho Java 17 là mã chuẩn tương thích với Java 21+ mà chưa xem thay đổi ngữ pháp.
- Bật preview tràn lan cho toàn bộ dự án chỉ để dùng những thứ Java 17 đã có cách viết chính thức như `switch expression` hoặc `instanceof` pattern matching.

## 10. Các lỗi và nhầm lẫn thường gặp

### 10.1. "Dùng dấu mũi tên nghĩa là preview"

**Không đúng.** Dấu mũi tên trong nhánh switch là cú pháp chính thức của Java 17.

~~~java
static int score(String tier) {
    return switch (tier) {
        case "A" -> 100;
        case "B" -> 80;
        default -> 0;
    };
}
~~~

Không cần preview.

### 10.2. "Có switch expression thì dùng được `case String s`"

**Không đúng trong Java 17 mặc định.** Switch expression và pattern matching for switch thuộc hai tính năng khác nhau. Nếu thêm type pattern, chương trình phụ thuộc vào preview của Java 17.

### 10.3. "`default` xử lý cả null"

**Không đúng trong switch chính thức của Java 17.** Null selector làm switch ném `NullPointerException`. Hãy kiểm tra null trước khi vào switch hoặc xác định rõ null không được phép.

### 10.4. "Sealed class đã final thì switch theo sealed cũng final"

**Không đúng.** `sealed` được chính thức hóa ở Java 17 (JEP 409), nhưng **switch type patterns** trên hierarchy đó vẫn là preview. Các JEP có tiến độ riêng.

### 10.5. "Bỏ `default` trong switch expression kiểu String vẫn hợp lệ"

Thông thường là **không**, nếu các case chỉ là một số giá trị String cụ thể; compiler cần bảo đảm tính đầy đủ. Với enum đã liệt kê toàn bộ hằng, có thể bỏ `default`.

### 10.6. "`yield` là cú pháp preview"

**Không đúng.** `yield` đã là thành phần chính thức của switch expression từ Java 14. Trong một nhánh có block, `yield` trả kết quả cho biểu thức switch; `return` trả về từ phương thức, còn `break` không phải cú pháp để trả giá trị cho switch expression.

### 10.7. "Cứ chạy được trong JDK 17 thì dùng được bằng `--release 17`"

**Không đúng.** JDK chứa preview feature nhưng mặc định không bật. Nếu mã chỉ biên dịch được khi dùng `--enable-preview`, đó là một dấu hiệu quan trọng cho biết ví dụ **không đáp ứng ràng buộc Java 17 chính thức mặc định**.

### 10.8. "Pattern matching for `instanceof` cũng preview trong Java 17"

**Không đúng.** Pattern matching for `instanceof` là tính năng chính thức từ Java 16 theo [JEP 394](https://openjdk.org/jeps/394). Dùng:

~~~java
if (input instanceof String text) {
    System.out.println(text.length());
}
~~~

là hợp lệ trên Java 17 mà không bật preview. Đừng nhầm pattern `instanceof` với pattern switch.

## 11. Chọn cấu trúc phù hợp theo yêu cầu thực tế

| Bài toán | Cách viết phù hợp nếu phải chạy Java 17 không preview |
|---|---|
| Chọn giá trị theo các mã String như `"OPEN"`, `"CLOSED"` | Switch expression với nhánh hằng String |
| Chọn kết quả theo một enum có tập giá trị hữu hạn | Switch expression với case enum |
| Mỗi nhánh cần tính toán nhiều bước trước khi trả kết quả | Switch expression với block và `yield` |
| Kiểm tra runtime type là `String`, `Integer`, kiểu record... | `if` + pattern matching cho `instanceof` |
| Xử lý null trước khi phân nhánh | `if (value == null)` hoặc `Objects.requireNonNull(value)` |
| Xử lý các kiểu con của sealed hierarchy | `if/instanceof` và nhánh dự phòng phù hợp |
| Muốn dùng `case Type variable` ngay trong switch | Cân nhắc nâng lên Java 21+ hoặc chấp nhận rõ ràng thử nghiệm preview của JDK 17 |

Đối với dự án đang vận hành, **phiên bản Java mục tiêu** quan trọng hơn ví dụ mã mới nhất bạn tìm thấy trên mạng. Một cú pháp hợp lệ ở Java 21 không mặc nhiên hợp lệ ở Java 17.

## 12. Bài tập kiểm tra hiểu biết

### Bài 1 — Phân loại cú pháp

Cho các nhánh:

~~~java
case "A" -> 1;
case "B", "C" -> 2;
case String text -> text.length();
case null -> 0;
default -> -1;
~~~

**Câu hỏi:** Trong Java 17, nhánh nào thuộc switch expression chính thức và nhánh nào thuộc pattern switch preview?

**Đáp án:** Các nhánh khớp hằng `"A"`, `"B", "C"` và `default` là chính thức. Nhánh `case String text` và `case null` thuộc khả năng preview của pattern switch ở Java 17. Danh sách trên dùng để nhận diện độc lập từng cú pháp, không phải một khối switch có thể dán nguyên và biên dịch trực tiếp.

### Bài 2 — Viết switch expression chính thức

Yêu cầu: với tham số `String size`, trả về:

- `"S"` → `1`.
- `"M"` → `2`.
- `"L"` → `3`.
- Giá trị khác → `0`.

**Đáp án tham khảo:**

~~~java
static int sizeRank(String size) {
    if (size == null) {
        return 0;
    }

    return switch (size) {
        case "S" -> 1;
        case "M" -> 2;
        case "L" -> 3;
        default -> 0;
    };
}
~~~

Đoạn trên chạy bằng `javac --release 17` và tự xử lý null trước switch.

### Bài 3 — Chuyển type-pattern switch về Java 17 không preview

Cho mục tiêu (mã pattern switch chỉ để hình dung):

~~~java
// PREVIEW trên Java 17:
// return switch (value) {
//     case String s -> "String=" + s;
//     case Integer n -> "Integer=" + n;
//     default -> "Other";
// };
~~~

**Hãy viết cách triển khai chỉ dùng tính năng chính thức của Java 17.**

**Đáp án tham khảo:**

~~~java
static String describe(Object value) {
    if (value instanceof String s) {
        return "String=" + s;
    }
    if (value instanceof Integer n) {
        return "Integer=" + n;
    }
    return "Other";
}
~~~

### Bài 4 — Xử lý `yield`

Vì sao đoạn sau không cần bật preview?

~~~java
static int cost(String kind) {
    return switch (kind) {
        case "SIMPLE" -> 10;
        case "COMPLEX" -> {
            int base = 10;
            yield base * 3;
        }
        default -> 0;
    };
}
~~~

**Đáp án:** Vì `switch expression`, nhánh `->` và `yield` đều là tính năng chính thức trong Java 17. Không có type pattern hay mở rộng preview nào.

### Bài 5 — Chọn hướng nâng cấp

Dự án đang biên dịch bằng JDK 17 với `--release 17`. Một đồng nghiệp đề xuất dùng `switch (obj)` với `case String s` và bảo đây là Java 17 chuẩn vì code hoạt động khi bật preview.

**Hãy giải thích cách đánh giá.**

**Đáp án gợi ý:** Cú pháp đó là *pattern matching for switch*, thuộc preview trong Java 17, nên không đáp ứng yêu cầu chỉ dùng tính năng chính thức Java 17. Có thể giữ Java 17 và dùng `if/instanceof`, hoặc nâng Java lên 21+ theo kế hoạch dự án để sử dụng pattern switch đã chính thức. Bật preview là một lựa chọn thử nghiệm riêng, không thay đổi trạng thái của tính năng.

## 13. Tài liệu tham khảo

- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): đặc tả và việc chính thức hóa switch expression ở Java 14.
- [OpenJDK JEP 406 — Pattern Matching for switch (Preview)](https://openjdk.org/jeps/406): pattern switch ở JDK 17, trạng thái preview.
- [OpenJDK JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): khả năng thay thế bằng cú pháp chính thức của Java 17.
- [OpenJDK JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): trạng thái chính thức của sealed hierarchies trong Java 17.
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): pattern switch chính thức từ Java 21.
- [Oracle Java SE 17 — Switch Expressions](https://docs.oracle.com/en/java/javase/17/language/switch-expressions.html): cú pháp `->`, `yield`, kiểu kết quả và tính đầy đủ.
- [Oracle Java SE 17 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-switch-expressions-and-statements.html): tài liệu preview của JDK 17.
- [Java Language Specification 17 — `14.11 The switch Statement`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11) và [`15.28 switch Expressions`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): quy tắc chính thức của ngôn ngữ Java 17.

