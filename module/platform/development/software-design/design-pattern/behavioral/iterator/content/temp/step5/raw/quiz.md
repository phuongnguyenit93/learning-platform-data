Câu 1: Iterator Pattern giúp mã duyệt collection đạt mục tiêu chính nào?
A. Đi qua phần tử mà không lộ cách lưu trữ bên trong
B. Buộc mọi collection dùng chung cấu trúc mảng tuyến tính
C. Cho client thao tác trực tiếp node của cây nội bộ
D. Tự sắp xếp collection khi mỗi lần gọi next
Đáp án đúng: A

Câu 2: Trong Java, Iterator và Iterable khác nhau chủ yếu ở đâu?
A. Iterable đọc từng phần tử, Iterator chỉ tạo stream
B. Iterable cung cấp iterator, Iterator duyệt phần tử
C. Iterator luôn có index, Iterable luôn không có index
D. Iterator lưu dữ liệu gốc, Iterable lưu bản sao
Đáp án đúng: B

Câu 3: Iterator.hasNext() được dùng để kiểm tra điều gì?
A. Phần tử hiện tại đã bị xóa khỏi collection
B. Có phần tử tiếp theo mà không cần lấy nó ra
C. Vị trí cursor hiện nằm trước phần tử đầu
D. Collection có hỗ trợ sắp xếp hay không
Đáp án đúng: B

Câu 4: Gọi Iterator.next() khi không còn phần tử sẽ dẫn đến gì?
A. Trả null với mọi implementation của Iterator
B. Tự động quay lại phần tử đầu tiên của collection
C. Ném NoSuchElementException theo hợp đồng Iterator
D. Chặn thread đợi phần tử mới được thêm vào
Đáp án đúng: C

Câu 5: Để duyệt một Iterable hai lần độc lập, cách nào phù hợp?
A. Dùng lại iterator đã hết và gọi next từ đầu
B. Gọi remove sau phần tử cuối để đặt lại cursor
C. Dùng hasNext lặp lại để reset vị trí hiện tại
D. Lấy iterator mới cho mỗi lượt duyệt
Đáp án đúng: D

Câu 6: Với for (T x : values), điều kiện về đối tượng values trong Java là gì?
A. Chỉ cần triển khai Iterator nhưng không Iterable
B. Là mảng hoặc triển khai Iterable phù hợp
C. Bắt buộc là java.util.ArrayList cụ thể
D. Bắt buộc cung cấp ListIterator hai chiều
Đáp án đúng: B

Câu 7: Khi tự viết Iterator cho danh sách liên kết, thông tin nào thường cần giữ?
A. Bản sao của mọi node và database connection
B. Con trỏ node kế tiếp và trạng thái xóa phần tử
C. Toàn bộ mã nguồn của lớp LinkedList đã dùng
D. Danh sách lớp kế thừa của từng node dữ liệu
Đáp án đúng: B

Câu 8: Một triển khai hasNext() đúng với collection ổn định nên có đặc tính nào?
A. Mỗi lần gọi phải tăng vị trí cursor thêm một
B. Gọi khi còn phần tử sẽ tự xóa phần tử đầu
C. Gọi nhiều lần không làm tiến vị trí cursor
D. Kết quả luôn false sau lần gọi đầu tiên
Đáp án đúng: C

Câu 9: Nếu Iterator<T> đang trỏ tới phần tử đầu, next() nên thực hiện gì?
A. Trả phần tử thứ hai và giữ cursor ở đầu
B. Chỉ tiến cursor mà không trả phần tử nào
C. Trả phần tử đầu rồi tiến cursor sang vị trí sau
D. Trả cả collection rồi đặt cursor ở cuối
Đáp án đúng: C

Câu 10: Iterator.remove() có mục đích gì khi implementation hỗ trợ?
A. Xóa bất kỳ phần tử nào có cùng kiểu dữ liệu
B. Xóa phần tử được trả bởi lần next gần nhất
C. Xóa toàn bộ collection khi cursor tới cuối
D. Xóa phần tử sẽ được trả bởi lần next kế
Đáp án đúng: B

Câu 11: Với Iterator thông thường, gọi remove() hai lần sau một next() gây gì?
A. IllegalStateException do chưa next lại
B. NoSuchElementException vì collection rỗng
C. ConcurrentModificationException mọi lần gọi
D. UnsupportedOperationException dù có hỗ trợ xóa
Đáp án đúng: A

Câu 12: Nếu iterator không hỗ trợ xóa, gọi remove() sẽ có kết quả nào?
A. Có thể ném UnsupportedOperationException
B. Luôn ném NoSuchElementException vì thiếu dữ liệu
C. Luôn tự tạo bản sao trước khi xóa phần tử
D. Luôn xóa thành công dù collection bất biến
Đáp án đúng: A

Câu 13: ListIterator mở rộng Iterator bằng khả năng nào?
A. Duyệt map theo cặp key và value có hash
B. Duyệt stream song song qua executor riêng
C. Duyệt tất cả collection mà không cần index
D. Duyệt lùi và sửa List tại vị trí cursor
Đáp án đúng: D

Câu 14: Muốn bắt đầu duyệt ngược List từ cuối, nên lấy iterator thế nào?
A. list.iterator() rồi gọi previous() trên Iterator
B. list.listIterator(0) rồi gọi previous() ngay
C. listIterator(size) rồi gọi previous()
D. list.iterator() rồi gọi reset() trước previous()
Đáp án đúng: C

