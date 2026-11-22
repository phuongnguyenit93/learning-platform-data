# Thứ tự phần tử, phần tử trùng và chi phí truy cập theo vị trí

## 1. Redis List biểu diễn điều gì?

Trong Spring Data Redis, **List** là một cấu trúc dữ liệu Redis lưu **chuỗi phần tử có thứ tự** dưới một key. Nó phù hợp với những thao tác lấy hoặc thêm phần tử ở đầu/cuối, ví dụ hàng đợi tác vụ đơn giản, chuỗi sự kiện gần đây, danh sách công việc chờ xử lý hay một ngăn xếp (stack).

Ba đặc điểm quyết định cách sử dụng Redis List:

1. **Thứ tự có ý nghĩa:** phần tử đầu, phần tử cuối và vị trí tương đối được Redis duy trì theo thứ tự lệnh đã thực thi.
2. **Phần tử trùng được phép:** một giá trị có thể xuất hiện nhiều lần; Redis List không tự loại trùng như Redis Set.
3. **Truy cập theo vị trí có chi phí khác nhau:** thêm/xóa ở hai đầu thường nhanh, còn truy cập phần tử ở sâu trong danh sách phải đi qua các phần tử trung gian.

Ví dụ:

~~~text
Key: lesson:list:orders

Đầu (left/head)                           Cuối (right/tail)
     |                                           |
     v                                           v
  [order-A] -> [order-B] -> [order-A] -> [order-C]
     0            1            2            3
    -4           -3           -2           -1
~~~

List trên có **4 phần tử**, trong đó **order-A xuất hiện 2 lần**. Chỉ số **0** trỏ đến phần tử đầu, chỉ số **-1** trỏ đến phần tử cuối. Đây là hai cách đánh số vị trí khác nhau trong cùng một danh sách.

Trong ứng dụng Java, API tương ứng là **ListOperations** được truy cập qua **RedisTemplate.opsForList()** hoặc **StringRedisTemplate.opsForList()**.

## 2. Khác biệt giữa Redis List và các cấu trúc dễ nhầm

| Cấu trúc | Thứ tự | Có cho phép giá trị/member trùng? | Trường hợp phù hợp |
| --- | --- | --- | --- |
| **Redis List** | Có, theo thứ tự phần tử được chèn và thao tác | **Có** | Hàng đợi đơn giản, stack, danh sách hoạt động gần đây |
| **Redis Set** | Không bảo đảm thứ tự | **Không** | Kiểm tra membership, loại trùng |
| **Redis Sorted Set** | Có, theo score và quy tắc sắp xếp | Member duy nhất; ghi lại member sẽ cập nhật score | Leaderboard, xếp hạng |
| **Redis Stream** | Entry có ID, đọc theo dòng sự kiện | Payload có thể trùng; mỗi entry có ID riêng | Luồng sự kiện cần consumer group và acknowledgment |
| **Java List trong JVM** | Có | Có | Dữ liệu nội bộ một tiến trình Java |

Điểm đáng chú ý là Redis List lưu dữ liệu **trên Redis Server** và có thể được nhiều instance Spring Boot truy cập đồng thời. Java List thông thường chỉ tồn tại trong tiến trình ứng dụng, trừ khi được đồng bộ bằng cơ chế khác.

Redis không tự hiểu phần tử **order-A** là “một đơn hàng duy nhất” hay “hai lượt xử lý của cùng đơn hàng”. Redis chỉ lưu chuỗi bytes tương ứng ở hai vị trí. Quy tắc nghiệp vụ về trùng lặp phải do ứng dụng quyết định.

## 3. Thứ tự của List hình thành từ các lệnh thêm phần tử

### 3.1. RPUSH thêm vào bên phải

Trong **redis-cli tương tác**, chạy:

~~~text
RPUSH lesson:row132:queue A B C
LRANGE lesson:row132:queue 0 -1
~~~

Kết quả danh sách:

~~~text
[A, B, C]
~~~

**RPUSH key value ...** thêm phần tử vào **cuối** theo thứ tự xuất hiện trong lệnh. Giá trị trả về là độ dài List sau thao tác.

Nếu tiếp tục:

~~~text
RPUSH lesson:row132:queue D
LRANGE lesson:row132:queue 0 -1
~~~

Kết quả:

~~~text
[A, B, C, D]
~~~

Đây là cách dễ đọc khi muốn **giữ thứ tự đầu vào** trong một lần thêm nhiều phần tử.

### 3.2. LPUSH thêm vào bên trái

Nếu từ danh sách hiện tại gọi:

~~~text
LPUSH lesson:row132:queue urgent
LRANGE lesson:row132:queue 0 -1
~~~

Kết quả:

~~~text
[urgent, A, B, C, D]
~~~

**LPUSH** thêm vào **đầu**. Khi truyền **nhiều value trong cùng một LPUSH**, từng value được thêm vào đầu theo thứ tự lệnh xử lý, nên thứ tự nhìn từ trái sang phải bị đảo so với chuỗi tham số:

~~~text
DEL lesson:row132:multi
LPUSH lesson:row132:multi A B C
LRANGE lesson:row132:multi 0 -1
~~~

Kết quả:

~~~text
[C, B, A]
~~~

Đối chiếu:

~~~text
DEL lesson:row132:multi
RPUSH lesson:row132:multi A B C
LRANGE lesson:row132:multi 0 -1
~~~

Kết quả là **[A, B, C]**.

Điều này rất quan trọng khi đọc **leftPushAll(...)** trong Spring Data Redis: nếu bạn kỳ vọng danh sách giữ nguyên thứ tự mảng đầu vào từ trái sang phải, hãy xác định rõ đang thêm ở đầu hay cuối.

### 3.3. Thêm, lấy và xóa là các hành vi khác nhau

