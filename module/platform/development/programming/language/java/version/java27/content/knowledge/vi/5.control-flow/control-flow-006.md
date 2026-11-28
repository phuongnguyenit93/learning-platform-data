# Đánh giá ngắn mạch và tác dụng phụ trong biểu thức điều kiện

Trong Java 27, một điều kiện như `if (user != null && user.isActive())` không chỉ tính ra `true` hoặc `false`: nó còn quyết định **biểu thức nào thật sự được thực thi**. Quy tắc này gọi là *đánh giá ngắn mạch* (*short-circuit evaluation*). Hiểu đúng quy tắc giúp viết điều kiện an toàn với `null`, tránh truy cập ngoài phạm vi mảng và kiểm soát những lời gọi hàm có tác dụng phụ.

Bài học thuộc chương **Điều khiển luồng**, áp dụng cho Java 27 và các phiên bản Java hiện đại có cùng quy tắc ngôn ngữ. Các ví dụ chỉ dùng cú pháp, API và cách viết còn được hỗ trợ.

## 1. Kết quả logic và việc thực thi biểu thức là hai vấn đề khác nhau

Xét điều kiện:

```java
if (hasPermission() && hasRemainingQuota()) {
    processRequest();
}
```

Để kết quả của toán tử `&&` là `true`, **cả hai** điều kiện phải đúng. Tuy nhiên, nếu `hasPermission()` trả về `false` thì Java biết ngay toàn bộ điều kiện là `false`; nó không gọi `hasRemainingQuota()` nữa.

Đây không đơn thuần là một phép tối ưu hiệu năng: việc bỏ qua hàm còn có thể thay đổi chương trình nếu hàm đó tăng bộ đếm, ghi log, truy vấn hệ thống, thay đổi trạng thái hoặc ném ngoại lệ.

**Tác dụng phụ** (*side effect*) là một thay đổi có thể quan sát được ngoài giá trị mà biểu thức trả về, ví dụ:

- Gán giá trị cho biến hoặc trường; dùng `++` và `--`.
- Thêm phần tử vào collection, thay đổi trạng thái đối tượng.
- Ghi log, cập nhật metric, gửi yêu cầu mạng, ghi file hoặc dữ liệu.
- Gọi một phương thức có hành vi phụ thuộc vào trạng thái bên ngoài.

Một phương thức kiểm tra thuần (*pure predicate*) chỉ tính và trả về `boolean`, không làm thay đổi trạng thái quan sát được. Điều kiện ghép từ các predicate thuần thường dễ đọc, dễ thử nghiệm và dễ dự đoán hơn điều kiện chứa nhiều tác dụng phụ.

## 2. Toán tử nào đánh giá ngắn mạch?

| Toán tử trên giá trị boolean | Ý nghĩa | Khi nào đánh giá biểu thức bên phải? |
| --- | --- | --- |
| `a && b` | AND có ngắn mạch | **Chỉ khi** `a` là `true` |
| `a \|\| b` | OR có ngắn mạch | **Chỉ khi** `a` là `false` |
| `a & b` | AND không ngắn mạch | **Luôn đánh giá** `b` nếu `a` hoàn thành bình thường |
| `a \| b` | OR không ngắn mạch | **Luôn đánh giá** `b` nếu `a` hoàn thành bình thường |
| `a ^ b` | XOR: đúng khi hai giá trị khác nhau | **Luôn đánh giá** `b` nếu `a` hoàn thành bình thường |
| `!a` | Phủ định | Phải đánh giá `a`, rồi đảo giá trị |
| `condition ? x : y` | Chọn một trong hai nhánh | Chỉ đánh giá **một** trong `x` hoặc `y` |

Trong bảng này, `&`, `|` và `^` được xét khi hai toán hạng thuộc kiểu `boolean` hoặc `Boolean`. Các ký hiệu đó cũng là toán tử thao tác bit khi dùng với số nguyên; đây là ngữ cảnh khác.

Hai toán tử `&&` và `||` chỉ nhận toán hạng kiểu `boolean` hoặc `Boolean`, và kết quả có kiểu nguyên thủy `boolean`. Java không ngầm coi số khác 0 là `true` hoặc tham chiếu không `null` là `true`.

### 2.1. `&&`: dừng ở điều kiện đầu tiên sai

```java
boolean accepted = isValidInput() && isAuthorized();
```

Trình tự:

1. Đánh giá `isValidInput()`.
2. Nếu kết quả là `false`: kết quả của `&&` là `false`; **không gọi** `isAuthorized()`.
3. Nếu kết quả là `true`: gọi `isAuthorized()`, rồi sử dụng giá trị hàm trả về.

Ví dụ với ba điều kiện:

```java
boolean permitted =
        request != null
        && request.isAuthenticated()
        && request.hasPermission();
```

Java xử lý từ trái sang phải. Nếu `request == null` thì cả hai lời gọi phương thức đều bị bỏ qua. Nếu yêu cầu không được xác thực, `hasPermission()` không được gọi.

### 2.2. `||`: dừng ở điều kiện đầu tiên đúng

```java
boolean allowed = isAdmin() || hasDelegatedAccess();
```

Trình tự:

1. Đánh giá `isAdmin()`.
2. Nếu `true`: kết quả của `||` là `true`; **không gọi** `hasDelegatedAccess()`.
3. Nếu `false`: gọi `hasDelegatedAccess()` để xác định kết quả.

Ví dụ thực tế:

```java
boolean displayNotice = isFirstVisit() || hasUnreadAnnouncement();
```

Khi đã biết đây là lần truy cập đầu tiên, Java bỏ qua phép kiểm tra thông báo chưa đọc. Cách viết này phù hợp khi chỉ cần biết **có ít nhất một lý do** để hiển thị thông báo và không yêu cầu cả hai phép kiểm tra cùng chạy.

### 2.3. `&`, `|` và `^`: không bỏ qua vế phải

```java
boolean result = checkA() & checkB();  // Gọi cả hai nếu checkA() hoàn thành bình thường
boolean other  = checkA() | checkB();  // Tương tự
boolean xor    = checkA() ^ checkB();  // Đúng nếu hai kết quả khác nhau
```

Khi các toán hạng là `boolean`, `a & b` và `a && b` có **cùng bảng chân trị**, tương tự `a | b` và `a || b`. Khác biệt nằm ở việc **có đánh giá vế phải hay không**.

Không nên dùng `&` hoặc `|` chỉ để ép hai phương thức có tác dụng phụ cùng thực thi. Nếu cả hai phép kiểm tra đều cần chạy, cách thể hiện ý định rõ ràng hơn là:

```java
boolean identityValid = checkIdentity();
boolean quotaValid = checkQuota();

boolean accepted = identityValid && quotaValid;
```

Hai phương thức luôn được gọi vì chúng là hai câu lệnh độc lập. Toán tử `&&` phía sau chỉ kết hợp hai kết quả đã có.

> **Giới hạn của chữ “luôn”:** Với `&`, `|`, `^`, Java đánh giá vế trái trước. Nếu việc đánh giá vế trái ném ngoại lệ hoặc kết thúc bất thường, vế phải cũng không được chạy. Toán tử không ngắn mạch không có nghĩa là mọi tác dụng phụ chắc chắn sẽ xảy ra.

## 3. Chạy thử: quan sát thứ tự và các lời gọi bị bỏ qua

Ví dụ sau là một chương trình Java hoàn chỉnh. Phương thức `trace` vừa in tên bước đã thực thi, vừa trả về giá trị `boolean`.

```java
public class ShortCircuitDemo {

    static boolean trace(String label, boolean value) {
        System.out.print(label + " ");
        return value;
    }

    public static void main(String[] args) {
        System.out.println(trace("A", false) && trace("B", true));
        System.out.println(trace("A", true)  && trace("B", true));

        System.out.println(trace("A", true)  || trace("B", false));
        System.out.println(trace("A", false) || trace("B", true));

        System.out.println(trace("A", false) &  trace("B", true));
        System.out.println(trace("A", true)  |  trace("B", false));

        System.out.println(
                trace("C", true) ? trace("T", true) : trace("F", false)
        );
    }
}
```

Chạy bằng JDK 27:

```bash
javac ShortCircuitDemo.java
java ShortCircuitDemo
```

Kết quả:

```text
A false
A B true
A true
A B true
A B false
A B true
C T true
```

Ở dòng đầu, `trace("A", false)` đã đủ làm `&&` trả về `false`, vì vậy không xuất hiện chữ `B`. Ở dòng thứ ba, vế trái của `||` là `true` nên `B` cũng không xuất hiện. Hai dòng dùng `&` và `|` đều in `A B`. Dòng cuối cho thấy toán tử `?:` chỉ đánh giá nhánh `T` được chọn.

Ví dụ cho thấy **cùng kết quả boolean vẫn có thể đi kèm chuỗi tác dụng phụ khác nhau**.

