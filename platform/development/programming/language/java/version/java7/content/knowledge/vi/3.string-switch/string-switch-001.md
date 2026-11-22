# Điều phối theo giá trị chuỗi bằng `switch(String)` trong Java

**Chủ đề:** Java 7 — `switch với String`  
**Bài học:** Điều phối theo giá trị chuỗi

Trong ứng dụng, ta thường nhận một **giá trị chuỗi** rồi quyết định hành động tương ứng: `"start"` để khởi chạy, `"pause"` để tạm dừng, `"stop"` để dừng, hoặc một tên thao tác từ dòng lệnh, message hay yêu cầu API. **Điều phối theo chuỗi** là bước chuyển giá trị đầu vào thành **một nhánh xử lý có hợp đồng rõ ràng**.

Từ Java 7, `switch` nhận trực tiếp một biểu thức kiểu `String`. Tính năng này **vẫn được hỗ trợ trong các JDK hiện đại**; đồng thời cú pháp `switch expression` mới hơn giúp việc trả về kết quả gọn và tránh lỗi rơi qua nhánh. Bài học sử dụng ví dụ chạy trên **JDK 17+**, phân biệt phần có từ Java 7 với phần được bổ sung sau này và chỉ giữ các cách dùng còn phù hợp.

## 1. Khi nào cần điều phối dựa trên chuỗi?

Hãy xét một hệ thống có tập lệnh hữu hạn:

| Đầu vào | Ý nghĩa | Kết quả điều phối |
| --- | --- | --- |
| `start` hoặc `run` | Bắt đầu xử lý | `RUNNING` |
| `pause` | Tạm dừng | `PAUSED` |
| `stop` | Kết thúc | `STOPPED` |
| Giá trị không hỗ trợ | Không có lệnh tương ứng | Trả lỗi hoặc trạng thái `UNKNOWN` |
| `null` / chuỗi rỗng | Không có lệnh hợp lệ | Từ chối đầu vào theo hợp đồng |

Cốt lõi không phải là lệnh cụ thể mà là quy tắc: **mỗi giá trị được chấp nhận ánh xạ tới một hành vi xác định**. Phần điều phối nên độc lập với thao tác gây tác dụng phụ (ghi cơ sở dữ liệu, gọi mạng, xóa tệp...) để có thể kiểm thử mà không thực hiện các thao tác đó.

Ví dụ dùng `switch(String)` thích hợp cho **tập hằng số nhỏ và ổn định**: một vài trạng thái, loại sự kiện, lệnh CLI hoặc tên chế độ. Khi điều kiện liên quan tới phạm vi giá trị, tiền tố, quy tắc ghép mẫu, biểu thức chính quy, hoặc tập lệnh cấu hình động, cần cân nhắc công cụ khác; `switch` không thay thế mọi loại kiểm tra chuỗi.

## 2. `switch(String)` hoạt động như thế nào?

### 2.1. Cú pháp của `switch` statement

`switch` đánh giá biểu thức chọn nhánh **một lần**, rồi tìm một `case` có giá trị tương ứng. Từ Java 7, biểu thức đó có thể là `String`. Cú pháp dạng statement vẫn hợp lệ trên JDK 17+:

```java
switch (command) {
    case "start":
    case "run":
        result = "RUNNING";
        break;
    case "pause":
        result = "PAUSED";
        break;
    case "stop":
        result = "STOPPED";
        break;
    default:
        result = "UNKNOWN";
        break;
}
```

Đây là **đoạn minh họa**, giả sử `command` và `result` đã được khai báo. Hai nhãn `"start"` và `"run"` cùng đi vào một khối xử lý: không có lệnh ở giữa nên chúng biểu thị **hai bí danh cùng hành vi**.

**Phân biệt ba phần dễ nhầm:**

- `case "start":` chỉ **điểm vào** của một nhánh; tự nó không buộc chương trình thoát khỏi `switch`.
- `break;` thoát khỏi `switch` dạng statement. Nếu thiếu, việc chạy có thể tiếp tục vào nhánh phía dưới (**fall-through**), dù giá trị không khớp nhánh sau. Chỉ dùng fall-through khi chủ ý nhóm nhánh hoặc đã giải thích rõ.
- `default:` xử lý giá trị không khớp nhãn nào. Không bắt buộc theo cú pháp, nhưng thường cần trong điều phối đầu vào để tránh trả kết quả không xác định hoặc sử dụng trạng thái cũ.

