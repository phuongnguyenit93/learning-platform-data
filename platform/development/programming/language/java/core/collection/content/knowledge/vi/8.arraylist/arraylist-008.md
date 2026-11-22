# Khi nào ArrayList là lựa chọn phù hợp?

`ArrayList` thường là một điểm bắt đầu tốt cho một dãy dữ liệu có thứ tự, có thể thay đổi độ dài, được xây dựng chủ yếu bằng cách thêm cuối rồi đọc hoặc duyệt nhiều lần. Nhưng nó không phải lựa chọn mặc định cho mọi tập dữ liệu chỉ vì có phương thức `add`.

Muốn chọn đúng, cần trả lời hai nhóm câu hỏi: **dữ liệu cần giữ ý nghĩa gì** và **chương trình sẽ thao tác với dữ liệu theo cách nào**. Giữ thứ tự, giữ bản ghi trùng, truy cập theo chỉ số, tìm theo mã, lấy đầu hàng đợi và sửa đồng thời là những nhu cầu khác nhau.

Bài này hướng dẫn cách đánh giá những nhu cầu đó, giải thích cơ chế khiến `ArrayList` phù hợp hoặc kém phù hợp, rồi áp dụng vào một ví dụ Java 17 hoàn chỉnh.

## 1. Trước hết, xác định có thật sự cần một List không

`List` là mô hình một dãy phần tử có vị trí. Ví dụ:

~~~text
chi so:     0       1       2       3
du lieu:   Lan:8   Lan:8   An:9    Ha:7
~~~

Hai dòng `Lan:8` có thể đại diện cho hai lần ghi nhận riêng và đều cần được giữ. Vị trí cũng có ý nghĩa: nếu chưa sắp xếp lại, dãy phản ánh thứ tự chương trình thêm dữ liệu.

Một `ArrayList`:

- Giữ thứ tự các phần tử trong danh sách.
- Cho phép nhiều phần tử bằng nhau theo `equals`.
- Cho phép đọc hoặc thay thế phần tử tại một chỉ số.
- Cho phép tăng, giảm số phần tử.
- Cho phép `null`, dù ứng dụng có thể chủ động cấm `null`.

Đây là các đặc điểm khác với “một tập phần tử duy nhất” hoặc “một bảng tra cứu theo khóa”.

### 1.1. Giữ thứ tự không có nghĩa là tự sắp xếp

Nếu thêm B, A, C thì danh sách là `[B, A, C]`, không tự thành `[A, B, C]`. Muốn có thứ tự theo tên, điểm hoặc thời gian, phải thực hiện bước sắp xếp tương ứng.

Sau khi chèn ở giữa hoặc xóa, chỉ số phía sau có thể đổi. Do đó, chỉ số là vị trí hiện tại trong dãy, không nên được dùng thay cho mã định danh bền vững của một bản ghi.

### 1.2. Cho phép trùng có thể là yêu cầu, không phải lỗi

Trong lịch sử giao dịch, dữ liệu đo, dòng hóa đơn hoặc danh sách lượt đăng ký, hai giá trị bằng nhau chưa chắc là một dữ liệu cần loại bỏ. Chuyển sang `Set` chỉ để “tra cứu nhanh hơn” có thể làm mất thông tin về số lần xuất hiện.

Ngược lại, nếu yêu cầu cốt lõi là “mỗi mã chỉ xuất hiện một lần”, dùng danh sách rồi gọi `contains` trước từng `add` có thể vừa khó thể hiện quy tắc vừa tạo nhiều lần tìm kiếm tuyến tính. Cần xác định tính duy nhất ngay từ mô hình dữ liệu.

### 1.3. Truy cập theo vị trí khác truy cập theo mã

`scores.get(200)` lấy phần tử đang ở vị trí 200. Nó không tìm người có mã 200.

Nếu câu hỏi thường xuyên là “đối tượng nào có mã X?”, cấu trúc ánh xạ từ mã đến đối tượng thường diễn đạt mục đích rõ hơn. Một dãy để trình bày và một chỉ mục để tìm kiếm có thể cùng tồn tại nếu ứng dụng thật sự cần cả hai; khi ấy phải quản lý tính nhất quán giữa chúng.

## 2. Vì sao cơ chế mảng làm ArrayList phù hợp với một số kiểu thao tác?

`ArrayList` triển khai `List` bằng một mảng có khả năng được thay bằng mảng lớn hơn khi cần. Các vị trí của mảng nền chứa tham chiếu tới phần tử.

Mô hình đơn giản:

~~~text
size = 4, capacity = 6

chi so mang:    0     1     2     3     4     5
              [A]   [B]   [C]   [D]   [ ]   [ ]
              <--- phan tu dang co --> <du tru>
~~~

**Kích thước (size)** là số phần tử thực sự có. **Dung lượng (capacity)** là số vị trí mảng nền có thể chứa. Dung lượng không phải số phần tử đã được tạo.

Tài liệu [ArrayList Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html) mô tả các thao tác truy cập theo chỉ số có chi phí hằng số và thêm cuối có chi phí hằng số khấu hao; các phần việc khác cần được xem theo kiểu thao tác cụ thể.

### 2.1. Đọc một chỉ số không cần đi qua các phần tử trước

Để lấy phần tử tại i, cấu trúc truy cập vị trí mảng tương ứng. `get(i)` và `set(i, value)` có chi phí O(1) với chỉ số hợp lệ.