| Lệnh | Phần tử bị tác động | Có lấy/xóa phần tử khỏi List? |
| --- | --- | --- |
| **LPUSH** | Thêm vào đầu | Không xóa phần tử đang có |
| **RPUSH** | Thêm vào cuối | Không xóa phần tử đang có |
| **LINDEX** | Đọc tại vị trí | **Chỉ đọc** |
| **LRANGE** | Đọc một đoạn | **Chỉ đọc** |
| **LPOP** | Đầu danh sách | **Lấy và xóa** phần tử đầu |
| **RPOP** | Cuối danh sách | **Lấy và xóa** phần tử cuối |
| **LSET** | Vị trí được chỉ định | Ghi đè value tại vị trí đó |
| **LINSERT** | Trước/sau một pivot | Chèn phần tử và dịch các vị trí về sau |
| **LREM** | Những phần tử có value khớp | Xóa một hoặc nhiều lần xuất hiện |
| **LTRIM** | Chỉ giữ phạm vi được chỉ định | Xóa các phần tử ngoài phạm vi |

Không nên nhìn vào tên lệnh “left/right” rồi tự suy ra thứ tự FIFO/LIFO: cần xem **đầu được ghi** và **đầu được đọc/xóa** trong từng workflow.

## 4. Chỉ số vị trí: dương, âm và đoạn bao gồm hai đầu

Redis List hỗ trợ chỉ số:

- **0** là phần tử đầu.
- **1** là phần tử thứ hai.
- **-1** là phần tử cuối.
- **-2** là phần tử kế cuối.
- Nếu index nằm ngoài độ dài List, **LINDEX** trả nil.

Tạo dữ liệu:

~~~text
RPUSH lesson:row132:index apple banana cherry date
~~~

Các lệnh đọc:

~~~text
LINDEX lesson:row132:index 0
LINDEX lesson:row132:index 2
LINDEX lesson:row132:index -1
LINDEX lesson:row132:index -2
LINDEX lesson:row132:index 99
~~~

Kỳ vọng lần lượt là **apple**, **cherry**, **date**, **cherry** và **nil**.

### 4.1. LRANGE sử dụng cả start và stop

~~~text
LRANGE lesson:row132:index 0 -1
LRANGE lesson:row132:index 0 1
LRANGE lesson:row132:index 1 2
LRANGE lesson:row132:index -2 -1
~~~

Giải thích:

| Lệnh LRANGE | Phạm vi nhận được |
| --- | --- |
| 0 -1 | Toàn bộ List: apple, banana, cherry, date |
| 0 1 | Hai phần tử đầu: apple, banana |
| 1 2 | Phần tử thứ hai và thứ ba: banana, cherry |
| -2 -1 | Hai phần tử cuối: cherry, date |

**Stop của LRANGE là inclusive**, nghĩa là phần tử ở chỉ số stop cũng được lấy nếu nằm trong List. Đây là khác biệt dễ nhầm với nhiều API Java dùng end-exclusive.

Nếu start vượt quá chiều dài hoặc đoạn không có phần tử hợp lệ, LRANGE trả một danh sách rỗng. Chỉ số âm không mang ý nghĩa đảo thứ tự; chúng chỉ giúp định vị phần tử tính từ phía cuối.

### 4.2. LSET ghi đè tại một vị trí đang tồn tại

~~~text
LSET lesson:row132:index 1 blueberry
LRANGE lesson:row132:index 0 -1
~~~

Danh sách trở thành:

~~~text
[apple, blueberry, cherry, date]
~~~

**LSET** thay thế value tại chỉ số 1, **không thêm phần tử mới**. Nếu chỉ số nằm ngoài phạm vi, Redis báo lỗi **index out of range**; LSET không tự mở rộng List tới vị trí yêu cầu.

### 4.3. Chỉ số là vị trí hiện tại, không phải ID ổn định

Giả sử ứng dụng thấy **banana** ở index 1. Một client khác LPUSH một value mới; banana sẽ dịch sang index 2. Nếu ứng dụng sau đó gọi LSET tại index 1 với ý nghĩ đang sửa banana, nó có thể ghi đè **nhầm phần tử**.

~~~text
Ban đầu:            [apple, banana, cherry]
Client A đọc index 1     -> banana
Client B LPUSH urgent    -> [urgent, apple, banana, cherry]
Client A LSET index 1    -> ghi đè apple, không phải banana
~~~

Vì vậy **không dùng index như khóa định danh lâu dài của bản ghi** trong hệ thống có nhiều writer. Nếu cần cập nhật một thực thể theo ID, mô hình Hash/key riêng hoặc một cấu trúc có định danh ổn định có thể phù hợp hơn.

## 5. Redis List cho phép phần tử trùng

Tạo List:

~~~text
RPUSH lesson:row132:duplicates A B A C A
LRANGE lesson:row132:duplicates 0 -1
LLEN lesson:row132:duplicates
~~~

Redis lưu đầy đủ:

~~~text
[A, B, A, C, A]
~~~

Và **LLEN** trả **5**, không phải 3. List không loại các bản sao của A.

Nếu hệ thống theo dõi lần mở trang và một người dùng mở cùng URL ba lần, ba entry giống nhau có thể hợp lệ. Ngược lại, nếu List đang đại diện cho “những tác vụ duy nhất chờ thực hiện”, ba entry giống nhau có thể tạo việc xử lý lặp.

### 5.1. LPOS tìm vị trí của value

~~~text
LPOS lesson:row132:duplicates A
LPOS lesson:row132:duplicates B
LPOS lesson:row132:duplicates missing
LPOS lesson:row132:duplicates A COUNT 0
~~~

Ở trạng thái trên:

- LPOS tìm **A** đầu tiên thường trả vị trí **0**.
- LPOS tìm **B** trả **1**.
- Value không tồn tại trả nil.
- Với **COUNT 0** ở những phiên bản Redis hỗ trợ LPOS và tùy chọn COUNT, Redis có thể trả **toàn bộ các vị trí khớp** theo thứ tự tìm kiếm.

Không nên quét toàn List liên tục để kiểm tra một phần tử có tồn tại khi List rất lớn; **LPOS có chi phí tìm kiếm tuyến tính theo số phần tử cần duyệt**. Nếu mục đích chủ yếu là kiểm tra membership hoặc loại trùng, **Redis Set** thường là cấu trúc phù hợp hơn.

### 5.2. LREM xóa những lần xuất hiện phù hợp

LREM có dạng:

~~~text
LREM key count value
~~~

Ý nghĩa **count**:

| count | Cách xóa |
| --- | --- |
| **count > 0** | Xóa tối đa count phần tử khớp, xét từ **đầu sang cuối**. |
| **count < 0** | Xóa tối đa trị tuyệt đối của count phần tử khớp, xét từ **cuối về đầu**. |
| **count = 0** | Xóa **tất cả** những phần tử có value khớp. |

Ví dụ:

~~~text
RPUSH lesson:row132:remove A B A C A
LREM lesson:row132:remove 1 A
LRANGE lesson:row132:remove 0 -1
~~~

Kết quả:

~~~text
[B, A, C, A]
~~~

Chỉ **A đầu tiên** bị xóa. Tiếp tục:

~~~text
LREM lesson:row132:remove -1 A
LRANGE lesson:row132:remove 0 -1
~~~

Kết quả:

~~~text
[B, A, C]
~~~

Lần này xóa **A cuối cùng**. Cuối cùng:

~~~text
LREM lesson:row132:remove 0 A
LRANGE lesson:row132:remove 0 -1
~~~

Kết quả:

~~~text
[B, C]
~~~

**LREM so sánh value**, không phân biệt hai entry trùng value bằng ID độc lập. Nếu mỗi lần xuất hiện là một sự kiện riêng, việc xóa theo value có thể xóa nhầm hoặc xóa quá nhiều sự kiện.

### 5.3. Kiểm tra trước rồi LPUSH không bảo đảm duy nhất

Một cách triển khai sai ý định loại trùng:

~~~java
if (redis.opsForList().index("lesson:row132:tasks", 0) == null) {
    redis.opsForList().leftPush("lesson:row132:tasks", "job-42");
}
~~~

Đoạn code trên chỉ nhìn phần tử ở index 0 và **không kiểm tra toàn List**; ngay cả khi dùng LPOS để tìm trong toàn List thì bước **kiểm tra rồi thêm** vẫn gồm nhiều lệnh riêng. Hai request có thể cùng thấy chưa tồn tại rồi cùng thêm **job-42**.

Nếu cần danh sách duy nhất, hãy thiết kế ràng buộc ở nơi phù hợp, ví dụ kết hợp Set và List trong một Lua script/transaction theo quy tắc riêng, hoặc dùng Redis Set nếu thứ tự không quan trọng. Đừng kỳ vọng Redis List tự bảo đảm uniqueness.

## 6. Chi phí truy cập theo vị trí: vì sao O(1) và O(N) khác nhau?

Trong phân tích thuật toán, **N** là số phần tử trong List. Ký hiệu:

- **O(1)**: chi phí không tăng tuyến tính theo số phần tử; thao tác tập trung vào đầu/cuối thường có tính chất này.
- **O(N)**: trong trường hợp xấu nhất, cần duyệt qua số phần tử tỷ lệ với độ dài List.
- **O(S + M)**: mô tả thao tác lấy một đoạn, gồm chi phí đi tới vị trí bắt đầu và chi phí trả **M phần tử**.

Redis hiện đại tổ chức List bằng cấu trúc tối ưu cho thao tác ở hai đầu, thường gồm các khối dữ liệu nằm trong một quicklist. Chi tiết nội bộ có thể thay đổi theo phiên bản, cấu hình và độ dài List, nhưng **mô hình chi phí của các lệnh** mới là điều quan trọng khi thiết kế.

### 6.1. Bảng chi phí của những thao tác thường gặp

| Lệnh | Độ phức tạp điển hình | Ý nghĩa thực tế |
| --- | --- | --- |
| **LPUSH / RPUSH** | O(1) cho mỗi phần tử | Thêm ở đầu/cuối phù hợp với List dài. |
| **LPOP / RPOP** | O(1) cho mỗi phần tử | Lấy và loại bỏ phần tử đầu/cuối nhanh. |
| **LLEN** | O(1) | Đọc độ dài không cần duyệt toàn bộ phần tử. |
| **LINDEX** | O(N) trong trường hợp xấu nhất | Phải đi tới vị trí cần đọc; gần đầu/cuối thường rẻ hơn. |
| **LSET** | O(N) trong trường hợp xấu nhất | Cần tìm tới vị trí trước khi ghi đè value. |
| **LRANGE** | O(S + M) | Tốn công tìm điểm bắt đầu và trả M phần tử. |
| **LPOS** | O(N) trong trường hợp xấu nhất | Tìm value bằng cách duyệt danh sách. |
| **LINSERT** | O(N) | Tìm pivot, rồi chèn trước/sau pivot. |
| **LREM** | O(N + M) theo mô tả thuật toán | Duyệt tìm value và xóa các lần xuất hiện cần thiết. |
| **LTRIM** | Phụ thuộc số phần tử bị loại bỏ | Cần loại các phần tử nằm ngoài đoạn giữ lại. |

**Chú ý:** đây là độ phức tạp theo số phần tử và hình thức truy cập, không phải cam kết rằng mỗi lệnh luôn có độ trễ bằng một con số cố định. Kích thước value, đường truyền mạng, serialization, áp lực CPU/bộ nhớ và cấu hình Redis vẫn ảnh hưởng thời gian thực tế.

### 6.2. Vì sao LINDEX 0 khác LINDEX giữa List?

Giả sử một List có một triệu phần tử:

~~~text
LINDEX very:large:list 0
LINDEX very:large:list -1
LINDEX very:large:list 500000
~~~

Đọc phần tử đầu hoặc cuối có thể tận dụng cấu trúc dữ liệu của Redis để truy cập rất gần hai đầu. Nhưng đọc phần tử ở khoảng giữa cần **đi tới vị trí đó** bằng cách duyệt các phần tử/khối trung gian.

Trong trường hợp xấu nhất, chi phí theo độ dài List là **O(N)**. Vì vậy Redis List **không nên được xem như một mảng Java cho phép truy cập ngẫu nhiên O(1) tại mọi chỉ số**.

Số chỉ mục lớn không đồng nghĩa phải duyệt từ đầu trong mọi phiên bản/cấu trúc nội bộ: Redis có thể chọn hướng gần hơn từ đầu hoặc cuối. Điều cần ghi nhớ vẫn là **truy cập sâu vào giữa List có thể đắt hơn nhiều so với thao tác ở hai đầu**.

