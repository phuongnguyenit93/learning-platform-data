# Danh sách liên kết đôi và chi phí của nút trong LinkedList

## 1. LinkedList lưu một chuỗi nút thay vì một mảng phần tử

`LinkedList<E>` của Java là danh sách liên kết đôi (doubly linked list). Mỗi lần xuất hiện trong danh sách được biểu diễn bằng một nút (node). Nút giữ tham chiếu đến phần tử và liên kết với nút trước, nút sau.

Điểm khác biệt quan trọng với danh sách dựa trên mảng là: để thêm hoặc bỏ một nút tại vị trí đã biết, danh sách nối lại một số liên kết quanh vị trí đó. Nó không cần dịch cả đoạn phần tử phía sau sang các ô mảng khác.

Nhưng lợi ích này có giá:

- Muốn đến một vị trí ở giữa, thường phải đi qua các nút.
- Mỗi lần xuất hiện cần một đối tượng nút và các tham chiếu quản lý.
- Đọc qua chuỗi nút có thể phải chạm đến nhiều vùng bộ nhớ khác nhau.
- Thêm/xóa liên tục tạo ra công việc cấp phát và thu gom các nút.

Vì thế, “LinkedList chèn/xóa O(1)” chỉ đúng nếu nói rõ đã xác định được vị trí cần thao tác. Nó không mô tả đầy đủ một lời gọi xóa theo chỉ số hoặc theo giá trị.

Theo [API LinkedList của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html), lớp này triển khai cả List và Deque. Ta có thể dùng nó như một dãy có chỉ số hoặc như một hàng đợi hai đầu. Hai cách dùng cùng một cấu trúc nhưng dẫn đến những mẫu chi phí rất khác nhau.

Bài dùng Java 17 trở lên. Các ví dụ hoạt động trong một luồng, không có thay đổi cấu trúc từ nơi khác trong lúc iterator đang chạy.

## 2. Mô hình một nút: item, prev và next

### 2.1. Ba tham chiếu có ba vai trò khác nhau

Hình dạng khái niệm của một nút:

```text
Node
  item ----> đối tượng phần tử E
  prev ----> nút đứng trước
  next ----> nút đứng sau
```
Trong triển khai OpenJDK 17, Node là lớp nội bộ riêng của LinkedList, không phải một kiểu nút mà API công khai cho người gọi giữ và thao tác trực tiếp.

Bảng phân biệt:

| Thành phần | Trỏ đến cái gì? | Mục đích |
| --- | --- | --- |
| item | Đối tượng phần tử, hoặc null | Giữ giá trị của lần xuất hiện trong danh sách |
| prev | Một nút khác, hoặc null ở đầu | Cho phép đi lùi và nối lại phía trước |
| next | Một nút khác, hoặc null ở cuối | Cho phép đi tiến và nối lại phía sau |

item không phải bản sao sâu của đối tượng. Nếu phần tử là một đơn hàng, nút giữ tham chiếu đến đơn hàng; toàn bộ dữ liệu đơn hàng không được nhét trực tiếp vào các trường liên kết.

Khi gọi `getFirst()`, `get(i)` hoặc `iterator.next()`, ta nhận **phần tử E**, không nhận Node nội bộ. Giữ một tham chiếu đến phần tử không có nghĩa là có một tham chiếu đến nút chứa nó.

### 2.2. first và last thuộc đối tượng danh sách

Bản thân đối tượng LinkedList giữ tham chiếu đến nút đầu, nút cuối và thông tin kích thước.

```text
                  first                         last
                    |                             |
                    v                             v
null <-prev- [node A] <-prev- [node B] <-prev- [node C]
             [      ] -next-> [      ] -next-> [      ] -next-> null

Mỗi node còn có item riêng trỏ đến A, B hoặc C.
```
Cách đọc gọn hơn:

```text
first -> [A] <-> [B] <-> [C] <- last

[A], [B], [C] là các nút, không phải vị trí bộ nhớ được bảo đảm.
```
Trong mô hình OpenJDK 17, danh sách này không phải vòng tròn và không dùng một nút giả cố định để biểu diễn biên. Một số sách hoặc cấu trúc liên kết khác dùng nút canh (sentinel); không áp nguyên sơ đồ đó vào LinkedList của Java.

Các chi tiết triển khai trong bài được đối chiếu với [mã nguồn LinkedList của OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/LinkedList.java). API quy định hành vi công khai; hình dạng Node là thông tin triển khai để giải thích cơ chế và chi phí.

### 2.3. Vì sao cần cả prev và next?

next đủ để đi tiến. Thêm prev cho phép:

- Đi lùi từ cuối.
- Biết nút trước khi đã có một nút ở giữa.
- Bỏ một nút đã biết bằng cách nối hai hàng xóm của nó lại.
- Giữ các thao tác ở cả hai đầu không cần đi từ đầu qua toàn chuỗi.

Đổi lại, mỗi nút có thêm một tham chiếu và mỗi lần nối/gỡ phải giữ hai chiều nhất quán. Liên kết đôi là một sự đánh đổi về cấu trúc, không phải một khả năng miễn phí.

## 3. Những quan hệ phải luôn đúng

Một cấu trúc liên kết chỉ hữu ích khi các liên kết của nó nhất quán. Những quan hệ sau giúp đọc hiểu thuật toán và phát hiện lỗi khi tự triển khai một danh sách tương tự.

