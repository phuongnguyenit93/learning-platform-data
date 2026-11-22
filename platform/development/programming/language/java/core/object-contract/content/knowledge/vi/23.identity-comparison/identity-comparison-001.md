# Khi bài toán cần phân biệt từng thể hiện dù giá trị bằng nhau

## 1. Vấn đề cần giải quyết

Trong Java, hai biến tham chiếu có thể trỏ đến **hai đối tượng khác nhau** nhưng các đối tượng ấy mang **cùng giá trị logic**. Có những bài toán chỉ quan tâm nội dung: hai vé có cùng mã được xem là tương đương. Nhưng cũng có bài toán phải phân biệt chính xác **từng thể hiện (instance) được tạo ra trong bộ nhớ**: vé thứ nhất đã được xử lý, còn vé thứ hai chưa, dù cả hai cùng mã.

Câu hỏi phải đặt ra trước khi chọn phép so sánh là:

- **Value equality (bằng nhau về giá trị):** hai đối tượng có được xem là tương đương theo quy tắc nghiệp vụ hay không?
- **Reference identity (cùng danh tính đối tượng):** hai tham chiếu có trỏ đến **chính cùng một đối tượng** hay không?

Đây là hai quan hệ khác nhau. `equals()` có thể được định nghĩa để coi hai đối tượng khác nhau là bằng nhau; điều đó không biến chúng thành một instance.

## 2. Phân biệt `==`, `equals()` và hash code

| Công cụ | Ý nghĩa khi dùng với đối tượng | Khi nào phù hợp |
| --- | --- | --- |
| `a == b` | Hai tham chiếu cùng trỏ đến một đối tượng, hoặc cả hai đều `null`. | Cần nhận diện **chính instance**. |
| `a.equals(b)` | Bằng nhau theo cách lớp cài đặt `equals`; có thể báo lỗi nếu `a == null`. | Cần so sánh **giá trị/ngữ nghĩa nghiệp vụ**. |
| `Objects.equals(a, b)` | So sánh theo `equals`, xử lý `null` an toàn. | Cần value equality khi một trong hai tham chiếu có thể `null`. |
| `a.hashCode()` | Mã băm theo hợp đồng `equals`–`hashCode`; có thể bị ghi đè. | Làm việc với cấu trúc băm theo giá trị. |
| `System.identityHashCode(a)` | Mã băm theo danh tính mặc định, bất kể lớp ghi đè `hashCode`. | Chẩn đoán/thuật toán dựa trên identity, **không** dùng riêng nó để xác nhận cùng đối tượng. |

Với **kiểu nguyên thủy** (`int`, `double`, `boolean`...), `==` so sánh giá trị nguyên thủy; bài học này tập trung vào **tham chiếu đối tượng**. `Object.equals` mặc định tương đương so sánh identity, nhưng nhiều lớp như `String`, các lớp wrapper và `record` dùng value equality. Vì vậy không thể suy ra ý nghĩa `equals` mà bỏ qua hợp đồng của lớp.

Đặc điểm quan trọng: nếu `a == b` thì một lời gọi `a.equals(b)` hợp lệ phải trả về `true` với cách cài đặt `equals` tuân thủ hợp đồng thông thường. Chiều ngược lại **không đúng**: `a.equals(b)` là `true` không có nghĩa `a == b`.

## 3. Ví dụ chạy được: hai instance cùng giá trị

Tạo file **`IdentityComparisonDemo.java`**:

```java
import java.util.HashMap;
import java.util.IdentityHashMap;
import java.util.Map;

record Ticket(String code) {}

public class IdentityComparisonDemo {
    public static void main(String[] args) {
        Ticket first = new Ticket("T-01");
        Ticket second = new Ticket("T-01");
        Ticket alias = first;

        System.out.println("first == second: " + (first == second));
        System.out.println("first.equals(second): " + first.equals(second));
        System.out.println("alias == first: " + (alias == first));

        Map<Ticket, String> byValue = new HashMap<>();
        byValue.put(first, "first");
        byValue.put(second, "second");

        Map<Ticket, String> byIdentity = new IdentityHashMap<>();
        byIdentity.put(first, "first");
        byIdentity.put(second, "second");

        System.out.println("HashMap size: " + byValue.size());
        System.out.println("HashMap get(first): " + byValue.get(first));
        System.out.println("IdentityHashMap size: " + byIdentity.size());
        System.out.println("IdentityHashMap get(first): " + byIdentity.get(first));
        System.out.println("IdentityHashMap get(second): " + byIdentity.get(second));
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac IdentityComparisonDemo.java
java IdentityComparisonDemo
```