### 6.3. Vì sao LRANGE 0 -1 có thể gây tải?

~~~text
LRANGE very:large:list 0 -1
~~~

Lệnh trên yêu cầu **toàn bộ phần tử**. Dù chi phí tìm phần tử bắt đầu rất thấp, Redis vẫn phải đọc, tạo kết quả và truyền **N phần tử** qua mạng. Khi List lớn, đây là một thao tác tốn CPU, bộ nhớ tạm và băng thông.

Nếu chỉ cần 20 phần tử đầu, hãy giới hạn phạm vi:

~~~text
LRANGE very:large:list 0 19
~~~

Nếu chỉ cần 20 phần tử cuối:

~~~text
LRANGE very:large:list -20 -1
~~~

**Stop là inclusive**; đoạn 0 19 có tối đa 20 phần tử. Hãy cân nhắc giới hạn số phần tử trả về khi xây dựng API.

### 6.4. Phân trang bằng offset có chi phí tăng dần

Ví dụ một màn hình lấy 20 phần tử mỗi trang:

~~~text
LRANGE very:large:list 0 19
LRANGE very:large:list 20 39
LRANGE very:large:list 20000 20019
~~~

Trang ở offset lớn có thể cần duyệt nhiều hơn để tìm điểm bắt đầu. Hơn nữa, khi một client khác LPUSH/LPOP, các phần tử **dịch vị trí**. Phân trang bằng chỉ số vì thế có thể xuất hiện phần tử lặp hoặc bỏ sót giữa hai lần gọi.

Với dữ liệu dài cần phân trang ổn định, hãy cân nhắc cấu trúc có **định danh/sort key ổn định** hoặc mô hình truy xuất khác. List vẫn thích hợp cho việc lấy **N phần tử mới nhất** ở một đầu; nó kém phù hợp hơn cho truy vấn ngẫu nhiên sâu trên danh sách rất dài.

## 7. FIFO, LIFO và cách chọn đầu push/pop

Một List có thể được dùng làm hàng đợi (queue) hoặc ngăn xếp (stack) tùy cách chọn đầu.

### 7.1. Queue FIFO: vào trước ra trước

Một cách phổ biến:

~~~text
RPUSH lesson:row132:fifo job-A
RPUSH lesson:row132:fifo job-B
RPUSH lesson:row132:fifo job-C
LPOP lesson:row132:fifo
LPOP lesson:row132:fifo
~~~

Hai lần LPOP lấy **job-A**, sau đó **job-B**. Mỗi phần tử mới được thêm vào **đuôi**, phần tử lâu nhất được lấy từ **đầu**.

~~~mermaid
flowchart LR
    A["RPUSH job-A, job-B, job-C"] --> B["[A, B, C]"]
    B --> C["LPOP"]
    C --> D["Trả A; còn [B, C]"]
~~~

Một cách khác là LPUSH vào đầu và RPOP ở cuối; cũng tạo FIFO. Điều quan trọng là **push và pop ở hai đầu đối diện**.

### 7.2. Stack LIFO: vào sau ra trước

~~~text
RPUSH lesson:row132:stack A B C
RPOP lesson:row132:stack
RPOP lesson:row132:stack
~~~

Hai lần RPOP lấy **C**, rồi **B**. Khi push và pop ở **cùng một đầu**, List hoạt động như stack.

### 7.3. Thứ tự khi nhiều producer cùng ghi

Giả sử producer A và producer B cùng RPUSH vào một key:

~~~text
Producer A: RPUSH queue job-A
Producer B: RPUSH queue job-B
~~~

Mỗi lệnh RPUSH là một thao tác nguyên tử; Redis áp dụng một thứ tự thực thi đối với các lệnh đến cùng key. Tuy nhiên, nếu hai producer phát request gần như đồng thời, ứng dụng **không thể dựa vào thời điểm log ở hai máy khác nhau** để tự khẳng định A chắc chắn đứng trước B.

Thứ tự List phản ánh **thứ tự Redis thực thi các thao tác**, còn nghiệp vụ yêu cầu ordering toàn cục theo timestamp/sự kiện cần thêm cơ chế xác định trình tự phù hợp.

### 7.4. Các phần tử trùng trong queue

~~~text
RPUSH lesson:row132:jobs email:42 email:42 email:43
LPOP lesson:row132:jobs
LPOP lesson:row132:jobs
~~~

Hai lần LPOP đều có thể trả **email:42**. Redis List không biết việc gửi email đầu đã thành công để bỏ qua lần thứ hai.

Nếu ứng dụng không được phép xử lý một job trùng, cần **idempotency** ở tầng worker hoặc cơ chế queue phù hợp, thay vì dựa vào List để loại trùng.

## 8. Blocking pop: đợi phần tử mà không liên tục polling

Khi queue tạm thời rỗng, một worker có thể dùng **BLPOP** hoặc **BRPOP** để đợi phần tử xuất hiện.

Ví dụ trong redis-cli:

~~~text
BLPOP lesson:row132:wait 2
~~~

Ở đây **2** là timeout tính theo giây; nếu không có phần tử, Redis chờ tối đa khoảng 2 giây rồi trả kết quả rỗng. Nếu phần tử đến trong lúc chờ, Redis trả về **tên key và value được lấy ra**.

Trong Spring Data Redis, API blocking của ListOperations có thể dùng Duration:

~~~java
String job = redis.opsForList().leftPop(
        "lesson:row132:wait",
        Duration.ofSeconds(2)
);
~~~

Khi hết thời gian chờ mà không có phần tử, kết quả có thể là null; code xử lý worker cần tính tới trường hợp đó.

**Blocking pop chiếm dụng một kết nối trong lúc chờ**, nên phải cân nhắc connection pool, số lượng worker, timeout và khả năng dừng ứng dụng. Trong môi trường WebFlux reactive, không gọi một API blocking trên event-loop nếu chưa có cách xử lý phù hợp.

### Blocking pop có bảo đảm xử lý thành công không?

Không. **LPOP/BLPOP xóa phần tử khỏi List khi trả về**, trước khi ứng dụng thực sự hoàn thành nghiệp vụ:

1. Worker nhận job bằng BLPOP.
2. Redis đã loại job khỏi queue.
3. Worker gặp lỗi hoặc process bị dừng trước khi xử lý xong.
4. Job không còn trong queue nguồn để worker khác tự lấy lại.

Nếu cần cơ chế **at-least-once**, acknowledgment, pending list, retry và phục hồi worker lỗi, hãy thiết kế riêng. Một mô hình List là chuyển job từ queue chờ sang queue đang xử lý bằng thao tác nguyên tử như **LMOVE/BLMOVE** (với Redis phiên bản hỗ trợ), rồi xác nhận bằng việc xóa khỏi danh sách processing; vẫn phải có cơ chế xử lý job treo và trùng lặp.

**Redis Streams** với consumer group và acknowledgment thường phù hợp hơn khi cần các bảo đảm giao nhận và quan sát pending message. Redis List vẫn rất hữu ích cho queue đơn giản nếu chấp nhận và xử lý rõ giới hạn này.

## 9. Thao tác cập nhật bên trong List: cần cân nhắc O(N)

### 9.1. LINSERT tìm phần tử mốc (pivot)

~~~text
RPUSH lesson:row132:insert A C D
LINSERT lesson:row132:insert BEFORE C B
LRANGE lesson:row132:insert 0 -1
~~~

Kết quả:

~~~text
[A, B, C, D]
~~~

**LINSERT** tìm value mốc **C** rồi chèn B trước nó. Nếu nhiều phần tử cùng có value C, Redis sử dụng vị trí khớp đầu tiên theo quy tắc lệnh. Việc tìm pivot có thể phải duyệt List, vì vậy LINSERT có độ phức tạp O(N) trong trường hợp xấu nhất.

Nếu cần chèn thường xuyên vào vị trí bất kỳ trong List rất dài, cấu trúc này có thể không phù hợp.

### 9.2. LSET cập nhật theo index

~~~text
LSET lesson:row132:insert 2 C2
LRANGE lesson:row132:insert 0 -1
~~~

Kết quả là **[A, B, C2, D]**. LSET cập nhật giá trị tại index 2, nhưng phải tìm tới vị trí đó; chi phí có thể tăng theo độ sâu.

### 9.3. LTRIM giữ một cửa sổ gần đây

Một ứng dụng chỉ muốn lưu tối đa **100 sự kiện gần nhất** có thể thao tác:

~~~text
LPUSH lesson:row132:recent event-new
LTRIM lesson:row132:recent 0 99
~~~

LPUSH đưa event-new lên đầu; LTRIM giữ tối đa 100 phần tử đầu, bỏ phần ngoài phạm vi. Đây là mẫu dùng List hợp lý để lưu lịch sử gần đây có kích thước giới hạn.

Tuy nhiên, **LPUSH và LTRIM là hai lệnh riêng biệt**. Nếu cần bảo đảm danh sách không bao giờ vượt giới hạn ngay cả trong những interleaving giữa nhiều client, có thể gộp trong Redis transaction hoặc Lua script. Trong nhiều ứng dụng cache/thống kê, khoảng vượt ngắn giữa hai lệnh có thể được chấp nhận; phải quyết định theo yêu cầu thực tế.

Không nên hiểu **LTRIM O(1) trong mọi trường hợp**. Chi phí phụ thuộc số phần tử bị loại bỏ và cấu trúc List hiện tại; lần cắt bỏ một khối lượng dữ liệu lớn có thể tốn tài nguyên.

### 9.4. LTRIM và key rỗng

Khi một List bị xóa hết phần tử thông qua pop hoặc trim, Redis thường loại **chính key đó** khỏi không gian key. Khi đó:

~~~text
TYPE lesson:row132:empty
LLEN lesson:row132:empty
~~~

TYPE có thể trả **none**, còn LLEN trên key không tồn tại trả **0**. Đừng nhầm List rỗng với một key đã tồn tại có TTL: trong Redis, các cấu trúc List rỗng thường không được giữ lại như một key dữ liệu độc lập.

## 10. TTL áp dụng cho key List, không phải từng phần tử

Redis cho phép đặt expiration cho **toàn bộ key**:

~~~text
RPUSH lesson:row132:ttl A B C
EXPIRE lesson:row132:ttl 60
TTL lesson:row132:ttl
RPOP lesson:row132:ttl
TTL lesson:row132:ttl
~~~

Trong trường hợp bình thường, RPOP không làm reset TTL của key. Khi TTL hết hạn, **toàn bộ List** biến mất, không phải chỉ một phần tử.

Các trường hợp cần phân biệt:

- LPUSH/RPUSH trên một List đang có TTL thường giữ expiration hiện tại.
- Tạo List mới bằng LPUSH/RPUSH khi key chưa tồn tại sẽ không tự đặt TTL; muốn hết hạn cần EXPIRE hoặc cách thiết kế thích hợp.
- Nếu lấy hết phần tử, key bị xóa; TTL của key đó không còn.
- Redis List không tự hỗ trợ mỗi phần tử có TTL độc lập. Nếu từng entry cần deadline riêng, có thể phải dùng key riêng, Sorted Set với timestamp/score hoặc một mô hình dữ liệu khác.

Chẳng hạn một “queue công việc phải chạy trước 12:00” không thể chỉ dựa vào TTL 1 giờ của cả List để biết job nào riêng lẻ đã quá hạn. Cần lưu deadline của từng job và xử lý theo quy tắc nghiệp vụ.

## 11. Ví dụ Spring Boot: giữ thứ tự, cho phép trùng, truy cập theo vị trí

### 11.1. Dependency và cấu hình

Với Spring Boot 3.x dùng Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

Ví dụ Redis Server chạy local:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
~~~

Đây là cấu hình kết nối minh họa; nếu ứng dụng chạy trong container hoặc Redis có ACL/TLS, phải sử dụng địa chỉ và cấu hình tương ứng. Spring Boot thường tự tạo bean **StringRedisTemplate** khi starter và kết nối được cấu hình phù hợp.