## 4. Thứ tự đánh giá và độ ưu tiên toán tử

Java quy định thứ tự đánh giá toán hạng của các toán tử theo hướng **trái sang phải**. Vế trái của phép toán nhị phân được đánh giá đầy đủ trước khi bắt đầu vế phải, trừ khi quy tắc ngắn mạch quyết định bỏ qua vế phải.

```java
boolean ok = checkFirst() && checkSecond() && checkThird();
```

Các hàm được gọi theo thứ tự `checkFirst`, `checkSecond`, `checkThird`, nhưng chuỗi có thể dừng ở bất cứ hàm nào trả về `false`. Với chuỗi `||`, Java dừng khi gặp `true` đầu tiên.

`&&` và `||` kết hợp từ trái sang phải; JLS còn bảo đảm việc đổi cách nhóm một chuỗi cùng toán tử (chỉ thay dấu ngoặc) không làm đổi thứ tự tác dụng phụ và kết quả:

```java
(a() && b()) && c()
a() && (b() && c())
```

Hai biểu thức trên có cùng kết quả và thứ tự gọi các hàm. Quy tắc tương tự áp dụng cho chuỗi chỉ có `||`.

Tuy nhiên, **`&&` có độ ưu tiên cao hơn `||`**:

```java
boolean permitted = isAdmin || isOwner && isActive;
```

Java hiểu là:

```java
boolean permitted = isAdmin || (isOwner && isActive);
```

Nếu `isAdmin` là `true` thì `permitted` luôn đúng, kể cả `isActive` là `false`. Nếu nghiệp vụ yêu cầu người dùng phải hoạt động dù là admin hay chủ sở hữu, viết rõ:

```java
boolean permitted = (isAdmin || isOwner) && isActive;
```

Hai biểu thức khác nhau cả về **giá trị** lẫn **những phần có thể bị bỏ qua**. Ưu tiên toán tử là quy tắc cú pháp; thứ tự đánh giá là quy tắc thực thi. Khi phối hợp `&&` với `||`, dấu ngoặc giúp người đọc kiểm chứng cả hai điều đó.

## 5. Dùng ngắn mạch làm lớp bảo vệ trước thao tác không an toàn

### 5.1. Kiểm tra `null` trước khi gọi phương thức

```java
static boolean isNonEmpty(String text) {
    return text != null && !text.isEmpty();
}
```

Nếu `text` là `null`, vế trái trả về `false` và `text.isEmpty()` không được gọi. Đổi `&&` thành `&` có thể gây `NullPointerException` khi Java vẫn đánh giá vế phải.

Cũng có thể chủ động coi giá trị `null` là một trường hợp hợp lệ:

```java
static boolean isMissingOrBlank(String text) {
    return text == null || text.isBlank();
}
```

Nếu `text == null`, `||` dừng ở `true` và không gọi `isBlank()`. Viết nhầm `text != null || text.isBlank()` sẽ gọi phương thức khi `text` là `null` và gây lỗi.

### 5.2. Kiểm tra chỉ số trước khi truy cập mảng

```java
static boolean isPositiveAt(int[] values, int index) {
    return values != null
            && index >= 0
            && index < values.length
            && values[index] > 0;
}
```

Điều kiện thứ tư chỉ chạy khi mảng tồn tại và chỉ số hợp lệ. Các phép kiểm tra nên đi **từ điều kiện tiên quyết đến thao tác phụ thuộc**:

1. Mảng khác `null`.
2. Chỉ số không âm.
3. Chỉ số nhỏ hơn độ dài mảng.
4. Mới truy cập phần tử.

Không thể hoán đổi tùy ý thứ tự các điều kiện nếu một điều kiện sử dụng dữ liệu mà điều kiện trước đang bảo vệ.

### 5.3. `instanceof` và biến pattern trong Java hiện đại

```java
static boolean containsUsefulText(Object input) {
    return input instanceof String text && !text.isBlank();
}
```

Nếu `input` không phải `String` (kể cả `null`), vế phải không chạy. Nếu pattern khớp, biến `text` được xác định và có thể sử dụng ở vế phải của `&&`. Đây là cách kết hợp ngắn mạch với *pattern variable flow scoping* của Java hiện đại để vừa kiểm tra kiểu, vừa dùng dữ liệu đã được kiểm tra.

Lưu ý, ngắn mạch chỉ bảo vệ đúng những thao tác nằm **sau** điều kiện kiểm tra tương ứng; nó không thể sửa một lỗi đã xảy ra ở chính vế trái.

