# Java 7 — Nhóm nhãn, `break` và kiểm soát rơi qua nhánh trong `switch` với `String`

## Mục tiêu bài học

Từ Java 7, `switch` có thể phân nhánh theo `String`. Cú pháp `switch` dạng dấu hai chấm (`case ...:`) **vẫn hợp lệ trên Java hiện đại**, nhưng có một đặc điểm rất quan trọng: sau khi khớp một nhãn `case`, luồng thực thi tiếp tục chạy những câu lệnh ở phía dưới **cho đến khi gặp `break`, `return`, `throw` hoặc kết thúc `switch`**, kể cả khi đi qua nhãn của `case` khác. Hiện tượng này gọi là **fall-through** (rơi qua nhánh).

Bài học tập trung vào ba kỹ năng đi cùng nhau:

1. **Nhóm nhãn:** cho nhiều giá trị `String` cùng chạy một khối lệnh mà không lặp code.
2. **Đặt `break` đúng chỗ:** kết thúc nhánh sau khi đã xử lý, tránh vô tình chạy thêm nhánh bên dưới.
3. **Kiểm soát fall-through:** nhận diện khi nào rơi qua nhánh là lỗi, khi nào được chủ ý và cách chọn cú pháp hiện đại an toàn hơn.

Các ví dụ được kiểm chứng với cú pháp Java 17+, gồm cả dạng `switch` truyền thống đã có từ Java 7 và dạng mũi tên (`->`) được hỗ trợ ổn định trên JDK hiện đại. Các kiến thức đều đang được áp dụng; không cần dùng JDK cũ hoặc API đã lỗi thời.

## 1. `switch` với `String` hoạt động như thế nào?

Xét cú pháp cơ bản:

```java
switch (command) {
    case "START":
        // Thực hiện khi command là "START".
        break;
    case "STOP":
        // Thực hiện khi command là "STOP".
        break;
    default:
        // Thực hiện nếu không nhãn nào khớp.
}
```

Đây là **đoạn cú pháp minh họa**, không phải một lớp chạy độc lập. Khi `command` là một chuỗi khác `null`, `switch` so sánh chuỗi đó với các giá trị nhãn; nhãn khớp xác định **vị trí bắt đầu thực thi**.

Các quy tắc cần nắm:

- Các nhãn `case "START":`, `case "STOP":` là các **giá trị `String` hằng tại thời điểm biên dịch**. Không dùng một biến thay đổi ở runtime làm nhãn `case`; các nhãn trùng nhau cũng không hợp lệ.
- So khớp có phân biệt chữ hoa/chữ thường: `"START"` khác `"start"`, khoảng trắng cũng là một phần dữ liệu.
- Với cú pháp `switch` dùng `String` như trong bài, cần xử lý đầu vào `null` **trước `switch`**; nếu không, chương trình có thể ném `NullPointerException` và không tự chạy vào `default`.
- `default` chỉ chọn nhánh khi không có `case` nào khớp. `default` **không phải** cơ chế xử lý `null` cho các ví dụ dạng truyền thống ở đây.
- Trong cú pháp dấu hai chấm, nhãn `case` **không tự ngắt** luồng thực thi. Sau khi vào một nhánh, cần chủ động kiểm soát điểm dừng.
- `break;` kết thúc `switch` gần nhất mà nó thuộc về (khi không có nhãn `break` chỉ định đích); những câu lệnh **sau toàn bộ `switch`** vẫn có thể tiếp tục chạy.

Một cách đọc đúng là: **giá trị chuỗi chọn điểm bắt đầu; `break`/`return`/`throw` quyết định điểm kết thúc**, chứ mỗi nhãn `case` không tự tạo một khối độc lập.

## 2. Nhóm nhiều nhãn bằng các `case` liên tiếp

Giả sử một công cụ nhỏ chia các HTTP method dạng chuỗi thành nhóm. Cả `GET` và `HEAD` thuộc nhóm đọc; `POST` và `PUT` thuộc nhóm ghi. Ở cú pháp `switch` dấu hai chấm, cách nhóm đơn giản là **để các nhãn đứng liên tiếp và không có câu lệnh thực thi giữa chúng**:

```java
case "GET":
case "HEAD":
    result = "READ";
    break;
```

Đoạn trên là **một nhánh bên trong `switch`**, không phải chương trình độc lập. Nếu `method` là `"GET"`, luồng chạy từ nhãn `GET` xuống `HEAD` rồi thực hiện `result = "READ";`. Nếu là `"HEAD"`, nó bắt đầu tại nhãn `HEAD` và thực hiện cùng lệnh. Trong cả hai trường hợp, `break` đưa luồng ra khỏi `switch`. Không có lệnh nào bị chạy thừa giữa hai nhãn.

### Chương trình đầy đủ: `GroupingBreakDemo.java`

```java
public final class GroupingBreakDemo {
    private static String category(String method) {
        if (method == null) {
            return "INVALID";
        }

        String result;
        switch (method) {
            case "GET":
            case "HEAD":
                result = "READ";
                break;

            case "POST":
            case "PUT":
                result = "WRITE";
                break;

            case "DELETE":
                result = "DELETE";
                break;

            default:
                result = "UNKNOWN";
        }
        return result;
    }

    public static void main(String[] args) {
        System.out.println("GET -> " + category("GET"));
        System.out.println("HEAD -> " + category("HEAD"));
        System.out.println("PUT -> " + category("PUT"));
        System.out.println("DELETE -> " + category("DELETE"));
        System.out.println("PATCH -> " + category("PATCH"));
        System.out.println("get -> " + category("get"));
        System.out.println("null -> " + category(null));
    }
}
```

Tại thư mục chứa file, dùng JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 GroupingBreakDemo.java
java GroupingBreakDemo
```

Output:

```text
GET -> READ
HEAD -> READ
PUT -> WRITE
DELETE -> DELETE
PATCH -> UNKNOWN
get -> UNKNOWN
null -> INVALID
```

**Giải thích:** `GET` và `HEAD` chọn cùng phần gán `READ`; `POST` và `PUT` cùng gán `WRITE`; `DELETE` có nhánh riêng. `PATCH` không khớp nhãn nào nên vào `default`. `get` không khớp `GET` do phân biệt chữ hoa/chữ thường. Với `null`, điều kiện đầu hàm trả về `INVALID` trước khi thực hiện `switch`.

`default` ở vị trí cuối không bắt buộc có `break` vì phía dưới không còn nhánh nào; tuy nhiên việc có hay không có `break` phải được quyết định theo **vị trí và luồng chạy thực tế**, không phải vì tên `default`.

### Nhóm nhãn khác gì fall-through có hành động?

Xem hai trường hợp:

```java
// A. Nhóm nhãn: không có lệnh nào giữa hai case.
case "GET":
case "HEAD":
    result = "READ";
    break;

// B. Rơi qua nhánh SAU KHI đã thực hiện lệnh.
case "critical":
    actions.append("PAGE");
case "warning":
    actions.append("LOG");
    break;