Vì phần tử trong ví dụ là String, **StringRedisTemplate** giúp giá trị hiển thị dễ hiểu trong redis-cli.

### 11.2. Service hoàn chỉnh

~~~java
package example.redis;

import java.util.List;
import java.util.Objects;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RecentActivityStore {

    private static final String KEY = "lesson:row132:activities";

    private final StringRedisTemplate redis;

    public RecentActivityStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    /** Ghi vào đầu để hoạt động mới nhất đứng trước. */
    public long record(String activity) {
        if (activity == null || activity.isBlank()) {
            throw new IllegalArgumentException("activity must not be blank");
        }

        Long size = redis.opsForList().leftPush(KEY, activity);
        return Objects.requireNonNull(size, "Redis did not return list size");
    }

    /** Đọc tối đa limit hoạt động gần nhất mà không xóa chúng. */
    public List<String> latest(int limit) {
        if (limit <= 0 || limit > 100) {
            throw new IllegalArgumentException("limit must be 1..100");
        }

        List<String> entries = redis.opsForList().range(KEY, 0, limit - 1);
        return entries == null ? List.of() : entries;
    }

    /** Đọc vị trí hiện tại, tính từ 0; null nếu không có phần tử. */
    public String atIndex(long index) {
        return redis.opsForList().index(KEY, index);
    }

    /** Loại bỏ phần tử cũ nhất ở cuối. */
    public String removeOldest() {
        return redis.opsForList().rightPop(KEY);
    }

    /** Số phần tử đang có. */
    public long size() {
        Long length = redis.opsForList().size(KEY);
        return length == null ? 0L : length;
    }

    /** Xóa toàn bộ những phần tử có value trùng activity. */
    public long removeAll(String activity) {
        Long removed = redis.opsForList().remove(KEY, 0, activity);
        return removed == null ? 0L : removed;
    }
}
~~~

Ví dụ gọi lần lượt:

~~~java
store.record("VIEW:42");
store.record("CLICK:42");
store.record("VIEW:42");

List<String> latest = store.latest(10);
String first = store.atIndex(0);
String oldest = store.removeOldest();
~~~

Sau ba lần record, List theo thứ tự từ đầu đến cuối:

~~~text
[VIEW:42, CLICK:42, VIEW:42]
~~~

Lần VIEW:42 mới nhất ở đầu, một VIEW:42 cũ hơn vẫn còn ở cuối. **String first** nhận VIEW:42. **removeOldest()** trả và xóa VIEW:42 ở cuối.

Nếu muốn loại tất cả các lần VIEW:42, **removeAll("VIEW:42")** dùng LREM với count = 0. Hành vi này có thể đúng khi xóa một loại hoạt động, nhưng sẽ **mất toàn bộ sự kiện trùng** nếu chúng đại diện cho các lần xảy ra riêng biệt.

### 11.3. Đọc dữ liệu bằng redis-cli

Sau khi service ghi dữ liệu:

~~~text
TYPE lesson:row132:activities
LLEN lesson:row132:activities
LRANGE lesson:row132:activities 0 -1
LINDEX lesson:row132:activities 0
LINDEX lesson:row132:activities -1
~~~

TYPE là **list**. Redis CLI hiển thị giá trị String trực tiếp vì StringRedisTemplate thường sử dụng serializer UTF-8.

Nếu ứng dụng sử dụng RedisTemplate với serializer khác, các phần tử có thể xuất hiện dưới dạng bytes khó đọc. **Chi phí vị trí của Redis List không thay đổi**, nhưng cách quan sát dữ liệu sẽ khác.

### 11.4. Giới hạn 100 hoạt động gần nhất

Để giữ danh sách không tăng vô hạn, có thể tạo phương thức:

~~~java
public void recordBounded(String activity) {
    if (activity == null || activity.isBlank()) {
        throw new IllegalArgumentException("activity must not be blank");
    }

    redis.opsForList().leftPush(KEY, activity);
    redis.opsForList().trim(KEY, 0, 99);
}
~~~

Đây là **mẫu giữ 100 phần tử gần đây**, với hai lệnh Redis riêng. Nếu nhiều producer yêu cầu giới hạn tuyệt đối và tính nguyên tử của việc ghi + trim, cần kết hợp bằng Lua script hoặc transaction phù hợp. Mỗi lần trim còn có chi phí xóa phần tử; không nên dùng cách này để xóa hàng triệu phần tử trong mỗi request.

## 12. Đọc danh sách khi có concurrency

Một thao tác đơn lẻ như LPUSH, RPUSH, LPOP, RPOP hoặc LINDEX được Redis xử lý nguyên tử ở mức lệnh. Nhưng nhiều lần gọi liên tiếp từ Spring Data Redis **không tự thành một snapshot nguyên tử**.

### 12.1. LLEN rồi LINDEX có thể không còn cùng trạng thái

~~~java
Long len = redis.opsForList().size(key);
String last = redis.opsForList().index(key, len - 1);
~~~

Giữa hai lời gọi, một client khác có thể LPOP hoặc LTRIM khiến độ dài và vị trí phần tử thay đổi. Thậm chí List có thể trở nên rỗng, khiến index trả null.

Vì vậy, nếu mục đích chỉ là đọc phần tử cuối hiện tại, dùng **LINDEX key -1** sẽ đơn giản và giảm số round-trip. Nếu muốn **lấy và xóa** phần tử cuối một cách nguyên tử, dùng **RPOP**.

### 12.2. LRANGE và cập nhật đồng thời

Mỗi LRANGE riêng lẻ thấy kết quả của List tại thời điểm Redis thực thi lệnh đó. Nhưng nếu API phân trang gọi:

~~~text
LRANGE activity:list 0 9
LRANGE activity:list 10 19
~~~

và có client LPUSH giữa hai lần gọi, vị trí cũ bị dịch. Kết quả của hai trang có thể chồng lắp hoặc bỏ sót phần tử dù mỗi lệnh riêng lẻ hoạt động đúng.

Nếu cần lịch sử sự kiện có định danh, offset ổn định hoặc tiêu thụ có checkpoint, nên cân nhắc Stream hay mô hình lưu trữ khác tùy yêu cầu.

### 12.3. Hai consumer không nhận cùng một phần tử từ một lần LPOP