## 6. Tác dụng phụ trong điều kiện: vì sao dễ gây lỗi?

### 6.1. `++`, `--` có thể không thực thi

```java
int attempts = 0;
boolean enabled = false;

boolean accepted = enabled && ++attempts > 0;

System.out.println(accepted); // false
System.out.println(attempts); // 0
```

Vì `enabled` là `false`, Java không đánh giá `++attempts > 0`. Bộ đếm giữ nguyên ở 0. Thay `enabled` thành `true` sẽ khiến `++attempts` được thực thi.

Do đó, không nên đặt bước tăng bộ đếm **bắt buộc xảy ra** ở vế phải của `&&` hoặc `||`. Nếu mọi lần kiểm tra đều phải được đếm, hãy viết thành câu lệnh riêng:

```java
int attempts = 0;
boolean enabled = false;

attempts++;
boolean accepted = enabled && attempts <= 3;
```

Cách này cho thấy rõ việc tăng bộ đếm là độc lập với việc điều kiện đúng hay sai. Tương tự, nên tránh gán biến ngay trong điều kiện nếu có thể viết thành câu lệnh dễ hiểu hơn.

### 6.2. Ghi log, audit và metric có thể bị bỏ qua

Giả sử nghiệp vụ yêu cầu **mọi** lần kiểm tra quyền đều được ghi nhận. Cách viết sau có rủi ro bỏ sót:

```java
// Ví dụ minh họa: recordAudit(...) trả về boolean.
boolean allowed = hasAccess(user) && recordAudit(user);
```

Nếu `hasAccess(user)` là `false`, `recordAudit(user)` không chạy. Ngoài ra, kết quả `recordAudit` còn vô tình tham gia vào quyết định cấp quyền.

Thể hiện nghiệp vụ bằng các bước tách biệt:

```java
boolean allowed = hasAccess(user);
recordAudit(user, allowed);

if (allowed) {
    handleRequest();
}
```

Khi đó audit diễn ra ở cả hai trường hợp `allowed` đúng và sai, miễn là các câu lệnh trước nó hoàn thành bình thường. Đồng thời quyết định cho phép truy cập không bị lẫn với kết quả ghi audit.

Một quy tắc thực hành hữu ích: **đặt tác dụng phụ cần diễn ra vô điều kiện thành câu lệnh riêng**, và để các biểu thức điều kiện chủ yếu đọc trạng thái rồi trả về `boolean`.

### 6.3. Phương thức có tác dụng phụ chỉ chạy khi nhánh chứa nó được chọn

```java
if (isEligible() && sendNotification()) {
    markCompleted();
}
```

`sendNotification()` chỉ chạy nếu `isEligible()` trả về `true`. Điều này có thể đúng ý định, nhưng cách ghép vào điều kiện che giấu bước gửi thông báo và làm việc đọc code khó hơn. Nếu gửi thông báo là một hành động nghiệp vụ, nên tách:

```java
if (isEligible()) {
    boolean sent = sendNotification();

    if (sent) {
        markCompleted();
    }
}
```

Hai đoạn có thể cùng hiệu quả trong tình huống đơn giản; đoạn sau trình bày rõ hành động, điều kiện xử lý và vị trí dễ ghi log, thử lại hoặc xử lý lỗi.

### 6.4. Đánh giá lặp lại trong vòng lặp

```java
while (hasNextItem() && hasCapacity()) {
    processNextItem();
}
```

Mỗi lần kiểm tra vòng lặp, Java đánh giá từ trái sang phải. Nếu `hasNextItem()` trả về `false` thì không gọi `hasCapacity()` trong lần đó. Khi đánh giá lần tiếp theo, các hàm có thể trả về giá trị khác.

Vì vậy, điều kiện của `while` hoặc `for` cần được hiểu là biểu thức được **đánh giá lại theo tiến trình vòng lặp**, không phải một giá trị tính một lần rồi giữ nguyên. Tránh gọi những phương thức thay đổi trạng thái ngoài dự kiến trong điều kiện lặp, vì lỗi có thể xuất hiện chỉ sau một số vòng nhất định.

## 7. `Boolean` có thể `null`: ngắn mạch không tự giải quyết mọi lỗi

Toán tử `&&` và `||` nhận `Boolean`, nhưng Java phải **unbox** nó thành `boolean` để quyết định hướng thực thi. Nếu toán hạng cần dùng có giá trị `null`, quá trình unboxing gây `NullPointerException`.