Nếu mỗi nhánh có thể `return` ngay từ phương thức thì không cần `break` vì `return` đã kết thúc phương thức. Với logic có kết quả trả về, đây là một cách giảm nguy cơ quên `break`.

### 2.2. So khớp bằng **giá trị**, không dựa trên tham chiếu

Java so khớp nội dung chuỗi của `switch(String)` theo ngữ nghĩa tương đương `String.equals`, nên hai đối tượng `String` khác nhau nhưng chứa cùng nội dung vẫn chọn cùng nhánh. **Không cần và không nên phụ thuộc vào string interning hay dùng `==` để quyết định nhánh**.

Các điểm cần nhớ:

1. So khớp là **chính xác và phân biệt chữ hoa/chữ thường**: `"START"` khác `"start"`; `" start "` cũng khác `"start"`.
2. Nhãn `case` phải là **hằng chuỗi tại thời điểm biên dịch** (string literal hoặc biểu thức hằng kiểu `String` hợp lệ). Không thể viết `case someVariable:` nếu biến đó chỉ nhận giá trị ở runtime.
3. Các nhãn trùng nội dung trong cùng `switch` là lỗi biên dịch. Thứ tự viết nhánh không phải là một cơ chế ưu tiên như thứ tự điều kiện `if/else if`.
4. `switch` trên chuỗi **không hỗ trợ tự động** so khớp chứa từ khóa, so khớp tiền tố, regex, chuyển chữ hoa/thường hay bỏ khoảng trắng.
5. Nếu biểu thức chọn nhánh là `null`, `switch(String)` kiểu truyền thống gây `NullPointerException`. Hãy kiểm tra `null` trước khi điều phối, trừ khi đang chủ đích dùng cú pháp xử lý `null` được hỗ trợ ở phiên bản Java mới hơn.

Cách trình biên dịch tối ưu có thể dùng mã băm `hashCode()` và kiểm tra bằng `equals()`; đó là **chi tiết triển khai**, không phải hợp đồng để lập trình viên dựa vào. Hai chuỗi cùng hash vẫn phải được phân biệt bằng nội dung, như ví dụ kiểm chứng ở phần 6.

## 3. Ví dụ thực tế: điều phối một bộ lệnh

Tạo tệp `CommandRouterDemo.java`:

```java
import java.util.Locale;

public class CommandRouterDemo {
    public static String dispatch(String rawCommand) {
        if (rawCommand == null) {
            return "ERROR: missing command";
        }

        String command = rawCommand.strip()
                .toLowerCase(Locale.ROOT);

        if (command.isEmpty()) {
            return "ERROR: empty command";
        }

        switch (command) {
            case "start":
            case "run":
                return "RUNNING";
            case "pause":
                return "PAUSED";
            case "stop":
                return "STOPPED";
            default:
                return "ERROR: unknown command";
        }
    }

    public static void main(String[] args) {
        System.out.println(dispatch(" RUN "));
        System.out.println(dispatch("pause"));
        System.out.println(dispatch("Stop"));
        System.out.println(dispatch("delete"));
        System.out.println(dispatch(" "));
        System.out.println(dispatch(null));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 CommandRouterDemo.java
java CommandRouterDemo
```

**Kết quả chính xác:**

```text
RUNNING
PAUSED
STOPPED
ERROR: unknown command
ERROR: empty command
ERROR: missing command
```

Đường đi của một lệnh được xác định tường minh:

1. **Kiểm tra thiếu dữ liệu:** nếu `rawCommand == null`, trả thông báo lỗi trước khi gọi phương thức trên chuỗi. Đây là cách giữ hợp đồng không gây `NullPointerException` ngoài dự kiến.
2. **Chuẩn hóa có chủ đích:** `strip()` bỏ khoảng trắng đầu/cuối theo định nghĩa whitespace của Java; `toLowerCase(Locale.ROOT)` giúp tên lệnh máy không phụ thuộc locale mặc định của máy chủ.
3. **Kiểm tra chuỗi rỗng sau chuẩn hóa:** `" "` không được coi là một lệnh hợp lệ.
4. **Điều phối:** `"start"` và `"run"` trả cùng kết quả `"RUNNING"`, ba lệnh hợp lệ có kết quả xác định.
5. **Từ chối giá trị lạ:** `"delete"` không khớp nên đi vào `default`. Nó **không vô tình trở thành một lệnh khác**.

**Phiên bản API:** cú pháp `switch(String)` là tính năng từ **Java 7**. Phương thức `String.strip()` có từ **Java 11**, được chọn vì đây là cách xử lý khoảng trắng thường phù hợp hơn trên JDK hiện đại. Nếu đang phải biên dịch bằng JDK 7 thật sự, cần thay `strip()` bằng API có sẵn của phiên bản đó theo hợp đồng đầu vào; bài học này chủ đích ưu tiên môi trường Java hiện hành.

Một quy tắc thiết kế quan trọng: việc coi `" START "` là `"start"` là **quyết định của ứng dụng**, không phải tính năng tự động của `switch`. Với mã định danh, khóa truy cập, giá trị đã ký, mã điều khiển có phân biệt chữ hoa/thường, hoặc input đòi hỏi so khớp chính xác, không tự ý bỏ khoảng trắng hay đổi chữ vì như vậy làm thay đổi ý nghĩa dữ liệu.

## 4. Hai kiểu viết `switch` còn hữu ích trên Java hiện đại

### 4.1. Statement: phù hợp điều phối nhiều lệnh

Kiểu `switch (value) { case "...": ... }` được trình bày ở trên là **statement**. Nếu một nhánh thực hiện thao tác, có thể tổ chức mã như:

```java
switch (command) {
    case "start":
        startJob();
        break;
    case "stop":
        stopJob();
        break;
    default:
        reportUnknown(command);
        break;
}
```

Đây là **mã minh họa**, các phương thức `startJob`, `stopJob` và `reportUnknown` cần được định nghĩa trong ứng dụng thật. Mục đích là cho thấy mỗi nhánh thực hiện một hành động rõ ràng. Đặt `break` để tránh rơi xuống nhánh tiếp theo.

### 4.2. `switch expression`: phù hợp ánh xạ giá trị thành kết quả

Java hiện đại có **switch expression** (chuẩn hóa từ Java 14) dùng `->` và trả về giá trị. Cú pháp này giúp giảm boilerplate, không có fall-through ngầm giữa các nhánh dùng mũi tên và thường dễ kiểm tra khi chỉ ánh xạ chuỗi sang một kết quả.

Tạo tệp `ModernSwitchDemo.java`:

```java
import java.util.Locale;

public class ModernSwitchDemo {
    static int priority(String raw) {
        if (raw == null) {
            return -1;
        }

        return switch (raw.strip().toLowerCase(Locale.ROOT)) {
            case "low" -> 1;
            case "normal", "medium" -> 2;
            case "high" -> 3;
            default -> -1;
        };
    }

    public static void main(String[] args) {
        System.out.println(priority(" LOW "));
        System.out.println(priority("medium"));
        System.out.println(priority("HIGH"));
        System.out.println(priority("urgent"));
        System.out.println(priority(null));
    }
}
```

```bash
javac -encoding UTF-8 ModernSwitchDemo.java
java ModernSwitchDemo
```

```text
1
2
3
-1
-1
```

Đây là code **Java 17+**, không phải cú pháp chạy được trên Java 7. Ý tưởng điều phối vẫn giống nhau: chọn nhánh theo **nội dung String**. Hai nhãn của cùng một nhánh được ngăn cách bằng dấu phẩy (`case "normal", "medium"`), dễ đọc hơn dạng hai `case` liên tiếp.

