# Quan sát trạng thái phiên JShell với /list, /vars, /methods, /types và /imports

JShell cho phép nhập và đánh giá Java theo từng snippet. Khi phiên có nhiều biến, phương thức, kiểu và import, cần biết những gì đang có hiệu lực, đoạn mã nào đã tạo ra chúng và import nào đang được sử dụng. Năm lệnh /list, /vars, /methods, /types và /imports cung cấp các góc nhìn khác nhau để kiểm tra trạng thái đó.

Các lệnh này là công cụ quan sát phiên làm việc. Chúng không tự chạy lại snippet hoặc thay đổi giá trị biến. Chúng thuộc JShell hiện hành, được đưa vào JDK từ Java 9 và tiếp tục có trong các JDK mới.

## 1. Tổng quan năm lệnh

| Lệnh | Nội dung được liệt kê | Câu hỏi được trả lời |
|---|---|---|
| `/list` | Snippet mã đã nhập hoặc nạp bằng `/open`, kèm ID và nội dung | Tôi đã nhập những đoạn mã nào? |
| `/vars` | Biến đang có hiệu lực, kiểu và giá trị | Hiện có thể sử dụng những biến nào? |
| `/methods` | Phương thức, kiểu tham số và kiểu trả về | Tôi đã khai báo những phương thức nào? |
| `/types` | Các khai báo lớp, interface và kiểu | Những kiểu nào đang tồn tại trong phiên? |
| `/imports` | Các import đang có hiệu lực | Những package hoặc kiểu nào đang được import? |

Mỗi lệnh tập trung vào một loại thông tin. Ví dụ, `/list` có thể hiển thị snippet khai báo phương thức; `/methods` hiển thị chữ ký của phương thức đó. `/list` có thể hiển thị một câu lệnh hoặc biểu thức; `/vars` cho biết biến được tạo bởi biểu thức nếu có.

## 2. /list: xem mã nguồn snippet và ID

`/list` hiển thị các snippet đang có hiệu lực mà bạn đã nhập trực tiếp hoặc nạp bằng `/open`. Mỗi dòng có ID và mã nguồn tương ứng.

Ví dụ:

```
jshell> int taskCount = 3
jshell> int scale(int value) { return value * 2; }
jshell> record Task(String title, boolean done) {}
jshell> /list

   1 : int taskCount = 3;
   2 : int scale(int value) { return value * 2; }
   3 : record Task(String title, boolean done) {}
```

ID giúp xác định chính xác snippet khi xem hoặc thao tác với nó. Snippet do người dùng nhập thường có ID số; snippet khởi tạo của JShell thường dùng tiền tố `s`, ví dụ `s1`, `s2`.

Các dạng gọi thường dùng:

| Lệnh | Công dụng |
|---|---|
| `/list` | Liệt kê snippet đang có hiệu lực. |
| `/list <name>` | Liệt kê snippet theo tên; ưu tiên snippet đang hoạt động nếu có nhiều phiên bản. |
| `/list <id>` | Xem snippet theo ID. |
| `/list 2-5` | Xem một khoảng ID. |
| `/list -start` | Chỉ liệt kê các snippet khởi tạo đã được đánh giá. |
| `/list -all` | Liệt kê cả snippet lỗi, bị thay thế, đã drop và snippet khởi tạo. |

Dùng `/list` khi cần tìm ID trước khi truy vấn một biến, phương thức hoặc kiểu cụ thể. Nếu một snippet đã bị thay thế hoặc drop, nó không xuất hiện trong danh sách mặc định; dùng `/list -all` để xem lịch sử đầy đủ hơn.

## 3. /vars: xem biến, kiểu và giá trị

`/vars` liệt kê các biến đang có hiệu lực trong phiên. Mỗi biến được hiển thị cùng kiểu dữ liệu, tên và giá trị hiện tại.

Ví dụ:

```
jshell> int taskCount = 3
jshell> String project = "JShell"
jshell> int doubled = taskCount * 2
jshell> /vars

  int taskCount = 3
  String project = "JShell"
  int doubled = 6
```