```

Đây là **hai đoạn minh họa đặt ở hai `switch` khác nhau**; không đặt chúng liên tiếp ngoài ngữ cảnh. Trường hợp A gộp nhiều nhãn cho **một hành động chung**. Trường hợp B, khi đầu vào `critical`, chương trình thực hiện **hai hành động liên tiếp** vì không gặp `break` sau `PAGE`. Đó là fall-through có câu lệnh thực thi, thường cần xem xét kỹ hơn.

## 3. `break` kiểm soát điểm kết thúc nhánh

Trong `switch` truyền thống, `break;` làm kết thúc cấu trúc `switch` hiện tại. Nó không có nghĩa là kết thúc phương thức và không tự kết thúc vòng lặp bên ngoài.

| Cấu trúc | Tác dụng | Khi nào dùng |
| --- | --- | --- |
| `break;` trong `switch` | Rời `switch` gần nhất; tiếp tục sau khối `switch` | Khi nhánh đã hoàn tất, các nhánh dưới không được chạy |
| `return value;` | Trả kết quả và rời phương thức hiện tại | Khi nhánh đã có đầy đủ kết quả để trả |
| `throw new ...;` | Ném ngoại lệ, chuyển điều khiển theo cơ chế exception | Khi đầu vào hoặc trạng thái không hợp lệ |
| Không có lệnh kết thúc, còn lệnh bên dưới | Chạy tiếp vào phần phía dưới cho đến khi gặp điểm dừng | Chỉ khi fall-through thực sự đúng với yêu cầu |
| `case "A", "B" -> ...` trên JDK mới | Một switch rule độc lập; **không rơi qua rule tiếp theo** | Ưu tiên cho code mới nếu muốn tách nhánh rõ ràng |

Ví dụ `return` có thể thay `break` trong hàm chỉ trả kết quả:

```java
private static String operation(String value) {
    if (value == null) {
        return "UNKNOWN";
    }
    switch (value) {
        case "GET":
        case "HEAD":
            return "READ";
        default:
            return "OTHER";
    }
}
```

Đây là **một phương thức minh họa để đặt trong một lớp**, không có `main` độc lập. Mỗi nhánh kết thúc bằng `return` nên không cần thêm `break` ngay sau nó. Trong ví dụ đầu tiên, ta dùng biến `result` và `break` để làm rõ phạm vi của `break`.

### Đặt `break` sai vị trí gây gì?

Nếu xóa `break` sau `result = "READ";` trong `GroupingBreakDemo`, đầu vào `GET` sẽ gán `READ` rồi **chạy tiếp** đến phần gán `WRITE` trước khi gặp `break` kế tiếp. Khi đó hàm trả `WRITE` dù yêu cầu là `READ`. Đây là lỗi logic nguy hiểm vì chương trình **vẫn biên dịch và vẫn chạy**, chỉ trả kết quả sai.

Với các nhánh có side effect (gửi thông báo, ghi log, thay đổi trạng thái), lỗi còn có thể gây **thực hiện hành động thừa**. `break` vì vậy là một phần của ngữ nghĩa chương trình, không phải dấu trang trí.

## 4. Fall-through vô tình và fall-through có chủ ý

Thí nghiệm sau có hai phần: một đoạn **thiếu `break` không mong muốn**, và một đoạn **cố tình thực hiện thêm bước chung** cho mức độ nghiêm trọng cao.

### Chương trình đầy đủ: `FallThroughDemo.java`

```java
public final class FallThroughDemo {
    private static String accidental(String command) {
        StringBuilder trace = new StringBuilder();
        switch (command) {
            case "audit":
                trace.append("AUDIT");
            case "notify":
                if (trace.length() > 0) {
                    trace.append(" -> ");
                }
                trace.append("NOTIFY");
                break;
            default:
                trace.append("SKIP");
        }
        return trace.toString();
    }

    private static String intentional(String severity) {
        StringBuilder actions = new StringBuilder();
        switch (severity) {
            case "critical":
                actions.append("PAGE");
                // Fall through intentionally: a critical event must also be logged.
            case "warning":
                if (actions.length() > 0) {
                    actions.append(" -> ");
                }
                actions.append("LOG");
                break;
            default:
                actions.append("IGNORE");
        }
        return actions.toString();
    }

    public static void main(String[] args) {
        System.out.println("audit=" + accidental("audit"));
        System.out.println("notify=" + accidental("notify"));
        System.out.println("critical=" + intentional("critical"));
        System.out.println("warning=" + intentional("warning"));
        System.out.println("info=" + intentional("info"));
    }
}
```

Lệnh chạy:

```bash
javac --release 17 -encoding UTF-8 FallThroughDemo.java
java FallThroughDemo
```

Output:

```text
audit=AUDIT -> NOTIFY
notify=NOTIFY
critical=PAGE -> LOG
warning=LOG
info=IGNORE
```

**Phân tích phần `accidental`:**

- Với `audit`, chạy `trace.append("AUDIT")`; thiếu `break` nên chạy tiếp nhánh `notify` và thêm `NOTIFY`. Kết quả là `AUDIT -> NOTIFY`, dù giả sử yêu cầu chỉ muốn ghi nhận audit.
- Với `notify`, chỉ chạy phần tạo `NOTIFY`, vì điểm bắt đầu là nhãn `notify`.
- Đây là lỗi nghiệp vụ **nếu yêu cầu không cho phép thông báo sau audit**. Compiler không thể biết ý định của người viết code.

Cách sửa cho yêu cầu “`audit` chỉ làm audit” là thêm `break;` ngay sau `trace.append("AUDIT");`:

```java
case "audit":
    trace.append("AUDIT");
    break;