Kết quả:

```text
first == second: false
first.equals(second): true
alias == first: true
HashMap size: 1
HashMap get(first): second
IdentityHashMap size: 2
IdentityHashMap get(first): first
IdentityHashMap get(second): second
```

Diễn giải:

1. Mỗi lần `new Ticket(...)` tạo ra một đối tượng riêng, nên `first == second` là `false`.
2. `record Ticket` sinh `equals` dựa trên thành phần `code`; cùng `"T-01"` khiến `first.equals(second)` là `true`.
3. `alias = first` chỉ sao chép **tham chiếu**; nó không tạo thêm đối tượng.
4. `HashMap` dùng `hashCode` và `equals` của khóa, nên khóa `second` thay giá trị gắn với khóa tương đương `first`; còn một entry.
5. `IdentityHashMap` phân biệt `first` và `second` bằng `==`, nên lưu được hai entry độc lập.

**Bài học:** chọn `HashMap` khi “cùng mã vé” nghĩa là một khóa logic; chọn `IdentityHashMap` khi “đúng đối tượng vé này” mới là khóa.

## 4. Những tình huống identity là đúng yêu cầu

### 4.1. Theo dõi mỗi instance trong quá trình xử lý

Giả sử một luồng xử lý nhận hai đối tượng sự kiện có cùng `eventCode`. Hệ thống phải đánh dấu **đối tượng đã duyệt trong lần chạy hiện tại**, chứ không gom mọi đối tượng có cùng mã thành một. Một tập hợp theo identity phù hợp cho việc ghi nhận từng instance:

```java
Set<Event> visited =
        Collections.newSetFromMap(new IdentityHashMap<Event, Boolean>());

visited.add(eventA);
boolean alreadyVisited = visited.contains(eventB);
```

Đoạn trên **chỉ là trích đoạn minh họa**, giả định lớp `Event` và các biến `eventA`, `eventB` đã được khai báo; cần import `java.util.Set`, `java.util.Collections`, `java.util.IdentityHashMap`. Nếu hai biến trỏ đến hai instance khác nhau, `contains(eventB)` là `false` dù `eventA.equals(eventB)` trả về `true`. Nếu `eventB` là alias của `eventA`, kết quả là `true`.

Đặc biệt hữu ích khi duyệt **đồ thị đối tượng có chu trình**, phát hiện đối tượng đã ghé qua và tránh lặp vô hạn. Nếu dùng `HashSet` mà các nút khác instance lại có `equals` giống nhau, thuật toán có thể bỏ sót nút hợp lệ.

### 4.2. Gắn trạng thái tạm thời vào từng đối tượng

Ví dụ trình kiểm tra cấu trúc, bộ tuần tự hóa, bộ ghi dấu vết hoặc debugger muốn gắn trạng thái `VISITING`, `VISITED` cho **từng object**. Hai object được xem là có cùng giá trị vẫn có thể nằm ở vị trí khác nhau trong đồ thị, có tham chiếu con khác nhau, hoặc trải qua trạng thái xử lý khác nhau. Bảng ánh xạ identity giúp trạng thái không bị nhập nhằng.

### 4.3. Quản lý đối tượng làm khóa đồng bộ hóa

Monitor của `synchronized (lock)` gắn với **danh tính đối tượng `lock`**. Hai đối tượng lock khác nhau không phối hợp với nhau chỉ vì `lockA.equals(lockB)` trả về `true`. Các thread muốn bảo vệ cùng một vùng trạng thái phải dùng **cùng instance lock** (thường là một trường `private final Object lock = new Object();` được chia sẻ bởi đúng các thao tác cần đồng bộ).

Không tạo một đối tượng lock mới chỉ có cùng giá trị cho từng lời gọi rồi cho rằng chúng sẽ loại trừ lẫn nhau. Cũng tránh khóa trên string literal hoặc đối tượng công khai có thể bị mã khác dùng chung một cách ngoài ý muốn.

### 4.4. Phân biệt đối tượng sống với cùng một khóa nghiệp vụ