Biến được khai báo tường minh và scratch variable do JShell tạo từ biểu thức đều có thể xuất hiện trong `/vars`, miễn là snippet tạo ra chúng còn hoạt động.

Các dạng gọi:

| Lệnh | Công dụng |
|---|---|
| `/vars` | Liệt kê các biến đang có hiệu lực. |
| `/vars <name>` | Xem biến theo tên. |
| `/vars <id>` | Xem biến được tạo bởi snippet có ID đó. |
| `/vars -start` | Liệt kê biến trong các snippet khởi tạo đã đánh giá. |
| `/vars -all` | Liệt kê biến từ cả snippet lỗi, bị thay thế, đã drop và snippet khởi tạo. |

`/vars` chỉ đọc trạng thái biến; nó không đánh giá lại biểu thức khởi tạo. Nếu muốn kiểm tra đoạn mã tạo ra một biến, dùng `/list` với ID tương ứng.

### 3.1. Giá trị biến thay đổi như thế nào?

Nếu một biến được gán giá trị mới, `/vars` hiển thị giá trị hiện tại:

```
jshell> int retries = 2
jshell> retries = 5
jshell> /vars

  int retries = 5
```

Trong ví dụ, snippet khai báo tạo biến `retries`; câu lệnh gán tiếp theo cập nhật giá trị của biến. `/vars` hiển thị trạng thái hiện tại, không phải toàn bộ lịch sử giá trị. Dùng `/history` hoặc `/list -all` khi cần xem các lần nhập mã đã tạo nên trạng thái đó.

## 4. /methods: xem chữ ký phương thức

`/methods` liệt kê các phương thức đang có hiệu lực. Kết quả thể hiện tên phương thức, kiểu tham số và kiểu trả về.

Ví dụ:

```
jshell> int scale(int value) { return value * 2; }
jshell> String label(String name, int count) {
   ...>     return name + ": " + count;
   ...> }
jshell> /methods

  int scale(int)
  String label(String,int)
```

Chữ ký giúp xác định cách gọi phương thức. Với `scale(int)`, phương thức nhận một tham số `int` và trả về `int`. Với `label(String,int)`, phương thức nhận hai tham số theo thứ tự `String`, `int` và trả về `String`.

Các dạng gọi:

| Lệnh | Công dụng |
|---|---|
| `/methods` | Liệt kê các phương thức đang có hiệu lực. |
| `/methods <name>` | Liệt kê phương thức theo tên. |
| `/methods <id>` | Xem phương thức được khai báo bởi snippet có ID đó. |
| `/methods -start` | Liệt kê phương thức trong snippet khởi tạo. |
| `/methods -all` | Liệt kê phương thức từ cả snippet lỗi, bị thay thế, đã drop và snippet khởi tạo. |

Java cho phép overload phương thức. Nếu có nhiều phương thức cùng tên nhưng khác danh sách tham số, `/methods` hiển thị từng chữ ký để bạn phân biệt.

Ví dụ:

```
jshell> int twice(int value) { return value * 2; }
jshell> int twice(int value, int factor) { return value * factor; }
jshell> /methods twice

  int twice(int)
  int twice(int,int)
```

Dùng `/methods <name>` để kiểm tra các overload theo tên; dùng `/methods <id>` khi cần xác định phương thức được tạo bởi một snippet cụ thể.

## 5. /types: xem các kiểu đã khai báo

`/types` liệt kê các khai báo kiểu đang có hiệu lực, gồm class và interface. Record cũng là một dạng class nên có thể xuất hiện trong danh sách.

Ví dụ:

```
jshell> class Ticket {}
jshell> interface Auditable { String id(); }
jshell> record Task(String title, boolean done) {}
jshell> /types

  class Ticket
  interface Auditable
  record Task
```

Các dạng gọi:

| Lệnh | Công dụng |
|---|---|
| `/types` | Liệt kê các khai báo kiểu đang có hiệu lực. |
| `/types <name>` | Xem khai báo kiểu theo tên. |
| `/types <id>` | Xem kiểu được khai báo bởi snippet có ID đó. |
| `/types -start` | Liệt kê kiểu trong snippet khởi tạo. |
| `/types -all` | Liệt kê kiểu từ cả snippet lỗi, bị thay thế, đã drop và snippet khởi tạo. |

