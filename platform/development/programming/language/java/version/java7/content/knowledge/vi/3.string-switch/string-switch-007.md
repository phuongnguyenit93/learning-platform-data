# Java 7 — Chọn String, enum hoặc cấu trúc tra cứu phù hợp

## 1. Vấn đề cần giải quyết

Java 7 bổ sung khả năng sử dụng **`String` làm selector của `switch`**. Tính năng này vẫn hữu ích khi chọn hành vi dựa trên một tập nhỏ các tên lệnh, trạng thái hoặc mã có nội dung xác định. Tuy nhiên, **không phải mọi chuỗi đều nên được xử lý bằng `switch(String)`**. Khi bài toán có một tập giá trị nghiệp vụ cố định, `enum` đem lại kiểu dữ liệu rõ ràng hơn; khi cần ánh xạ nhiều khóa đến dữ liệu hoặc handler, `Map`/cấu trúc tra cứu thường phù hợp hơn.

Điểm lựa chọn cốt lõi:

- **`switch(String)`:** phù hợp khi đang xử lý một số ít giá trị chuỗi cố định, các nhánh rõ ràng và không cần cấu trúc đăng ký có thể thay đổi khi chạy.
- **`switch(enum)`:** phù hợp khi các giá trị thuộc **một tập khái niệm nghiệp vụ hữu hạn, đã được định nghĩa ở mức kiểu** và nhiều phần của chương trình dùng chung tập đó.
- **`Map<K,V>` hoặc bảng handler:** phù hợp khi bản chất công việc là **tra cứu khóa → giá trị/hành động**, số khóa tăng, danh sách đến từ cấu hình hoặc cần đăng ký handler mà không viết chuỗi nhánh `case` dài.
- **`EnumMap<E,V>`:** là lựa chọn kết hợp khi khóa đã là `enum` nhưng bài toán vẫn là tra cứu hoặc ánh xạ handler.

Bài này tập trung vào lựa chọn cấu trúc điều khiển và dữ liệu **còn áp dụng trên các JDK hiện đại**; ví dụ hoàn chỉnh sử dụng Java 17+. Cú pháp `switch(String)` kiểu truyền thống có từ Java 7, còn **`switch expression` với `->` trong ví dụ Java 17 là tính năng ngôn ngữ được chuẩn hóa ở Java 14**. Không nhầm hai thời điểm xuất hiện này.

## 2. Hiểu đúng `switch(String)` trước khi chọn

### 2.1. Ví dụ cú pháp quen thuộc

```java
String channel = "WEB";

switch (channel) {
    case "WEB":
        System.out.println("Browser");
        break;
    case "MOBILE":
        System.out.println("App");
        break;
    default:
        System.out.println("Unknown channel");
}
```

Đây là **đoạn mã minh họa có thể đặt trong một phương thức**, không phải chương trình độc lập. Với `channel = "WEB"`, nó in ra `Browser`.

Trên Java 17+, khi cần **trả về một giá trị** thay vì thực hiện các lệnh bên trong mỗi nhánh, cú pháp `switch expression` thường gọn hơn:

```java
static String labelFor(String channel) {
    return switch (channel) {
        case "WEB" -> "Browser";
        case "MOBILE" -> "App";
        default -> "Unknown channel";
    };
}
```

Phương thức trên là ví dụ để đặt trong một lớp. Dạng `->` tránh lỗi quên `break`/rơi xuống nhánh kế tiếp (*fall-through*) của nhóm `case:` truyền thống. `switch expression` cần có nhánh bao phủ mọi trường hợp; với selector `String`, thông thường dùng `default`.

### 2.2. Bốn quy tắc dễ ảnh hưởng tới quyết định

**So khớp theo giá trị chuỗi, phân biệt hoa/thường.** Trong `switch(String)`, `"web"` và `"WEB"` là hai giá trị khác nhau. Trình biên dịch triển khai so khớp có xét **nội dung chuỗi**, không dựa vào so sánh tham chiếu `==` giữa hai `String`. Không cần gọi `intern()` để switch hoạt động.

**Giá trị `case` là hằng tại thời điểm biên dịch.** Có thể viết `case "WEB"` hoặc một biến `static final String` được khởi tạo bằng biểu thức hằng; không thể dùng chuỗi tải từ database/cấu hình làm `case` động. Nếu danh sách khóa thay đổi theo cấu hình, nên xem xét tra cứu bằng `Map` hoặc một cơ chế đăng ký có kiểm soát.

**Null cần chính sách rõ ràng.** Với `switch(String)` thông thường trên Java 17, selector `null` gây `NullPointerException`. Hãy kiểm tra đầu vào ngay tại biên dữ liệu và trả lỗi có ngữ nghĩa. Các khả năng `switch` mới trên những phiên bản Java khác có quy tắc riêng; ví dụ trong bài chủ động dùng tập cú pháp ổn định của Java 17.

