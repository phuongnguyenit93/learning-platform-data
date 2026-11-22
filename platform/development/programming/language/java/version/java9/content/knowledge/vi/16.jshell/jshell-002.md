# Snippet, biến kết quả tạm và trạng thái phiên làm việc trong JShell

JShell là công cụ tương tác trong JDK, cho phép nhập, đánh giá và thử mã Java từng phần. Công cụ này hữu ích khi kiểm tra biểu thức, thử API, khai báo biến hoặc phương thức nhỏ và khám phá cách một kiểu dữ liệu hoạt động. JShell được đưa vào JDK từ Java 9 và vẫn có trong các JDK hiện hành.

Ba khái niệm liên kết với nhau trong một phiên JShell:

- **Snippet** là đơn vị mã hoặc lệnh mà JShell tiếp nhận và quản lý.
- **Biến kết quả tạm (scratch variable)** là biến do JShell tạo để giữ kết quả của một biểu thức có giá trị chưa được gán vào biến do người dùng đặt tên.
- **Trạng thái phiên (session state)** là các khai báo, biến, phương thức, kiểu và snippet còn hiệu lực trong tiến trình JShell hiện tại.

## 1. Snippet là đơn vị mã của JShell

Khi nhập mã, JShell phân tích đầu vào thành snippet. Mỗi snippet có một ID trong phiên để có thể xem, lưu, thay thế hoặc loại bỏ riêng.

| Loại | Ví dụ | Tác dụng |
|---|---|---|
| Import | `import java.time.LocalDate;` | Cho phép dùng kiểu được import trong các lần nhập sau. |
| Khai báo biến | `int retryCount = 3;` | Tạo biến có tên `retryCount`. |
| Khai báo phương thức | `int square(int n) { return n * n; }` | Định nghĩa phương thức có thể gọi ở snippet khác. |
| Khai báo kiểu | `record Point(int x, int y) {}` | Đưa kiểu vào trạng thái phiên. |
| Câu lệnh | `System.out.println("Hello");` | Thực thi hành động, có thể tạo output hoặc tác dụng phụ. |
| Biểu thức | `retryCount * 2` | Đánh giá biểu thức; nếu có giá trị, JShell lưu kết quả bằng scratch variable. |

JShell cho phép nhập trực tiếp khai báo, câu lệnh và biểu thức ở cấp cao nhất, không cần viết lớp chứa phương thức `main` như khi chạy chương trình Java thông thường.

Các lệnh điều khiển của JShell bắt đầu bằng dấu `/`, ví dụ `/list`, `/vars` và `/reset`. Đây là lệnh của công cụ, không phải cú pháp Java. Chúng thao tác trên trạng thái phiên hoặc lịch sử nhập mã.

## 2. Biến kết quả tạm (scratch variable)

Khi một biểu thức trả về giá trị và người dùng không gán giá trị đó cho biến có tên, JShell tạo một scratch variable để giữ kết quả. Tên biến có dạng `$` theo sau bởi ID của snippet, ví dụ `$1`, `$2`, `$4`.

Ví dụ nhập lần lượt:

```
8 + 5
$1 * 2
String language = "Java";
language.substring(0, 2)
System.out.println("side effect")
/vars
```

JShell hiển thị các giá trị:

```
int $1 = 13
int $2 = 26
String language = "Java"
String $4 = "Ja"
```

Cách đọc kết quả:

1. Biểu thức `8 + 5` tạo snippet số 1 và scratch variable `$1` có giá trị `13`.
2. Biểu thức `$1 * 2` tạo snippet số 2, đọc `$1` và lưu kết quả `26` vào `$2`.
3. Khai báo `String language = "Java";` tạo biến có tên `language`. Đây là snippet số 3, không tạo scratch variable.
4. Biểu thức `language.substring(0, 2)` tạo snippet số 4 và biến kết quả `$4` có giá trị `"Ja"`.
5. `System.out.println(...)` là câu lệnh trả về `void`. Nó in dòng `side effect` ra output và không tạo biến kết quả tạm.

ID của scratch variable gắn với ID snippet đã tạo ra nó. Dãy tên có thể không liên tiếp: khai báo biến hoặc câu lệnh có thể chiếm ID nhưng không tạo scratch variable. Không nên hiểu `$1`, `$2` là bộ đếm riêng cho số biểu thức có kết quả.

Scratch variable có kiểu cụ thể và có thể được tham chiếu trong các snippet tiếp theo của cùng phiên. Ví dụ, sau khi tạo `$1`, bạn có thể nhập `$1 + 100` để tính tiếp mà không cần khai báo biến trung gian mới.

Scratch variable thuộc trạng thái của JShell. Khi snippet tạo ra biến bị loại bỏ, bị thay thế hoặc phiên bị reset, trạng thái của biến tương ứng cũng thay đổi. Đây là tên biến phục vụ tương tác; không nên đưa tên `$1` vào mã nguồn ứng dụng Java thông thường.

### 2.1. Biểu thức, khai báo và câu lệnh