case "notify":
    trace.append("NOTIFY");
    break;
```

Đây là đoạn sửa **nằm trong `switch`**, không phải một lớp độc lập. Khi chạy phiên bản đã sửa với `audit`, kết quả chỉ còn `AUDIT`.

**Phân tích phần `intentional`:**

- `critical` cần vừa gọi trực (`PAGE`) vừa ghi log (`LOG`); fall-through thực hiện cả hai theo đúng thứ tự.
- `warning` chỉ cần `LOG`; nó bắt đầu ngay ở nhánh `warning`, bỏ qua `PAGE`.
- Nhận xét “có chủ ý” phải đi từ **yêu cầu nghiệp vụ**, không chỉ từ việc đã có comment. Comment như `// Fall through intentionally` giúp người đọc nhận biết ý định nhưng **không thay đổi hành vi Java**.
- Nếu hai nhánh chỉ cần **cùng một** hành động, dùng **nhóm nhãn không lệnh ở giữa** sẽ dễ đọc hơn.
- Trong code mới, nếu cần nhiều hành động có điều kiện, cân nhắc tách thành lời gọi hàm rõ ràng thay vì phụ thuộc vào thứ tự của các `case`.

### Bảng vết thực thi

| Giá trị `severity` | Điểm bắt đầu | Các câu lệnh chạy | Kết quả |
| --- | --- | --- | --- |
| `critical` | `case "critical"` | `PAGE`, sau đó `LOG` | `PAGE -> LOG` |
| `warning` | `case "warning"` | `LOG` | `LOG` |
| `info` | `default` | `IGNORE` | `IGNORE` |

Mô tả vết chạy giúp kiểm tra được **thứ tự side effect**. Một nhánh có fall-through có thể vẫn sinh output trông đúng ở một số input, nên cần thử nhiều giá trị chứ không chỉ happy path.

## 5. `break` trong `switch` nằm bên trong vòng lặp

Một hiểu nhầm thường gặp: “`break` trong `switch` sẽ dừng vòng lặp bao quanh”. Thực tế, `break` không nhãn chỉ thoát **cấu trúc breakable gần nhất**. Nếu một `switch` nằm trong `for`, `break` tại nhánh `switch` thoát `switch`, rồi `for` vẫn tiếp tục.

### Chương trình đầy đủ: `LoopSwitchDemo.java`

```java
public final class LoopSwitchDemo {
    public static void main(String[] args) {
        for (String command : new String[]{"GET", "STOP", "POST"}) {
            switch (command) {
                case "STOP":
                    System.out.println("inside STOP");
                    break;
                default:
                    System.out.println("inside " + command);
            }
            System.out.println("after " + command);
        }
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 LoopSwitchDemo.java
java LoopSwitchDemo
```

Output:

```text
inside GET
after GET
inside STOP
after STOP
inside POST
after POST
```

Điểm quan sát quan trọng là vẫn có dòng `after STOP` và hai dòng dành cho `POST`. Nếu nghiệp vụ thực sự yêu cầu **dừng xử lý mọi lệnh sau STOP**, hãy thiết kế rõ điểm dừng của vòng lặp (chẳng hạn điều kiện thoát vòng lặp, một cờ dừng, hoặc `return` nếu muốn rời hẳn phương thức). Không thể coi `break;` ở trong `switch` là cách dừng cả vòng lặp.

Đừng nhầm `continue` với `break`: `continue` chỉ có nghĩa hợp lệ khi nằm trong ngữ cảnh vòng lặp; trong ví dụ lồng nhau, nó chuyển sang vòng lặp kế tiếp theo quy tắc của `continue`, chứ không đơn thuần “thoát switch và chạy lệnh sau switch”.

## 6. Cách viết hiện đại trên JDK 17+: nhóm nhãn mà không có fall-through