**Giá trị không có nhánh cần được xử lý chủ ý.** Với switch statement, nếu thiếu `default` và không nhánh nào khớp, chương trình có thể đi tiếp mà không làm gì. Với lệnh nghiệp vụ như hủy/hoàn tiền/thay đổi trạng thái, hành vi im lặng này thường khó kiểm tra. Chọn thông báo lỗi, kết quả “không hỗ trợ” hoặc giá trị dự phòng **theo hợp đồng nghiệp vụ**, không tự mặc định mọi giá trị lạ là một hành động hợp lệ.

### 2.3. Khi nào nên tiếp tục dùng `String`?

`switch(String)` đặc biệt dễ đọc khi bạn **chỉ xử lý các token cố định của một giao thức ở biên hệ thống**: chẳng hạn `"CREATE"`, `"CANCEL"`, `"STATUS"`. Mỗi nhánh thể hiện một quy tắc cụ thể; thay đổi token trong hợp đồng đầu vào cần được review cùng mã nguồn.

Nếu nhiều tầng nghiệp vụ phải so sánh lại cùng các chuỗi này, mỗi nơi có thể viết lệch `"CANCEL"`/`"CANCELED"` hoặc bỏ quên một nhánh. Đó là tín hiệu để chuyển token thô sang **kiểu `enum` được kiểm soát** ngay khi parse.

## 3. Dùng `enum` cho một tập khái niệm nghiệp vụ cố định

Một `enum` khai báo tập giá trị hợp lệ ở mức kiểu:

```java
enum Command {
    CREATE,
    CANCEL,
    STATUS
}
```

Thay vì truyền một `String` có thể chứa bất cứ nội dung nào, các phương thức nghiệp vụ nhận `Command`:

```java
static String describe(Command command) {
    return switch (command) {
        case CREATE -> "Created";
        case CANCEL -> "Cancelled";
        case STATUS -> "Status requested";
    };
}
```

Đoạn này là phương thức minh họa đặt **cùng lớp chứa `Command`**. `switch expression` trên `enum` bao phủ toàn bộ các hằng đã khai báo nên không cần `default`. Khi lập trình viên thêm hằng mới vào `Command` rồi biên dịch lại, compiler có thể phát hiện biểu thức switch chưa bao phủ hằng đó. Điều này giúp tránh quên cập nhật một nhánh nghiệp vụ.

Ưu điểm của `enum`:

1. **Tập giá trị có tên và kiểu rõ ràng:** chữ ký `process(Command command)` tự mô tả hơn so với `process(String command)`.
2. **IDE/compiler hỗ trợ:** autocomplete, refactor, phát hiện nhiều nhầm lẫn kiểu và thiếu nhánh ở switch expression.
3. **Có thể gắn dữ liệu/hành vi:** nếu mỗi giá trị có mã bên ngoài, mô tả hoặc chính sách riêng, `enum` có thể có field và phương thức, thay vì để nhiều chuỗi rải rác.
4. **So sánh bằng `==` an toàn:** các hằng `enum` là các instance duy nhất của kiểu enum đó.
5. **Dễ thống nhất quy tắc trong ứng dụng:** sau khi parse ở biên hệ thống, logic lõi sử dụng `Command` thay vì parse `String` nhiều lần.

Giới hạn: tập hằng `enum` được xác định khi biên dịch; **không thể thêm giá trị mới tùy ý từ cấu hình khi ứng dụng đang chạy**. Nếu sản phẩm hỗ trợ plugin hoặc danh mục khóa được thêm thường xuyên mà không phát hành lại ứng dụng, `enum` có thể không hợp cho **toàn bộ danh sách khóa**.

### 3.1. Đừng tự động gọi `Enum.valueOf` trên dữ liệu bất kỳ

`Command.valueOf("CREATE")` trả `Command.CREATE`, nhưng `Command.valueOf("create")` ném `IllegalArgumentException` vì tên phải khớp chính xác; `null` cũng không được chấp nhận. Nếu API cần alias `"new"` hay chữ thường, hãy **xác thực và chuyển đổi rõ ràng ở biên hệ thống**:

```java
static Command parseCommand(String raw) {
    if (raw == null || raw.isBlank()) {
        throw new IllegalArgumentException("Command is required");
    }

    return switch (raw.strip().toUpperCase(java.util.Locale.ROOT)) {
        case "CREATE", "NEW" -> Command.CREATE;
        case "CANCEL" -> Command.CANCEL;
        case "STATUS" -> Command.STATUS;
        default -> throw new IllegalArgumentException("Unknown command: " + raw);
    };
}
```