```java
Boolean approved = null;
boolean ready = true;

boolean result = ready && approved; // Ném NullPointerException
```

Với `ready == true`, vế phải bắt buộc được đánh giá và `approved` bị unbox. Nhưng nếu `ready == false`, `approved` bị bỏ qua và toàn bộ điều kiện là `false`.

Trong nhiều trường hợp, ý nghĩa mong muốn là “chỉ `Boolean.TRUE` mới được coi là đúng”. Khi đó:

```java
Boolean approved = null;

boolean result = Boolean.TRUE.equals(approved); // false, không ném lỗi
```

Hoặc nếu cần bảo vệ trước khi unbox:

```java
boolean result = approved != null && approved;
```

Đối với một cờ ba trạng thái (`true`, `false`, `null`), cần xác định rõ nghiệp vụ muốn xử lý `null` ra sao, thay vì dựa vào tính ngắn mạch một cách tình cờ.

Điểm tương tự xảy ra với toán tử `?:` khi điều kiện có kiểu `Boolean`:

```java
Boolean flag = null;
// String label = flag ? "on" : "off"; // NullPointerException do unboxing
String label = Boolean.TRUE.equals(flag) ? "on" : "off";
```

## 8. Toán tử ba ngôi `?:`: chỉ một nhánh được thực thi

Cấu trúc:

```java
result = condition ? valueWhenTrue : valueWhenFalse;
```

Java đánh giá `condition` trước. Nếu đúng, chỉ đánh giá `valueWhenTrue`; nếu sai, chỉ đánh giá `valueWhenFalse`. Nhánh không được chọn **không chạy**. Đây là một dạng chọn nhánh trong biểu thức, không phải toán tử AND/OR.

```java
String title = isGuest()
        ? loadGuestTitle()
        : loadMemberTitle();
```

Chỉ một trong hai phương thức tải tiêu đề được gọi mỗi lần biểu thức được đánh giá. Cả hai nhánh vẫn phải hợp lệ về kiểu và cú pháp khi biên dịch, dù một nhánh không được chọn lúc chạy.

Khi mỗi nhánh chỉ tính một giá trị đơn giản, `?:` thường ngắn gọn và dễ đọc. Khi một nhánh có nhiều tác dụng phụ hoặc cần xử lý ngoại lệ, dùng `if/else` thường rõ ràng hơn:

```java
String title;
if (isGuest()) {
    title = loadGuestTitle();
} else {
    title = loadMemberTitle();
}
```

Nếu biểu thức `?:` có các kiểu nhánh khác nhau, Java có thể phải thực hiện chuyển đổi kiểu, boxing hoặc unboxing trên giá trị **được chọn**. Do đó đừng suy luận rằng chỉ vì nhánh kia không chạy thì kết quả chắc chắn không thể ném ngoại lệ.

## 9. Ngắn mạch có bảo đảm mọi thao tác đều an toàn không?

**Không.** Nó bảo đảm thứ tự và điều kiện đánh giá, nhưng không biến các phương thức thành thao tác an toàn tuyệt đối.

- **Ngoại lệ ở vế trái:** Nếu `loadStatus()` ném ngoại lệ, Java không đánh giá vế phải; cả `&&` lẫn `&` đều không thể tiếp tục bình thường.
- **Ngoại lệ ở vế phải:** Nếu logic buộc phải đánh giá vế phải và phương thức ném ngoại lệ, ngoại lệ vẫn được truyền ra theo quy tắc thông thường.
- **Trạng thái thay đổi đồng thời:** `resource != null && resource.isReady()` không tự tạo một giao dịch nguyên tử. Với biến/trạng thái dùng chung giữa các thread, cần cơ chế đồng bộ hóa hoặc thiết kế dữ liệu phù hợp.
- **Điều kiện sai vẫn có tác dụng phụ ở phần đã chạy:** `checkAndUpdate() && otherCheck()` có thể đổi trạng thái trong `checkAndUpdate()` dù kết quả toàn biểu thức là `false`.

Nếu muốn kiểm soát lỗi hoặc bảo đảm cập nhật trạng thái, hãy thể hiện điều đó bằng cấu trúc chương trình phù hợp: câu lệnh riêng, `try/catch` khi cần, giao dịch hoặc cơ chế đồng bộ hóa. Toán tử logic không thay thế các cơ chế này.

## 10. Các lỗi đọc code thường gặp