Đây là lý do `ArrayList` hữu ích khi thuật toán cần truy cập nhiều vị trí rời rạc, xử lý các khoảng chỉ số, đọc hàng đang chọn hoặc tra các phần tử đã được nạp sẵn.

O(1) ở đây mô tả công việc truy cập danh sách. Nếu sau đó phải giải mã tài liệu, gọi mạng hoặc xử lý đối tượng phức tạp, tổng công việc của ứng dụng còn có những chi phí khác.

### 2.2. Thêm cuối phù hợp với việc tích lũy kết quả

Khi mảng còn chỗ, thêm cuối chủ yếu là ghi một tham chiếu và tăng kích thước. Khi đầy, có thể phải cấp mảng lớn hơn và chuyển các tham chiếu cũ.

Vì tăng mảng diễn ra theo những đợt, chi phí đó được phân bổ trên một chuỗi thêm cuối: O(1) khấu hao mỗi lần. Một lần riêng lẻ vẫn có thể tốn O(n) khi tăng mảng.

Do đó, mô hình “đọc từng bản ghi, nếu hợp lệ thì thêm vào cuối kết quả” thường phù hợp. Tuy nhiên, nếu yêu cầu giới hạn độ trễ cho từng lần ghi cực kỳ chặt, chữ “khấu hao” chưa đủ để chứng minh đáp ứng thời hạn.

### 2.3. Duyệt một lượt phù hợp với dữ liệu đã được gom trong bộ nhớ

Một vòng duyệt n phần tử có chi phí quản lý duyệt O(n), cộng công việc thực hiện với từng phần tử. Mảng tham chiếu được bố trí theo các vị trí liên tiếp, tránh việc phải cấp một nút liên kết riêng cho mỗi vị trí như mô hình danh sách liên kết.

Không được suy ra rằng toàn bộ đối tượng phần tử cũng nằm liên tiếp trong bộ nhớ, hoặc rằng `ArrayList` luôn thắng mọi cấu trúc trong mọi phép đo. Nó chứa tham chiếu; cách các đối tượng được tạo và cách JVM quản lý bộ nhớ vẫn ảnh hưởng hiệu năng.

### 2.4. Chèn/xóa ở đầu hoặc giữa phải giữ nguyên thứ tự

Nếu có n phần tử và chèn tại i, phần đuôi dài n−i phải dịch để mở chỗ. Xóa tại i phải dồn n−i−1 phần tử phía sau.

Đặt trước dung lượng có thể tránh tăng mảng nhưng không loại bỏ phần việc dịch đuôi. Đây là hạn chế quan trọng khi kiểu thao tác chính là sửa liên tục ở đầu hoặc giữa một danh sách lớn.

## 3. Những tình huống thường phù hợp

| Tình huống | Vì sao ArrayList hợp lý | Điều kiện cần xem thêm |
|---|---|---|
| Gom các bản ghi hợp lệ từ một nguồn hữu hạn | Thêm cuối, giữ thứ tự và số lần xuất hiện | Toàn bộ kết quả phải vừa ngân sách bộ nhớ |
| Tạo danh sách kết quả để hiển thị | Có thứ tự, truy cập theo vị trí | Cần quy định ai được sửa danh sách |
| Nạp một lô rồi xử lý hoặc sắp xếp | Dễ duyệt, truy cập và cập nhật theo chỉ số | Tính cả thời gian sắp xếp và tạo bản sao |
| Giữ một danh sách làm việc trong một phương thức | Quyền sở hữu rõ, không cần phối hợp ghi giữa nhiều luồng | Không để tham chiếu nội bộ thoát ra ngoài ngoài ý muốn |
| Cần bản sao có thể thay đổi của một collection | Constructor nhận nguồn tạo cấu trúc danh sách riêng | Các đối tượng phần tử vẫn có thể được chia sẻ |
| Dữ liệu tăng giảm vừa phải, sửa giữa không chiếm ưu thế | Mã đơn giản và phù hợp nhiều thao tác thông thường | Đo trên tải thật nếu thao tác sửa trở thành điểm nghẽn |

### 3.1. Danh sách kết quả của một phép lọc

Một nguồn có m bản ghi, cần giữ những bản ghi vượt điều kiện. Dùng một `ArrayList` kết quả rồi thêm cuối từng bản ghi được giữ giúp:

- Bảo toàn thứ tự nguồn.
- Giữ mọi lần xuất hiện nếu yêu cầu không loại trùng.
- Không làm thay đổi danh sách đầu vào.
- Tránh xóa từng phần tử khỏi giữa nguồn chỉ để tạo đầu ra mới.

Chi phí vòng lọc là O(m) cộng chi phí điều kiện; bộ nhớ kết quả phụ thuộc số bản ghi được giữ. Nếu chỉ muốn tính tổng hoặc đếm, có thể không cần giữ cả danh sách kết quả.

### 3.2. Dữ liệu được xây một lần, đọc nhiều lần

Một ứng dụng có thể dùng `ArrayList` trong giai đoạn xây dựng, sau đó công bố một danh sách không cho sửa cấu trúc. Cách này tách rõ giai đoạn thay đổi khỏi giai đoạn sử dụng.

Điều đó không yêu cầu đối tượng trả về cuối cùng phải có lớp triển khai `ArrayList`. Ví dụ `List.copyOf` có thể tạo một biểu diễn khác. Nên thiết kế theo hợp đồng cần cung cấp, thay vì ép nơi nhận biết lớp nội bộ.