Hai đối tượng mô tả “khách hàng mã 123” có thể là hai bản sao dữ liệu trong bộ nhớ. Nếu muốn so sánh **khách hàng nào**, hãy dùng định danh nghiệp vụ ổn định và chính sách `equals` phù hợp. Nếu muốn hỏi **biến nào đang tham chiếu đến cùng object đang được thao tác**, dùng `==`. Identity trong JVM không phải định danh nghiệp vụ dài hạn: tải lại từ database, deserialize hoặc nhận bản sao qua API thường cho instance mới.

## 5. Quy tắc ra quyết định## 6. Quy tắc ra quyết định

| Câu hỏi/nhu cầu | Chọn | Lý do |
| --- | --- | --- |
| “Hai giá trị `String` có cùng nội dung?” | `equals` hoặc `Objects.equals` | Nội dung mới là tiêu chí. |
| “Đây có đúng object đang được giữ trong bộ nhớ không?” | `==` | Yêu cầu cùng instance. |
| “Hai bản ghi cùng khóa nghiệp vụ có đại diện một thực thể logic?” | So sánh ID/giá trị theo hợp đồng domain | Identity tham chiếu không bền qua lần tải/copy. |
| “Đã duyệt chính nút object này trong đồ thị chưa?” | Tập hợp/map theo identity | Không nhập các nút riêng chỉ vì `equals` giống nhau. |
| “Map cần gom các khóa có giá trị tương đương?” | `HashMap` | Dựa trên `equals`/`hashCode`. |
| “Map phải lưu metadata tách riêng theo từng object?” | `IdentityHashMap` | Dựa trên `==` cho khóa. |
| “Hai thao tác có dùng chung monitor đồng bộ?” | Kiểm tra cùng object lock | Monitor có danh tính theo instance. |

Cách tự hỏi nhanh: **Nếu tạo thêm một đối tượng bằng `new` với nội dung y hệt, yêu cầu có coi nó là một mục riêng không?** Nếu có, rất có thể cần identity trong **phạm vi vòng đời các object đó**. Nếu không, ưu tiên value equality hoặc một ID nghiệp vụ.

## 6. Những cạm bẫy thường gặp

### 7.1. Dùng `==` cho `String` hoặc wrapper

`String` có cơ chế intern; compiler/JVM cũng có các cơ chế tái sử dụng một số đối tượng. Vì vậy đôi khi `==` tình cờ là `true` với hai giá trị bằng nhau. Điều đó **không bảo đảm** hai chuỗi cùng nội dung sẽ cùng instance:

```java
String x = new String("java");
String y = new String("java");

System.out.println(x == y);      // false
System.out.println(x.equals(y)); // true
```

Đoạn này là trích đoạn Java độc lập về mặt câu lệnh (có thể đặt trong `main`). Tránh suy luận về value equality từ hành vi cache của boxed `Integer` hoặc string pool. Với chuỗi nội dung, dùng `equals` hoặc `Objects.equals`.

### 7.2. Tưởng `identityHashCode` là địa chỉ bộ nhớ hay ID duy nhất

`System.identityHashCode(obj)` **không phải địa chỉ bộ nhớ**, không là ID ổn định giữa những lần chạy JVM, và **có thể trùng** ở hai object khác nhau. Vì vậy:

- `System.identityHashCode(a) == System.identityHashCode(b)` **không chứng minh** `a == b`.
- Khi cần so sánh trực tiếp danh tính, dùng `a == b`; khi cần cấu trúc dữ liệu theo danh tính, dùng cấu trúc thực sự hỗ trợ identity.

Lưu ý `System.identityHashCode(null)` trả về `0`; số này cũng không phải một dấu hiệu nhận diện duy nhất.

### 7.3. Mặc định mọi `equals` đều là value equality

Nếu lớp không ghi đè `Object.equals`, mặc định `equals` dùng identity; khi đó `a.equals(b)` và `a == b` cho cùng kết quả nếu `a` không null. Nhưng lớp có thể được thay đổi để ghi đè `equals` sau này. Hãy chủ động chọn toán tử/thư viện phản ánh **ý định thuật toán**, không dựa vào hành vi tình cờ hiện tại của một lớp.

### 7.4. Dùng `IdentityHashMap` làm thay thế phổ quát cho `HashMap`