`/types` giúp kiểm tra kiểu đã được định nghĩa trong phiên mà không cần đọc lại toàn bộ mã nguồn. Nếu cần xem phần khai báo đầy đủ, dùng `/list <id>` để lấy snippet tương ứng.

## 6. /imports: xem các import đang có hiệu lực

`/imports` liệt kê các import hiện đang có hiệu lực. Kết quả bao gồm cả import được thiết lập bởi các snippet khởi tạo của JShell.

Ví dụ:

```
jshell> import java.time.LocalDate;
/imports

  import java.io.*
  import java.math.*
  import java.net.*
  import java.nio.file.*
  import java.util.*
  import java.util.concurrent.*
  import java.util.function.*
  import java.util.prefs.*
  import java.util.regex.*
  import java.util.stream.*
  import java.time.LocalDate
```

Các import mặc định giúp dùng nhiều kiểu Java phổ biến mà không cần viết import tường minh. Tuy nhiên, không phải mọi package của Java đều được import sẵn. Ví dụ, `java.time.LocalDate` cần được import trước khi dùng tên đơn `LocalDate`.

Khác với bốn lệnh còn lại, cú pháp trợ giúp hiện hành của `/imports` chỉ cung cấp lệnh không đối số. Không có tùy chọn `-all`, `-start` hoặc bộ lọc theo tên/ID trong cú pháp lệnh được JShell hiện hành công bố. Lệnh chỉ hiển thị các import đang hoạt động, bao gồm import khởi tạo.

## 7. Kết hợp năm lệnh để hiểu toàn bộ phiên

Năm lệnh bổ sung cho nhau. Một quy trình kiểm tra hữu ích:

1. Chạy `/list` để tìm snippet và ID.
2. Chạy `/vars` để xem biến cùng giá trị.
3. Chạy `/methods` để xem chữ ký phương thức.
4. Chạy `/types` để xem các class, interface và record.
5. Chạy `/imports` để xác định các import đang có hiệu lực.
6. Dùng bộ lọc tên hoặc ID nếu cần kiểm tra một thành phần cụ thể.
7. Dùng tùy chọn `-all` hoặc `-start` ở các lệnh hỗ trợ khi cần kiểm tra snippet đã drop, bị thay thế hoặc snippet khởi tạo.

Ví dụ hoàn chỉnh dưới đây tạo một số thành phần rồi chạy cả năm lệnh.

**InspectionDemo.jsh**

```
import java.time.LocalDate;

int taskCount = 3;
String project = "JShell";
int doubled = taskCount * 2;

int scale(int value) {
    return value * 2;
}

record Task(String title, boolean done) {}

List<Task> tasks = List.of(
        new Task("Read", true),
        new Task("Build", false)
);

LocalDate releaseDate = LocalDate.of(2025, 1, 1);

/list
/vars
/methods
/types
/imports

/vars taskCount
/methods scale
/types Task
/list 2

/exit
```

Chạy bằng JDK:

```
jshell --feedback concise InspectionDemo.jsh
```

Một phần output quan sát được trên JDK 24:

```
   1 : import java.time.LocalDate;
   2 : int taskCount = 3;
   3 : String project = "JShell";
   4 : int doubled = taskCount * 2;
   5 : int scale(int value) { return value * 2; }
   6 : record Task(String title, boolean done) {}
   7 : List<Task> tasks = List.of(new Task("Read", true), new Task("Build", false));
   8 : LocalDate releaseDate = LocalDate.of(2025, 1, 1);

  int taskCount = 3
  String project = "JShell"
  int doubled = 6
  List<Task> tasks = [Task[title=Read, done=true], Task[title=Build, done=false]]
  LocalDate releaseDate = 2025-01-01
  int scale(int)
  record Task
  import java.time.LocalDate
```

Trong phiên này:

- `/list` hiển thị tám snippet do người dùng nhập.
- `/vars` hiển thị năm biến và giá trị hiện tại.
- `/methods` hiển thị chữ ký `scale(int)`.
- `/types` hiển thị `record Task`.
- `/imports` hiển thị các import mặc định cùng `java.time.LocalDate`.
- `/vars taskCount`, `/methods scale`, `/types Task` và `/list 2` minh họa cách lọc theo tên hoặc ID.

Output có thể có khác biệt nhỏ về cách căn lề hoặc cách hiển thị giá trị object giữa các phiên bản JDK và feedback mode. Các loại thông tin và chữ ký được minh họa là kết quả thực tế của JShell.

## 8. Phân biệt trạng thái đang hoạt động và lịch sử snippet

Mặc định, các lệnh `/list`, `/vars`, `/methods` và `/types` tập trung vào nội dung đang có hiệu lực. Khi một khai báo bị thay thế hoặc drop, nó có thể biến mất khỏi kết quả mặc định.

Các tùy chọn `-all` và `-start` giúp mở rộng phạm vi kiểm tra:

- `-all` bao gồm snippet lỗi, bị thay thế, đã drop và snippet khởi tạo.
- `-start` chỉ tập trung vào snippet khởi tạo đã được đánh giá.

Ví dụ:

```
jshell> int score = 10;
jshell> int score = 20;
/vars
  int score = 20

/vars -all
  int score = (not-active)
  int score = 20
```

Khi một biến được khai báo lại, khai báo trước bị thay thế. `/vars` cho biết biến đang hoạt động; `/vars -all` cho phép nhìn thấy cả phiên bản cũ. Tương tự, `/list -all` hữu ích khi cần xem toàn bộ snippet đã nhập, còn `/list -start` dùng để xem các snippet khởi tạo.

Không phải lệnh nào trong nhóm cũng hỗ trợ cùng một tùy chọn. `/imports` chỉ liệt kê import hiện hành và không có dạng `-all` hoặc `-start`. Hãy dùng `/help` hoặc trợ giúp của từng lệnh để xác nhận cú pháp trên JDK đang chạy.

## 9. Lỗi thường gặp và cách tránh

1. **Dùng `/list` để tìm giá trị biến:** `/list` hiển thị mã nguồn snippet; dùng `/vars` để xem giá trị hiện tại.
2. **Dùng `/vars` để tìm chữ ký phương thức:** dùng `/methods` để xem tên, tham số và kiểu trả về.
3. **Nghĩ `/types` chỉ liệt kê class:** interface và record cũng có thể xuất hiện.
4. **Cho rằng `/imports` chỉ hiển thị import do người dùng nhập:** kết quả còn gồm các import mặc định từ snippet khởi tạo.
5. **Không tìm thấy snippet đã drop:** kiểm tra `/list -all`; mặc định chỉ liệt kê snippet đang hoạt động.
6. **Không thấy khai báo cũ sau khi ghi đè:** dùng `/vars -all`, `/methods -all` hoặc `/types -all` phù hợp để xem các mục đã bị thay thế.
7. **Dùng tùy chọn không được hỗ trợ:** `/imports` không có `-all`, `-start` hay bộ lọc tên. Kiểm tra `/help /imports` khi cần xác nhận.
8. **Nhầm ID snippet với số thứ tự của biến:** ID gắn với snippet nguồn. Dùng `/list` để xác định ID trước khi lọc theo ID.

## 10. Ghi nhớ

- `/list` xem mã nguồn snippet và ID.
- `/vars` xem biến đang hoạt động cùng kiểu và giá trị.
- `/methods` xem chữ ký phương thức, gồm tên, kiểu tham số và kiểu trả về.
- `/types` xem class, interface và record đã khai báo.
- `/imports` xem import hiện đang có hiệu lực, bao gồm import khởi tạo.
- Bộ lọc tên/ID và tùy chọn `-all`, `-start` giúp truy vấn sâu hơn ở bốn lệnh đầu; `/imports` chỉ có dạng liệt kê import hiện hành.
- Kết hợp năm lệnh giúp kiểm tra trạng thái phiên mà không phải chạy lại các snippet.