Cú pháp `switch` dạng mũi tên (switch rule) hiện đã ổn định trên các JDK hiện đại. Nó phù hợp khi **mỗi nhóm nhãn là một quyết định độc lập**: không muốn người sửa code quên `break` và vô tình chạy sang nhánh khác.

### Chương trình đầy đủ: `ModernSwitchDemo.java`

```java
public final class ModernSwitchDemo {
    private static String category(String method) {
        if (method == null) {
            return "INVALID";
        }
        return switch (method) {
            case "GET", "HEAD" -> "READ";
            case "POST", "PUT" -> "WRITE";
            case "DELETE" -> "DELETE";
            default -> "UNKNOWN";
        };
    }

    public static void main(String[] args) {
        System.out.println("GET -> " + category("GET"));
        System.out.println("HEAD -> " + category("HEAD"));
        System.out.println("PUT -> " + category("PUT"));
        System.out.println("PATCH -> " + category("PATCH"));
    }
}
```

Chạy:

```bash
javac --release 17 -encoding UTF-8 ModernSwitchDemo.java
java ModernSwitchDemo
```

Output:

```text
GET -> READ
HEAD -> READ
PUT -> WRITE
PATCH -> UNKNOWN
```

Với cú pháp này:

- `case "GET", "HEAD" -> "READ"` nhóm nhiều nhãn trong **một rule**.
- Khi chọn rule `GET/HEAD`, chương trình tạo giá trị `READ`; nó **không rơi qua** rule `POST/PUT`.
- Ví dụ là **switch expression**, trả về một giá trị để dùng ngay trong `return`. Trong switch expression, một rule có block nhiều lệnh có thể dùng `yield` để cung cấp kết quả; không dùng `break` kiểu cổ điển để trả giá trị.
- `break` cũng không cần để ngăn fall-through trong switch rule dạng mũi tên của một **switch statement**.
- Trên JDK 17, nếu dùng mũi tên, các nhãn được phân tách bằng dấu phẩy. Cú pháp này **khác** kiểu nhiều dòng `case "GET": case "HEAD":` của switch truyền thống.

### Nên chọn cách nào?

| Nhu cầu | Cách diễn đạt | Lý do |
| --- | --- | --- |
| Đọc, duy trì code Java 7 dùng `switch(String)` dạng dấu hai chấm | Nhóm `case` liên tiếp và có `break` hoặc `return` rõ ràng | Hiểu đúng luồng chạy, tránh sửa nhầm |
| Viết code mới có nhiều nhãn chung một kết quả | `case "A", "B" -> value` | Diễn đạt trực tiếp ý định, không fall-through |
| Có nhiều nhánh có hành động độc lập | Mỗi rule mũi tên là một hành động; block `{ ... }` khi cần | Loại bỏ phụ thuộc vào vị trí nhãn bên dưới |
| Thực sự cần xử lý hai bước có quan hệ điều kiện | Hai hành động được gọi tường minh, hoặc fall-through có tài liệu/test rõ | Giữ thứ tự hiệu ứng dễ kiểm chứng |
| Giá trị có thể `null` | Kiểm tra `null` theo hợp đồng trước `switch` như các ví dụ | Không để đầu vào không hợp lệ vô tình gây NPE |

**Ranh giới phiên bản:** `switch` trên `String` xuất hiện từ Java 7; switch rule dùng `->` và switch expression là tính năng **được hoàn thiện ở các phiên bản Java mới hơn** và có sẵn trong Java 17+. Nếu dự án cần biên dịch với `--release 7`, không sao chép cú pháp `->` vào mã nguồn đó. Nếu dự án chạy Java 17+, có thể chọn cú pháp phù hợp với mục tiêu diễn đạt và quy ước dự án.

## 7. Những lỗi thường gặp khi nhóm nhãn và đặt `break`

### 7.1. Dùng fall-through để diễn đạt hai nhãn cùng hành động

```java
case "GET":
    result = "READ"; // Không cần thực thi lệnh ở đây nếu muốn nhóm nhãn.
case "HEAD":
    result = "READ";
    break;
```

Đoạn này chạy ra `READ` cho cả hai nhãn, nhưng khi đầu vào `GET` thì phần gán bị thực hiện **hai lần**. Nếu sau này phần gán thay thành thao tác có side effect, cấu trúc này có thể tạo bug. Khi ý định chỉ là một hành động chung, viết:

```java
case "GET":
case "HEAD":
    result = "READ";
    break;
```

Hai đoạn là ví dụ **để đặt bên trong một `switch`**, không phải chương trình chạy độc lập.

### 7.2. Quên `break` sau một nhánh đã có hành động

Nếu một nhánh bắt đầu ghi log, gọi API hoặc thay đổi dữ liệu mà thiếu `break`, nó có thể tiếp tục thực hiện hành động của nhánh dưới. Vấn đề không nằm ở việc compiler sai: đó là hành vi đúng theo ngôn ngữ nhưng **sai theo yêu cầu**. Lập test cho input khớp nhãn **ngay trước** nhãn kế tiếp; đây là cách hiệu quả để phát hiện rơi qua nhánh.

### 7.3. Nghĩ `default` luôn ở cuối hoặc tự ngăn fall-through

Trong switch dạng dấu hai chấm, `default` cũng là một nhãn. Nó có thể xuất hiện ở vị trí khác cuối khối; nếu sau nó còn các nhãn/câu lệnh và không có điểm dừng thì luồng vẫn có thể chạy tiếp. Đặt `default` ở cuối là một lựa chọn giúp dễ đọc nhưng không được dùng vị trí làm thay thế cho việc hiểu luồng điều khiển.

### 7.4. Bỏ quên giá trị `null` và khác biệt chữ hoa/thường

`switch` truyền thống với `String` không tự chuẩn hóa `"get"` thành `"GET"`. Nếu có nhu cầu hỗ trợ input không phân biệt hoa/thường, phải **xác định quy tắc chuẩn hóa đầu vào**. Nếu `null` là đầu vào có thể xảy ra, hãy quyết định rõ trả lỗi, trả giá trị đặc biệt hay ném exception **trước** `switch`. `default` không xử lý thay phần đó trong các ví dụ trên.

### 7.5. Coi `break` và `return` là một

`break` trong switch lồng trong loop vẫn cho chạy phần sau switch và các vòng lặp tiếp theo; `return` rời phương thức. Việc thay `break` bằng `return` để “sửa bug rơi qua nhánh” có thể gây **bỏ qua công việc sau `switch`**. Chọn theo luồng chạy cần thiết.

### 7.6. Trùng nhãn hoặc dùng giá trị không phải hằng

Các `case` trong cùng một `switch` phải không trùng giá trị; các nhãn chuỗi phải là hằng thích hợp khi biên dịch. Ví dụ `case "GET":` xuất hiện hai lần trong cùng `switch` sẽ gây lỗi biên dịch. Một biến được gán ở runtime không tự trở thành nhãn `case` hợp lệ.

## 8. Kiểm chứng bằng test có đầu vào và output dự kiến

Đối với một nhóm `switch(String)`, nên lập ma trận test **trước khi kết luận cách nhóm nhãn đúng**:

| Thí nghiệm | Đầu vào | Kết quả mong đợi | Điều cần chứng minh |
| --- | --- | --- | --- |
| `GroupingBreakDemo` | `GET`, `HEAD` | `READ` cho cả hai | Hai nhãn được nhóm đúng |
| `GroupingBreakDemo` | `POST`, `PUT` | `WRITE` cho cả hai | Nhóm thứ hai không đè nhóm đầu |
| `GroupingBreakDemo` | `DELETE` | `DELETE` | Nhánh riêng dừng đúng |
| `GroupingBreakDemo` | `PATCH` | `UNKNOWN` | `default` xử lý trường hợp không khớp |
| `GroupingBreakDemo` | `get` | `UNKNOWN` | Nhãn String phân biệt hoa/thường |
| `GroupingBreakDemo` | `null` | `INVALID` | Guard trước switch ngăn NPE |
| `FallThroughDemo` / `accidental` | `audit` | `AUDIT -> NOTIFY` **ở phiên bản lỗi** | Bằng chứng thiếu `break` gây hành động thừa |
| `FallThroughDemo` / `intentional` | `critical` | `PAGE -> LOG` | Fall-through có chủ ý được kiểm chứng |
| `FallThroughDemo` / `intentional` | `warning` | `LOG` | Không chạy `PAGE` cho mức thấp |
| `ModernSwitchDemo` | `GET`, `HEAD`, `PUT` | `READ`, `READ`, `WRITE` | Rule mũi tên không fall-through |
| `LoopSwitchDemo` | Chuỗi lệnh chứa `STOP` rồi `POST` | Vẫn có `after STOP` và phần `POST` | `break` thoát switch, không thoát vòng lặp |

