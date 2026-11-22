# Thực hành tổng hợp: xây phép phân loại trả giá trị bằng switch expression trong Java

## 1. Bài toán và kết quả mong đợi

Giả sử một hệ thống tiếp nhận các phiếu hỗ trợ khách hàng. Mỗi phiếu có **loại sự kiện** như sự cố dịch vụ, cảnh báo bảo mật, lỗi thanh toán, câu hỏi sử dụng hoặc góp ý tính năng. Hệ thống cần **phân loại** mỗi loại sang một tuyến xử lý (đội phụ trách) và thời hạn phản hồi dự kiến.

Ta muốn viết một hàm có giao diện rõ ràng:

~~~text
Loại sự kiện đầu vào
          |
          v
Phép phân loại bằng switch expression
          |
          v
Một kết quả: đội phụ trách + thời hạn phản hồi
~~~

Ví dụ:

| Loại phiếu | Đội phụ trách | Mục tiêu phản hồi (phút) |
| --- | --- | ---: |
| SERVICE_OUTAGE | incident | 15 |
| SECURITY_ALERT | security | 10 |
| PAYMENT_ERROR | billing | 60 |
| USAGE_QUESTION | support | 240 |
| FEATURE_REQUEST | product | 1440 |

**Các giá trị thời gian trong bảng là quy tắc giả định của bài thực hành, không phải cam kết SLA thực tế của một sản phẩm.**

Thay vì viết nhiều câu lệnh `if/else` hoặc một `switch` statement gán cùng biến qua nhiều nhánh, ta sử dụng **`switch expression`**: một biểu thức chọn nhánh và **trả về một giá trị** có kiểu được kiểm tra khi biên dịch.

Đây là tính năng **đã chính thức hóa từ Java 14** theo **JEP 361** và vẫn được hỗ trợ trong JDK hiện đại. Tài liệu dùng các ví dụ chạy trên **Java 17+**; một ví dụ sử dụng `record`, là tính năng đã ổn định từ Java 16. Phần cú pháp cốt lõi `switch expression` không cần bật preview.

## 2. Nhìn rõ sự khác biệt giữa switch expression và switch statement

Cả hai đều dùng từ khóa `switch` nhưng có **vai trò khác nhau**.

### Switch statement: thực hiện các câu lệnh

~~~java
String category;
switch (code) {
    case 1 -> category = "urgent";
    case 2 -> category = "normal";
    default -> category = "other";
}
~~~

Đây là đoạn minh họa đặt trong một phương thức có biến `code`. Nó là **statement**: chương trình thực thi một trong các lệnh gán vào `category`. Dùng dấu mũi tên `->` không tự làm switch trở thành expression.

### Switch expression: trực tiếp tạo ra giá trị

~~~java
String category = switch (code) {
    case 1 -> "urgent";
    case 2 -> "normal";
    default -> "other";
};
~~~

Dấu hiệu quan trọng:

- Toàn bộ phần `switch (...) { ... }` nằm **bên phải phép gán**, vì vậy nó là một **expression**.
- Mỗi nhánh tạo ra một **giá trị** có kiểu phù hợp với `String`.
- Dấu **`;` sau ngoặc đóng** kết thúc câu lệnh khai báo/gán chứa biểu thức.
- Không cần tạo biến tạm và không cần gán biến ấy trong từng case.
- Compiler kiểm tra **tính bao phủ (exhaustiveness)** của switch expression.

Switch statement vẫn hoàn toàn hợp lệ trong Java mới; không phải API bị loại bỏ. Hãy chọn statement khi mục tiêu chủ yếu là **thực hiện hành động**, và expression khi mục tiêu là **tính một kết quả**.

Một phép phân loại thuần túy (cùng đầu vào, cùng đầu ra) thường dễ đọc và dễ kiểm thử hơn khi được biểu diễn bằng switch expression.

## 3. Cú pháp cần nhớ trước khi thực hành

Mẫu phổ biến nhất:

~~~java
Result value = switch (selector) {
    case A -> resultA;
    case B, C -> resultBC;
    default -> resultOther;
};
~~~

Trong đó:

- `selector` là giá trị được xét, ví dụ `int`, `String` hoặc `enum` trong Java 17.
- Mỗi nhãn `case` chọn một nhánh.
- `case B, C` cho phép **nhiều nhãn dùng chung một kết quả**.
- `-> expression` trả về giá trị của expression đó.
- `default` xử lý các giá trị không khớp nhãn, khi thích hợp.
- Mọi đường thực thi bình thường của switch expression phải **có giá trị kết quả**; một nhánh có thể kết thúc đột ngột bằng `throw`.

### Nhánh cần nhiều câu lệnh: dùng `yield`

Nếu cần tính toán, chuẩn hóa hoặc ghi log hợp lệ trước khi tạo kết quả, dùng **block**:

~~~java
int answer = switch (code) {
    case 1 -> {
        int baseline = 15;
        int safetyMargin = 5;
        yield baseline + safetyMargin;
    }
    default -> 60;
};
~~~

**`yield` đưa giá trị ra khỏi switch expression.** Nó **không giống**:

- `break`: thoát vòng lặp hoặc switch statement, không cung cấp giá trị cho switch expression.
- `return`: kết thúc phương thức; **không được dùng để return ra khỏi switch expression như ví dụ `yield`**.
- `continue`: chuyển vòng lặp; không phải cách cấp kết quả cho biểu thức.

Với nhánh ngắn, ưu tiên `case X -> expression;`. Với nhánh cần nhiều câu lệnh, dùng `case X -> { ... yield value; }`. Đừng thêm block không có lý do chỉ để mọi nhánh trông giống nhau.

### Có thể ném exception ngay trong nhánh

~~~java
int minutes = switch (code) {
    case 1 -> 10;
    case 2 -> 30;
    default -> throw new IllegalArgumentException("Unknown code: " + code);
};
~~~

Một nhánh `throw` là hợp lệ vì nó **không hoàn tất bình thường**, không cần tạo một giá trị giả. Cách này hữu ích khi dữ liệu đầu vào không hợp lệ cần bị từ chối, thay vì lặng lẽ phân loại thành “khác”.

## 4. Thiết kế hợp đồng phân loại trước khi viết code

Để một bộ phân loại đáng tin cậy, nên xác định:

1. **Miền đầu vào:** một tập loại phiếu do `enum` định nghĩa, hay chuỗi từ API/JSON, hay một mã số?
2. **Miền đầu ra:** một `String`, `enum`, một số phút, hoặc object gom nhiều thuộc tính?
3. **Nhánh nào tương đương:** những loại đầu vào nào được nhóm chung và vì sao?
4. **Đầu vào không hợp lệ:** với chuỗi lạ, có trả trạng thái UNKNOWN hợp lệ hay phải ném exception?
5. **`null`:** có được chấp nhận hay phải bị từ chối? Nếu từ chối, lỗi cần rõ ràng.
6. **Tính đầy đủ:** khi thêm một giá trị `enum` mới, có muốn compiler buộc cập nhật bộ phân loại không?
7. **Tác dụng phụ:** có cần cập nhật database, gửi email trong nhánh, hay nên giữ hàm phân loại thuần túy và xử lý tác dụng phụ bên ngoài?
8. **Kiểm thử:** có thể viết test cho **toàn bộ nhánh**, các đầu vào biên và dữ liệu lỗi hay không?

Trong bài này, kết quả gồm **hai thuộc tính**, nên một `record Route` là kiểu giá trị gọn, có các accessor `team()` và `targetMinutes()`. `record` ổn định từ Java 16; ví dụ được compile với `--release 17`. Nếu dự án chỉ nhắm Java 14, có thể thay record bằng class thông thường hoặc trả về một `enum`/`String`; cú pháp `switch expression` vẫn áp dụng.

## 5. Ví dụ Java 17+ số 1: phân loại phiếu bằng enum và trả về record

Tạo file tên **`TicketRoutingDemo.java`**:

~~~java
import java.util.Objects;

public class TicketRoutingDemo {
    enum TicketType {
        SERVICE_OUTAGE, SECURITY_ALERT, PAYMENT_ERROR,
        USAGE_QUESTION, FEATURE_REQUEST
    }

    record Route(String team, int targetMinutes) {}

    static Route classify(TicketType type) {
        Objects.requireNonNull(type, "type");
        return switch (type) {
            case SERVICE_OUTAGE -> new Route("incident", 15);
            case SECURITY_ALERT -> {
                String team = "security";
                int targetMinutes = 10;
                yield new Route(team, targetMinutes);
            }
            case PAYMENT_ERROR -> new Route("billing", 60);
            case USAGE_QUESTION -> new Route("support", 240);
            case FEATURE_REQUEST -> new Route("product", 1440);
        };
    }

    static void assertRoute(TicketType type, String team, int minutes) {
        Route route = classify(type);
        if (!route.team().equals(team) || route.targetMinutes() != minutes) {
            throw new AssertionError(type + " => " + route);
        }
    }