Vì đây là **expression** phải tạo ra giá trị, Java kiểm tra tính đầy đủ của các nhánh. Với tập giá trị `String` không đóng, `default` là cách thông thường để cung cấp giá trị cho trường hợp không khớp. Nếu thân nhánh dài, có thể dùng khối `{ ... yield result; }` để trả giá trị từ nhánh; không dùng `break value` của cú pháp cũ để thay thế `yield`.

**Lựa chọn:** dùng kiểu cũ khi duy trì mã có sẵn hoặc khi logic tác động trực tiếp đến một số hành động; ưu tiên `switch expression` khi đang viết mới trên JDK 17+ và nhiệm vụ thực sự là ánh xạ đầu vào thành một kết quả. Cả hai đều là lựa chọn được hỗ trợ.

## 5. Định nghĩa hợp đồng chuẩn hóa chuỗi trước khi điều phối

`switch` chỉ quyết định nhánh; **bước chuẩn hóa quyết định dữ liệu nào được xem là tương đương**. Hãy ghi rõ chính sách trong API thay vì rải lời gọi `trim`/`strip`/`toLowerCase` tùy chỗ.

### 5.1. Phân biệt ba chính sách thường gặp

| Chính sách | Cách xử lý | Tình huống phù hợp |
| --- | --- | --- |
| **Khớp chính xác** | Giữ nguyên chuỗi và `switch (raw)` sau kiểm tra `null` | Giao thức, identifier, mã lệnh có phân biệt hoa/thường hoặc dữ liệu đã ký. |
| **Bỏ khoảng trắng ở biên** | `raw.strip()` | Đầu vào người dùng cho phép gõ thừa khoảng trắng. |
| **Không phân biệt hoa/thường theo quy ước lệnh** | `raw.strip().toLowerCase(Locale.ROOT)` | Tên lệnh/keyword có tập giá trị do ứng dụng định nghĩa. |

**Không có một chính sách chuẩn hóa đúng cho mọi trường hợp.** Với giao thức mà `"Start"` khác `"start"`, việc đổi chữ làm sai yêu cầu. Với input từ người dùng mà hệ thống chấp nhận cả `"RUN"` và `"run"`, xử lý thống nhất trước khi `switch` giúp tránh phải liệt kê mọi biến thể.

### 5.2. Locale, Unicode và so khớp văn bản

- `toLowerCase()` **không truyền locale** dựa vào locale mặc định của runtime. Với **lệnh kỹ thuật có quy ước ổn định**, dùng `toLowerCase(Locale.ROOT)` để giảm phụ thuộc môi trường. Với ngôn ngữ tự nhiên hoặc tên riêng, xử lý hoa/thường có thể cần locale cụ thể và quy tắc nghiệp vụ.
- `strip()` có từ Java 11, dựa trên định nghĩa ký tự trắng của Java; nó không tương đương việc xóa **mọi ký tự Unicode trông giống khoảng trắng**. Nếu input yêu cầu quy tắc Unicode rất cụ thể, cần xác định và kiểm thử danh sách ký tự được chấp nhận.
- Hai chuỗi nhìn giống nhau có thể có các dạng mã hóa Unicode khác nhau, chẳng hạn ký tự có dấu dựng sẵn và ký tự nền + dấu kết hợp. `String.equals` và `switch(String)` **không tự chuẩn hóa Unicode**. Khi nghiệp vụ cho phép, có thể chuẩn hóa bằng `java.text.Normalizer` trước khi so sánh; nhưng không được thay đổi identifier hay dữ liệu bảo mật một cách tự động.
- `equalsIgnoreCase` hữu ích trong điều kiện `if` đơn lẻ, nhưng `switch` không có chế độ `case-insensitive`. Khi thiết kế cả bộ điều phối, hãy chuẩn hóa một lần theo chính sách đã chọn và so sánh các nhãn được viết ở cùng dạng.

**Giới hạn đầu vào:** nếu chuỗi đến từ request, file hay message không tin cậy, hãy kiểm tra null, độ dài, tập ký tự được phép và danh sách lệnh hợp lệ **trước khi** thực hiện hành động. `default` phải có chính sách từ chối hoặc báo lỗi, không âm thầm chọn thao tác có tác dụng phụ.

## 6. Những lỗi dễ gặp và cách kiểm chứng