### 3.3. Thay thế giá trị ở các vị trí đã có

Nếu yêu cầu là cập nhật phần tử tại i mà không thêm hoặc xóa vị trí, `set(i, value)` không phải dịch phần đuôi. Một danh sách làm việc có nhiều lần đọc và thay thế theo chỉ số có thể phù hợp với `ArrayList`.

Tuy nhiên, nếu cần tìm đúng bản ghi bằng mã trước mỗi lần thay thế, bước tìm đó vẫn có thể là tuyến tính. Phải phân tích cả tìm vị trí lẫn cập nhật, không chỉ nhìn `set`.

### 3.4. Một số thay đổi giữa vẫn có thể chấp nhận được

Một danh sách 30 phần tử được người dùng thỉnh thoảng sắp xếp lại không nhất thiết cần cấu trúc phức tạp chỉ vì chèn giữa có O(n). Số phần tử và tần suất thực tế quyết định phần chi phí có đáng quan tâm hay không.

Ví dụ này minh họa cách suy xét, không đặt ra ngưỡng “dưới 30 luôn dùng ArrayList”. Không có một con số phổ quát thay cho yêu cầu, môi trường và phép đo.

## 4. Những nhu cầu nên khiến ta cân nhắc cấu trúc khác

### 4.1. Hàng đợi: thêm cuối và lấy/xóa đầu liên tục

Nếu cứ `add(value)` rồi `remove(0)`, mỗi lần xóa đầu của `ArrayList` phải dồn các phần tử còn lại.

Tháo n phần tử bằng xóa đầu có tổng số tham chiếu dịch:

~~~text
(n - 1) + (n - 2) + ... + 1 + 0 = n(n - 1)/2
~~~