    public static void main(String[] args) {
        assertRoute(TicketType.SERVICE_OUTAGE, "incident", 15);
        assertRoute(TicketType.SECURITY_ALERT, "security", 10);
        assertRoute(TicketType.PAYMENT_ERROR, "billing", 60);
        assertRoute(TicketType.USAGE_QUESTION, "support", 240);
        assertRoute(TicketType.FEATURE_REQUEST, "product", 1440);
        System.out.println("allEnumCasesVerified=" + TicketType.values().length);
        System.out.println("outage=" + classify(TicketType.SERVICE_OUTAGE));
        System.out.println("security=" + classify(TicketType.SECURITY_ALERT));
        System.out.println("feedback=" + classify(TicketType.FEATURE_REQUEST));

        boolean nullRejected = false;
        try {
            classify(null);
        } catch (NullPointerException expected) {
            nullRejected = "type".equals(expected.getMessage());
        }
        System.out.println("nullRejected=" + nullRejected);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 TicketRoutingDemo.java
java TicketRoutingDemo
~~~

**Stdout đã được kiểm thử trên JDK hiện đại với target Java 17:**

~~~text
allEnumCasesVerified=5
outage=Route[team=incident, targetMinutes=15]
security=Route[team=security, targetMinutes=10]
feedback=Route[team=product, targetMinutes=1440]
nullRejected=true
~~~

### Phân tích từng phần

**1. Đầu vào kiểu enum**

`TicketType` chỉ có năm giá trị được mô tả. Việc sử dụng `enum` thay cho chuỗi tùy ý ngăn mã nghiệp vụ vô tình truyền `"security-alert"`, `"SECURITY"` và `"alert"` như ba loại không đồng nhất. Nếu đầu vào đến từ HTTP/JSON, hãy **parse/validate ở lớp biên** rồi truyền enum đã được xác nhận vào hàm phân loại.

**2. Kết quả kiểu record**

`Route(team, targetMinutes)` là một giá trị bất biến ở mức các thành phần kiểu `String` và `int`. Record tự sinh accessor, `equals`, `hashCode` và `toString` phù hợp. Đầu ra có nhiều thuộc tính nhưng vẫn chỉ là **một giá trị** của switch expression. Đừng hiểu “switch trả một giá trị” thành “bắt buộc chỉ trả primitive hoặc String”.

**3. Cách trả kết quả trực tiếp**

`return switch (type) { ... };` là hợp lệ vì switch là một **expression** xuất hiện tại vị trí sau `return`. Chúng ta không cần tạo một biến `Route route;` bên ngoài và gán trong từng nhánh.

**4. Nhánh có block và `yield`**

Ở `SECURITY_ALERT`, code tính `team` và `targetMinutes` trong block rồi `yield new Route(...)`. Những biến cục bộ đó có scope trong block. `yield` trả **record** về switch expression, và `return` bên ngoài trả record từ phương thức `classify`.

**5. Enum không cần `default` nếu mọi hằng số đã được bao phủ**

Vì đã liệt kê tất cả năm hằng số của `TicketType`, switch expression là **exhaustive**. Không có `default` là chủ ý thiết kế để compiler cảnh báo khi sau này thêm hằng số mới nhưng chưa bổ sung nhánh phân loại.

**6. Kiểm tra `null` tường minh**

`Objects.requireNonNull(type, "type")` từ chối null trước switch với `NullPointerException` và một thông điệp định hướng. Unit test trong `main` xác nhận trường hợp null bị từ chối; bài không dựa trên chuỗi lỗi do JVM tự tạo cho một null switch.

**7. Kiểm tra kết quả bằng assertion chủ động**

`assertRoute` ném `AssertionError` khi kết quả không khớp. Điều này **không giống câu lệnh `assert` của Java**, vốn có thể bị tắt nếu không bật `-ea`. Dùng method kiểm tra chủ động giúp bản demo có kết quả rõ ràng trong mọi lần chạy.

**8. Không có `fall-through` giữa các nhánh mũi tên**

Sau khi chọn `SERVICE_OUTAGE`, chương trình trả một `Route("incident",15)`; nó không đi tiếp sang nhánh `SECURITY_ALERT`. Đây là lợi ích quan trọng khi viết bộ phân loại: không cần thêm `break;` sau từng nhánh `->`.

## 6. Tại sao kiểm tra tính bao phủ enum lại rất hữu ích?

Giả sử có người thêm:

~~~java
enum TicketType {
    SERVICE_OUTAGE, SECURITY_ALERT, PAYMENT_ERROR,
    USAGE_QUESTION, FEATURE_REQUEST, DATA_LOSS
}
~~~

Nhưng phương thức `classify` **chưa có nhánh `DATA_LOSS`** và không có `default`.

Khi biên dịch lại source tương ứng, `javac` sẽ từ chối switch expression không exhaustive. Việc thiếu nhánh được phát hiện **trước khi deploy**, thay vì âm thầm trả về một tuyến xử lý mặc định không đúng.

Trong thực tế, cần hỏi: khi thêm enum mới, muốn gì?

- Nếu mỗi hằng số cần quy tắc riêng, hãy **liệt kê tất cả case và không đặt `default` che lấp phần thiếu**.
- Nếu chính sách thực sự có một kết quả mặc định hợp lệ cho nhiều giá trị, `default -> ...` là đúng về mặt nghiệp vụ; nhưng phải hiểu compiler sẽ không nhắc cập nhật nhánh khi thêm enum.
- Khi enum đến từ một thư viện khác được cập nhật riêng, cũng cần **biên dịch lại các phụ thuộc và chạy integration tests**; khả năng toàn vẹn mã byte ở runtime không thể chỉ dựa vào compile-time exhaustiveness của một module chưa được rebuild.
- Các ngoại lệ xảy ra khi enum runtime thay đổi khác với enum ở thời điểm compile có thể khác nhau theo phiên bản JDK và dạng switch; không viết test phụ thuộc chặt vào một câu chữ thông báo lỗi.

**Bài học:** exhaustiveness là một hợp đồng có giá trị, đặc biệt với các trạng thái domain hữu hạn. Nhưng nó **không** thay thế version management, unit tests hoặc xác thực dữ liệu đầu vào.

## 7. Ví dụ Java 14 thuần: switch expression không cần record

Để tách phần cốt lõi ra khỏi tính năng record mới hơn, ví dụ sau sử dụng **chỉ cú pháp switch expression đã stable từ Java 14**:

~~~java
public class Java14SwitchValueDemo {
    static String className(int code) {
        return switch (code) {
            case 0 -> "NONE";
            case 1, 2 -> "NORMAL";
            case 3 -> "IMPORTANT";
            default -> throw new IllegalArgumentException("Unknown: " + code);
        };
    }

    public static void main(String[] args) {
        System.out.println(className(0));
        System.out.println(className(2));
        System.out.println(className(3));
    }
}
~~~

Tên file: **`Java14SwitchValueDemo.java`**. Trên JDK hỗ trợ cross-compilation cho Java 14:

~~~bash
javac --release 14 -encoding UTF-8 Java14SwitchValueDemo.java
java Java14SwitchValueDemo
~~~

Đầu ra dự kiến:

~~~text
NONE
NORMAL
IMPORTANT
~~~

Đây là một **ví dụ cú pháp Java 14 stable**, không có record, text block hay pattern matching từ các bản mới. Lệnh có thể chạy bằng JDK mới có hỗ trợ `--release 14`, nhưng chỉ được thực thi nếu đúng JDK và toolchain hỗ trợ; các bài test thực tế phía trên đã chạy với `--release 17`. Hãy coi hai mục tiêu riêng: **khả năng biên dịch source theo Java 14** và **chạy sản phẩm trên runtime mục tiêu**.

Một chi tiết hữu ích: `case 1, 2 -> "NORMAL";` cho thấy nhiều giá trị đầu vào có cùng kết quả nhưng vẫn không có fall-through.

## 8. Dữ liệu đầu vào String: phải làm rõ chuẩn hóa và chính sách lỗi

Trong nhiều hệ thống, dữ liệu ban đầu là mã từ HTTP, database hoặc message queue, chẳng hạn:

~~~text
sev0
 SEV1
OUTAGE
info
SEV9
~~~

Lúc này, có thể sử dụng **String switch expression**, nhưng không nên giả định:

- `"sev0"` tự bằng `"SEV0"`: String switch **phân biệt chữ hoa/thường**.
- Dữ liệu có khoảng trắng tự được trim: không có hành vi chuẩn hóa ngầm.
- Bất kỳ mã lạ nào cũng nên được gắn vào nhóm “thấp nhất”: điều đó có thể che dữ liệu sai.
- `null` tự được đưa vào nhánh `default` trong Java 17: điều này **không đúng**.
- Một nhánh `case` có thể dùng phép so sánh tùy ý như `case code.startsWith("SEV")`: trong String switch expression thông thường của Java 17, nhãn case là **hằng chuỗi**, không phải điều kiện boolean tùy ý.

Thiết kế nên đi theo hai bước:

1. **Validate và normalize** dữ liệu đầu vào một lần, ví dụ `Objects.requireNonNull(rawCode)`, `strip()`, `toUpperCase(Locale.ROOT)`.
2. **Phân loại** mã đã chuẩn hóa bằng switch expression.

Sử dụng `Locale.ROOT` thay cho default locale giúp quy tắc mã máy/mã sự kiện ổn định hơn giữa môi trường. Nó không phải giải pháp quốc tế hóa văn bản tự nhiên: nếu đang phân loại tên riêng hoặc ngôn ngữ người dùng, cần đặc tả dữ liệu riêng.

## 9. Ví dụ Java 17+ số 2: String switch, nhóm nhãn, yield và lỗi chủ động

Tạo file **`CodeClassificationDemo.java`**:

~~~java
import java.util.Locale;
import java.util.Objects;

public class CodeClassificationDemo {
    static int responseMinutes(String rawCode) {
        Objects.requireNonNull(rawCode, "rawCode");
        String code = rawCode.strip().toUpperCase(Locale.ROOT);
        return switch (code) {
            case "SEV0", "OUTAGE" -> 5;
            case "SEV1" -> {
                int baseline = 15;
                int safetyMargin = 5;
                yield baseline + safetyMargin;
            }
            case "SEV2" -> 60;
            case "SEV3", "INFO" -> 240;
            default -> throw new IllegalArgumentException(
                    "Unsupported code: " + rawCode);
        };
    }

    static String grade(int score) {
        if (score < 0 || score > 100) {
            throw new IllegalArgumentException("score out of range");
        }
        int band = score / 10;
        return switch (band) {
            case 10, 9 -> "A";
            case 8, 7 -> "B";
            case 6, 5 -> "C";
            default -> "D";
        };
    }

    public static void main(String[] args) {
        System.out.println("sev0=" + responseMinutes(" sev0 "));
        System.out.println("outage=" + responseMinutes("OUTAGE"));
        System.out.println("sev1=" + responseMinutes("sev1"));
        System.out.println("sev2=" + responseMinutes("SEV2"));
        System.out.println("info=" + responseMinutes("info"));

        boolean unknownRejected = false;
        try {
            responseMinutes("SEV9");
        } catch (IllegalArgumentException expected) {
            unknownRejected = true;
        }
        System.out.println("unknownRejected=" + unknownRejected);

        int[] boundaries = {0, 49, 50, 69, 70, 89, 90, 100};
        for (int score : boundaries) {
            System.out.println("grade" + score + "=" + grade(score));
        }

        boolean invalidScoreRejected = false;
        try {
            grade(101);
        } catch (IllegalArgumentException expected) {
            invalidScoreRejected = true;
        }
        System.out.println("invalidScoreRejected=" + invalidScoreRejected);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 CodeClassificationDemo.java
java CodeClassificationDemo
~~~

**Stdout đã được kiểm chứng:**

~~~text
sev0=5
outage=5
sev1=20
sev2=60
info=240
unknownRejected=true
grade0=D
grade49=D
grade50=C
grade69=C
grade70=B
grade89=B
grade90=A
grade100=A
invalidScoreRejected=true
~~~

### Phân tích ý nghĩa bài thực hành

**Nhóm hằng chuỗi trong một case:** `case "SEV0", "OUTAGE" -> 5;` là hai mã hợp lệ cùng nhận SLA minh họa 5 phút. Không cần viết hai khối if/else hoặc trùng return statement.

**Sử dụng yield khi cần tính:** `case "SEV1" -> { ... yield baseline + safetyMargin; }` tính 15 + 5 = 20. Block vẫn **sinh một giá trị int** cho toàn bộ switch expression.

**Xử lý mã không biết:** `default -> throw new IllegalArgumentException(...)` từ chối `SEV9`. Chỉ nên áp dụng chính sách này nếu các mã chưa biết thực sự phải lỗi; với yêu cầu sản phẩm cần “OTHER”, có thể trả một enum `UNKNOWN` thay cho exception. Điểm cốt lõi là **quyết định có chủ đích**.

**Chuẩn hóa trước switch:** `" sev0 "` được `strip()` và `toUpperCase(Locale.ROOT)` thành `"SEV0"`, nên cùng nhóm với `"OUTAGE"`. Cách xử lý không phụ thuộc locale mặc định của server.

**Phân loại điểm theo khoảng:** Java 17 switch trên `int` không tự hỗ trợ nhãn như `case 70..89`. Thay vào đó, code kiểm tra miền [0,100] rồi ánh xạ `score / 10` thành các **band rời rạc**. Mỗi band (số nguyên) được switch xử lý.

**Kiểm tra biên:** các điểm 49/50, 69/70, 89/90 xác nhận ranh giới giữa các nhóm; 0 và 100 xác nhận hai đầu miền. `grade(101)` bị từ chối **trước khi lấy band**, tránh việc ngoài miền bị phân loại sai.

**Không giả định số thập phân cũng chia 10 như int:** `score` có kiểu `int`, nên `/10` là chia số nguyên. Nếu yêu cầu phân loại điểm có phần thập phân hoặc khoảng với ranh giới không đều, có thể dùng `if/else`, hàm tìm band hoặc một bảng rules thay vì cố gò vào switch.

## 10. Ranh giới dữ liệu và exception: xử lý null đúng theo phiên bản Java

### Java 14–17 với switch expression cổ điển

Đối với `switch` trên `String` hoặc `enum`:

~~~java
String value = null;
String result = switch (value) {
    case "A" -> "alpha";
    default -> "other";
};
~~~

Đây là **đoạn minh họa lỗi runtime** ở Java 17, không phải cách xử lý null. **`default` không bắt null** trong dạng switch cổ điển này. Selector null gây **`NullPointerException`** trước khi một nhánh default thông thường có thể được chọn.

Vì vậy hãy xác định hợp đồng rõ:

~~~java
Objects.requireNonNull(value, "value");
String result = switch (value) {
    case "A" -> "alpha";
    default -> "other";
};
~~~

Hoặc, nếu null có ý nghĩa hợp lệ, xử lý **trước switch**:

~~~java
String result = value == null
        ? "missing"
        : switch (value) {
            case "A" -> "alpha";
            default -> "other";
        };
~~~

Cả hai đoạn trên là **mã minh họa trong phương thức** có import `Objects` nếu cần. Đừng bắt `NullPointerException` chung quanh mọi phép phân loại rồi trả “other”, vì như vậy có thể che lỗi lập trình xảy ra **bên trong** các nhánh.

### Java 21+ có mở rộng mới, nhưng phải dùng đúng language level

Từ **Java 21**, **pattern matching for switch** (JEP 441) được chính thức hóa, cho phép có nhãn `case null` trong những trường hợp phù hợp. Ví dụ một đoạn Java 21+:

~~~java
String answer = switch (value) {
    case null -> "missing";
    case "A" -> "alpha";
    default -> "other";
};
~~~

**Đây là ví dụ dành cho Java 21 trở lên**, không được sao chép vào file compile `--release 17` rồi kết luận switch expression Java 17 bị lỗi. Để biên dịch với Java 17 và không dùng preview, hãy giữ giải pháp kiểm tra null bên ngoài switch như phía trên.

Khi migrate sang Java mới, không phải mọi hành vi về null đều tự động biến mất: nếu một switch không có nhãn xử lý null thích hợp, việc truyền null vẫn có thể gây `NullPointerException`. Không nên coi `default` là catch-all cho null nếu đặc tả language version không cho phép.

## 11. Exhaustiveness: ý nghĩa, giới hạn và hai cách chứng minh

**Exhaustive** nghĩa là với mọi giá trị đầu vào mà language rules yêu cầu xét, switch expression có một nhánh cho ra kết quả hoặc ném exception. Compiler kiểm tra nó tại **compile time**.

### Với int, String: thường cần default

~~~java
String label = switch (number) {
    case 1 -> "one";
    case 2 -> "two";
    default -> "other";
};
~~~

Vì `int` có nhiều giá trị ngoài 1 và 2, nhánh `default` làm switch expression exhaustive.

### Với enum: có thể bao phủ hết hằng số không cần default

~~~java
enum Flag { ON, OFF }

static int number(Flag flag) {
    return switch (flag) {
        case ON -> 1;
        case OFF -> 0;
    };
}
~~~

Nếu sau này thêm `UNKNOWN` vào enum và **biên dịch lại source này**, compiler có thể yêu cầu bổ sung nhánh mới. Đây là một công cụ giúp quản lý phát triển domain model.

### Không phải mọi kết quả đều cần literal value

Một nhánh có thể `throw`:

~~~java
int result = switch (number) {
    case 0 -> 0;
    default -> throw new IllegalStateException("Unsupported number");
};
~~~

Switch vẫn exhaustive về control flow vì mọi giá trị ngoài 0 đều được xử lý bằng exception, không âm thầm bỏ qua.

### Khi một switch exhaustive nhưng dữ liệu thay đổi ở runtime

Nếu enum hoặc thư viện được nâng cấp độc lập khiến giá trị mới xuất hiện **mà client chứa switch chưa được rebuild**, compile-time coverage không đảm bảo không có lỗi runtime. Các bản JDK có thể dùng exception khác nhau trong những trường hợp hiếm như thế. Thiết kế release nên kiểm tra **dependency versions**, chạy integration tests và rebuild phù hợp.

## 12. Ba lỗi biên dịch có chủ đích: dùng để học chính xác luật

Để phân biệt lỗi thiết kế switch expression với lỗi dữ liệu runtime, hãy thử những đoạn **cố tình sai**.

### Lỗi A: switch không bao phủ hết miền int

~~~java
class IncompleteSwitch {
    static int classify(int n) {
        return switch (n) {
            case 1 -> 10;
        };
    }
}
~~~

Chưa có nhánh cho các `int` khác 1. Với `javac --release 17`, source này **không biên dịch**, vì expression chưa exhaustive.

Trên JDK được kiểm thử, compiler báo:

~~~text
error: the switch expression does not cover all possible input values
~~~

Cách sửa: thêm `default -> ...` hoặc thiết kế lại miền selector (ví dụ enum hữu hạn) và bao phủ hết giá trị.

### Lỗi B: dùng return bên trong nhánh block

~~~java
class InvalidYield {
    static int classify(int n) {
        return switch (n) {
            case 1 -> { return 10; }
            default -> 20;
        };
    }
}
~~~

Đây cũng là **mã cố ý sai**. Compiler Java 17 được kiểm thử báo:

~~~text
error: attempt to return out of a switch expression
~~~

Cách sửa:

~~~java
case 1 -> {
    yield 10;
}
~~~

Ở đây `yield` trả giá trị cho **switch expression**, còn `return` bên ngoài là cách phương thức trả kết quả. Hai tác vụ không tương đương.

### Lỗi C: case null trong language level 17

~~~java
class NullCaseVersion {
    static String classify(String s) {
        return switch (s) {
            case null -> "missing";
            default -> "known";
        };
    }
}
~~~

Với `--release 17` **không bật preview**, đoạn này bị từ chối vì nhãn `case null` chưa là cú pháp stable ở Java 17. Máy kiểm thử báo:

~~~text
error: null in switch cases is not supported in -source 17
~~~

Cách sửa cho dự án Java 17: kiểm tra null ở ngoài switch. Nếu dự án đã áp dụng Java 21+, cú pháp `case null` được hỗ trợ theo JEP 441.

**Phạm vi kết quả:** ba bài test âm đã được chạy trên JDK hiện đại với `javac --release 17`; trạng thái thất bại đúng như dự kiến. Thông điệp lỗi cụ thể có thể khác nhau giữa vendor, phiên bản và locale, vì vậy CI nên kiểm tra **exit code** và nhóm lỗi, không chụp nguyên văn stderr làm hợp đồng tuyệt đối.

## 13. Quy tắc về kiểu kết quả: tất cả nhánh phải tương thích

Một switch expression có **kiểu** được compiler xác định. Khi đặt trong ngữ cảnh gán hoặc return, kiểu mục tiêu giúp kiểm tra kết quả.

Hợp lệ:

~~~java
String label = switch (code) {
    case 0 -> "none";
    case 1 -> "one";
    default -> "many";
};
~~~

Cũng hợp lệ khi trả một kiểu domain:

~~~java
Route route = switch (type) {
    case SERVICE_OUTAGE -> new Route("incident", 15);
    case SECURITY_ALERT -> new Route("security", 10);
    default -> new Route("support", 240);
};
~~~

Hai đoạn là **minh họa trong scope đã khai báo `code`, `type` và `Route`**, không phải file Java độc lập.

Điều cần tránh: nhánh A trả `String`, nhánh B trả `int`, trong khi bạn mong kết quả là `String`. Compiler không thể chuyển mọi kết quả thành String chỉ vì chúng đều có phương thức `toString()`. Hãy chọn **một kiểu đầu ra rõ ràng** (ví dụ `enum` hoặc record) và giữ cùng hợp đồng ở mọi nhánh.

Với `var result = switch (...)`, compiler suy ra kiểu chung từ các nhánh theo quy tắc của ngôn ngữ (có thể sử dụng boxing hoặc least upper bound). Không nên lạm dụng `var` nếu tập kết quả có nhiều kiểu khác nhau khiến kiểu suy ra khó đọc; khai báo kiểu domain tường minh giúp người dùng API và reviewer hiểu rõ.

Nếu một nhánh có `throw`, nó không cần một giá trị kết quả để thỏa tương thích kiểu, bởi nhánh đó không hoàn tất bình thường.

## 14. Không có fall-through với nhánh mũi tên, nhưng phải hiểu hai dạng cú pháp

Trong Java 14+, switch expression có thể dùng:

1. **Switch rules** với `case L -> ...`, thường được khuyến nghị khi phân loại.
2. **Switch-labeled statement groups** với `case L: ...` và `yield`, có khả năng fall-through theo quy tắc cũ của dạng colon.

Ví dụ cách viết colon hợp lệ:

~~~java
int minutes = switch (code) {
    case 1:
        yield 5;
    case 2:
        yield 30;
    default:
        yield 60;
};
~~~

Dạng này vẫn **hợp lệ**, không phải cú pháp đã bị loại. Tuy nhiên với bộ phân loại đơn giản, mũi tên thường dễ đọc hơn và giảm rủi ro fall-through không mong đợi.

Không nên **trộn** nhóm nhãn colon và switch rules arrow trong **cùng một switch block**. Compiler sẽ từ chối các kiểu trộn không hợp lệ. Một file có thể có **nhiều switch khác nhau** dùng hai cách viết, nhưng mỗi switch block cần theo grammar tương ứng.

Nhớ thêm: `yield` **không dùng thay `break` trong switch statement thông thường** để mô phỏng việc trả về một biến. Nó là cú pháp dành cho việc đưa giá trị ra khỏi switch expression. Với switch statement, một `return` hợp lệ có thể trả từ phương thức hoặc `break` thoát statement, tùy thiết kế.

## 15. Một quy trình phát triển classifier dễ bảo trì

### Bước 1 — liệt kê input và expected output

Trước khi viết code, tạo bảng mapping như phần 1. Một hàng mô tả **một quy tắc nghiệp vụ**, không tự thêm hằng số “thử nghiệm” vào enum mà không xác định kết quả mong muốn.

### Bước 2 — chọn kiểu input

Nếu tập giá trị được quản lý trong code, dùng `enum`. Nếu input là chuỗi từ hệ thống ngoài, validate + normalize tại boundary rồi **chuyển về domain enum** khi phù hợp.

### Bước 3 — chọn kiểu output

Nếu chỉ một nhãn, trả `String` hoặc enum. Nếu nhiều thuộc tính, trả một object bất biến phù hợp như `record` (Java 16+) hoặc class có final fields. Không tạo side effect chỉ để mang kết quả qua biến toàn cục.

### Bước 4 — viết switch expression

Dùng `return switch (...) { ... };` trong method tính kết quả. Với từng case, ưu tiên `-> expression`. Nếu cần nhiều câu lệnh, dùng block + `yield`.

### Bước 5 — quyết định default

Với enum đã bao phủ toàn bộ, thường **không cần default** nếu muốn compiler bắt buộc cập nhật khi thêm giá trị. Với String/int có miền rộng, chọn default có ý nghĩa nghiệp vụ hoặc ném lỗi rõ ràng.

### Bước 6 — validate null và input ngoài miền

Không để null hoặc mã không hợp lệ lặng lẽ trở thành kết quả bình thường nếu domain không chấp nhận. Với numeric ranges, kiểm tra biên trước khi lấy bucket.

### Bước 7 — kiểm thử tất cả nhánh

Dùng các phép kiểm tra trả về expected values. Với enum, có thể thêm test duyệt `values()` và xác nhận mỗi hằng số có đường đi hợp lệ.

### Bước 8 — bổ sung test cho thay đổi domain

Thử thêm tạm một giá trị enum trong branch phát triển để xem compiler có phát hiện nhánh thiếu không. Không nhất thiết commit test cố ý làm build fail; có thể giữ dưới dạng negative test riêng.

### Bước 9 — tách phần phân loại và phần thực thi

Hàm phân loại nên **tính route**, còn tầng khác thực hiện gửi thông báo, cập nhật database hay lập lịch. Như vậy test classifier nhanh và không phụ thuộc tài nguyên ngoài.

### Bước 10 — chốt hợp đồng

Ghi rõ semantics của từng loại phiếu, chính sách invalid/null, cách xử lý khi enum tăng và mục tiêu tương thích JDK. Không phụ thuộc vào thông báo exception của một implementation cụ thể làm contract kiểm thử.

## 16. Thiết kế kiểm thử có giá trị hơn việc nhìn stdout

Hai chương trình ở phần 5 và 9 đã dùng các kiểm tra chủ động. Trong dự án thực, có thể tách thành unit tests theo một khuôn như sau:

| Nhóm kiểm thử | Input | Expected |
| --- | --- | --- |
| Route enum | SERVICE_OUTAGE | incident, 15 |
| Route enum | SECURITY_ALERT | security, 10 |
| Route enum | PAYMENT_ERROR | billing, 60 |
| Route enum | USAGE_QUESTION | support, 240 |
| Route enum | FEATURE_REQUEST | product, 1440 |
| Null contract | null | NullPointerException hoặc lỗi domain đã đặc tả |
| Normalize | `" sev0 "` | 5 phút |
| Group labels | `"OUTAGE"` | 5 phút |
| Yield branch | `"sev1"` | 20 phút |
| Unknown string | `"SEV9"` | IllegalArgumentException |
| Grade lower bound | 0 | D |
| Grade boundary | 49 / 50 | D / C |
| Grade boundary | 69 / 70 | C / B |
| Grade boundary | 89 / 90 | B / A |
| Grade upper bound | 100 | A |
| Invalid score | -1 / 101 | IllegalArgumentException |

**Lưu ý:** bảng này chỉ là **bảng ca kiểm thử**, không phải một API JUnit đã chạy trong bài. Hai file Java chạy được có sẵn assertions chủ động để chứng minh những nhánh thiết yếu.

### Nếu dùng JUnit Jupiter

Ví dụ phương thức test có thể viết trong class test thích hợp:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class RoutingTests {
    @Test
    void routesOutage() {
        var route = TicketRoutingDemo.classify(
                TicketRoutingDemo.TicketType.SERVICE_OUTAGE);
        assertEquals("incident", route.team());
        assertEquals(15, route.targetMinutes());
    }

    @Test
    void rejectsNullTicket() {
        assertThrows(NullPointerException.class,
                () -> TicketRoutingDemo.classify(null));
    }
}
~~~

**Đây là mã minh họa dùng JUnit Jupiter**, không phải ví dụ chạy chỉ với JDK. Dự án cần thêm **JUnit Jupiter dependency**, cấu hình test runner và giữ `TicketRoutingDemo` trong package/visibility cho phép test truy cập. Trong `TicketRoutingDemo` của bài, class và các thành phần demo ở cùng default package; trong dự án thật hãy dùng package rõ ràng, tách production/test sources và thiết kế public API phù hợp.

**Không kiểm thử bằng cách so đúng mọi ký tự thông điệp `NullPointerException` của JVM.** Trong ví dụ này ta chủ động gọi `Objects.requireNonNull(type,"type")`; điều quan trọng với test hợp đồng là **loại exception** và, nếu nghiệp vụ cần, một mã lỗi/kiểu lỗi có cấu trúc.

### Kiểm thử side effects

Một classifier thuần không nên gửi email hoặc thay đổi database khi chỉ cần trả Route. Nếu các nhánh có side effects, test phải ghi nhận **số lần thực thi**, tránh lỗi một nhánh được gọi nhiều lần hoặc ngoại lệ khiến tác vụ đã diễn ra một phần. Cách đơn giản là tách:

~~~text
type -> classify(type) -> Route
                          |
                          v
                   process(Route)
~~~

Khi `classify` chỉ trả giá trị, unit tests có thể tập trung vào đúng mapping; integration tests xử lý `process` độc lập.

## 17. Những lỗi thường gặp và cách khắc phục

**Lỗi 1 — Quên rằng switch expression phải exhaustive.**  
Với int/String, thường cần `default`. Với enum, có thể liệt kê mọi hằng số. Hãy để compiler kiểm tra thay vì giả định.

**Lỗi 2 — Gọi một switch có mũi tên là expression dù không dùng kết quả.**  
Không hẳn. `switch (...) { case X -> doSomething(); }` có thể là statement; expression phải xuất hiện ở ngữ cảnh dùng giá trị.

**Lỗi 3 — Dùng `return` bên trong block khi cần `yield`.**  
Không hợp lệ trong switch expression. Dùng `yield result;` để đưa kết quả ra switch, rồi `return switch(...) ...;` ở phương thức.

**Lỗi 4 — Nghĩ nhánh `->` cần thêm `break;`.**  
Không cần. Arrow rules không có fall-through sang case sau.

**Lỗi 5 — Dùng `case 70..89` trong switch int Java 17.**  
Không phải cú pháp phạm vi hợp lệ của Java 17. Hãy validate rồi quy đổi sang band hoặc dùng if/else khi ranh giới không đều.

**Lỗi 6 — Cho rằng `default` nhận null trong switch cổ điển.**  
Sai ở Java 17; selector null gây NPE. Xử lý null trước switch, hoặc dùng cú pháp null phù hợp Java 21+ khi target ngôn ngữ hỗ trợ.

**Lỗi 7 — Lẫn tính năng Java 14 với preview/Java 21.**  
Switch expression stable Java 14, nhưng `case null` trong switch với pattern matching stable Java 21. Đừng copy mã khác language level và coi tất cả thuộc Java 14.

**Lỗi 8 — Đưa cả tên mã chuỗi chưa chuẩn hóa vào case.**  
String switch phân biệt chữ hoa/thường. Nên normalize input theo hợp đồng nếu người dùng có thể gửi mã dưới nhiều dạng.

**Lỗi 9 — Nuốt mọi mã lạ vào nhánh “mức thấp”.**  
Có thể khiến sự cố thật bị phân tuyến sai. Với domain không chấp nhận mã lạ, dùng `default -> throw ...`.

**Lỗi 10 — Thêm `default` vào enum chỉ vì thói quen.**  
Nếu yêu cầu phải xử lý mọi enum constant riêng, default có thể che cảnh báo khi thêm hằng số. Quyết định có default theo hợp đồng.

**Lỗi 11 — Nhánh trả các kiểu không tương thích.**  
Chọn một kiểu output rõ ràng. Đừng trộn int, String và object rồi hy vọng compiler tự biến thành String theo `toString()`.

**Lỗi 12 — Kết quả phụ thuộc vào biến ngoài bị sửa ở mỗi case.**  
Chỉ là một cách viết có thể có nhưng làm classifier khó kiểm thử. Trả về giá trị trực tiếp thường rõ hơn.

**Lỗi 13 — Đặt `yield` bên ngoài switch expression.**  
`yield` có vai trò ngữ pháp riêng; dùng nó ở ngoài ngữ cảnh được phép sẽ lỗi compile.

**Lỗi 14 — Dùng `break value;` làm cú pháp chính thức hiện nay.**  
Trong Java hiện đại, đưa giá trị ra switch expression dùng **`yield value;`**. Không sao chép cú pháp preview cũ dùng break-with-value.

**Lỗi 15 — Dùng `switch` với selector bất kỳ trong Java 17.**  
Không phải mọi kiểu đều switch được ở Java 17. Cú pháp pattern switch mở rộng miền selector đã stable từ Java 21. Với Java 17, ví dụ tập trung int, String và enum.

**Lỗi 16 — Không kiểm thử biên numeric ranges.**  
Nếu dùng `score / 10`, cần kiểm tra 49/50, 69/70, 89/90 và giá trị ngoài miền, không chỉ 75 và 95.

**Lỗi 17 — Tin `assert` luôn chạy trong production.**  
Java assertions có thể bị tắt theo mặc định. Dùng unit-test framework hoặc chủ động ném `AssertionError` trong demo khi cần kiểm chứng.

**Lỗi 18 — Suy rằng không có default sẽ luôn tránh mọi lỗi runtime.**  
Compiler xác minh source đang biên dịch. Nếu phiên bản enum/phụ thuộc thay đổi độc lập, vẫn cần kiểm thử compatibility khi triển khai.

**Lỗi 19 — Gắn chính sách nghiệp vụ cứng vào demo mà không ghi chú.**  
SLA ở đây là ví dụ. Với code thật, quy tắc có thể cần cấu hình, versioning, audit và test phù hợp quy trình sản phẩm.

**Lỗi 20 — So chuỗi `toString()` của record làm hợp đồng lâu dài.**  
`Route.toString()` hữu ích để quan sát demo nhưng API nghiệp vụ nên kiểm tra `team()` và `targetMinutes()`, tránh gắn hợp đồng ngoại vi vào định dạng hiển thị debug.

## 18. Bài tập mở rộng theo thứ tự tăng độ khó

### Bài tập A — thêm trạng thái enum

Thêm `DATA_LOSS` vào `TicketType`. Không thêm case ngay, hãy compile lại và xem compiler báo gì. Sau đó quyết định `Route("incident", 5)` hoặc chính sách thực tế phù hợp, bổ sung case và test.

**Điểm cần chứng minh:** compiler giúp tìm chỗ thiếu và test xác nhận mapping mới.

### Bài tập B — nhóm các loại tương đương

Thêm loại `DOCUMENTATION_QUESTION` và cho nó cùng Route với `USAGE_QUESTION`. Dùng một nhãn:

~~~java
case USAGE_QUESTION, DOCUMENTATION_QUESTION ->
        new Route("support", 240);
~~~

Đây là **đoạn minh họa** yêu cầu enum đã khai báo hằng số mới. Chỉ gộp nếu hai trường hợp thực sự có cùng policy.

### Bài tập C — phân loại mã HTTP status

Thiết kế hàm:

~~~text
200–299 -> SUCCESS
400–499 -> CLIENT_ERROR
500–599 -> SERVER_ERROR
còn lại -> OTHER
~~~

Thực hiện bằng `if/else` hoặc chuẩn hóa thành status family rồi dùng switch expression. Không viết `case 200..299` như thể Java 17 có range pattern.

### Bài tập D — trả một object nhiều thuộc tính

Thêm thuộc tính `notifyOnCall` kiểu boolean vào `Route`. Cập nhật tất cả constructor calls và tests. Một switch expression có phải trả ba giá trị riêng biệt không?

*Gợi ý:* vẫn trả **một object** chứa ba thuộc tính; kiểu output duy nhất giúp thiết kế rõ.

### Bài tập E — phân loại null theo ngôn ngữ mục tiêu

Giữ nguyên Java 17 và xử lý null trước String switch. Sau đó nếu có môi trường Java 21+, thử phiên bản dùng `case null`. Hãy đảm bảo test null có cùng hợp đồng nghiệp vụ.

### Bài tập F — bỏ nhánh default của String

Cố tình xóa `default` khỏi `responseMinutes(String)` và biên dịch. Compiler phản ứng thế nào? Vì sao String có miền giá trị quá lớn để liệt kê hết nhãn?

### Bài tập G — thiết kế test ở boundary

Bổ sung test `grade(-1)`, `grade(101)`, `grade(49)`, `grade(50)`, `grade(69)` và `grade(70)`. Thử thay quy tắc chia band để kiểm tra test có bắt được hồi quy.

### Bài tập H — tách nghiệp vụ khỏi side effect

Thay vì để `classify` vừa tính route vừa gửi notification, thiết kế service:

~~~text
Ticket -> Route = classifier.classify(ticket.type)
       -> DeliveryService.dispatch(Route, Ticket)
~~~

Viết unit tests cho classifier và mock/fake service cho dispatch. Khi đổi SLA, các test routing không cần kết nối mạng.

## 19. Checklist hoàn thành một bộ phân loại switch expression

- [ ] Xác định chính xác input domain, output type và expected mapping.
- [ ] Chọn Java target release phù hợp; switch expression stable từ Java 14.
- [ ] Nếu dùng record thì source cần Java 16+; hai demo chính target Java 17.
- [ ] Phân biệt expression với statement, không dựa riêng vào dấu `->`.
- [ ] Dùng `case X -> expression;` cho nhánh ngắn.
- [ ] Dùng block + `yield` khi cần nhiều câu lệnh trước khi tạo kết quả.
- [ ] Không dùng `return` thay `yield` trong nhánh block.
- [ ] Nếu enum được liệt kê hết, cân nhắc bỏ default để compiler giúp phát hiện giá trị mới.
- [ ] Nếu String/int có giá trị ngoài miền, đưa ra default hợp lý hoặc ném lỗi.
- [ ] Validate null theo đúng release; Java 17 không có stable `case null`.
- [ ] Chuẩn hóa mã String trước phân loại nếu domain yêu cầu.
- [ ] Nếu phân loại theo khoảng số, validate miền và kiểm thử các ranh giới.
- [ ] Mọi case tạo kết quả có kiểu tương thích với kiểu đích.
- [ ] Tách side effects ra khỏi hàm tính route khi có thể.
- [ ] Biên dịch bằng `javac --release` tương ứng và chạy trên runtime được hỗ trợ.
- [ ] Kiểm thử mọi enum case, mọi group, lỗi invalid/null và các thay đổi domain.
- [ ] Không phụ thuộc vào chuỗi exception message để làm contract.
- [ ] Đối chiếu tài liệu Java Language Specification và JEP khi dùng tính năng mới hơn.

## 20. Câu hỏi tự kiểm tra

**Câu 1.** Switch expression ổn định từ Java nào?  
**Đáp án:** Java 14, theo JEP 361.

**Câu 2.** `switch (...) { case A -> ... }` có tự động là expression không?  
**Đáp án:** Không; phải xem switch đang được dùng để **tạo giá trị** hay chỉ thực thi statement.

**Câu 3.** Nhánh `case 1 -> { int x = 2; yield x * 3; }` tạo giá trị nào?  
**Đáp án:** 6.

**Câu 4.** Vì sao không dùng `return value;` thay `yield value;` trong block của switch expression?  
**Đáp án:** `return` không được dùng để return ra khỏi switch expression; `yield` mới là cú pháp cấp giá trị cho expression đó.

**Câu 5.** `case "A", "B" -> 10;` có ý nghĩa gì?  
**Đáp án:** Cả mã A và B đều tạo kết quả 10, không có fall-through.

**Câu 6.** Enum có ba hằng số đều được liệt kê bằng case thì cần default không?  
**Đáp án:** Không bắt buộc; compiler xác minh exhaustiveness.

**Câu 7.** Nếu thêm hằng số enum mới nhưng không cập nhật switch expression không có default và compile lại thì sao?  
**Đáp án:** Compiler phát hiện switch expression không exhaustive.

**Câu 8.** Có thể dùng String switch với null ở Java 17 mà default trả “other” không?  
**Đáp án:** Không; switch cổ điển trên null ném NullPointerException. Kiểm tra null trước switch.

**Câu 9.** `case null` trở thành cú pháp stable trong bối cảnh pattern matching for switch ở Java nào?  
**Đáp án:** Java 21.

**Câu 10.** `default -> throw new IllegalArgumentException(...)` có hợp lệ trong switch expression trả `int` không?  
**Đáp án:** Có. Nhánh throw không hoàn tất bình thường, nên không phải tạo một giá trị int.

**Câu 11.** Vì sao `grade(101)` phải bị từ chối trước khi chạy switch trên band?  
**Đáp án:** Nó nằm ngoài miền [0,100]; nếu chỉ chia 10 rồi switch, có thể được phân loại sai như điểm hợp lệ.

**Câu 12.** Sự khác nhau giữa `Route route = switch(...)` và `return switch(...)` là gì?  
**Đáp án:** Cả hai dùng switch expression trả giá trị; một lưu vào biến, một trả trực tiếp từ phương thức.

**Câu 13.** Có nên dùng một default “bình thường” cho mã sự cố chưa biết trong hệ thống yêu cầu dữ liệu phải hợp lệ không?  
**Đáp án:** Không nhất thiết; có thể che dữ liệu lỗi. Khi mã không hợp lệ phải bị từ chối, nên dùng exception hoặc error result có cấu trúc.

**Câu 14.** Tại sao `case 70..89` không dùng được để phân loại điểm trong Java 17?  
**Đáp án:** Java 17 switch expression không có cú pháp range case đó; dùng bucket, if/else hoặc bảng rules.

**Câu 15.** Các giá trị record như `Route("incident", 15)` có làm switch expression trả hai giá trị không?  
**Đáp án:** Không. Nó trả một object `Route` chứa hai thành phần.

**Câu 16.** Tại sao nên tránh side effects bên trong classifier?  
**Đáp án:** Để phân loại dễ kiểm thử, không lặp tác dụng phụ khi retry, và tách quyết định khỏi hành động.

## Tài liệu Java chính thức

- **OpenJDK JEP 361 — Switch Expressions:** switch expressions được chuẩn hóa trong Java 14, mũi tên `->`, `yield` và yêu cầu exhaustiveness: https://openjdk.org/jeps/361
- **Oracle Java SE 17 — JLS §15.28 Switch Expressions:** quy tắc type của switch expression, switch rules, `yield`, kết quả của expression và kiểm tra exhaustiveness: https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28
- **Oracle Java SE 17 — JLS §14.11 Switch Statements:** phân biệt switch statement với expression và dạng nhãn `case`: https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11
- **dev.java — Branching with Switch Expressions:** ví dụ hiện hành về switch expressions, colon labels, exhaustiveness và xử lý null: https://dev.java/learn/branching-with-switch-expressions/
- **OpenJDK JEP 441 — Pattern Matching for switch:** sự phát triển đến Java 21, trong đó có xử lý `case null`: https://openjdk.org/jeps/441
- **Oracle JDK 21 — Java Language Changes:** xác nhận pattern matching for switch stable ở Java 21, phân biệt với Java 17 preview: https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html
- **OpenJDK JEP 395 — Records:** record đã chính thức hóa từ Java 16; được dùng trong ví dụ Java 17 để trả kết quả có cấu trúc: https://openjdk.org/jeps/395
- **Oracle Java SE 17 — `Objects.requireNonNull`:** kiểm tra đầu vào null rõ ràng: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Objects.html
- **Oracle Java SE 17 — `String.strip()`:** loại bỏ whitespace ở đầu/cuối mã trước khi phân loại: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html
- **Oracle Java SE 17 — `Locale.ROOT`:** chuẩn hóa mã không phụ thuộc default locale: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html