### 6.1. Dùng `==` để so sánh chuỗi

`==` trên đối tượng kiểm tra tham chiếu, không phải hợp đồng so nội dung. `switch(String)` chọn nhánh theo **giá trị nội dung**, kể cả chuỗi được tạo tại runtime; không cần ép dùng `intern()`.

### 6.2. Lo ngại hai chuỗi trùng mã băm sẽ chọn nhầm nhánh

Một số chuỗi có cùng `hashCode()` nhưng khác nội dung. Điều phối bằng `switch(String)` vẫn phân biệt đúng; bộ biên dịch bảo đảm **ngữ nghĩa so khớp chuỗi**, bất kể cách hiện thực. Ta có thể kiểm chứng trực tiếp bằng hai chuỗi `"FB"` và `"Ea"`, là một cặp có hash Java trùng nhau.

Tạo tệp `CollisionDemo.java`:

```java
public class CollisionDemo {
    static String dispatch(String input) {
        if (input == null) {
            return "NONE";
        }

        switch (input) {
            case "FB":
                return "BRANCH_FB";
            case "Ea":
                return "BRANCH_EA";
            default:
                return "OTHER";
        }
    }

    public static void main(String[] args) {
        System.out.println("FB".hashCode() == "Ea".hashCode());
        System.out.println(dispatch(new String("FB")));
        System.out.println(dispatch(new String("Ea")));
    }
}
```

```bash
javac -encoding UTF-8 CollisionDemo.java
java CollisionDemo
```

```text
true
BRANCH_FB
BRANCH_EA
```

Chương trình cho thấy việc trùng hash **không gây trùng nhánh**, và `new String("FB")` vẫn được điều phối như literal có cùng nội dung. Ví dụ chỉ phục vụ kiểm chứng ngữ nghĩa; ứng dụng không cần chủ động tạo `new String(...)` mỗi lần xử lý lệnh.

### 6.3. Quên `break` hoặc xử lý `null`

Với `switch` statement dùng dấu hai chấm, thiếu `break` là nguyên nhân lỗi rất thực tế khi có các thao tác khác nhau. Chỉ nhóm nhánh khi chủ ý; dùng `return` khi phương thức trả kết quả, hoặc `->` trên JDK mới để tránh fall-through.

Kiểm tra `null` trước khi dùng `switch(String)` truyền thống. Java 21 có khả năng xử lý `case null` trong các dạng `switch` được tăng cường, nhưng cú pháp đó **không tương thích với Java 17 thông thường**; dùng tiền kiểm `null` là cách dễ mang đi giữa các phiên bản.

### 6.4. Tin rằng `case` hỗ trợ biến hoặc điều kiện động

Đoạn sau là **ý tưởng không hợp lệ trong `switch(String)`**:

```java
// Không biên dịch nếu allowedCommand chỉ được xác định lúc runtime.
// case allowedCommand: ...
// case command.startsWith("start"): ...
```

Đây là **minh họa cú pháp sai dưới dạng comment**. Nhãn `case` cho `String` phải là hằng theo quy tắc ngôn ngữ, không phải kết quả của một phép kiểm tra động. Khi cần điều kiện như `startsWith` hoặc `matches`, dùng `if/else if` hoặc bộ phân tích input chuyên dụng trước khi điều phối.

### 6.5. Cho `default` gọi nhầm hành động nguy hiểm

`default` nghĩa là **không khớp lệnh nào**, không có nghĩa “thao tác mặc định luôn an toàn”. Ví dụ lệnh không biết không nên tự chuyển thành `"delete"`, `"approve"` hay một quyền truy cập cao hơn. Hãy biểu diễn kết quả không hợp lệ rõ ràng: trả kiểu `UNKNOWN`, `Optional.empty()` hoặc ném exception phù hợp với API và để tầng gọi quyết định phản hồi.

## 7. Thiết kế bộ điều phối dễ mở rộng và kiểm thử

Một bộ điều phối tốt có thể tách thành ba bước:

1. **Parse/validate:** nhận chuỗi và quyết định có hợp lệ không; áp dụng đúng chính sách khoảng trắng/chữ hoa-thường.
2. **Route:** ánh xạ giá trị hợp lệ đến loại lệnh hoặc hành động. Đây là phần `switch` thực hiện rõ nhất.
3. **Execute:** thực hiện hành động nghiệp vụ, kiểm tra quyền và xử lý ngoại lệ ở đúng tầng.

Ví dụ: API nhận tên thao tác `"download"`. Bộ điều phối có thể trả mã lệnh `DOWNLOAD` nhưng **quyền tải dữ liệu vẫn phải kiểm tra ở bước thực thi**. Việc input khớp một `case` không chứng minh caller được phép chạy lệnh đó. Đừng trộn logic phân quyền vào thao tác chuẩn hóa chữ hoặc dùng nhãn nhánh làm cơ chế bảo vệ duy nhất.

### 7.1. Chọn `switch`, `if/else`, `enum` hay `Map`

| Công cụ | Nên dùng khi | Cẩn thận |
| --- | --- | --- |
| `switch(String)` | Tập lệnh hằng, ít nhánh, mỗi nhánh có hành vi rõ | Null, case-sensitive, `default`, fall-through của statement |
| `switch expression` | Viết mới trên JDK 17+; ánh xạ chuỗi thành kết quả có kiểu | Phải cung cấp giá trị cho trường hợp không khớp |
| `if/else if` | Điều kiện động, tiền tố, khoảng giá trị hoặc cần các phép kiểm tra khác | Thứ tự điều kiện quan trọng; tránh biểu thức chồng lấn khó hiểu |
| `enum` | Tập trạng thái/nghiệp vụ cố định và được dùng nhiều chỗ trong mã | Parse chuỗi bên ngoài một lần, không để chuỗi tùy ý len vào lõi domain |
| `Map<String, Handler>` | Có nhiều handler độc lập, cần tra cứu/đăng ký động | Quản lý handler thiếu, side effects, vòng đời và quyền truy cập rõ ràng |

Nếu ứng dụng chỉ có 3–8 lệnh rõ ràng, `switch` thường dễ hiểu nhất. Nếu danh sách lên hàng trăm lệnh và mỗi lệnh có handler riêng, có thể chuyển phần dispatch sang bảng đăng ký có kiểm soát. Nếu logic thay đổi theo tiền tố hoặc biểu thức chính quy, hãy phân tích cú pháp trước rồi điều phối **kết quả parse** thay vì dùng nhiều nhánh `switch` không phù hợp.

### 7.2. Định nghĩa giá trị trả về và lỗi thống nhất

Tránh trả về nhiều chuỗi “gần giống” như `"Unknown"`, `"UNKNOWN"`, `"Invalid command"` mà caller phải suy đoán. Trong ứng dụng lớn, cân nhắc kiểu kết quả như `enum CommandType`, `record DispatchResult` (Java 16+) hoặc loại lỗi riêng. Khi input là chuỗi từ bên ngoài, không lưu toàn bộ dữ liệu nhạy cảm vào log lỗi; log nên phản ánh loại lỗi và metadata cần thiết.

Nếu phương thức chỉ **phân loại lệnh**, không nên gọi mạng/xóa dữ liệu ngay trong `switch`: kiểm thử bộ phân loại có thể xác minh đầu ra độc lập. Khi lệnh có tác dụng phụ, đặt handler ở bước sau và kiểm soát xử lý lỗi theo nghiệp vụ.

## 8. Kiểm thử các nhánh quan trọng

Một bộ điều phối chuỗi cần được kiểm tra theo **các lớp đầu vào** thay vì chỉ chạy thử trường hợp đúng:

| Trường hợp kiểm thử | Dữ liệu ví dụ | Điều phải xác nhận |
| --- | --- | --- |
| Nhánh hợp lệ | `"start"` | Đúng kết quả `RUNNING` |
| Bí danh | `"run"` | Chung kết quả với `"start"` |
| Khác chữ hoa/thường nếu được cho phép | `"Stop"` | Chuẩn hóa và chọn đúng nhánh |
| Khoảng trắng biên nếu được cho phép | `" RUN "` | Không thành `UNKNOWN` |
| Không hợp lệ | `"delete"` | Từ chối, không chạy tác vụ khác |
| Chuỗi rỗng/blank | `""`, `" "` | Trả đúng lỗi đầu vào |
| Giá trị `null` | `null` | Không phát sinh `NullPointerException` ngoài hợp đồng |
| Chuỗi mới có cùng nội dung | `new String("stop")` | Chọn cùng nhánh như literal |
| Chuỗi khác nhưng trùng hash | `"FB"` và `"Ea"` | Không bị chọn sai nhánh |
| Unicode/locale (nếu có trong hợp đồng) | Giá trị có dấu hoặc ký tự đặc biệt | Chuẩn hóa đúng chính sách, không dựa locale máy |

Nên kiểm thử cả kết quả và **tác dụng phụ**: lệnh lạ không gọi handler, caller không có quyền bị từ chối dù tên lệnh hợp lệ, và dữ liệu không được xử lý nhiều lần vì fall-through. Với `switch expression`, kiểm thử nhánh `default` vẫn cần thiết vì lập trình viên có thể định nghĩa chính sách trả lỗi sai.

## 9. Bài thực hành

**Bài 1 — Bộ điều phối chế độ đọc:** viết `static String mode(String raw)` nhận `"view"`, `"read"`, `"edit"` và trả `"READ_ONLY"` hoặc `"READ_WRITE"`. Hỗ trợ bí danh `"view"`/`"read"`, chuẩn hóa theo chính sách đã công bố, trả lỗi cho `null`, rỗng và lệnh khác. Cài đặt bằng `switch(String)` statement và dùng `return` tại mỗi nhánh.

**Bài 2 — Chuyển sang switch expression:** viết lại bài 1 trên JDK 17+, dùng `case "view", "read" ->`. So sánh số vị trí cần `break` và tính rõ ràng của nhánh `default`; xác nhận cùng kết quả trên toàn bộ bộ test.

**Bài 3 — Tránh side effects:** thêm handler giả (ví dụ một biến đếm số lần gọi) và bảo đảm chỉ lệnh hợp lệ làm biến đếm tăng. Trường hợp `null` hoặc lệnh lạ phải không gọi bất kỳ handler nào.

**Bài 4 — Chính sách chuẩn hóa:** viết hai phiên bản: một bộ điều phối khớp chính xác, một bộ cho phép `strip` và `Locale.ROOT`. Thử `"RUN"`, `" run "` và `"run"`; giải thích vì sao ba chuỗi là khác nhau với so khớp chính xác nhưng có thể thành cùng lệnh theo chính sách thứ hai. Không tự mở rộng chuẩn hóa sang khóa bảo mật hoặc dữ liệu đã ký.

**Bài 5 — Mã băm trùng nhau:** chạy `CollisionDemo` và giải thích tại sao `"FB"` và `"Ea"` cùng hash mà vẫn vào hai nhánh khác nhau. Nêu điểm khác giữa `switch(String)` và so sánh bằng `==`.

## 10. Ghi nhớ

- **Java 7** cho phép `switch` nhận `String`, tính năng này vẫn còn giá trị và được hỗ trợ hiện nay.
- `case` so khớp **nội dung String chính xác**, phân biệt hoa/thường, và dùng nhãn hằng ở thời điểm biên dịch. Không tự chuẩn hóa input.
- **Kiểm tra `null`, chuỗi rỗng, lệnh ngoài tập cho phép** trước khi thực hiện hành động. Thiết kế `default` có chủ đích.
- Khi dùng dạng statement với dấu hai chấm, hiểu **fall-through** và kết thúc nhánh đúng bằng `break`/`return`. Với JDK 17+, `switch expression` dùng `->` thường phù hợp cho ánh xạ giá trị.
- **Tách parse → route → execute** để bộ điều phối dễ kiểm thử, dễ mở rộng và không đánh đồng tên lệnh hợp lệ với quyền thực thi.
- Chọn `switch` khi **tập giá trị hữu hạn, rõ ràng**; chọn `if`/parser hoặc `Map`/`enum` nếu bản chất điều phối đòi hỏi điều kiện hay kiến trúc khác.