Một hàng đợi thường phù hợp hơn với giao diện `Queue` hoặc `Deque`. `ArrayDeque` hỗ trợ các thao tác ở hai đầu với phần lớn thao tác có chi phí hằng số khấu hao; nó không cung cấp `get(i)` và không cho phép phần tử `null`. Xem [ArrayDeque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

Lựa chọn cần phản ánh cả dữ liệu lẫn thao tác: không thay bằng deque nếu ứng dụng thực sự cần truy cập tùy ý theo chỉ số và không có cách thiết kế khác phù hợp.

### 4.2. Kiểm tra phần tử có tồn tại rất nhiều lần

`ArrayList.contains` có thể phải so sánh qua nhiều phần tử. Gọi nó cho từng phần tử của một tập lớn khác có thể tạo số phép so sánh tăng theo tích hai kích thước.

Nếu cần tính duy nhất và kiểm tra thành viên, cân nhắc `HashSet`. Các thao tác cơ bản có hiệu năng hằng số khi hàm băm phân bố tốt; tập này không bảo đảm thứ tự duyệt. Đây là điều kiện của cấu trúc băm, không phải lời hứa O(1) tuyệt đối cho mọi hàm băm và mọi dữ liệu, theo [HashSet Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html).

Nếu danh sách nhỏ, số lần kiểm tra ít, hoặc cần giữ phần tử trùng, chi phí tạo và duy trì một tập bổ sung có thể không cần thiết. Cần đánh giá nhu cầu thực tế thay vì thay mọi `contains` bằng một cấu trúc khác theo thói quen.

### 4.3. Tìm đối tượng theo khóa

Nếu thao tác chính là “lấy khách hàng theo mã”, một `Map<Id, Customer>` thường mô tả yêu cầu trực tiếp hơn `List<Customer>` rồi duyệt tìm.

`HashMap` có các thao tác `get` và `put` hiệu quả khi hàm băm phân bố tốt, và không bảo đảm thứ tự duyệt, như nêu tại [HashMap Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

Cần xác định quy tắc khi hai bản ghi cùng khóa. Dùng map có thể thay thế một giá trị cũ bằng giá trị mới; đó là một quyết định dữ liệu, không chỉ tối ưu thời gian.

### 4.4. Chèn/xóa giữa thường xuyên khi đã có vị trí duyệt

Một danh sách liên kết có lợi trong một số chuỗi thao tác khi đã có bộ lặp ở vị trí phù hợp. Nhưng đổi thành `LinkedList` rồi vẫn gọi `get(i)`, `add(i, x)`, `remove(i)` không tự tạo thao tác O(1): cần đi tới nút tương ứng.

Tài liệu [LinkedList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html) nêu các thao tác theo chỉ số đi từ đầu hoặc cuối, tùy bên nào gần hơn. Vì vậy, phải xét cả cách tìm vị trí, không chỉ thao tác cập nhật liên kết.

Nếu những lần thay đổi giữa có thể gom thành lô hoặc tạo một danh sách kết quả mới trong một lượt, thay thuật toán có thể hữu ích hơn đổi cấu trúc.

### 4.5. Số lượng cố định hoặc dữ liệu nguyên thủy rất lớn

Khi kích thước cố định, cần tương tác với API nhận mảng, hoặc muốn lưu số nguyên trong `int[]`, mảng có thể phù hợp hơn.

`ArrayList<Integer>` giữ các tham chiếu `Integer`, không phải một vùng `int` nguyên thủy tự tăng. Việc đóng hộp, bộ nhớ đối tượng và tham chiếu có thể đáng kể với khối dữ liệu số lớn. Mảng nguyên thủy tránh phần biểu diễn đó nhưng đổi lại cần tự quản lý kích thước logic hoặc chấp nhận độ dài cố định.

Không dùng một công thức byte cố định cho mọi JVM để so sánh bộ nhớ; cấu hình tham chiếu, tiêu đề đối tượng và căn chỉnh có thể khác nhau.

### 4.6. Dữ liệu không có giới hạn hữu ích trong bộ nhớ

`ArrayList` giữ các phần tử trong bộ nhớ. Nó không phải cơ chế tự phân trang dữ liệu từ đĩa, cơ sở dữ liệu hoặc mạng.

Nếu nguồn rất lớn hoặc liên tục không kết thúc, cần xem cách xử lý từng phần, theo lô, theo luồng hoặc lưu trữ bên ngoài. Gọi một collection là “dynamic” không có nghĩa là dung lượng vô hạn.

Tương tự, có thể dùng danh sách cho một trang kết quả đã tải, nhưng không vì cần hiển thị một trang mà phải nạp toàn bộ hàng triệu bản ghi vào danh sách để cắt trang trong bộ nhớ.

### 4.7. Nhiều luồng cùng sửa

`ArrayList` không tự đồng bộ hóa. Nhiều luồng ghi vào cùng một danh sách hoặc đọc xen ghi đòi hỏi thiết kế phối hợp phù hợp; không được dùng việc “chưa thấy ConcurrentModificationException” làm bằng chứng an toàn.

Một danh sách chỉ được dùng trong một luồng, hoặc được xây xong rồi chia sẻ để đọc qua cơ chế công bố an toàn, có yêu cầu khác với danh sách nhiều luồng cùng ghi.

Bọc đồng bộ, dùng bản sao, phân chia quyền sở hữu hay chọn cấu trúc đồng thời là những lựa chọn tùy mẫu truy cập. Không có một thao tác thêm dung lượng hoặc một từ khóa kiểu dữ liệu nào tự giải quyết toàn bộ vấn đề.

## 5. Cách ra quyết định theo thứ tự

Thay vì bắt đầu bằng câu “ArrayList hay LinkedList nhanh hơn?”, hãy đi qua các câu sau:

1. **Dữ liệu có phải một dãy có thứ tự và có vị trí không?** Nếu không, xem lại việc có cần `List`.
2. **Có cần giữ phần tử trùng không?** Nếu có, không thay bằng set chỉ để làm nhanh một thao tác.
3. **Các thao tác chiếm ưu thế là gì?** Thêm cuối, duyệt và đọc theo chỉ số ủng hộ `ArrayList`; lấy đầu liên tục hoặc tìm theo khóa gợi ý mô hình khác.
4. **Kết quả có vừa bộ nhớ và sống trong bao lâu?** Tính cả vùng dự trữ, đối tượng phần tử và các bản sao cùng tồn tại.
5. **Ai được sửa và có bao nhiêu luồng truy cập?** Chọn cách chuyển giao và đồng bộ ngay từ hợp đồng.
6. **Có bằng chứng phần việc này là điểm nghẽn không?** Nếu cần tối ưu, đo trên tải có ý nghĩa và kiểm tra cả kết quả lẫn chi phí.

Các câu trả lời có thể dẫn tới việc dùng `ArrayList` bên trong và một kiểu công khai khác bên ngoài. “Chọn cấu trúc để xây dữ liệu” và “cung cấp quyền gì cho nơi dùng dữ liệu” là hai quyết định liên quan nhưng không đồng nhất.

## 6. Khai báo List, dùng ArrayList và thiết kế quyền sửa

### 6.1. Giao diện không tự quy định khả năng thay đổi

Một đoạn thân phương thức minh họa:

~~~java
List<String> names = new ArrayList<>();
names.add("An");
~~~

Biến có kiểu `List`, nhưng đối tượng thật là `ArrayList`, nên thao tác thêm vẫn được hỗ trợ.

Dùng `List` ở chỗ chỉ cần hợp đồng danh sách giúp giảm phụ thuộc vào lớp triển khai. Nhưng một phương thức nhận `List` không được tự giả định rằng mọi nguồn đều hỗ trợ thêm, xóa hoặc thay thế: có danh sách chỉ đọc và có danh sách kích thước cố định.

Nếu phương thức cần sửa đầu vào, phải nêu rõ yêu cầu đó hoặc tự tạo bản sao làm việc. Không âm thầm sắp xếp danh sách mà người gọi mong được giữ nguyên.

### 6.2. Khi thật sự cần API riêng của ArrayList

`ensureCapacity` và `trimToSize` không thuộc giao diện `List`. Nếu một phần xây dựng dữ liệu cần sử dụng chúng, biến nội bộ có thể mang kiểu `ArrayList`:

~~~java
ArrayList<String> building = new ArrayList<>(expectedCount);
building.ensureCapacity(nextExpectedTotal);
~~~

Đây là đoạn minh họa, với các biến số lượng đã được kiểm tra hợp lệ. Dung lượng dự kiến không làm kích thước danh sách tăng và không cho phép `get` vào vị trí chưa được thêm.

Không cần ép kiểu một `List` bất kỳ về `ArrayList` chỉ vì hy vọng đối tượng thật thuộc lớp đó. Một hợp đồng công khai trả `List` có thể thay đổi triển khai mà vẫn đáp ứng hợp đồng.

### 6.3. Bản sao có thể sửa, view chỉ đọc và bản chụp không giống nhau

| Cách tạo | Quyền sửa cấu trúc qua tham chiếu kết quả | Có phản ánh thay đổi cấu trúc của nguồn sau đó? |
|---|---|---|
| `new ArrayList<>(source)` | Có | Không, cấu trúc danh sách riêng |
| `Collections.unmodifiableList(source)` | Không | Có, đây là view của nguồn |
| `List.copyOf(source)` | Không | Không phản ánh cập nhật nguồn sau khi tạo |

`List.copyOf` không chấp nhận phần tử `null` và không hứa lớp triển khai cụ thể. Nó có thể tái sử dụng một danh sách không sửa được phù hợp; đừng suy ra rằng mỗi lời gọi luôn cấp một `ArrayList` mới. Xem [List.copyOf Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).

View chỉ đọc giữ liên hệ với nguồn, theo [Collections.unmodifiableList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)). Nếu nguồn vẫn bị sửa ở nơi khác, nơi giữ view có thể quan sát dữ liệu thay đổi.

Tất cả các cách trên đều không tự sao chép sâu từng đối tượng phần tử. Nếu phần tử có thể thay đổi, một danh sách không cho thêm/xóa vẫn có thể chứa đối tượng bị thay đổi qua tham chiếu khác. Muốn một giá trị ổn định hoàn toàn còn phải thiết kế phần tử và cách chia sẻ nó.

### 6.4. Không phải mọi cách tạo List đều thay thế được ArrayList làm việc

`List.of(...)` cho một danh sách không sửa được. `Arrays.asList(array)` tạo danh sách kích thước cố định được hậu thuẫn bởi mảng: có thể thay phần tử qua `set`, nhưng không thêm/xóa vị trí như một `ArrayList` độc lập. Xem [Arrays.asList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html#asList(T...)).

Vì vậy, nếu cần tiếp tục thêm/xóa sau khi nhận một nguồn như vậy, có thể tạo `new ArrayList<>(source)`. Lý do chọn ở đây là khả năng sửa cấu trúc và quyền sở hữu, không chỉ độ phức tạp.

## 7. Ví dụ hoàn chỉnh: gom dữ liệu, đọc theo vị trí, sắp xếp và chuyển giao kết quả

Yêu cầu giả định:

- Đầu vào là một lô điểm hữu hạn.
- Loại bản ghi có điểm âm.
- Giữ đủ số lần xuất hiện; hai bản ghi `Lan:8` đều có ý nghĩa.
- Có danh sách làm việc để đọc theo chỉ số và sắp xếp.
- Khi đã chuẩn bị kết quả, tạo bản chụp không cho sửa cấu trúc.
- Không làm thay đổi danh sách đầu vào.

`ArrayList` phù hợp với giai đoạn làm việc: xây bằng thêm cuối, duyệt, truy cập chỉ số và sắp xếp. Giai đoạn chuyển giao có hợp đồng riêng và dùng `List.copyOf`.

### 7.1. Mã nguồn

Lưu thành `ArrayListChoiceDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.Objects;

public class ArrayListChoiceDemo {
    record Score(String name, int points) {
        Score {
            Objects.requireNonNull(name, "name");
        }

        @Override
        public String toString() {
            return name + ":" + points;
        }
    }

    static List<Score> collectValidScores(List<Score> input) {
        Objects.requireNonNull(input, "input");
        List<Score> result = new ArrayList<>();
        for (Score score : input) {
            Objects.requireNonNull(score, "score");
            if (score.points() >= 0) {
                result.add(score);
            }
        }
        return result;
    }

    public static void main(String[] args) {
        List<Score> input = List.of(
                new Score("Lan", 8),
                new Score("Minh", -1),
                new Score("Lan", 8),
                new Score("An", 9),
                new Score("Ha", 7));

        List<Score> working = collectValidScores(input);
        System.out.println("accepted: " + working);
        System.out.println("duplicate Lan:8 count: "
                + Collections.frequency(working, new Score("Lan", 8)));
        System.out.println("get(2): " + working.get(2));
        long total = 0;
        for (Score score : working) {
            total += score.points();
        }
        System.out.println("total: " + total);

        working.sort(Comparator.comparingInt(Score::points)
                .reversed().thenComparing(Score::name));
        System.out.println("sorted: " + working);
        List<Score> snapshot = List.copyOf(working);
        List<Score> view = Collections.unmodifiableList(working);

        working.add(new Score("Binh", 6));
        System.out.printf("after append: working=%d, snapshot=%d, view=%d%n",
                working.size(), snapshot.size(), view.size());
        System.out.println("snapshot: " + snapshot);
        try {
            snapshot.add(new Score("Chi", 10));
        } catch (UnsupportedOperationException exception) {
            System.out.println("snapshot.add: UnsupportedOperationException");
        }

        List<Score> mutableCopy = new ArrayList<>(snapshot);
        mutableCopy.set(0, new Score("An", 10));
        System.out.println("mutable copy: " + mutableCopy);
        System.out.println("snapshot after copy.set: " + snapshot);
        System.out.println("input unchanged: " + input);

        List<String> nullable = new ArrayList<>();
        nullable.add(null);
        System.out.println("ArrayList accepts null: " + nullable);
        try {
            List.copyOf(nullable);
        } catch (NullPointerException exception) {
            System.out.println("List.copyOf null: NullPointerException");
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 ArrayListChoiceDemo.java
java ArrayListChoiceDemo
~~~

### 7.2. Kết quả stdout

~~~text
accepted: [Lan:8, Lan:8, An:9, Ha:7]
duplicate Lan:8 count: 2
get(2): An:9
total: 32
sorted: [An:9, Lan:8, Lan:8, Ha:7]
after append: working=5, snapshot=4, view=5
snapshot: [An:9, Lan:8, Lan:8, Ha:7]
snapshot.add: UnsupportedOperationException
mutable copy: [An:10, Lan:8, Lan:8, Ha:7]
snapshot after copy.set: [An:9, Lan:8, Lan:8, Ha:7]
input unchanged: [Lan:8, Minh:-1, Lan:8, An:9, Ha:7]
ArrayList accepts null: [null]
List.copyOf null: NullPointerException
~~~

### 7.3. Mỗi kết quả chứng minh điều gì?

`accepted` giữ thứ tự của các bản ghi hợp lệ trong đầu vào. Hai bản ghi `Lan:8` vẫn còn và `Collections.frequency` cho kết quả 2. Điều này phù hợp với yêu cầu giữ số lần xuất hiện.

`get(2)` lấy `An:9` theo vị trí trước khi sắp xếp. Nó không tìm theo tên. Tổng điểm 32 được tính trong một lượt duyệt.

Bước `sort` chủ động đổi thứ tự thành giảm dần theo điểm, rồi theo tên nếu bằng điểm. Danh sách không tự có thứ tự này chỉ vì dùng `ArrayList`. Bộ so sánh làm việc trên các trường của `Score`, không dựa vào chuỗi hiển thị của `toString`.

Sau khi thêm Binh vào `working`, kích thước của `working` và view cùng là 5, còn snapshot vẫn là 4. Đây là sự khác biệt quan sát được giữa view và bản chụp.

`snapshot.add` bị từ chối. Tạo `new ArrayList<>(snapshot)` lại cho phép sửa; `set` trên bản sao thay tham chiếu tại vị trí 0 mà không đổi snapshot.

`Score` trong ví dụ có hai thành phần `String` và `int`, không có trường dữ liệu có thể sửa qua một collection lồng bên trong. Việc thay một phần tử bằng `new Score(...)` khác với sửa nội dung của một đối tượng phần tử có thể thay đổi được. Không suy rộng rằng mọi `record` đều bất biến sâu chỉ vì nó là record.

Danh sách đầu vào được giữ nguyên vì hàm lọc tạo danh sách riêng. Việc `input` được tạo bằng `List.of` cũng cho thấy nhận một `List` không có nghĩa là có thể sửa nó tại chỗ.

Cuối cùng, `ArrayList` chấp nhận `null`, nhưng chuyển một danh sách có `null` bằng `List.copyOf` bị từ chối. Chính sách dữ liệu cần nhất quán ở ranh giới, không chỉ đúng ở cấu trúc làm việc.

### 7.4. Vì sao hàm collectValidScores trả List?

Mã trong ví dụ cần một danh sách kết quả có thể thay đổi để tiếp tục sắp xếp; helper tạo nó bằng `ArrayList` và trả qua kiểu `List`. Khả năng sửa ở đây đến từ hợp đồng và cách triển khai helper trong chương trình, không đến từ tên giao diện.

Trong một API thực, hãy ghi rõ kết quả có thể sửa hay chỉ đọc, có độc lập với nguồn không và có cho phép `null` không. Người gọi không nên phải đoán bằng cách thử `add` rồi bắt ngoại lệ.

Ví dụ chỉ có quyền sửa trong cùng một luồng. Nó không minh chứng hành vi của nhiều luồng ghi chung và không phải phép đo tốc độ giữa các collection.

## 8. Phân tích chi phí của toàn bộ ví dụ

Gọi m là số bản ghi đầu vào và n là số bản ghi được giữ, với n <= m.

### 8.1. Giai đoạn lọc

Mỗi bản ghi được xem một lần. Với phép kiểm tra điểm có chi phí hằng số, vòng lọc có tổng công việc O(m); việc thêm cuối kết quả đóng góp O(n) khấu hao và nằm trong O(m).

Danh sách kết quả giữ n tham chiếu cùng vùng dự trữ có thể có. Nó không tạo lại toàn bộ đối tượng `Score` cho mỗi lần thêm: các phần tử được giữ là tham chiếu tới những đối tượng đầu vào phù hợp.

Nếu không cần danh sách mà chỉ cần tổng điểm, có thể cộng trong lúc duyệt và tránh lưu kết quả. Nhưng ví dụ còn cần đọc theo chỉ số và sắp xếp, nên việc giữ một dãy có lý do.

### 8.2. Giai đoạn truy cập và tổng hợp

Một lần `get(2)` là O(1) trong cấu trúc thật đang dùng. Một lần tính tổng là O(n).

Nếu gọi một phương thức tính tổng bằng cách duyệt lại cho mỗi phần tử, tổng chi phí của thiết kế có thể tăng lên O(n²), dù từng `get` riêng lẻ vẫn O(1). Cấu trúc phù hợp không tự sửa một thuật toán lặp lại công việc không cần thiết.

### 8.3. Giai đoạn sắp xếp

Sắp xếp danh sách cần công việc so sánh và di chuyển tham chiếu; không thể coi đây là O(1) vì chỉ có một dòng `sort`.

Với bộ so sánh có chi phí hằng số và thuật toán sắp xếp đối tượng thông thường của Java, phân tích dùng bậc O(n log n) cho trường hợp tổng quát. Dữ liệu đã có các đoạn thứ tự hoặc điều kiện cụ thể có thể làm lượng công việc thực khác nhau.

Trong ví dụ, so sánh tên còn phụ thuộc độ dài các chuỗi; coi mỗi phép so sánh là O(1) là một giả định khi tách riêng kích thước danh sách khỏi kích thước tên. Khi bộ so sánh gọi phép tính nặng, số phép so sánh và chi phí mỗi phép so sánh đều quan trọng. Không quy toàn bộ thời gian cho collection. Tham khảo mô tả thuật toán sắp xếp mặc định tại [List.sort Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#sort(java.util.Comparator)).

### 8.4. Giai đoạn bản sao và vòng đời bộ nhớ

Khi tạo snapshot từ danh sách làm việc có thể sửa, cần tính công việc bảo toàn n phần tử và bộ nhớ của biểu diễn kết quả. Trong ví dụ, đầu vào, working, snapshot và mutableCopy có thể cùng tồn tại.

Các danh sách có thể chia sẻ đối tượng `Score` nhưng có cấu trúc lưu trữ riêng. Do đó, “sao chép n tham chiếu” và “sao chép n đối tượng nghiệp vụ” là hai mô hình bộ nhớ khác nhau.

Đừng tạo snapshot sau từng lần thêm chỉ vì muốn “dữ liệu luôn bất biến”; có thể làm tổng sao chép tăng đáng kể. Hãy chọn ranh giới chuyển giao phù hợp với yêu cầu.

## 9. Những quyết định thực tế giúp dùng ArrayList đúng chỗ

### 9.1. Đặt trước dung lượng khi có ước lượng đáng tin

Nếu biết sẽ giữ gần k phần tử và k hợp lý với bộ nhớ, `new ArrayList<>(k)` có thể giảm các lần tăng mảng. Nếu chỉ biết số lượng đầu vào rất lớn nhưng tỷ lệ giữ lại rất nhỏ, cấp theo toàn bộ đầu vào có thể lãng phí.

Trong ví dụ lọc, dùng constructor mặc định tránh tự giả định mọi bản ghi đều hợp lệ. Đây là lựa chọn để minh họa rõ, không phải quy tắc rằng phép lọc tuyệt đối không được đặt trước dung lượng.

Đặt trước dung lượng không tạo phần tử, không bảo đảm đủ bộ nhớ cho mọi k và không làm chèn đầu trở thành hằng số.

### 9.2. Giữ quyền sở hữu rõ ràng

Một danh sách nội bộ có thể được sửa tự do trong giai đoạn xây dựng nếu không bị chia sẻ ngoài ý muốn. Khi đưa ra ngoài, hãy quyết định người nhận có được sửa không và các thay đổi có cần quay lại nguồn không.

Trả thẳng một `ArrayList` nội bộ có thể cho phép nơi gọi làm mất những điều kiện mà lớp đang giữ. Trả một view chỉ đọc lại có thể khiến nơi gọi thấy các thay đổi về sau. Cần chọn theo ý nghĩa dữ liệu, không chỉ chọn tên một phương thức bọc.

### 9.3. Chỉ giữ dữ liệu cần thiết

Một danh sách được giữ lâu sẽ giữ tham chiếu tới các phần tử còn trong nó. Nếu dữ liệu chỉ cần trong phạm vi một yêu cầu, đừng đặt nó vào một biến sống toàn ứng dụng chỉ vì muốn tái sử dụng dung lượng.

Nếu cần dùng lại một danh sách lớn, cần xem xét vòng đời, bộ nhớ giữ lại và yêu cầu đa luồng. Việc tái sử dụng có thể có lợi hoặc có hại tùy mẫu tải.

### 9.4. Chọn thuật toán theo lô khi có thể

Nhiều chèn giữa có thể được gom thành `addAll`. Nhiều xóa có thể được diễn đạt bằng xóa đoạn, lọc hoặc tạo kết quả mới, thay vì dời cùng đuôi nhiều lần.

Các thay đổi đó chỉ hợp lệ khi giữ đúng thứ tự, số lần xuất hiện, quyền sở hữu và thời điểm mà nơi khác quan sát được kết quả. Tối ưu không được làm sai hợp đồng dữ liệu.

### 9.5. Đo đúng câu hỏi khi hiệu năng thực sự quan trọng

Một so sánh có ý nghĩa cần nêu rõ:

- Kích thước và phân bố dữ liệu.
- Tỷ lệ đọc, thêm cuối, chèn/xóa và tìm kiếm.
- Có tính constructor, tạo phần tử, sắp xếp và sao chép không.
- Có tính bộ nhớ và độ trễ ở các lần tăng mảng không.
- Danh sách được tạo mới hay tái sử dụng qua nhiều đợt.

Một lần bấm giờ trên máy đang tải hoặc một phép đo chỉ chạy một vòng không đủ để khẳng định cấu trúc nào luôn nhanh hơn. JVM cần được xét với khởi động, JIT, tối ưu và thu gom rác; thời gian của phần tử có thể lấn át thời gian của danh sách.

Không cần làm benchmark cho mọi danh sách nhỏ. Dùng hợp đồng và phân tích để chọn hướng hợp lý trước, rồi đo khi có mục tiêu hiệu năng hoặc bằng chứng cần tối ưu.

## 10. Những hiểu nhầm cần tránh

| Hiểu nhầm | Cách nhìn đúng |
|---|---|
| Mọi collection đều có thể thay bằng ArrayList | Ngữ nghĩa thứ tự, trùng, khóa và quyền sửa khác nhau |
| List nghĩa là danh sách chỉ đọc | List là giao diện; khả năng sửa tùy đối tượng và hợp đồng |
| ArrayList tự sắp xếp | Nó giữ thứ tự dãy hiện tại; sort là bước chủ động |
| ArrayList<Integer> tương đương int[] tự tăng | Có lớp biểu diễn tham chiếu và đóng hộp |
| contains nhanh vì get nhanh | contains có thể phải duyệt và so sánh nhiều phần tử |
| Còn dung lượng thì chèn giữa O(1) | Vẫn phải dịch đoạn đuôi |
| Thêm cuối O(1) nghĩa là mọi lần đều không cấp phát | O(1) khấu hao; có lần tăng mảng |
| ArrayList luôn tốt nhất cho dữ liệu nhỏ hoặc đọc nhiều | Đây là gợi ý theo thao tác, không phải luật tuyệt đối |
| Đổi sang LinkedList làm mọi chèn/xóa giữa O(1) | Cần tính việc đi tới vị trí |
| Bọc unmodifiableList tạo snapshot độc lập | Đó là view phản ánh nguồn |
| copyOf làm các đối tượng bên trong bất biến sâu | Nó không tự sao chép sâu đối tượng phần tử |
| Không thấy ngoại lệ thì dùng chung đa luồng an toàn | Cần quy tắc phối hợp và công bố dữ liệu đúng |
| Dynamic nghĩa là chứa bao nhiêu dữ liệu cũng được | Bộ nhớ và giới hạn môi trường vẫn hữu hạn |

## 11. Tự kiểm tra bằng các tình huống

### Tình huống 1: kết quả tìm kiếm một trang

Ứng dụng nhận tối đa 50 bản ghi cho một trang, cần giữ thứ tự do nguồn trả về và đọc bản ghi theo vị trí khi người dùng chọn hàng.

**Đánh giá:** `ArrayList` là một ứng viên phù hợp cho dữ liệu của trang. Cần quyết định danh sách có được sửa sau khi trả ra ngoài không. Không suy ra rằng phải tải toàn bộ cơ sở dữ liệu vào danh sách để làm phân trang.

### Tình huống 2: hàng đợi công việc

Chương trình liên tục thêm cuối rồi lấy và xóa đầu của một danh sách lớn.

**Đánh giá:** Đây là dấu hiệu cần xem mô hình `Queue`/`Deque`, thay vì trả chi phí dồn mảng sau mỗi lần lấy đầu. Nếu có nhiều luồng, còn phải chọn cách phối hợp phù hợp; một deque thông thường không tự giải quyết truy cập đồng thời.

### Tình huống 3: danh mục theo mã

Có 100.000 sản phẩm và thao tác thường gặp nhất là tìm sản phẩm bằng mã duy nhất.

**Đánh giá:** Một map theo mã có thể phù hợp với truy cập chính. Nếu còn cần danh sách trình bày theo thứ tự, có thể tạo một biểu diễn riêng, nhưng phải xác định thời điểm cập nhật và tính nhất quán. Không dùng chỉ số danh sách thay mã sản phẩm.

### Tình huống 4: dữ liệu đo trùng

Hai phép đo có cùng giá trị nhưng xảy ra ở hai lần ghi nhận khác nhau; báo cáo cần giữ cả hai và giữ thứ tự ghi nhận.

**Đánh giá:** `List` và `ArrayList` có thể phù hợp với ngữ nghĩa đó. Chuyển thành set chỉ để giảm số phần tử sẽ làm mất thông tin mà yêu cầu cần giữ.

### Tình huống 5: kết quả không được sửa

Một phương thức dùng `ArrayList` để xây kết quả, sau đó muốn nơi gọi không được thêm, xóa hoặc thay thế phần tử trong danh sách kết quả và không nhìn thấy các lần thêm về sau của bộ dựng.

**Đánh giá:** Có thể xem `List.copyOf` nếu chính sách dữ liệu không chứa `null`. Nếu phần tử có thể thay đổi, còn phải xử lý tính ổn định của chính phần tử; danh sách không sửa được chưa đồng nghĩa với toàn bộ đồ thị dữ liệu bất biến.

### Tình huống 6: chỉ cần tổng

Nguồn có rất nhiều bản ghi và chương trình chỉ cần tính một tổng, không đọc lại từng bản ghi sau đó.

**Đánh giá:** Có thể tích lũy tổng trong lúc duyệt mà không lưu cả nguồn vào `ArrayList`. Đây là trường hợp xem lại nhu cầu giữ dữ liệu có thể đem lại lợi ích lớn hơn chọn giữa hai lớp danh sách.

### Tình huống 7: nhiều cập nhật theo chỉ số

Một danh sách đã nạp xong, sau đó thường đọc và thay thế các phần tử tại chỉ số đã biết, ít chèn/xóa.

**Đánh giá:** Đây là kiểu thao tác ủng hộ `ArrayList`. Phải kiểm tra chỉ số còn đúng sau những thay đổi cấu trúc khác và không để nhiều luồng cùng sửa mà thiếu phối hợp.

Một quyết định chọn `ArrayList` có cơ sở là quyết định giải thích được **ý nghĩa của dãy**, **các thao tác chiếm ưu thế**, **giới hạn bộ nhớ** và **quyền thay đổi dữ liệu**. Khi các điều kiện đó khớp, cấu trúc này đem lại một cách viết đơn giản, dễ đọc và có mô hình chi phí rõ ràng.