Với code có side effect thật, test nên quan sát **số lần gọi**, **thứ tự gọi** và **trạng thái cuối**, không chỉ xem một chuỗi kết quả. Ví dụ, nếu yêu cầu “`audit` không gửi thông báo”, kết quả `AUDIT -> NOTIFY` phải được đánh dấu **FAIL về nghiệp vụ**, dù chương trình chạy không báo exception.

### Bài tập thực hành

**Bài 1.** Trong `GroupingBreakDemo`, hãy cố ý bỏ `break` sau `READ` rồi chạy với `GET` và `HEAD`. Giải thích vì sao cả hai thành `WRITE`. Đặt lại `break`, chạy lại và đối chiếu.

**Bài 2.** Thêm nhãn `"PATCH"` vào nhóm `POST/PUT` nếu hợp đồng của ứng dụng quy định đây là nhóm ghi. Test lại `PATCH` và `GET` để chắc chắn nhóm đọc không đổi.

**Bài 3.** Sửa `FallThroughDemo.accidental` để `audit` chỉ trả `AUDIT`. Vì sao thêm `break` đúng chỗ giải quyết lỗi, trong khi thêm `break` ở cuối `notify` không đủ?

**Bài 4.** Di chuyển phần xử lý `"GET", "HEAD"` sang dạng mũi tên trong `ModernSwitchDemo`, thay đổi vài input, so sánh cách kiểm soát fall-through giữa hai dạng.

**Bài 5.** Trong `LoopSwitchDemo`, yêu cầu mới là dừng *toàn bộ vòng lặp* khi gặp `STOP`. Hãy sửa điều khiển luồng một cách tường minh và dự đoán output trước khi chạy.

### Checklist khi review code

- [ ] Các `case` liền kề được nhóm vì có **chung hành động**, không phải vì vô tình thiếu `break`.
- [ ] Mỗi nhánh trong switch dạng dấu hai chấm có điểm kết thúc rõ: `break`, `return`, `throw`, hoặc fall-through **được giải thích và test**.
- [ ] Các nhánh làm thay đổi trạng thái hoặc gọi dịch vụ không bị chạy thêm ngoài ý muốn.
- [ ] Đã xử lý `null`, sự phân biệt chữ hoa/thường và giá trị không khớp nhãn.
- [ ] Đã kiểm tra vị trí `default` và các câu lệnh phía sau nó.
- [ ] Không nhầm `break` trong `switch` với việc dừng vòng lặp/phương thức bên ngoài.
- [ ] Với code Java 17+ mới, đã cân nhắc rule `->` khi không cần fall-through.
- [ ] Có ca test cho **nhãn đầu nhóm, nhãn cuối nhóm, nhãn ngay trước `break`, `default` và case có chủ ý rơi qua nhánh**.

## Tài liệu chính thức

- [Java Language Specification 17 — `14.11 switch Statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11): quy tắc nhãn, luồng điều khiển và phân biệt các dạng switch statement.
- [Java Language Specification 17 — `15.28 switch Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): cách switch expression trả về giá trị.
- [Oracle Java SE 7 Language Enhancements](https://docs.oracle.com/javase/7/docs/technotes/guides/language/enhancements.html): mốc bổ sung khả năng dùng `String` trong `switch`.

**Ghi nhớ:** Trong `switch` dấu hai chấm, **nhãn chọn nơi bắt đầu, `break` chọn nơi dừng**. Nhóm các nhãn khi chúng chia sẻ hành động; chỉ cho fall-through chạy qua các **câu lệnh thực thi** khi điều đó đúng yêu cầu và đã được test. Với Java hiện đại, switch rule dạng mũi tên giúp diễn đạt các nhánh độc lập mà không có fall-through ngoài ý muốn.