Đây là **phương thức minh họa**, cần đặt trong lớp có `enum Command`. `strip()` có từ Java 11; `Locale.ROOT` tránh phụ thuộc locale mặc định khi chuẩn hóa các token giao thức. Chỉ chuẩn hóa như vậy **nếu hợp đồng đầu vào cho phép bỏ khoảng trắng và không phân biệt hoa/thường**. Với khóa phân biệt chữ hoa/thường hoặc mang ý nghĩa Unicode riêng, giữ nguyên và so khớp đúng quy định.

Nếu tên enum thay đổi theo refactor, `name()` cũng thay đổi. **Không nên phụ thuộc vào `name()` hoặc `ordinal()` làm mã lưu trữ/bền vững ở database hoặc giao thức công khai** nếu chưa có cam kết ổn định. Với mã bên ngoài, khai báo một `code` cố định và một parser tường minh để tránh đổi tên hằng làm hỏng dữ liệu cũ.

### 3.2. Chọn `switch(enum)` hay đưa hành vi vào enum?

Với vài nhánh xử lý chung, `switch(enum)` thường minh bạch. Khi mỗi hằng có một chính sách/thuộc tính bền vững, có thể gắn thuộc tính vào enum. Nếu logic của từng nhánh cần nhiều dependency hoặc thay đổi độc lập, cân nhắc chiến lược (*strategy*)/dịch vụ riêng rồi chọn bằng enum hoặc map. Tránh ép enum thành “lớp chứa toàn bộ nghiệp vụ” với logic phức tạp và dependency khó kiểm thử.

## 4. Dùng `Map` khi bài toán là tra cứu hoặc điều phối handler

Khi câu hỏi thực tế là **“với key này, dữ liệu hoặc hành động tương ứng là gì?”**, `Map<K,V>` biểu diễn trực tiếp mối quan hệ đó.

### 4.1. Ánh xạ khóa → giá trị

```java
java.util.Map<String, Integer> priorities = java.util.Map.of(
    "LOW", 1,
    "NORMAL", 2,
    "HIGH", 3
);

Integer priority = priorities.get("NORMAL"); // 2
```

Dùng một bảng dữ liệu thường dễ duy trì hơn việc thêm hàng chục nhánh switch chỉ để trả về các hằng. `Map.of` (có trên JDK hiện đại) tạo map **không thể chỉnh sửa qua API map**; nó từ chối khóa/giá trị `null` và khóa trùng lúc tạo. `Map.ofEntries` phù hợp khi cần khai báo số mục lớn hơn giới hạn overload tiện lợi của `Map.of`.

**Đừng dựa vào thứ tự duyệt `Map.of`:** thứ tự các entry không được bảo đảm. Nếu thứ tự có ý nghĩa (như ưu tiên hiển thị), hãy lưu nó thành dữ liệu riêng hoặc chọn cấu trúc có quy tắc thứ tự rõ ràng.

### 4.2. Ánh xạ khóa → hành động

```java
java.util.Map<String, java.util.function.Supplier<String>> actions =
        java.util.Map.of(
            "CREATE", () -> "Created",
            "CANCEL", () -> "Cancelled",
            "STATUS", () -> "Status requested"
        );

java.util.function.Supplier<String> action = actions.get("CREATE");

if (action == null) {
    throw new IllegalArgumentException("Unknown command");
}

System.out.println(action.get()); // Created
```

Trong ví dụ này, `Supplier<String>` là handler không nhận tham số và trả về một kết quả. Với handler cần request, có thể sử dụng `Function<Request,Response>` hoặc interface nghiệp vụ có tên rõ ràng. Map giúp tách **bảng điều phối** khỏi **implementation của từng hành động**. Tuy nhiên, chỉ nên đăng ký những handler đã được phép chạy; không tạo hoặc gọi class bằng reflection từ chuỗi tùy ý của người dùng.

Map hỗ trợ mở rộng, nhưng **không có đảm bảo exhaustiveness của compiler như switch expression trên enum**. Key thiếu trong map sẽ được phát hiện lúc chạy hoặc trong kiểm thử. Hãy kiểm tra tính đầy đủ khi khởi động hoặc bằng test đối với danh sách key bắt buộc.

### 4.3. Map cố định, Map đăng ký động, và `EnumMap`