| Cách viết dễ lỗi | Vấn đề | Cách viết hoặc tư duy phù hợp |
| --- | --- | --- |
| `item != null & item.isValid()` | Vế phải vẫn chạy khi `item == null` | Dùng `item != null && item.isValid()` |
| `index < data.length && data[index] > 0` | Chưa kiểm tra `data != null` và `index >= 0` | Kiểm tra điều kiện tiên quyết từ trái sang phải |
| `isAdmin || isOwner && active` | `&&` ưu tiên hơn `||`, có thể bỏ qua `active` | Viết dấu ngoặc theo đúng yêu cầu nghiệp vụ |
| `flag && ++count > 0` | `count` không tăng khi `flag` sai | Tăng bộ đếm ở câu lệnh riêng nếu bắt buộc |
| `allowed || writeAudit()` | Audit bị bỏ qua khi `allowed` đúng | Ghi audit bằng câu lệnh riêng |
| `Boolean nullable && otherCheck()` | Có thể ném `NullPointerException` lúc unboxing | Xác định chính sách xử lý `null`; dùng `Boolean.TRUE.equals(...)` khi phù hợp |
| Dùng `&` để ép hai hàm cùng chạy | Tác dụng phụ bị che trong biểu thức | Gọi các hàm ở hai câu lệnh rồi kết hợp kết quả |

Nhớ rằng “ngắn mạch” không có nghĩa Java tính các phần theo thứ tự ngẫu nhiên. Java **đánh giá từ trái sang phải**, nhưng chỉ tiếp tục đánh giá những phần còn cần thiết.

## 11. Cách tự phân tích một biểu thức phức tạp

Khi gặp một điều kiện khó hiểu, có thể làm theo bốn bước:

1. **Thêm dấu ngoặc theo độ ưu tiên.** Xác định phạm vi của `&&`, `||` và `?:`.
2. **Đánh dấu mỗi hàm có tác dụng phụ.** Ghi lại hàm nào đổi trạng thái, truy cập I/O hoặc có thể ném ngoại lệ.
3. **Duyệt từ trái sang phải.** Với `&&` dừng nhánh khi gặp `false`; với `||` dừng nhánh khi gặp `true`. Đối với `&`, `|`, `^`, xem xét cả hai vế nếu không có kết thúc bất thường.
4. **Kiểm tra các trường hợp biên.** Thử `null`, collection/mảng rỗng, chỉ số âm, `Boolean` nullable và những giá trị khiến biểu thức dừng sớm.

Ví dụ:

```java
boolean canProceed =
        (user != null && user.isActive())
        && (hasSubscription() || hasTrial())
        && remainingSlots > 0;
```

Thứ tự thực thi:

- Nếu `user == null`, Java bỏ qua toàn bộ phần còn lại.
- Nếu `user` không active, Java cũng dừng với `false`.
- Nếu `hasSubscription()` trả về `true`, Java không gọi `hasTrial()`.
- Nếu không có cả subscription lẫn trial, Java không cần kiểm tra `remainingSlots > 0`.
- Chỉ khi các điều kiện trước đều đúng, Java mới xét số slot còn lại.

Cách phân tích này có thể dùng trực tiếp khi đọc code thật, tìm nguyên nhân metric không tăng, theo dõi lời gọi API không xảy ra hoặc giải thích vì sao một ngoại lệ chỉ xuất hiện với một số đầu vào.

## 12. Tài liệu chính thức

Các quy tắc trong bài dựa trên **Java Language Specification 27**:

- [JLS §15.7 — Evaluation Order](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.7): thứ tự đánh giá và kết thúc bất thường.
- [JLS §15.22.2 — Boolean Logical Operators](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.22.2): `&`, `|`, `^` trên boolean.
- [JLS §15.23 — Conditional-And Operator](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.23): quy tắc ngắn mạch của `&&`.
- [JLS §15.24 — Conditional-Or Operator](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.24): quy tắc ngắn mạch của `||`.
- [JLS §15.25 — Conditional Operator](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-15.html#jls-15.25): toán tử `?:` và nhánh được đánh giá.
- [JLS §5.1.8 — Unboxing Conversion](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-5.html#jls-5.1.8): `Boolean` chuyển thành `boolean` và trường hợp `null`.
- [JLS §6.3 — Scope of a Declaration](https://docs.oracle.com/en/java/javase/27/docs/specs/jls/jls-6.html#jls-6.3): phạm vi biến pattern phụ thuộc vào kết quả kiểm tra.