### 3.1. Danh sách rỗng

```text
size = 0
first = null
last  = null
```
Không có nút phần tử nào trong chuỗi. Một đối tượng LinkedList rỗng vẫn là một đối tượng chứa danh sách; “không có nút” không có nghĩa là không tốn bất kỳ bộ nhớ nào.

### 3.2. Danh sách có đúng một phần tử

```text
first ----+
          v
        [node X]
          ^
last -----+

node X.prev = null
node X.next = null
size = 1
```
first và last phải trỏ cùng một nút. Khi bỏ nút duy nhất, phải cập nhật **cả hai** về null.

Nếu chỉ cập nhật một đầu, cấu trúc có thể vừa báo rỗng theo một đường truy cập, vừa giữ một nút cũ theo đường khác. Đây là lỗi biên thường gặp khi tự viết danh sách liên kết.

### 3.3. Danh sách có nhiều nút

- first.prev bằng null.
- last.next bằng null.
- Nếu x.next là y thì y.prev phải là x.
- Nếu y.prev là x thì x.next phải là y.
- Đi next từ first phải đến đúng số nút bằng size rồi kết thúc.
- Đi prev từ last phải thu được cùng các nút theo thứ tự ngược lại.

LinkedList quản lý các quan hệ này bên trong. Người dùng API không tự sửa prev/next.

Lưu ý: `item == null` khác với `node == null`. LinkedList cho phép một nút có phần tử null; đó vẫn là một lần xuất hiện trong danh sách và vẫn làm size tăng. Không thể dùng “phần tử đầu là null” để khẳng định danh sách rỗng.

## 4. Chèn một nút: đổi một vùng liên kết nhỏ

### 4.1. Chèn X giữa P và Q

Trước:

```text
... <-> P <-> Q <-> ...

P.next = Q
Q.prev = P
```
Sau:

```text
... <-> P <-> X <-> Q <-> ...

X.prev = P
X.next = Q
P.next = X
Q.prev = X
```
Sau khi đã biết các nút liên quan, chỉ cần một số thao tác tạo nút và gán tham chiếu không tăng theo độ dài danh sách.

Không phải “đẩy” mọi nút phía sau Q sang chỗ khác. Vị trí của chúng trong thứ tự List thay đổi, nhưng không có một mảng chỉ số cần dịch vật lý.

Đây cũng giải thích câu trong tài liệu List rằng các phần tử sau điểm chèn có chỉ số tăng một đơn vị: **chỉ số logic thay đổi**, không có nghĩa LinkedList thực hiện sao chép cả đoạn đuôi như danh sách dựa trên mảng.

### 4.2. Thêm đầu

Với một danh sách không rỗng:

1. Tạo nút mới có prev là null và next là first cũ.
2. Cho nút first cũ trỏ prev về nút mới.
3. Cập nhật first.
4. Tăng size.

Nếu danh sách trước đó rỗng, nút mới đồng thời là first và last.

Không cần tìm đầu vì đối tượng danh sách đã giữ first. Số liên kết cần cập nhật là hằng số.

### 4.3. Thêm cuối

Tương tự:

1. Tạo nút mới có prev là last cũ và next là null.
2. Cho last cũ trỏ next đến nút mới.
3. Cập nhật last.
4. Nếu trước đó rỗng, cập nhật cả first.
5. Tăng size.

Đây là cơ chế của việc thêm cuối thông thường. Không có một mảng dự phòng phải mở rộng rồi sao chép tất cả tham chiếu cũ, nhưng **vẫn có một nút mới cần được cấp phát**.

Những bước trên mô tả quan hệ cần có sau thao tác trong một luồng. Không coi chuỗi gán liên kết này là một thao tác nguyên tử an toàn cho nhiều luồng.

## 5. Xóa một nút: nối hai hàng xóm rồi tách nút cũ

Giả sử đã xác định nút X cần bỏ:

```text
Trước: ... <-> P <-> X <-> Q <-> ...
Sau:   ... <-> P <------> Q <-> ...
```
Cần nối P.next với Q và Q.prev với P. Các trường hợp biên:

| X nằm ở đâu? | Việc cập nhật biên |
| --- | --- |
| Ở giữa | Nối hai hàng xóm |
| Là first nhưng còn nút sau | first trở thành nút sau; prev của first mới bằng null |
| Là last nhưng còn nút trước | last trở thành nút trước; next của last mới bằng null |
| Là nút duy nhất | Cả first và last trở thành null |

Sau đó size giảm. Trong OpenJDK 17, các tham chiếu của nút bị gỡ được bỏ phù hợp để tránh giữ dữ liệu và chuỗi nút không cần thiết qua nút đó.

Việc gỡ nút không đồng nghĩa đối tượng phần tử bị hủy ngay:

- Phương thức xóa có thể trả phần tử cho người gọi.
- Đối tượng có thể còn ở một vị trí khác trong cùng danh sách.
- Đối tượng có thể còn được giữ bởi một danh sách khác hoặc biến khác.
- Bộ thu gom rác quyết định thời điểm thu hồi đối tượng không còn được dùng.

Java không có bước `free(node)` mà người dùng LinkedList phải gọi sau mỗi lần xóa. Cần hiểu vòng đời tham chiếu, không viết chương trình phụ thuộc thời điểm thu gom chính xác.