| Đầu vào | Scratch variable? | Giải thích |
|---|---|---|
| `40 + 2` | Có | Biểu thức trả về một giá trị số. |
| `"Java".length()` | Có | Biểu thức trả về giá trị kiểu `int`. |
| `String name = "Ada";` | Không | Đây là khai báo biến có tên `name`. |
| `System.out.println("Hi");` | Không | Đây là câu lệnh có kiểu trả về `void`. |
| `new java.util.ArrayList<String>()` | Có | Biểu thức tạo và trả về một object. |

Nếu kết quả sẽ được dùng nhiều lần hoặc cần tên dễ hiểu, hãy khai báo biến tường minh:

```
int total = 40 + 2;
String upperName = "Ada".toUpperCase();
```

Cách này làm rõ ý nghĩa dữ liệu và giúp các snippet tiếp theo dễ đọc hơn.

## 3. Kiểm tra trạng thái bằng các lệnh JShell

| Lệnh | Công dụng |
|---|---|
| `/vars` | Liệt kê các biến đang có hiệu lực cùng kiểu và giá trị. |
| `/vars <name>` | Xem biến theo tên. |
| `/list` | Liệt kê các snippet mã đang có hiệu lực, kèm ID và nội dung. |
| `/list <id>` | Xem snippet theo ID. |
| `/list -all` | Liệt kê cả snippet khởi tạo, lỗi, bị thay thế và đã drop. |
| `/methods` | Liệt kê các phương thức đã khai báo. |
| `/types` | Liệt kê các kiểu đã khai báo. |
| `/imports` | Liệt kê các import hiện có hiệu lực. |
| `/history` | Hiển thị lịch sử lệnh và snippet đã nhập trong phiên. |

`/vars` và `/list` cung cấp hai góc nhìn khác nhau:

- `/vars` cho biết hiện có thể tham chiếu những biến nào, kiểu và giá trị của chúng.
- `/list` cho biết những snippet nào đã tạo nên trạng thái hiện tại, cùng ID và mã nguồn tương ứng.

Ví dụ:

```
int quantity = 4;
quantity * 3
String label = "Order";
label.toLowerCase()
/vars
/list
```

Sau khi đánh giá, `/vars` liệt kê `quantity`, `label` và scratch variable do hai biểu thức tạo ra. `/list` cho biết các snippet khai báo và biểu thức theo ID. Dùng ID hiển thị để xem một snippet cụ thể thay vì đoán thứ tự.

## 4. Thay đổi và loại bỏ snippet

Trạng thái phiên được cập nhật khi JShell đánh giá snippet. Khai báo biến, phương thức và kiểu có thể được sử dụng trong các lần nhập tiếp theo. Khi thay thế hoặc loại bỏ một snippet, các thành phần tương ứng không còn hoạt động theo trạng thái mới.

### 4.1. Dùng /drop

Lệnh `/drop` loại bỏ một snippet theo tên hoặc ID. Ví dụ:

```
int price = 100;
price + 20
/vars
/drop price
/vars
```

Trước khi drop, `/vars` liệt kê biến `price` và scratch variable được tạo bởi biểu thức. Sau khi drop khai báo `price`, biến có tên đó không còn hiệu lực.

Scratch variable được tạo bởi biểu thức là snippet riêng. Nếu nó đã chứa kết quả tính toán, giá trị đó có thể tiếp tục tồn tại dù biến nguồn bị drop. Sau khi drop, hãy dùng `/vars` và `/list` để kiểm tra trạng thái thực tế.

Có thể dùng `/drop 1` để loại bỏ snippet có ID 1. Nên xem `/list` trước để xác định chính xác ID hoặc tên cần thao tác.

### 4.2. Dùng /reset

`/reset` xóa các mã đã nhập khỏi trạng thái thực thi của JShell và khởi động lại execution state. Các snippet khởi tạo được chạy lại. Biến, phương thức, kiểu và scratch variable do người dùng tạo trong phần tương tác trước đó không còn hoạt động.

Đây là thao tác làm mới toàn bộ trạng thái phiên. Trước khi reset, nếu cần giữ mã đã nhập, hãy lưu snippet hoặc lịch sử ra file.

### 4.3. Dùng /reload

`/reload` khởi động lại trạng thái rồi phát lại các snippet hợp lệ cùng lệnh drop trong lịch sử tương ứng. Tùy chọn `/reload -restore` hỗ trợ khôi phục đoạn lịch sử giữa các mốc phiên theo cơ chế của JShell.

`/reset` bắt đầu lại trạng thái mặc định; `/reload` dựng lại trạng thái bằng cách đánh giá lại lịch sử. Chọn lệnh dựa trên việc bạn muốn xóa phiên hay tái tạo phiên trước đó.

## 5. Lưu và nạp snippet

JShell có các lệnh để lưu mã nguồn hoặc lịch sử:

- `/save <file>` lưu các snippet đang có hiệu lực vào file.
- `/save -all <file>` lưu tất cả snippet, bao gồm cả snippet lỗi, bị thay thế, đã drop và snippet khởi tạo.
- `/save -history <file>` lưu lịch sử tuần tự của các lệnh và snippet đã nhập kể từ khi JShell được khởi chạy.
- `/save <id> <file>` lưu một hoặc nhiều snippet được chọn theo ID.
- `/open <file>` đọc file và nạp nội dung như đầu vào JShell.