`IdentityHashMap` là cấu trúc chuyên biệt. Nó dùng **reference equality cho cả khóa và giá trị** trong các phép toán liên quan; hành vi này khác các triển khai `Map` thông thường và có thể tạo kết quả bất ngờ khi đối chiếu map/entry với cấu trúc dùng `equals`. Không có bảo đảm thứ tự duyệt. Nó cũng **không thread-safe**, và các tham chiếu mạnh trong map có thể giữ object sống lâu nếu không xóa entry khi không cần.

`IdentityHashMap` thích hợp cho topology/preservation của object graph và metadata theo instance; đừng dùng chỉ để né việc thiết kế `equals`/`hashCode` đúng cho khóa nghiệp vụ.

### 7.5. Tưởng danh tính JVM tồn tại qua serialization hoặc dịch vụ khác

Một object được copy, deserialize hoặc tái tạo ở JVM khác thường là instance mới. So sánh tham chiếu chỉ có ý nghĩa khi các tham chiếu cùng quan sát object trong một JVM đang chạy. Muốn nối dữ liệu qua lần chạy, database hay mạng, cần **ID ổn định** do ứng dụng quy định.

### 7.6. Nhầm identity với trạng thái hiện tại

Một object có thể đổi các trường mutable mà vẫn là **cùng instance** (`a == alias` vẫn `true`). Ngược lại, hai immutable record có thể bằng nhau suốt đời nhưng là **hai instance**. Đừng suy ra danh tính từ việc giá trị đã đổi hay chưa. Dùng khóa mutable trong `HashMap` còn gây rủi ro nếu các trường tham gia `hashCode` thay đổi sau khi thêm vào; đó là vấn đề hợp đồng băm, cần phân biệt với identity.

## 7. Checklist thiết kế và kiểm thử

1. Viết rõ tiêu chí: “bằng nhau về dữ liệu”, “cùng định danh nghiệp vụ” hay “chính cùng đối tượng trong bộ nhớ”.
2. Với value equality: định nghĩa/kiểm tra `equals` và `hashCode` nhất quán; xử lý `null` bằng `Objects.equals` khi cần.
3. Với reference identity: dùng `==`, `IdentityHashMap`, hoặc identity-backed set; không thay bằng so sánh identity hash code.
4. Thử ít nhất ba trường hợp: **cùng tham chiếu**, **khác instance nhưng `equals` là `true`**, và **khác giá trị**. Nếu có thể `null`, thử thêm cả `null`.
5. Rà soát vòng đời object, số lượng entry giữ trong map, luồng truy cập và nhu cầu đồng bộ; identity trong bộ nhớ không thay ID nghiệp vụ bên ngoài.
6. Khi dùng object làm lock, đảm bảo mọi thao tác cần phối hợp tham chiếu **cùng object lock**.

## 8. Câu hỏi tự kiểm tra

**Tình huống A:** `a` và `b` là hai instance khác nhau của cùng một `record Product("P1")`. `a.equals(b)` trả `true`. Nếu chỉ muốn gửi thông báo một lần cho mỗi mã sản phẩm, nên dùng `HashSet` hay identity set?

**Đáp án:** `HashSet` phù hợp vì yêu cầu gom theo mã/giá trị, giả sử quy tắc `equals` của `Product` đúng với định nghĩa trùng sản phẩm.

**Tình huống B:** Bộ phân tích cây object phải ghi nhận đường đi qua hai nút riêng cùng tên, và tránh quay lại đúng một nút đã thăm vì đồ thị có chu trình. Nên dùng loại visited set nào?

**Đáp án:** Identity set phù hợp vì mỗi nút là một object cụ thể; hai nút có cùng tên vẫn cần duyệt độc lập, trong khi quay lại cùng instance phải được nhận ra.

**Tình huống C:** Hai số `System.identityHashCode` bằng nhau có cho phép kết luận hai tham chiếu trỏ đến một object không?

**Đáp án:** Không. Hash có thể va chạm; để kết luận cùng instance trong JVM, so sánh `==`.

**Ghi nhớ:** “Giá trị như nhau” trả lời **đối tượng được coi là tương đương theo quy tắc nào**; “danh tính như nhau” trả lời **có phải đúng một thể hiện đang tồn tại hay không**. Lựa chọn nằm ở yêu cầu bài toán, không nằm ở việc hai object trông giống nhau đến mức nào.