Câu 15: Khi ListIterator ở cuối List có n phần tử, nextIndex() trả về gì?
A. n, chỉ số vị trí sẽ thêm ở cuối nếu cần
B. n-1, chỉ số phần tử đã được trả gần nhất
C. 0, vì iterator tự quay lại đầu danh sách
D. -1, vì không tồn tại phần tử tiếp theo
Đáp án đúng: A

Câu 16: ListIterator.add(x) chèn phần tử vào vị trí nào?
A. Ghi đè phần tử cuối vừa được next() trả
B. Chèn vào đầu List bất kể vị trí cursor
C. Thêm vào cuối List bất kể vị trí cursor
D. Ngay trước phần tử mà next() sẽ trả về
Đáp án đúng: D

Câu 17: ListIterator.set(x) hợp lệ khi nào?
A. Ngay khi tạo iterator dù chưa duyệt phần tử
B. Sau add mà chưa gọi next hoặc previous lại
C. Sau next/previous, nếu chưa có add hoặc remove
D. Sau remove mà chưa gọi next hoặc previous lại
Đáp án đúng: C

Câu 18: Vì sao xóa trực tiếp ArrayList.remove(x) trong for-each có thể gây lỗi?
A. Vì Iterator.remove không tồn tại trong Java
B. Vì ArrayList tự chuyển thành immutable List
C. Vì for-each luôn yêu cầu danh sách đã sort
D. Sửa cấu trúc ngoài iterator đang duyệt
Đáp án đúng: D

Câu 19: Với ArrayList, ConcurrentModificationException từ iterator là cơ chế gì?
A. Khóa đồng bộ bảo đảm không có race condition
B. Cơ chế rollback mọi thay đổi của collection
C. Fail-fast phát hiện sửa đổi theo best effort
D. Cam kết luôn phát hiện mọi sửa đổi đồng thời
Đáp án đúng: C

Câu 20: Iterator của CopyOnWriteArrayList có đặc điểm gì?
A. Duyệt ảnh chụp dữ liệu tại lúc tạo iterator
B. Luôn phản ánh tức thời mọi phần tử vừa thêm
C. Hỗ trợ remove trực tiếp qua iterator trên snapshot
D. Luôn khóa độc quyền List suốt quá trình duyệt
Đáp án đúng: A

Câu 21: Iterator của ConcurrentHashMap thường đảm bảo gì khi có cập nhật đồng thời?
A. Luôn ném ConcurrentModificationException khi cập nhật
B. Duyệt weakly consistent, có thể thấy một số cập nhật
C. Luôn chụp snapshot bất biến đầy đủ tại thời điểm tạo
D. Luôn đợi mọi thread khác ngừng cập nhật rồi duyệt
Đáp án đúng: B

Câu 22: Khi duyệt Collections.synchronizedList bằng Iterator, nên làm gì?
A. Chỉ gọi iterator mà không cần lock vì đã synchronized
B. Tạo thread riêng cho mỗi lần gọi hasNext
C. Đồng bộ thủ công trên list trong lúc duyệt
D. Đưa tất cả lời gọi next vào CompletableFuture
Đáp án đúng: C

Câu 23: Để kiểm thử kết quả duyệt HashSet, yếu tố nào cần tránh giả định?
A. Mỗi phần tử được duyệt tối đa một lần
B. Mọi phần tử hợp lệ đều có thể được duyệt
C. Duyệt một Set có kích thước hữu hạn sẽ kết thúc
D. Thứ tự cố định của phần tử giữa các lần chạy
Đáp án đúng: D

Câu 24: Iterator.forEachRemaining(action) thực hiện công việc nào?
A. Chạy action trên phần tử vừa remove rồi dừng
B. Tạo iterator mới rồi luôn bắt đầu từ phần tử đầu
C. Chỉ chuyển iterator sang cuối mà không gọi action
D. Gọi action cho các phần tử chưa được duyệt
Đáp án đúng: D

Câu 25: Với collection rỗng, tình huống kiểm thử Iterator nào đúng?
A. hasNext false; next ném NoSuchElementException
B. hasNext true để báo vị trí cursor hợp lệ
C. next trả null một lần rồi mới ném exception
D. remove luôn thành công dù chưa từng gọi next
Đáp án đúng: A

Câu 26: Với collection chỉ có một phần tử, trình tự nào cần kiểm tra?
A. hasNext true, next một lần, rồi hasNext false
B. hasNext false, next một lần, rồi hasNext true
C. next hai lần phải trả cùng phần tử đầu tiên
D. hasNext gọi hai lần phải tiêu thụ phần tử đó
Đáp án đúng: A

Câu 27: Nếu vừa duyệt vừa lọc bỏ phần tử của List, cách nào thích hợp?
A. Gọi List.remove trực tiếp trong mọi for-each
B. Tự tăng index trong khi dùng iterator độc lập
C. Dùng Collections.sort để xóa phần tử bị lọc
D. Dùng Iterator.remove hoặc List.removeIf phù hợp
Đáp án đúng: D

Câu 28: Khi hai thread dùng chung một Iterator thông thường, cần lưu ý gì?
A. Iterator tự bảo đảm thread-safe với mọi collection
B. Đồng bộ truy cập khi cursor bị chia sẻ giữa thread
C. Mỗi lời gọi next tự dùng transaction để khóa
D. hasNext đảm bảo next không thể bị thread khác lấy
Đáp án đúng: B