Ví dụ:

```
/save active-snippets.jsh
/save -history session-history.txt
/open active-snippets.jsh
```

`/save` lưu mã nguồn để có thể sử dụng lại; `/save -history` lưu chuỗi lệnh theo thứ tự đã nhập. `/open` đánh giá nội dung file trong phiên hiện tại. File không phải bản chụp toàn bộ bộ nhớ: các object đang tồn tại, trạng thái hệ thống bên ngoài và tác dụng phụ đã xảy ra không tự được tuần tự hóa.

Nếu file có lệnh JShell như `/drop` hoặc `/reset`, các lệnh đó cũng được xử lý khi nạp. Hãy xem nội dung file trước khi mở để biết những thao tác sẽ được thực hiện.

## 6. Ví dụ thực hành có thể chạy

Tạo file `ScratchSessionDemo.jsh`:

```
8 + 5
$1 * 2
String language = "Java";
language.substring(0, 2)
System.out.println("side effect")
/vars
/list
/drop 1
/vars
/reset
/vars
/exit
```

Chạy bằng JDK:

```
jshell --feedback concise ScratchSessionDemo.jsh
```

Output quan sát được:

```
side effect
  int $1 = 13
  int $2 = 26
  String language = "Java"
  String $4 = "Ja"

   1 : 8 + 5
   2 : $1 * 2
   3 : String language = "Java";
   4 : language.substring(0, 2)
   5 : System.out.println("side effect")
  int $2 = 26
  String language = "Java"
  String $4 = "Ja"
```

Giải thích:

1. Snippet 1 tính `8 + 5` và tạo `$1 = 13`.
2. Snippet 2 sử dụng `$1`, tạo `$2 = 26`.
3. Snippet 3 khai báo biến `language`, không tạo scratch variable.
4. Snippet 4 trả về `"Ja"` trong `$4`; ID 3 đã được dùng cho khai báo nên số biến tạm bị khuyết.
5. Snippet 5 in `side effect`. Vì phương thức trả về `void`, không có biến kết quả.
6. `/vars` hiển thị các biến đang hoạt động; `/list` hiển thị mã và ID snippet.
7. `/drop 1` loại bỏ snippet đầu tiên, vì thế `$1` biến mất. `$2` vẫn giữ giá trị đã tính là 26.
8. `/reset` xóa trạng thái mã tương tác; `/vars` sau reset không còn biến do người dùng tạo.

Transcript có thể thay đổi phần căn lề hoặc thông tin phụ theo JDK và feedback mode. Các giá trị, ID snippet và thay đổi trạng thái trong ví dụ đã được kiểm tra trên JDK 24 với feedback mode `concise`.

## 7. Lỗi thường gặp

1. **Cho rằng `$1`, `$2` đếm riêng số biểu thức:** tên scratch variable dựa trên ID snippet. Khai báo biến hoặc snippet khác có thể khiến số bị khuyết.
2. **Nhầm scratch variable với biến đã khai báo:** scratch variable do JShell sinh ra; biến có tên do người dùng khai báo giúp mã dễ hiểu hơn.
3. **Nghĩ rằng mọi đầu vào đều tạo biến tạm:** khai báo không tạo scratch variable; câu lệnh trả về `void` cũng không tạo biến kết quả.
4. **Dùng `/vars` để xem mã nguồn:** `/vars` chỉ tập trung vào biến; dùng `/list` để xem snippet.
5. **Drop theo ID mà không kiểm tra:** dùng `/list` để xác nhận ID và nội dung trước khi gọi `/drop`.
6. **Reset trước khi lưu công việc:** `/reset` xóa trạng thái thực thi. Dùng `/save` hoặc `/save -history` nếu cần giữ mã và lệnh.
7. **Coi file đã lưu là bản sao bộ nhớ:** file chỉ chứa mã nguồn hoặc lịch sử; object và tác dụng phụ runtime không được lưu thành snapshot.
8. **Không kiểm tra tác dụng phụ khi nạp lại:** `/open` và `/reload` đánh giá lại mã, nên các lệnh in, ghi file hoặc thao tác bên ngoài có thể chạy lại.

## 8. Ghi nhớ

- Snippet là đơn vị mã hoặc lệnh JShell quản lý bằng ID.
- Biểu thức có giá trị có thể tạo scratch variable tên theo ID snippet, ví dụ `$1`.
- Khai báo có tên, phương thức và kiểu dữ liệu được giữ trong trạng thái phiên.
- `/vars` xem biến; `/list` xem snippet; `/drop` loại bỏ snippet.
- `/reset` làm mới trạng thái; `/reload` phát lại lịch sử; `/save` và `/open` lưu, nạp mã và lệnh.
- Trạng thái trong bộ nhớ thuộc phiên JShell đang chạy. Muốn tái sử dụng ở phiên khác, lưu mã hoặc lịch sử và nạp lại khi cần.