- **Bảng tra cứu cố định:** dùng `Map.of` hoặc `Map.ofEntries`; rõ ràng về phần dữ liệu đã khai báo, không có nhu cầu sửa registry trong lúc chạy.
- **Bảng đăng ký trong lúc khởi tạo:** có thể dùng `HashMap` để đăng ký các handler, xác thực xung đột key rồi xuất bản bản không thể chỉnh sửa bằng `Map.copyOf`. Tránh cho nhiều phần code tùy tiện sửa registry.
- **Bảng thực sự thay đổi đồng thời lúc chạy:** phải thiết kế cơ chế đồng bộ phù hợp; `ConcurrentHashMap` là một công cụ cho truy cập/đăng ký đồng thời, nhưng không tự giải quyết các vấn đề nhất quán nghiệp vụ hoặc thứ tự thực thi handler.
- **Khóa là enum:** cân nhắc `EnumMap<Command,Handler>`. Nó dành cho key enum, biểu diễn bảng tra cứu theo tập hằng đã biết; vẫn cần xác thực đã đăng ký đủ handler và quản lý tính mutable.

Ví dụ minh họa khi khóa đã là enum:

```java
java.util.EnumMap<Command, String> messages =
        new java.util.EnumMap<>(Command.class);

messages.put(Command.CREATE, "Created");
messages.put(Command.CANCEL, "Cancelled");
messages.put(Command.STATUS, "Status requested");
```

Bảng trên là **đoạn mã trong lớp đã khai báo `Command`**, dùng khi yêu cầu là ánh xạ từ enum đến thông điệp. `EnumMap` tự thân mutable; nếu chia sẻ giữa nhiều thành phần cần chính sách không cho sửa, phải quản lý vòng đời và quyền thay đổi tương ứng.

## 5. Bảng chọn nhanh theo đặc điểm bài toán

| Câu hỏi thiết kế | `switch(String)` | `enum` + `switch` | `Map`/bảng tra cứu |
| --- | --- | --- | --- |
| Tập giá trị | Nhỏ, cố định trong source | Hữu hạn, cố định theo mô hình nghiệp vụ | Nhiều khóa hoặc bảng có thể xây dựng từ dữ liệu/đăng ký |
| Đầu vào | Token chuỗi như lệnh, mã giao thức | Giá trị đã được parse thành kiểu nghiệp vụ | Khóa để tra cứu dữ liệu hoặc handler |
| Compiler phát hiện thiếu nhánh? | Với switch expression cần `default` cho String; không suy ra danh mục nghiệp vụ | Switch expression enum có thể kiểm tra đủ hằng enum | Không; cần kiểm tra riêng |
| Bổ sung khóa mới | Sửa mã nguồn `case` | Sửa khai báo enum và chỗ dùng | Thêm entry/handler theo quy trình đăng ký |
| Động khi chạy | Không; `case` là hằng | Không thể thêm enum constant mới khi chạy | Có thể, nếu map/registry được thiết kế cho thay đổi |
| Dữ liệu ánh xạ thuần túy | Ít trực tiếp khi số key lớn | Có thể nhưng không nhất thiết gọn | Phù hợp nhất |
| Hành vi khác nhau mỗi nhánh | Tốt với ít nhánh đơn giản | Tốt với các trạng thái/loại nghiệp vụ hữu hạn | Tốt khi tách các handler độc lập |
| Rủi ro chính | Lặp literal, null, giá trị lạ, nhánh dài | Parse dữ liệu ngoài, đổi tên hằng, phụ thuộc nhằng nhịt | Thiếu key, trùng key, mutation và quyền gọi handler |

**Không có ngưỡng số lượng `case` tuyệt đối** quyết định cấu trúc nào nhanh/tốt hơn. Ưu tiên **mô hình dữ liệu, mức thay đổi, kiểm tra kiểu và khả năng đọc code**. Nếu hiệu năng thật sự ảnh hưởng đến ứng dụng, đo bằng profiler/benchmark trên workload thực tế thay vì mặc định `switch` nhanh hơn `Map` hoặc ngược lại.

### Luồng quyết định tham khảo

```text
Đầu vào là String từ ngoài hệ thống?
  ├─ Có → Kiểm tra null, định dạng, alias và chuẩn hóa theo hợp đồng.
  │         │
  │         ├─ Có tập giá trị nghiệp vụ đóng?
  │         │      └─ Parse String → enum → switch(enum) hoặc EnumMap.
  │         │
  │         ├─ Chỉ vài token ổn định, logic ngắn?
  │         │      └─ switch(String) trực tiếp ở biên hệ thống.
  │         │
  │         └─ Cần bảng khóa → dữ liệu/handler?
  │                └─ Map/registry có kiểm soát.
  │
  └─ Không → Nếu đã là enum, giữ kiểu enum; chọn switch hoặc EnumMap
              theo việc cần xử lý nhánh hay tra cứu dữ liệu.
```

## 6. Ví dụ Java 17+ hoàn chỉnh: ba cách giải quyết cùng một bài toán

Một dịch vụ nhận tên lệnh dưới dạng `String`. Có ba lệnh nội bộ: `CREATE`, `CANCEL`, `STATUS`. API cũng chấp nhận bí danh `NEW` cho `CREATE`, và trong ví dụ này cho phép khoảng trắng dư cũng như khác biệt chữ hoa/thường.