## 6. Đã biết nút khác với đã biết chỉ số hoặc giá trị

### 6.1. Biết chỉ số chưa có nghĩa là biết Node

Với mảng, từ chỉ số có thể xác định ô trực tiếp. Với LinkedList, get(i) phải tìm nút ở vị trí i bằng cách lần theo liên kết.

LinkedList chọn đi từ đầu hoặc từ cuối tùy phía nào gần hơn. Với một chỉ số phần tử hợp lệ:

```text
n = size trước thao tác
0 <= i < n

Số bước qua liên kết để đến i:
d(i) = min(i, n - 1 - i)

Chi phí tìm nút:
O(1 + d(i))
```
Cộng 1 để cả trường hợp first hoặc last vẫn có công việc hằng số.

Ví dụ danh sách có 1.000 phần tử:

- get(0): đã có first.
- get(999): đã có last.
- get(998): đi lùi một liên kết từ last.
- get(500): vẫn phải đi qua hàng trăm liên kết.

Vì vậy, get ở gần hai đầu có thể rẻ, nhưng get ở giữa có chi phí tuyến tính theo n.

### 6.2. Chèn/xóa theo chỉ số phải cộng bước tìm

```text
Chi phí add(i, value)
= tìm vị trí chèn
+ tạo nút
+ cập nhật một số liên kết.

Chi phí remove(i)
= tìm nút ở i
+ gỡ một số liên kết.
```
`add(size(), value)` là trường hợp cuối, có thể dùng last trực tiếp. Chèn trước một phần tử ở giữa vẫn phải tìm nút đó trước.

Một lệnh remove(i) không trở thành O(1) chỉ vì phần gỡ nút sau khi tìm là O(1).

### 6.3. Xóa theo giá trị còn phải tìm bằng quan hệ bằng nhau

`remove(value)` tìm lần xuất hiện đầu tiên theo quan hệ bằng nhau rồi mới gỡ nút. Nếu giá trị không có hoặc ở xa đầu, có thể phải xét cả danh sách.

Khi coi mỗi phép so sánh là hằng số, trường hợp xấu nhất là O(n). Nếu equals đọc một cấu trúc lớn, phải cộng chi phí so sánh đó. Liên kết đôi không tạo ra bảng tra cứu theo giá trị.

Với LinkedList<Integer>, còn phải phân biệt hai overload:

```java
// Đoạn minh họa; hai danh sách bắt đầu từ dữ liệu giống nhau.
LinkedList<Integer> byIndex = new LinkedList<>(List.of(10, 20, 10));
byIndex.remove(1);                   // Xóa chỉ số 1: [10, 10].

LinkedList<Integer> byValue = new LinkedList<>(List.of(10, 20, 10));
byValue.remove(Integer.valueOf(10)); // Xóa giá trị đầu tiên bằng 10: [20, 10].
```
Phân biệt đúng yêu cầu xóa trước, rồi mới phân tích số liên kết phải đi qua.

### 6.4. Bảng chi phí cần gắn điều kiện

Bảng xét mô hình thao tác cấu trúc thông thường của LinkedList, chưa tính công việc nghiệp vụ và tạm coi so sánh bằng nhau là hằng số.

| Thao tác | Chi phí | Lý do |
| --- | --- | --- |
| size(), isEmpty() | O(1) | Có thông tin kích thước được lưu |
| getFirst(), getLast(), peekFirst(), peekLast() | O(1) | Có first/last |
| addFirst(), addLast(), add(E) | O(1) về thao tác cấu trúc | Tạo một nút và nối ở đầu đã biết |
| removeFirst(), removeLast(), pollFirst(), pollLast() | O(1) | Gỡ nút ở đầu đã biết |
| get(i), set(i, value), remove(i) | O(1 + min(i, n - 1 - i)) | Phải đến nút ở i |
| add(i, value), với i < n | Chi phí tìm nút ở i cộng O(1) | Không bỏ qua bước định vị |
| add(n, value) | O(1) về thao tác cấu trúc | Thêm sau last |
| contains(value), remove(value) | O(n) ở trường hợp xấu nhất | Tìm tuyến tính |
| Duyệt toàn bộ bằng iterator | O(n) | Mỗi bước đi tiếp từ vị trí hiện tại |
| clear() trong OpenJDK 17 | O(n) với danh sách không rỗng | Đi qua các nút để bỏ tham chiếu |

Ký hiệu O(1) về thao tác cấu trúc không phải cam kết về độ trễ tối đa tính bằng nano giây. Cấp phát, thu gom rác, lịch chạy và hệ thống bộ nhớ vẫn ảnh hưởng thời gian thực tế.

## 7. Chi phí của nút gồm những gì?

### 7.1. Không chỉ có item

Một lần xuất hiện của phần tử cần chỗ cho:

1. Tham chiếu item.
2. Tham chiếu prev.
3. Tham chiếu next.
4. Phần thông tin quản lý đối tượng của JVM.
5. Phần đệm để đáp ứng căn chỉnh bộ nhớ nếu có.

Ngoài các nút, đối tượng LinkedList còn có trạng thái đối tượng danh sách. Còn bản thân đối tượng phần tử có thể chiếm một lượng bộ nhớ khác.