Nếu có một entry duy nhất ở đầu List và hai worker cùng LPOP, chỉ một lệnh lấy được entry đó. Worker còn lại sẽ lấy entry kế tiếp hoặc nil tùy trạng thái queue. Đây là tính nguyên tử của pop.

Tuy nhiên, nếu **hai entry có value trùng nhau**, hai worker vẫn có thể cùng nhận **cùng một nội dung String** vì đó là hai phần tử khác nhau của List.

Ví dụ:

~~~text
RPUSH queue job-42 job-42
LPOP queue
LPOP queue
~~~

Cả hai lần pop có thể trả job-42, hoàn toàn hợp lệ. Phải phân biệt **hai phần tử trùng nội dung** với **một phần tử bị lấy hai lần**.

## 13. Chọn cấu trúc dữ liệu dựa trên loại truy cập

Một Redis List rất hữu ích nếu thao tác chính là **thêm hoặc lấy ở hai đầu**. Nó kém phù hợp khi ứng dụng liên tục cần tìm, cập nhật hoặc xóa một value tại vị trí tùy ý.

| Yêu cầu | Redis List có phù hợp? | Lý do |
| --- | --- | --- |
| Queue FIFO đơn giản | **Có** | RPUSH + LPOP, thao tác ở hai đầu nhanh |
| Stack LIFO | **Có** | LPUSH + LPOP hoặc RPUSH + RPOP |
| Giữ 50 hoạt động gần nhất | **Có** | LPUSH + LTRIM và LRANGE phạm vi nhỏ |
| Cho phép lưu nhiều sự kiện giống nội dung | **Có** | List giữ phần tử trùng |
| Chỉ cần biết một ID đã có chưa | **Cân nhắc Set** | Membership trong List có thể phải duyệt O(N) |
| Chỉ cho phép member duy nhất | **Cân nhắc Set** | List không loại trùng |
| Cần bảng xếp hạng theo điểm | **Cân nhắc Sorted Set** | List không sắp xếp theo score |
| Tìm/cập nhật phần tử ở vị trí giữa thường xuyên | **Thường không tối ưu** | LINDEX/LSET/LINSERT có thể O(N) |
| Phân trang sâu, ổn định khi đang ghi | **Thường không phù hợp** | Offset tốn công và index thay đổi khi chèn/xóa |
| Event stream có consumer group, ack và pending | **Cân nhắc Streams** | List pop không tự có acknowledgment |
| Truy cập bản ghi theo ID | **Cân nhắc Hash/key riêng** | Index List không phải định danh ổn định |

### Khi nào cần kết hợp cấu trúc?

Một hệ thống có thể dùng:

- **List** để giữ thứ tự các ID cần xử lý.
- **Set** để kiểm tra một ID đã được enqueue hay chưa.
- **Hash** để lưu thông tin chi tiết của job theo ID.

Tuy nhiên, khi nhiều cấu trúc Redis phải được cập nhật nhất quán, thao tác GET/SET/SADD/RPUSH riêng lẻ sẽ có race và failure window. Cần thiết kế script, transaction hoặc cơ chế phục hồi phù hợp, nhất là khi nhiều instance Spring Boot cùng chạy.

Không nên thêm Set hay Hash chỉ vì nghe có vẻ đầy đủ; nếu List đáp ứng đúng nhu cầu về trùng lặp và thứ tự, cấu trúc đơn giản thường dễ vận hành hơn.

## 14. Một vài điểm cần biết khi chạy trên Redis Cluster

Redis Cluster chia không gian key theo hash slot. Mỗi thao tác **một List key** như LPUSH, RPUSH, LPOP, LLEN, LINDEX hoặc LRANGE có thể được client cluster-aware định tuyến tới node sở hữu slot của key đó.

Nếu dùng lệnh tác động **hai key**, ví dụ chuyển một phần tử từ queue chờ sang queue đang xử lý bằng LMOVE, các key trong Redis Cluster cần tuân thủ ràng buộc cùng slot.

Một cách đặt tên là dùng **hash tag**:

~~~text
queue:{email-worker}:waiting
queue:{email-worker}:processing
~~~

Hai key có cùng phần **email-worker** trong cặp ngoặc nhọn, nên Redis Cluster xếp chúng vào cùng slot. Điều này giúp thao tác LMOVE giữa hai List được định tuyến phù hợp.

Tuy nhiên:

- Không vì cần chuyển một queue mà đưa **tất cả** queue của hệ thống vào một tag global.
- Hai key cùng slot chỉ giải quyết định vị; không tự thiết kế được acknowledgment hoặc retry.
- Khi làm việc với Spring Data Redis, serializer của tên key phải giữ nguyên cú pháp hash tag theo bytes thực tế.

## 15. Bài thực hành tổng hợp

Mục tiêu: quan sát **thứ tự**, **phần tử trùng**, **truy cập theo chỉ số**, **thay đổi vị trí** và **sự khác biệt giữa pop và read**.

Thực hành trên Redis local hoặc Redis môi trường học có quyền ghi:

~~~bash
redis-cli -h 127.0.0.1 -p 6379
~~~

Trong chế độ tương tác, thực hiện từng bước.

### Bước 1. Tạo List có phần tử trùng

~~~text
RPUSH lesson:row132:lab A B A C
LLEN lesson:row132:lab
LRANGE lesson:row132:lab 0 -1
~~~

Kỳ vọng LLEN = 4; List từ trái sang phải là **[A, B, A, C]**.

### Bước 2. Đọc theo chỉ số dương và âm

~~~text
LINDEX lesson:row132:lab 0
LINDEX lesson:row132:lab 2
LINDEX lesson:row132:lab -1
LRANGE lesson:row132:lab 1 2
~~~

Kỳ vọng là **A**, **A**, **C**, rồi đoạn **[B, A]**. LRANGE không xóa phần tử.

### Bước 3. Thêm vào đầu và quan sát dịch vị trí

~~~text
LPUSH lesson:row132:lab urgent
LRANGE lesson:row132:lab 0 -1
LINDEX lesson:row132:lab 1
~~~