Tạo tệp **`RoutingChoicesDemo.java`**:

```java
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.function.Supplier;

public class RoutingChoicesDemo {
    enum Command { CREATE, CANCEL, STATUS }

    private static final Map<String, Supplier<String>> HANDLERS = Map.of(
        "CREATE", () -> "Created",
        "CANCEL", () -> "Cancelled",
        "STATUS", () -> "Status requested"
    );

    static String normalize(String raw) {
        if (raw == null) {
            throw new IllegalArgumentException("Command is required");
        }
        String key = raw.strip().toUpperCase(Locale.ROOT);
        if (key.isEmpty()) {
            throw new IllegalArgumentException("Command is required");
        }
        return key;
    }

    // Cách 1: switch trực tiếp trên String ở biên dữ liệu.
    static String byString(String raw) {
        return switch (normalize(raw)) {
            case "CREATE", "NEW" -> "Created";
            case "CANCEL" -> "Cancelled";
            case "STATUS" -> "Status requested";
            default -> throw new IllegalArgumentException(
                    "Unknown command: " + raw);
        };
    }

    // Cách 2: parse String thành kiểu nghiệp vụ trước.
    static Command parseCommand(String raw) {
        return switch (normalize(raw)) {
            case "CREATE", "NEW" -> Command.CREATE;
            case "CANCEL" -> Command.CANCEL;
            case "STATUS" -> Command.STATUS;
            default -> throw new IllegalArgumentException(
                    "Unknown command: " + raw);
        };
    }

    static String byEnum(Command command) {
        return switch (Objects.requireNonNull(command, "command")) {
            case CREATE -> "Created";
            case CANCEL -> "Cancelled";
            case STATUS -> "Status requested";
        };
    }

    // Cách 3: chuẩn hóa key rồi tìm handler trong Map.
    static String byMap(String raw) {
        String key = normalize(raw);
        if (key.equals("NEW")) {
            key = "CREATE";
        }
        Supplier<String> action = HANDLERS.get(key);
        if (action == null) {
            throw new IllegalArgumentException("Unknown command: " + raw);
        }
        return action.get();
    }

    public static void main(String[] args) {
        System.out.println("String: " + byString(" new "));
        System.out.println("enum: " + byEnum(parseCommand("status")));
        System.out.println("Map: " + byMap("cancel"));

        try {
            byString("undo");
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid: " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy với **JDK 17 hoặc mới hơn**:

```bash
javac --release 17 RoutingChoicesDemo.java
java RoutingChoicesDemo
```

**Stdout:**

```text
String: Created
enum: Status requested
Map: Cancelled
Invalid: Unknown command: undo
```

### Điều gì đang xảy ra?

1. **`normalize`** kiểm tra `null`, xóa khoảng trắng đầu/cuối bằng `strip()` và đổi chữ hoa bằng `Locale.ROOT`. Vì hợp đồng ví dụ cho phép những chuyển đổi này, `" new "` trở thành `"NEW"`. Nếu hệ thống thật yêu cầu token exact, nên **không tự ý chuyển đổi**.
2. **`byString`** giải quyết mọi nhánh ngay trên các giá trị String. Với vài lệnh ổn định, mã rõ ràng; với quá nhiều lệnh và side effect, hàm có thể phình to.
3. **`parseCommand` rồi `byEnum`** tách hẳn việc hiểu dữ liệu bên ngoài khỏi xử lý trạng thái nghiệp vụ. Ở lớp nghiệp vụ, chỉ còn ba giá trị `Command` hợp lệ.
4. **`byMap`** dùng tên lệnh chuẩn hóa để lấy một `Supplier<String>`; bí danh `NEW` cần được ánh xạ sang key chuẩn trước. Nếu không có handler, hàm trả lỗi tường minh.
5. Trường hợp `"undo"` được nhận diện là lệnh **không hỗ trợ**; chương trình bắt lỗi để minh họa, nhưng ứng dụng thật nên chuyển lỗi thành phản hồi phù hợp tại biên HTTP/UI/CLI.

**Ba cách cho cùng kết quả không có nghĩa dự án phải dùng cả ba.** Chương trình trên cố ý đặt ba cách cạnh nhau để so sánh. Trong code nghiệp vụ thật, hãy chọn một cấu trúc chính và chỉ kết hợp khi có lợi ích rõ ràng: ví dụ parser String ở ngoài, enum trong lõi, rồi `EnumMap` chứa handler.

## 7. Tình huống thực tế và cách chọn

### 7.1. API nhận trường `action` từ HTTP/JSON

Giả sử request có `{"action":"cancel"}`; quy trình phù hợp là kiểm tra JSON và kiểu trường, xác nhận action được phép, rồi **chuyển thành một lệnh nội bộ có kiểu** nếu đó là khái niệm nghiệp vụ đóng.

```text
HTTP/JSON action: "cancel"
        |
        v