Không cộng ba tham chiếu rồi gọi đó là kích thước đầy đủ của Node. Cũng không lấy một con số đo trên một JVM rồi xem là hằng số của ngôn ngữ Java.

### 7.2. Mô hình tách cấu trúc khỏi dữ liệu phần tử

Một cách ước lượng khái niệm:

```text
Bộ nhớ cấu trúc LinkedList
xấp xỉ
bộ nhớ container
+ n * bộ nhớ mỗi Node.

Bộ nhớ mỗi Node
bao gồm ba trường tham chiếu, phần quản lý đối tượng và căn chỉnh.

Bộ nhớ toàn đồ thị đang xét
còn có thể bao gồm các đối tượng phần tử và những gì chúng tham chiếu.
```
Ở đây n là số lần xuất hiện, không phải số đối tượng phần tử khác nhau.

Nếu thêm cùng một đối tượng 1.000 lần vào LinkedList theo triển khai OpenJDK 17, ta có 1.000 nút chứa tham chiếu đến cùng đối tượng đó. Nó không nhân bản đối tượng thành 1.000 bản sâu, nhưng cũng không gộp 1.000 nút thành một nút.

Nếu thêm null nhiều lần, mỗi lần vẫn có nút riêng. item bằng null không loại bỏ chỗ cần cho prev, next và thông tin quản lý nút.

### 7.3. Đếm trường tham chiếu khác với đếm byte

Với n nút, có 3n trường tham chiếu trong các nút. Hai liên kết biên chứa null khi danh sách không rỗng, nhưng trường giữ null vẫn chiếm chỗ trong biểu diễn của nút.

Số byte phụ thuộc vào JVM và cấu hình, chẳng hạn cách biểu diễn tham chiếu, tiêu đề đối tượng và căn chỉnh. Nếu cần con số cho một môi trường cụ thể, phải đo trong môi trường đó và ghi lại điều kiện đo.