List trở thành **[urgent, A, B, A, C]**. Phần tử tại index 1 là **A**, trong khi trước LPUSH index 1 là **B**.

### Bước 4. Xóa một trong nhiều phần tử trùng

~~~text
LREM lesson:row132:lab 1 A
LRANGE lesson:row132:lab 0 -1
~~~

Chỉ A đầu tiên bị xóa; kết quả **[urgent, B, A, C]**. A thứ hai vẫn có mặt.

### Bước 5. Lấy phần tử cuối và cập nhật theo vị trí

~~~text
RPOP lesson:row132:lab
LSET lesson:row132:lab 1 B2
LRANGE lesson:row132:lab 0 -1
~~~

RPOP lấy C và xóa khỏi List. LSET thay B tại index 1 thành B2; kết quả **[urgent, B2, A]**.

### Bước 6. Giới hạn độ dài

~~~text
LTRIM lesson:row132:lab 0 1
LRANGE lesson:row132:lab 0 -1
LLEN lesson:row132:lab
~~~

Chỉ còn **[urgent, B2]**, độ dài bằng 2.

### Bước 7. Thử TTL

~~~text
EXPIRE lesson:row132:lab 60
TTL lesson:row132:lab
LPUSH lesson:row132:lab newest
TTL lesson:row132:lab
~~~

TTL giảm theo thời gian; LPUSH trên key còn tồn tại không tự gia hạn TTL.

### Bước 8. Dọn các key đã tạo trong bài

~~~text
DEL lesson:row132:queue
DEL lesson:row132:multi
DEL lesson:row132:index
DEL lesson:row132:duplicates
DEL lesson:row132:remove
DEL lesson:row132:fifo
DEL lesson:row132:stack
DEL lesson:row132:jobs
DEL lesson:row132:insert
DEL lesson:row132:recent
DEL lesson:row132:ttl
DEL lesson:row132:activities
DEL lesson:row132:lab
~~~

Các lệnh dọn ở đây chỉ nhằm xóa đúng key minh họa trong Redis thử nghiệm. Đừng chạy FLUSHDB hoặc FLUSHALL để dọn một bài học nhỏ vì chúng ảnh hưởng nhiều dữ liệu khác.

## 16. Những sai lầm thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Thêm A, B, C bằng LPUSH nhưng thấy C, B, A | LPUSH thêm từng value vào đầu | Chọn RPUSH nếu muốn thứ tự mảng đầu vào giữ nguyên |
| Cùng một ID xuất hiện nhiều lần | List cho phép phần tử trùng | Xác định trùng có hợp lệ; nếu cần uniqueness, thiết kế riêng |
| LINDEX giữa List lớn bị chậm | Phải duyệt tới vị trí giữa, O(N) | Ưu tiên thao tác hai đầu hoặc chọn cấu trúc theo ID |
| API trả dữ liệu rất lớn | LRANGE 0 -1 lấy tất cả phần tử | Giới hạn range, tránh đọc toàn bộ List lớn |
| Phân trang có phần tử trùng hoặc bị sót | LPUSH/LPOP làm index dịch giữa hai lượt đọc | Dùng mô hình có ID/cursor ổn định nếu cần |
| LSET sửa nhầm phần tử | Index chỉ phản ánh vị trí hiện tại | Không dùng index làm ID dài hạn |
| LREM xóa nhiều bản ghi hơn dự kiến | count = 0 xóa tất cả value trùng | Chọn count và quy tắc nhận diện entry rõ ràng |
| Job biến mất khi worker lỗi | LPOP xóa khỏi List trước khi xử lý xong | Dùng processing list/ack workflow hoặc Redis Streams |
| TTL không còn sau khi List rỗng | Pop/trim làm key bị xóa | Kiểm tra EXISTS/TYPE và chính sách tạo key mới |
| Đọc không được bằng GET | Key là Redis List, không phải String | TYPE key rồi dùng LRANGE/LINDEX |
| Nhiều thao tác Java xảy ra không đồng bộ | Một loạt lệnh riêng lẻ không nguyên tử | Chọn một lệnh phù hợp, transaction hoặc script khi cần |

## 17. Cách lựa chọn thao tác theo mục tiêu

Khi đọc code Spring Data Redis sử dụng **opsForList()**, hãy tự hỏi:

1. **Thứ tự mong muốn là gì?** Nếu muốn mới nhất ở đầu, LPUSH; muốn giữ thứ tự đầu vào từ trái sang phải, thường chọn RPUSH.
2. **Có chấp nhận phần tử trùng không?** Nếu không, Redis List đơn thuần chưa đủ.
3. **Đọc có làm mất dữ liệu không?** LINDEX/LRANGE chỉ đọc; LPOP/RPOP vừa trả giá trị vừa xóa phần tử.
4. **Chủ yếu thao tác ở hai đầu hay truy cập vị trí giữa?** Thao tác ở hai đầu là điểm mạnh; truy cập ngẫu nhiên sâu có thể O(N).
5. **Danh sách có thể lớn đến mức nào?** Giới hạn size, output và lịch sử để tránh dùng LRANGE toàn bộ trên List rất lớn.
6. **Có nhiều producer/consumer không?** Các lệnh riêng lẻ nguyên tử, nhưng index có thể dịch và workflow nhiều bước cần thiết kế consistency.
7. **Khi xử lý thất bại có phải đưa phần tử trở lại không?** Với queue có yêu cầu tin cậy, cần cơ chế pending/ack/retry hoặc cấu trúc hỗ trợ sẵn.

**Ghi nhớ:** Redis List duy trì thứ tự theo các lệnh chèn/xóa và **cho phép trùng giá trị**. LPUSH, RPUSH, LPOP và RPOP thường có chi phí O(1) cho mỗi phần tử, còn truy cập vị trí sâu bằng LINDEX/LSET, tìm bằng LPOS/LREM hay đọc phạm vi lớn có thể tốn chi phí tuyến tính. Trong Spring Data Redis, hãy thiết kế dựa trên loại truy cập thực tế: dùng List mạnh nhất ở hai đầu, coi chỉ số là vị trí tạm thời và luôn xử lý rõ yêu cầu về trùng lặp, thời gian sống và concurrency.