Validate + normalize theo hợp đồng
        |
        v
Command.CANCEL
        |
        v
Service xử lý hủy với quyền truy cập và kiểm tra trạng thái thích hợp
```

Đừng lấy `rawAction` làm căn cứ duy nhất để cấp quyền: lệnh có tên hợp lệ **không đồng nghĩa người gọi được phép thực hiện**. Kiểm tra authentication, authorization và trạng thái nghiệp vụ tại đúng lớp. Nếu action không hợp lệ, trả lỗi đầu vào rõ ràng; nếu hợp lệ nhưng người gọi không được phép, xử lý theo quy tắc bảo mật của hệ thống.

### 7.2. Giao diện hiển thị nhãn từ mã trạng thái

Nếu bài toán chỉ là `"OPEN" → "Đang mở"`, `"CLOSED" → "Đã đóng"` và có nhiều mục ngôn ngữ, **bảng tra cứu hoặc cơ chế localization** phù hợp hơn viết một switch lớn cho từng ngôn ngữ. Nếu mã trạng thái thuộc một domain đóng và xuất hiện khắp code, parse sang enum trước rồi tra cứu thông điệp bằng enum hoặc mã ổn định.

### 7.3. Công cụ có nhiều thao tác độc lập

Khi mỗi command có handler riêng, phụ thuộc và test riêng, **registry** như `Map<String, CommandHandler>` (với interface `CommandHandler` do ứng dụng định nghĩa) giúp quản lý tập handler. Registry có thể được tạo tại startup từ các thành phần đã tin cậy. Nếu không cần thêm/bớt động, đăng ký cố định bằng DI hoặc `Map.of` có thể đủ đơn giản; chỉ dùng registry mutable khi có nhu cầu thật.

### 7.4. State machine có một tập trạng thái biết trước

Trạng thái `DRAFT`, `PUBLISHED`, `ARCHIVED` thường thích hợp với `enum`. Logic chuyển trạng thái có thể dùng `switch(enum)` cùng quy tắc xác thực trước/sau chuyển. Nếu bảng chuyển trạng thái lớn, có thể dùng `EnumMap<State, Set<State>>` hoặc mô hình state machine rõ ràng. **Không được coi việc switch tới một nhánh là đã đảm bảo mọi transition đều hợp lệ**; kiểm tra điều kiện nghiệp vụ vẫn cần thực hiện.

## 8. Chuẩn hóa đầu vào: quyết định có chủ đích

Chuỗi do người dùng/API gửi đến khác với constant trong mã nguồn. Cần xác định rõ:

- **Có phân biệt hoa/thường?** `switch(String)` mặc định phân biệt. Nếu hợp đồng quy định không phân biệt, chuẩn hóa hoặc ánh xạ có kiểm soát. `toUpperCase(Locale.ROOT)` thích hợp cho các token không phụ thuộc ngôn ngữ tự nhiên, nhưng không thay thế việc xác thực bộ ký tự được phép.
- **Có bỏ khoảng trắng hay không?** `strip()` loại bỏ các code point được `Character.isWhitespace` nhận diện ở đầu/cuối; không tự hiểu mọi dạng ký tự vô hình. Với giao thức exact, khoảng trắng thừa có thể phải bị từ chối.
- **Alias nào được phép?** Ví dụ `NEW` và `CREATE` cùng ánh xạ tới `Command.CREATE`. Danh sách alias cần rõ, tránh kiểu “gần giống thì đoán” khi hành động có tác động lớn.
- **Giá trị thiếu/không hợp lệ xử lý thế nào?** Phân biệt `null`, chuỗi trắng, lệnh không hỗ trợ, lệnh hỗ trợ nhưng người dùng không được phép.
- **Mã bên ngoài có ổn định không?** Nếu API/DB đang lưu mã, tách mã giao thức khỏi tên enum để tránh refactor làm thay đổi wire format.

Không nên coi chuẩn hóa là lớp bảo mật: `toUpperCase` hoặc `strip` chỉ xử lý cách biểu diễn. Sau khi parse, chương trình vẫn cần kiểm soát quyền truy cập và tình trạng tài nguyên của hành động tương ứng.

### 8.1. `enum.valueOf` có thể dùng ở đâu?

Nếu một cấu hình do **chính ứng dụng kiểm soát** đảm bảo luôn đúng tên enum, `Command.valueOf(text)` có thể đủ gọn. Khi nhận chuỗi từ người dùng hoặc hợp đồng có alias/mã độc lập, parser tường minh dễ kiểm soát lỗi và giữ ổn định giao thức hơn.

### 8.2. Xử lý `null` trong switch/map

- `switch(String)` với selector `null` trên Java 17 thông thường ném `NullPointerException`. Ví dụ chính **không để null đi tới switch** vì `normalize` đã báo lỗi phù hợp.
- Với map, `Map.get(key)` có thể trả `null` khi không có key; với các implementation cho phép null value, trả `null` cũng có thể là giá trị được lưu. Thiết kế map handler nên tránh giá trị null và xác định cách phát hiện key thiếu. `Map.of` từ chối null ngay khi tạo.
- `switch(enum)` cũng cần input enum hợp lệ; nếu có khả năng null, xử lý trước hoặc dùng ràng buộc dữ liệu như `Objects.requireNonNull`.

## 9. Hiệu năng và khả năng bảo trì

**Đừng chọn chỉ theo Big-O trên giấy.** Với `switch(String)`, compiler thường sinh mã so khớp dựa trên hash và kiểm tra `equals` để xử lý cả khả năng va chạm hash. Với `HashMap`, lookup thông thường có chi phí trung bình gần hằng số; `EnumMap` tối ưu cho enum keys. Hiệu năng cuối cùng còn phụ thuộc JIT, kích thước bảng, phân phối dữ liệu, tạo chuỗi, handler và bộ nhớ. Với vài lệnh trong service, **network, I/O và logic nghiệp vụ** thường có tác động nhiều hơn mức chênh lệch giữa các cách dispatch.

Các câu hỏi bảo trì quan trọng hơn:

1. **Khi thêm một lệnh mới, cần sửa bao nhiêu nơi?** Nếu phải tìm chuỗi ở nhiều lớp, chuyển sang enum/domain model hoặc registry.
2. **Có bỏ sót handler nào được phát hiện sớm không?** `switch expression` trên enum giúp compiler báo thiếu nhánh; map cần test/check startup.
3. **Ai sở hữu key và hợp đồng đầu vào?** Token bên ngoài nên có định nghĩa ổn định, tài liệu và test.
4. **Có thể gây thực thi hành động ngoài ý muốn không?** Handler phải do ứng dụng đăng ký, được kiểm tra quyền trước khi thực hiện.
5. **Ai được thay registry?** Nếu thực sự mutable và đồng thời, cần đồng bộ và quy tắc kiểm soát thay đổi; nếu cố định, map không thể sửa là lựa chọn ít rủi ro hơn.
6. **Có cần nhiều lớp abstraction không?** Với ba nhánh ngắn, một switch rõ ràng thường đơn giản và dễ kiểm thử hơn một hệ thống plugin/phân giải handler cầu kỳ.

**Kiểm thử tối thiểu** nên bao phủ: mỗi key hợp lệ, alias, khác biệt hoa/thường nếu được phép, `null`, chuỗi rỗng, key không hỗ trợ, trường hợp chưa đăng ký handler, và hành động bị từ chối do không đủ quyền. Với enum switch, khi bổ sung hằng mới phải biên dịch lại và cập nhật hành vi. Với map handler, nên có test xác minh mọi key bắt buộc đều có handler.

## 10. Sai lầm thường gặp

**Nhầm 1 — Mọi dữ liệu dạng chuỗi đều dùng `switch(String)`.** Nếu các chuỗi chỉ là tên của một tập trạng thái nghiệp vụ đóng, chuyển sang enum giúp thể hiện điều đó trong hệ kiểu. Nếu câu hỏi chỉ là ánh xạ key-value, dùng map trực tiếp hơn.

**Nhầm 2 — `enum` không thể nhận input từ JSON/HTTP.** Có thể, nhưng cần bước parse/mapping theo hợp đồng. Không nên rải `Enum.valueOf` khắp code và để exception khó hiểu trôi về client.

**Nhầm 3 — Chuyển sang `Map` sẽ tự động an toàn/đầy đủ.** Map không biết những key nào bắt buộc. Thiếu key, key trùng, giá trị null, đăng ký sai handler hoặc sửa registry giữa các request đều cần quy tắc kiểm soát.

**Nhầm 4 — `Map.of` là cấu trúc có thể thêm handler bất cứ lúc nào.** Map tạo bằng `Map.of` không hỗ trợ thay đổi qua các phương thức mutate; nếu cần dynamic registration, dùng cấu trúc và vòng đời phù hợp.

**Nhầm 5 — `default` cứ âm thầm bỏ qua mọi lệnh không biết.** Lệnh lạ trong API quan trọng nên nhận lỗi có chủ đích; default fallback chỉ hợp lý khi nghiệp vụ quy định hành vi đó.

**Nhầm 6 — `switch` không cần xử lý `null`.** Trên Java 17, switch kiểu thông thường cần selector không null. Kiểm tra ngay tại biên dữ liệu mang lại lỗi dễ hiểu hơn.

**Nhầm 7 — Truyền `raw.toUpperCase()` là chuẩn hóa hoàn toàn an toàn.** Chuyển chữ hoa mặc định tùy locale và có thể tạo bất ngờ. Với mã giao thức không phụ thuộc ngôn ngữ, chọn `Locale.ROOT` khi phù hợp và vẫn xác thực bộ ký tự/alias theo hợp đồng.

**Nhầm 8 — Giá trị `enum.ordinal()` là mã lưu trữ bền vững.** Thứ tự enum có thể đổi khi chèn/sắp lại hằng; nếu cần mã bền vững, dùng field `code` được định nghĩa rõ.

**Nhầm 9 — Chọn kiến trúc dựa vào một microbenchmark không đại diện.** Hãy ưu tiên biểu đạt mô hình và độ tin cậy; chỉ tối ưu khi dữ liệu đo trên ứng dụng thật chỉ ra bottleneck.

## 11. Bài tập tự đánh giá

**Câu 1.** Một parser CLI nhận đúng ba từ khóa cố định `start`, `stop`, `status` và chỉ cần trả về một thông báo ngắn. Chọn gì? — `switch(String)` là lựa chọn hợp lý nếu logic nhỏ, phân biệt đầu vào và nhánh lỗi rõ ràng. Nếu ba lệnh trở thành khái niệm được dùng trong nhiều tầng, chuyển String sang enum ở biên.

**Câu 2.** Hệ thống có ba trạng thái đơn hàng `NEW`, `PAID`, `CANCELLED`; nhiều service cần xử lý dựa trên trạng thái. Chọn gì? — `enum OrderState` và switch enum (hoặc state-machine phù hợp) giúp định nghĩa tập trạng thái nhất quán; vẫn phải kiểm tra transition và quyền truy cập.

**Câu 3.** Một ứng dụng cần ánh xạ 300 mã lỗi sang thông điệp mô tả có thể thay theo cấu hình. Chọn gì? — Bảng `Map`/cấu hình có xác thực và versioning phù hợp hơn switch 300 nhánh hoặc enum gắn cứng toàn bộ thông điệp.

**Câu 4.** Code dùng `Command.valueOf("create")` trong khi hằng là `CREATE`. Kết quả? — `IllegalArgumentException`. Nếu hợp đồng cho phép không phân biệt chữ hoa, chuẩn hóa rồi parse có kiểm soát.

**Câu 5.** Một registry `Map<String,Handler>` không có khóa `"CANCEL"` nhưng API vẫn chấp nhận lệnh đó. Ai phát hiện? — Compiler không tự kiểm tra đủ key; cần kiểm tra cấu hình khi khởi động hoặc test kiểm tra tính đầy đủ.

**Câu 6.** Có nên đưa mọi chuỗi HTTP action vào `Class.forName(action)` để tạo handler động? — Không. Input từ bên ngoài phải được đối chiếu với tập khóa và handler do ứng dụng cho phép, và kiểm tra quyền trước khi thực thi.

**Câu 7.** Có nên dùng `EnumMap` khi key đã là enum và cần tra nhãn hiển thị không? — Có, đó là lựa chọn phù hợp; cần quản lý các giá trị thiếu, quốc tế hóa nếu có và quy tắc mutable.

## 12. Tài liệu chuẩn để kiểm chứng

- [Oracle Java 17 — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/17/language/switch-expressions-and-statements.html): sự khác nhau giữa switch statement, switch expression và yêu cầu bao phủ nhánh.
- [dev.java — Branching with Switch Expressions](https://dev.java/learn/branching-with-switch-expressions/): ví dụ switch expression với enum, nhánh default và fall-through.
- [Java SE 17 API — Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html): `Map.of`, `Map.ofEntries`, `Map.copyOf` và hợp đồng null/duplicate.
- [Java SE 17 API — EnumMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/EnumMap.html): bảng tra cứu có khóa enum.
- [Java SE 17 API — Enum](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Enum.html): `name()`, `ordinal()` và `valueOf`.
- [Java SE 17 API — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `strip()`, `toUpperCase(Locale)` và thao tác trên chuỗi.

**Ghi nhớ:** `String` là **dữ liệu văn bản tại biên**, `enum` là **tập lựa chọn có kiểu trong mô hình nghiệp vụ**, còn `Map` là **quan hệ tra cứu từ key đến giá trị/hành động**. Chọn cấu trúc dựa trên bản chất bài toán, số nơi sử dụng, khả năng mở rộng và cách phát hiện lỗi; bảo đảm xử lý `null`, lệnh không hỗ trợ và quyền truy cập một cách tường minh.