[JOL của OpenJDK](https://github.com/openjdk/jol) là công cụ khảo sát bố trí đối tượng. Khi dùng kết quả của công cụ, cần phân biệt:

- Kích thước nông của một đối tượng (shallow size).
- Các đối tượng có thể đi tới qua tham chiếu trong một đồ thị.
- Phần dữ liệu được dùng chung với các đối tượng danh sách khác.
- Bộ nhớ thực sự bị giữ lại độc quyền theo một phân tích vòng đời cụ thể.

Không cộng toàn bộ đồ thị phần tử hai lần chỉ vì hai danh sách cùng trỏ đến những đối tượng đó.

### 7.4. “Không có capacity dự phòng” không đồng nghĩa “luôn tiết kiệm hơn”

Danh sách dựa trên mảng thường có một vùng ô tham chiếu, có thể có chỗ dự phòng. LinkedList không cần một mảng capacity kiểu đó, nhưng trả chi phí cho từng đối tượng Node.

Với dữ liệu phần tử nhỏ hoặc dùng chung nhiều, chi phí nút có thể chiếm tỷ trọng đáng kể. Với dữ liệu phần tử rất lớn, chi phí nút có thể nhỏ hơn khi nhìn theo tỷ lệ, nhưng nó vẫn tồn tại.

Không khẳng định một tỷ lệ bộ nhớ cố định giữa LinkedList và ArrayList. Capacity đã dành trước của ArrayList, cách JVM biểu diễn nút và đồ thị phần tử đều ảnh hưởng phép so sánh.

## 8. Cấp phát, thu gom rác và tính cục bộ bộ nhớ

### 8.1. Kích thước đang giữ khác với số nút đã tạo

Giả sử ứng dụng liên tục thêm một phần tử rồi lấy nó ra. size có thể hiếm khi lớn hơn 1, nhưng sau một triệu vòng đã có rất nhiều lần tạo và bỏ nút theo cách triển khai LinkedList.

Điều này phân biệt:

- **Bộ nhớ đang được giữ tại một thời điểm:** phụ thuộc số nút còn nằm trong cấu trúc và các tham chiếu còn sống.
- **Lưu lượng cấp phát theo thời gian:** phụ thuộc số lần tạo nút.
- **Công việc thu gom:** phụ thuộc JVM, tuổi thọ đối tượng, tải và cấu hình.

Tạo một nút nhỏ có thể được JVM thực hiện nhanh. Tuy vậy, “nhỏ” không có nghĩa miễn phí; một tải thêm/xóa lớn có thể khiến cấp phát và thu gom trở thành một phần đáng kể của hiệu năng.

`set(i, value)` thay phần tử tại nút đã tìm, không cần tạo một nút danh sách mới chỉ để thay item. Nếu đối số value được tạo bằng new ở phía người gọi, chi phí tạo đối tượng đó là một công việc riêng.

### 8.2. Đi theo liên kết có thể gây nhiều lần chờ dữ liệu

Các Node là những đối tượng riêng. API không hứa chúng nằm cạnh nhau trong bộ nhớ. Muốn đi tiếp, chương trình đọc next hoặc prev rồi mới biết nút kế tiếp.

Nếu dữ liệu của nút kế chưa ở bộ nhớ đệm CPU, lượt duyệt có thể phải chờ. Một danh sách dựa trên mảng có lợi thế là dãy ô tham chiếu của nó thường ở gần nhau trong cùng vùng dữ liệu mảng.

Đó là một lý do cần thận trọng trước câu “cùng O(n) nên tốc độ duyệt giống nhau”. Big O không mô tả hết số đối tượng, số lần gián tiếp qua tham chiếu và cách dữ liệu đi qua các tầng bộ nhớ.

Cũng không đảo thành một khẳng định tuyệt đối rằng mọi nút LinkedList luôn xa nhau hoặc LinkedList luôn chậm hơn. Bố trí thực tế, công việc trên phần tử và JVM đều cần được xem xét.

### 8.3. clear không chỉ bỏ hai đầu

Trong OpenJDK 17, clear đi qua các nút và bỏ item/next/prev trước khi đặt lại first, last và size. Vì vậy, clear của LinkedList không được phân tích như chỉ có hai phép gán first = last = null.

Việc bỏ các liên kết giúp tránh giữ một chuỗi dữ liệu không cần thiết qua tham chiếu cũ tới một nút, và phục vụ quản lý bộ nhớ của triển khai. Thời điểm bộ nhớ thật được thu hồi vẫn do GC quyết định.

Không gọi System.gc() rồi lấy thay đổi bộ nhớ của một lần chạy làm kích thước chuẩn của một Node. Số đo toàn tiến trình bị ảnh hưởng bởi nhiều đối tượng và quyết định của JVM.

## 9. Ví dụ chạy được: hai đầu, duyệt ngược và trạng thái biên

Lưu chương trình vào `LinkedListEndsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Deque;
import java.util.Iterator;
import java.util.LinkedList;
import java.util.List;
import java.util.NoSuchElementException;

public class LinkedListEndsDemo {
    public static void main(String[] args) {
        Deque<String> items = new LinkedList<>();
        System.out.println("initially empty = " + items.isEmpty());

        items.addLast("B");
        items.addFirst("A");
        items.addLast("C");
        System.out.println("forward = " + items);
        System.out.println("first = " + items.getFirst());
        System.out.println("last = " + items.getLast());

        List<String> reversed = new ArrayList<>();
        for (Iterator<String> it = items.descendingIterator(); it.hasNext();) {
            reversed.add(it.next());
        }
        System.out.println("reverse traversal = " + reversed);

        System.out.println("removed first = " + items.removeFirst());
        System.out.println("removed last = " + items.removeLast());
        System.out.println("one item remains = " + items);
        System.out.println("removed only item = " + items.removeLast());
        System.out.println("empty again = " + items.isEmpty());
        System.out.println("pollFirst on empty = " + items.pollFirst());

        try {
            items.removeFirst();
        } catch (NoSuchElementException ex) {
            System.out.println("removeFirst on empty = "
                    + ex.getClass().getSimpleName());
        }
    }
}
```
Biên dịch và chạy:

```shell
javac --release 17 LinkedListEndsDemo.java
java LinkedListEndsDemo
```
Kết quả:

```text
initially empty = true
forward = [A, B, C]
first = A
last = C
reverse traversal = [C, B, A]
removed first = A
removed last = C
one item remains = [B]
removed only item = B
empty again = true
pollFirst on empty = null
removeFirst on empty = NoSuchElementException
```
Giải thích theo cấu trúc:

- Thêm B vào danh sách rỗng tạo một nút vừa là đầu vừa là cuối.
- Thêm A ở đầu và C ở cuối tạo chuỗi A ↔ B ↔ C.
- descendingIterator đi theo thứ tự ngược, trả C, B, A.
- Sau khi bỏ A và C, còn một nút B nên hai đầu cùng chỉ đến nút đó.
- Bỏ B đưa cả hai đầu về trạng thái rỗng.
- pollFirst trả null khi rỗng; removeFirst ném NoSuchElementException khi rỗng.

Theo [hợp đồng Deque của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html), các cặp phương thức thường có cách báo không có phần tử khác nhau. Chọn cách báo phù hợp với luồng xử lý, không coi poll và remove là cùng một hợp đồng lỗi.

LinkedList còn cho phép lưu null. Nếu cho null vào, poll trả null có thể là phần tử vừa lấy ra thay vì dấu hiệu rằng trước đó rỗng. Với một hàng đợi cần dùng null làm tín hiệu kết thúc, hãy đặt chính sách không chứa null hoặc chọn cách quản lý trạng thái phù hợp. Không viết vòng xử lý dựa trên tín hiệu mơ hồ.

Biến được khai báo là Deque vì ví dụ chỉ cần thao tác hai đầu. Cách khai báo này thể hiện nhu cầu của mã gọi; cấu trúc thực tế vẫn là LinkedList.

## 10. Iterator giữ vị trí giúp tránh tìm lại nút

### 10.1. Iterator biết vị trí hiện tại trong chuỗi

Một iterator của LinkedList giữ trạng thái đủ để đi sang nút kế và làm việc với phần tử vừa trả về. Nó không phải gọi get(i) từ đầu cho mỗi lượt.

Khi đang đứng đúng vị trí, việc iterator.remove gỡ nút vừa trả về chỉ cần nối lại hàng xóm. ListIterator.add chèn tại con trỏ hiện tại cũng không cần bắt đầu một cuộc tìm chỉ số mới.

Đây là một trường hợp có thể tận dụng cơ chế liên kết:

```text
Tìm/đi đến vị trí một lần
-> đọc tuần tự các nút
-> sửa gần vị trí con trỏ
-> tiếp tục đi.
```
Ngược lại, tạo listIterator(i) ở một vị trí giữa vẫn cần tìm đến vị trí đó lúc khởi tạo. Tạo lại iterator ở giữa trong mỗi lượt có thể làm mất lợi ích giữ vị trí.

### 10.2. Chương trình chỉnh sửa trong một lượt

Lưu vào `LinkedListCursorEditDemo.java`:

```java
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;

public class LinkedListCursorEditDemo {
    public static void main(String[] args) {
        LinkedList<Integer> values = new LinkedList<>(
                List.of(10, -1, 20, -2, 30));
        int visited = 0;
        int removed = 0;
        int inserted = 0;

        for (ListIterator<Integer> it = values.listIterator(); it.hasNext();) {
            int value = it.next();
            visited++;

            if (value < 0) {
                it.remove();
                removed++;
            } else if (value == 20) {
                it.add(21);
                inserted++;
            }
        }

        System.out.println("result = " + values);
        System.out.println("visited original values = " + visited);
        System.out.println("removed nodes = " + removed);
        System.out.println("inserted nodes = " + inserted);
    }
}
```
Biên dịch và chạy:

```shell
javac --release 17 LinkedListCursorEditDemo.java
java LinkedListCursorEditDemo
```
Kết quả:

```text
result = [10, 20, 21, 30]
visited original values = 5
removed nodes = 2
inserted nodes = 1
```
Chương trình đọc năm phần tử ban đầu:

- Nút chứa -1 và -2 bị gỡ bằng iterator.remove.
- Khi gặp 20, một nút mới chứa 21 được chèn tại vị trí con trỏ.
- Phần tử mới được chèn nằm phía sau phần tử vừa đọc và trước phần tử sẽ được đọc tiếp. Theo quy tắc ListIterator.add, lần next tiếp theo vẫn trả phần tử vốn đứng kế tiếp, nên 21 không được đếm lại là một phần tử ban đầu đã duyệt.

Với một lượt đi tuần tự, điều kiện hằng số và mỗi phần tử chỉ gây số thao tác nút bị chặn bởi hằng số, tổng công việc cấu trúc là tuyến tính theo số phần tử ban đầu, cộng số nút được chèn.

Các bộ đếm trong chương trình là bộ đếm hành vi của thuật toán, không phải bộ đếm byte hoặc GC. Việc in cả danh sách ở cuối cũng có chi phí duyệt, không nên đặt vào một phép đo chỉ muốn so sánh riêng một thao tác nối nút.

### 10.3. Quy tắc sửa khi duyệt vẫn phải được giữ

- remove cần một phần tử vừa được next hoặc previous trả về và chưa bị xóa lại.
- add/remove qua chính iterator phải tuân theo trạng thái của iterator.
- Không tự gọi các thao tác sửa cấu trúc khác trên danh sách rồi mặc định iterator cũ vẫn hợp lệ.
- Fail-fast giúp phát hiện một số thay đổi không hợp lệ ở mức best effort; không phải cơ chế đồng bộ.

Giữ một iterator không có nghĩa là có một tham chiếu nút công khai ổn định để dùng tùy ý sau mọi thay đổi. Không thiết kế thuật toán giả định Java LinkedList cho phép trực tiếp truyền Node vào một phương thức public để xóa.

## 11. Ví dụ chạy được: nút riêng, phần tử dùng chung

Lưu vào `LinkedListPayloadSharingDemo.java`:

```java
import java.util.LinkedList;
import java.util.List;

public class LinkedListPayloadSharingDemo {
    static final class Task {
        String title;

        Task(String title) {
            this.title = title;
        }

        @Override
        public String toString() {
            return title;
        }
    }

    public static void main(String[] args) {
        Task shared = new Task("draft");
        LinkedList<Task> original = new LinkedList<>(List.of(shared, shared));
        LinkedList<Task> copy = new LinkedList<>(original);

        System.out.println("original size = " + original.size());
        System.out.println("same payload at two positions = "
                + (original.getFirst() == original.getLast()));

        original.removeFirst();
        System.out.println("original size after removal = " + original.size());
        System.out.println("copy size after original removal = " + copy.size());
        System.out.println("same payload across containers = "
                + (original.getFirst() == copy.getFirst()));

        shared.title = "approved";
        System.out.println("original values = " + original);
        System.out.println("copy values = " + copy);

        copy.clear();
        System.out.println("copy empty = " + copy.isEmpty());
        System.out.println("original size after copy.clear = " + original.size());
    }
}
```
Biên dịch và chạy:

```shell
javac --release 17 LinkedListPayloadSharingDemo.java
java LinkedListPayloadSharingDemo
```
Kết quả:

```text
original size = 2
same payload at two positions = true
original size after removal = 1
copy size after original removal = 2
same payload across containers = true
original values = [approved]
copy values = [approved, approved]
copy empty = true
original size after copy.clear = 1
```
Đọc kết quả theo hai tầng:

1. **Tầng cấu trúc:** xóa ở original không làm size của copy giảm. clear của copy không xóa lần xuất hiện còn lại trong original.
2. **Tầng phần tử:** các lần xuất hiện giữ tham chiếu đến cùng Task, nên thay title của Task được nhìn thấy khi duyệt cả hai danh sách.

Trong OpenJDK 17, tạo LinkedList mới từ collection dựng chuỗi nút mới cho các phần tử lấy từ collection nguồn. Nó không tái sử dụng một chuỗi Node như cấu trúc chung giữa hai danh sách.

Nhưng các đối tượng Task không tự được sao chép sâu. Ban đầu original có hai nút, copy có hai nút, trong khi cả bốn item đều có thể trỏ đến cùng một Task.

Sau khi original.removeFirst, một nút không còn nằm trong original. Điều này không xóa Task vì các nút khác và biến shared vẫn giữ tham chiếu đến nó.

Chương trình không quan sát trực tiếp Node nội bộ và không đo bộ nhớ. Nó kiểm chứng hành vi độc lập của hai đối tượng danh sách và hành vi dùng chung phần tử. Cách triển khai nút mới được giải thích từ cấu trúc của OpenJDK 17, không suy ra địa chỉ nút từ output.

Một hệ quả thiết kế: nếu tự tạo một lớp phần tử có trường prev/next rồi đưa nó vào java.util.LinkedList, LinkedList không tự dùng hai trường đó làm liên kết nội bộ. Nó vẫn bọc phần tử trong Node của nó. Cấu trúc “phần tử tự mang liên kết” là một thiết kế khác và không phải hợp đồng của Java LinkedList.

## 12. Dùng mô hình nút để đánh giá lựa chọn cấu trúc

### 12.1. Những mẫu có thể tận dụng liên kết đôi

- Làm việc ở đầu/cuối mà không cần truy cập chỉ số ngẫu nhiên.
- Đi tuần tự và chỉnh sửa tại vị trí con trỏ đã có.
- Cần hiểu rõ thao tác thêm/gỡ không phải dịch một dãy ô mảng.

Nhưng mỗi mẫu vẫn phải chịu chi phí nút, cấp phát và truy cập bộ nhớ. Cần so với tổng yêu cầu, không chỉ một phép nối liên kết.

### 12.2. Những mẫu dễ dùng sai

| Mẫu mã | Vấn đề cần xem |
| --- | --- |
| for i từ 0 đến size - 1 rồi get(i) | Mỗi lượt có thể tìm lại nút; tổng có thể bậc hai |
| remove(i) ở giữa liên tục | Phần gỡ rẻ nhưng phần tìm lại vị trí có thể đắt |
| remove(value) rất nhiều lần | Tìm theo giá trị vẫn tuyến tính trong trường hợp xấu |
| Thêm/xóa liên tục với size nhỏ | Bộ nhớ đang giữ nhỏ nhưng lưu lượng cấp phát nút có thể lớn |
| Thêm nhiều lần cùng một đối tượng | Không nhân bản phần tử, nhưng vẫn tạo nhiều nút |
| Chọn LinkedList chỉ vì “không có ô dự phòng” | Đã bỏ qua tiêu đề đối tượng và các liên kết trên từng nút |
| Dùng LinkedList giữa nhiều luồng mà không có thiết kế đồng bộ | Liên kết đôi không tạo an toàn luồng |

Nếu chỉ cần một Deque thông thường và không cần null, có thể cân nhắc [ArrayDeque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html), vốn dùng cấu trúc mảng và không có một Node liên kết riêng cho từng lần xuất hiện. Đây là một lựa chọn cần đánh giá theo tác vụ; không suy thành tỷ lệ tốc độ cố định hoặc tính tương thích hoàn toàn với các hành vi của LinkedList.

Nếu phần lớn công việc là đọc theo chỉ số hoặc duyệt ổn định, cũng cần xem xét một danh sách dựa trên mảng. Trước khi đổi cấu trúc, hãy ghi rõ yêu cầu về thứ tự, null, phần tử trùng, sửa tại con trỏ và mô hình luồng.

### 12.3. Đánh giá bằng số bước và bằng số đo đúng mục tiêu

Phân tích số bước trả lời “chi phí tăng như thế nào khi n tăng”. Đo hiệu năng trả lời “trên môi trường này, tác vụ này chạy ra sao”.

Để đánh giá chi phí nút thực tế, có thể cần:

- Đo bộ nhớ của cấu trúc với cùng tập đối tượng phần tử, tránh nhân đôi dữ liệu một cách không chủ ý.
- Đo lưu lượng cấp phát khi thêm/xóa, bên cạnh bộ nhớ còn giữ.
- Tách việc tạo phần tử nghiệp vụ khỏi việc thêm nút nếu mục tiêu chỉ là đo cấu trúc.
- Kiểm tra một lượt duyệt và mẫu sửa thực sự của ứng dụng.
- Ghi phiên bản JVM, tùy chọn quan trọng, kích thước dữ liệu và điều kiện đo.

Không suy từ một ví dụ nhỏ in ra kết quả đúng rằng chi phí cấp phát hoặc cache đã được đo. Các chương trình trong bài là minh chứng chức năng và mô hình tham chiếu.

## 13. Các lỗi phổ biến khi giải thích LinkedList

| Nhận định sai | Điều cần sửa |
| --- | --- |
| “Mỗi nút chứa nguyên đối tượng phần tử bên trong” | Node giữ tham chiếu item; đối tượng phần tử là một tầng khác |
| “Danh sách liên kết đôi là hai danh sách riêng” | Một chuỗi nút có liên kết theo hai hướng |
| “Có prev nên get(i) là O(1)” | Chỉ giúp bắt đầu từ phía gần hơn; vẫn phải đi qua liên kết |
| “Biết giá trị phần tử là biết nút” | Cùng một đối tượng có thể xuất hiện nhiều lần; API trả phần tử chứ không trả Node |
| “Xóa ở giữa luôn O(1)” | Chỉ phần gỡ tại nút đã xác định là hằng số |
| “Chỉ số sau điểm xóa giảm thì phải dịch mọi nút” | Chỉ số là vị trí logic; cấu trúc chỉ nối lại liên kết |
| “Không có capacity nên luôn ít bộ nhớ hơn” | Có chi phí đối tượng và ba tham chiếu cho từng nút |
| “Bỏ nút là phần tử bị hủy ngay” | Phần tử có thể còn tham chiếu; GC quyết định thu hồi |
| “clear chỉ cần bỏ first/last nên luôn O(1)” | OpenJDK 17 đi qua chuỗi để bỏ tham chiếu trong các nút |
| “Một Node luôn tốn đúng X byte trên mọi JVM” | Cách biểu diễn tham chiếu, tiêu đề và căn chỉnh phụ thuộc môi trường |
| “Iterator giữ nút nên không cần tuân theo quy tắc sửa” | Iterator có trạng thái và hợp đồng sửa riêng |
| “LinkedList là cấu trúc sẵn sàng cho nhiều luồng” | Lớp không tự đồng bộ; cần thiết kế truy cập phù hợp |

## 14. Thực hành với liên kết, chi phí và vòng đời

### Bài 1: Chèn giữa có cần cập nhật phần tử xa không?

Có chuỗi A ↔ B ↔ C ↔ D. Chèn X giữa B và C, giả sử đã có vị trí.

Các quan hệ mới là B.next = X, X.prev = B, X.next = C, C.prev = X. Không cần cập nhật liên kết của A và D chỉ để chèn tại vị trí này. Size tăng một.

Các vị trí logic của C và D tăng một, nhưng không có trường chỉ số trong từng Node cần tăng theo.

### Bài 2: Bỏ nút duy nhất

Danh sách chỉ có X, first và last cùng trỏ X. Bỏ X phải đưa first và last về null và size về 0. Bỏ sót một đầu là sai dù một số thao tác kiểm tra khác có thể chưa bộc lộ lỗi ngay.

### Bài 3: Ba tham chiếu trên mỗi nút

Danh sách có năm nút, mọi item khác null. Có bao nhiêu trường tham chiếu trong các nút, và bao nhiêu liên kết prev/next khác null?

Có 15 trường tham chiếu trong năm nút. Các liên kết prev/next khác null là 2 * (5 - 1) = 8; hai trường liên kết biên chứa null. Ngoài ra có năm item khác null. Không dùng số 15 để suy ra ngay một số byte nếu chưa biết biểu diễn JVM.

### Bài 4: Cùng đối tượng xuất hiện 100 lần

Theo mô hình OpenJDK 17, có 100 nút và 100 trường item trỏ đến cùng đối tượng. Không có 100 bản sao sâu của phần tử.

Xóa một lần xuất hiện chỉ bỏ một nút. Đối tượng vẫn có thể được giữ bởi 99 lần xuất hiện còn lại và các tham chiếu khác.

### Bài 5: Xóa theo chỉ số giữa một danh sách lớn

Vì sao remove(500_000) trên danh sách một triệu phần tử không được gọi đơn giản là O(1)?

Vì cần tìm nút ở chỉ số đó bằng cách đi qua các liên kết trước. Phần nối lại hàng xóm chỉ là bước sau khi đã đến nơi.

### Bài 6: Bộ nhớ nhỏ tại một thời điểm, cấp phát lớn theo thời gian

Một vòng lặp luôn addLast rồi removeFirst, không giữ lại phần tử, có thể chỉ giữ rất ít nút cùng lúc. Tuy vậy, nhiều vòng vẫn tạo nhiều nút theo thời gian. Hai phép đo “bộ nhớ đang giữ” và “tốc độ cấp phát” trả lời hai câu hỏi khác nhau.

### Bài 7: Nhận diện một tổng bậc hai

Nếu duyệt bằng get(i) từ 0 đến n - 1 trên LinkedList, mỗi lần bắt đầu định vị từ một đầu. Tổng số liên kết phải đi qua có thể Θ(n²). Dùng iterator giữ vị trí để đi một lượt giúp tránh tìm lại vị trí cho từng phần tử.

### Bài 8: Node và phần tử có cùng vòng đời không?

Không bắt buộc. Một nút bị gỡ có thể không còn được danh sách giữ, trong khi phần tử được trả về vẫn nằm trong một biến của người gọi. Ngược lại, nhiều nút của các danh sách khác nhau có thể cùng trỏ đến một phần tử.

Khi phân tích LinkedList, hãy tách **tìm vị trí → nối/gỡ liên kết → tạo/bỏ nút → vòng đời phần tử**. Bốn phần này giải thích vì sao liên kết đôi thuận lợi ở một số mẫu thao tác nhưng vẫn có chi phí thời gian và bộ nhớ mà một câu “chèn/xóa nhanh” không thể hiện đủ.
