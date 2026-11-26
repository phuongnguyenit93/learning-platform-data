Câu 01. Đặc điểm nào thuộc hợp đồng `List` trong Java Collections Framework?
A. Cho phép phần tử trùng và đọc phần tử theo chỉ số
B. Duy trì thứ tự sắp xếp tự nhiên khi thêm phần tử mới
C. Chỉ lưu một giá trị trên mỗi khóa như ánh xạ Map
D. Loại phần tử trùng và truy cập phần tử bằng khóa băm
Đáp án đúng: A

Câu 02. Trong `HashSet`, hai phần tử khác tham chiếu nhưng `equals()` trả `true` sẽ được xử lý thế nào khi `hashCode` tuân hợp đồng?
A. Sắp xếp hai phần tử cạnh nhau theo thứ tự hash code
B. Chỉ giữ một phần tử theo hợp đồng equals/hashCode nhất quán
C. Giữ cả hai phần tử vì tham chiếu object không trùng
D. Giữ cả hai phần tử nếu lần chèn diễn ra khác thread
Đáp án đúng: B

Câu 03. Khi gọi `Map.put(k, newValue)` với khóa `k` đã tồn tại, điều gì xảy ra?
A. Thay giá trị của khóa đó và trả về giá trị cũ
B. Tạo thêm cặp entry có cùng khóa trong Map
C. Ném lỗi trùng khóa trước khi thay đổi giá trị
D. Xóa khóa khỏi map và trả về chính khóa vừa xóa
Đáp án đúng: A

Câu 04. Với `Queue<String>` là `ArrayDeque`, sau `offer("A"); offer("B"); poll()`, giá trị nhận được là gì?
A. `null` vì `poll` chỉ xem chứ không lấy phần tử
B. Lỗi vì `ArrayDeque` không cài đặt giao diện `Queue`
C. `"B"` vì phần tử vừa thêm được ưu tiên lấy trước
D. `"A"` vì phần tử vào trước được lấy ở đầu hàng đợi
Đáp án đúng: D

Câu 05. Một `Deque` rỗng lần lượt gọi `addFirst("A")`, `addFirst("B")`, `removeLast()`; giá trị trả về là gì?
A. Ném lỗi vì addFirst không dùng chung được với removeLast
B. `"A"` vì hai lần chèn vào đầu đẩy A về phía cuối
C. `"B"` vì removeLast tương đương pop ở phía đầu
D. `null` vì removeLast chỉ lấy phần tử khi có offerLast
Đáp án đúng: B

Câu 06. Độ phức tạp truy cập `ArrayList.get(i)` hợp lệ thường là gì?
A. `O(log n)` vì phải đi qua một cây cân bằng
B. `O(n)` vì phải lần lượt bước qua từng node liên kết
C. `O(1)` nhờ đọc phần tử tại vị trí mảng nội bộ
D. `O(n log n)` vì cần sắp xếp trước khi đọc chỉ số
Đáp án đúng: C

Câu 07. Với `LinkedList.get(i)` ở vị trí giữa danh sách dài, thao tác thường có độ phức tạp nào?
A. `O(log n)` vì được tổ chức dưới dạng cây tìm kiếm
B. `O(n log n)` vì phải sắp xếp các node trước
C. `O(1)` vì có mảng chỉ mục đến từng node
D. `O(n)` do duyệt các node từ đầu hoặc cuối
Đáp án đúng: D

Câu 08. Khi chèn phần tử vào giữa một `ArrayList` bằng `add(index, element)`, chi phí đáng chú ý là gì?
A. `O(n log n)` do cả danh sách được sắp xếp lại
B. `O(n)` do phải dời các phần tử phía sau
C. `O(1)` do chỉ sửa liên kết hai node láng giềng
D. `O(log n)` do chỉ cần cân bằng lại cây con
Đáp án đúng: B

Câu 09. Khi hash phân bố đều, `HashMap.get(key)` thường đạt độ phức tạp trung bình nào?
A. Gần `O(log n)` vì khóa được đặt trong cây đỏ-đen
B. Gần `O(n)` vì phải so từng khóa trong toàn Map
C. Gần `O(1)` nhờ tra bucket từ hash của khóa
D. Gần `O(n log n)` vì cần sắp xếp bucket trước
Đáp án đúng: C

Câu 10. Khẳng định nào đúng về thứ tự duyệt entry của `HashMap`?
A. Duyệt các khóa tăng dần theo thứ tự tự nhiên của chúng
B. Sắp entry theo thời điểm truy cập gần nhất của mỗi khóa
C. Giữ nguyên thứ tự thêm giống cấu trúc LinkedHashMap
D. Không cam kết thứ tự thêm hay thứ tự sắp xếp khóa
Đáp án đúng: D

Câu 11. Nếu cần `Map` duyệt theo thứ tự chèn mặc định, cấu trúc nào phù hợp?
A. `LinkedHashMap` duy trì trình tự thêm entry vào Map
B. `IdentityHashMap` duy trì trình tự thêm entry vào Map
C. `HashMap` duy trì trình tự thêm entry vào Map
D. `TreeMap` duy trì trình tự thêm entry vào Map
Đáp án đúng: A

Câu 12. Để xây cache LRU đơn giản bằng `LinkedHashMap`, thiết kế nào phù hợp nhất?
A. Dùng insertion-order rồi override `equals` của Map
B. Bật natural ordering rồi override `hashCode` của key
C. Bật access-order rồi override `removeEldestEntry`
D. Dùng hash ordering rồi override `compareTo` của entry
Đáp án đúng: C

Câu 13. Với `TreeMap`, thứ tự duyệt khóa do yếu tố nào quyết định?
A. Giá trị `hashCode` của khóa được sắp theo tăng dần
B. Thứ tự đọc gần nhất theo cơ chế access-order
C. Thứ tự tự nhiên hoặc `Comparator` được chỉ định
D. Thứ tự thêm vào Map từ thao tác `put` đầu tiên
Đáp án đúng: C

Câu 14. Trong `HashSet`, thứ tự phần tử khi duyệt được bảo đảm ra sao?
A. Sắp phần tử theo thứ tự tự nhiên của chúng
B. Không có bảo đảm về thứ tự duyệt phần tử
C. Giữ thứ tự được thêm như LinkedHashSet
D. Sắp theo Comparator truyền vào constructor
Đáp án đúng: B

Câu 15. Loại `Set` nào duy trì thứ tự chèn khi lặp qua các phần tử?
A. `HashSet` bảo toàn trình tự chèn của phần tử
B. `TreeSet` bảo toàn trình tự chèn của phần tử
C. `LinkedHashSet` bảo toàn trình tự chèn của phần tử
D. `CopyOnWriteArraySet` sắp xếp phần tử theo comparator
Đáp án đúng: C

Câu 16. Nếu `TreeSet` dùng `Comparator` trả 0 cho hai object khác nhau theo `equals`, điều gì xảy ra khi thêm cả hai?
A. `TreeSet` coi chúng là trùng và chỉ giữ một
B. `TreeSet` vẫn thêm cả hai vì `equals` khác nhau
C. `TreeSet` so sánh tham chiếu để cho phép thêm cả hai
D. `TreeSet` dùng hashCode để phân biệt và giữ cả hai object
Đáp án đúng: A

Câu 17. Quy tắc nào của `equals()` và `hashCode()` cần tuân thủ khi dùng làm khóa băm?
A. Nếu hai object bằng nhau thì hash phải theo thứ tự tăng
B. `a.equals(b)` đúng thì `a.hashCode() == b.hashCode()`
C. Nếu hai object có cùng hash code thì `equals` phải đúng
D. Nếu hai object không cùng tham chiếu thì hash phải khác
Đáp án đúng: B

Câu 18. Hai object khác nhau theo `equals` nhưng có cùng `hashCode` có hợp lệ không?
A. Không; hash collision làm vi phạm hợp đồng Object
B. Có; hai khóa có thể trùng hash nhưng khác `equals`
C. Không; HashSet xóa bớt object khi có hash trùng
D. Có, nhưng HashMap sẽ bỏ qua `equals` khi tra key
Đáp án đúng: B

Câu 19. Nếu dùng một key mutable trong `HashMap` rồi thay field tham gia tính `hashCode`, rủi ro nào xuất hiện?
A. Map tự chuyển key đó sang weak reference trong bucket
B. Entry trở thành immutable trước lần gọi get tiếp theo
C. Entry có thể không tìm lại được bằng key đã đổi
D. Map tự tái băm các bucket khi field của key thay đổi
Đáp án đúng: C

Câu 20. Với `HashMap<String,String>`, phát biểu nào đúng về `null`?
A. Không hỗ trợ giá trị `null`, nhưng hỗ trợ khóa `null`
B. Chấp nhận một khóa `null` và nhiều giá trị `null`
C. Không hỗ trợ khóa `null`, nhưng hỗ trợ giá trị `null`
D. Hỗ trợ nhiều entry riêng biệt cùng khóa `null`
Đáp án đúng: B

Câu 21. Khi gọi `ConcurrentHashMap.put(null, 1)` hoặc `put("x", null)`, kết quả thường là gì?
A. Thêm entry null như HashMap nhưng bảo vệ bằng lock
B. Lặng lẽ bỏ qua lời gọi put mà không thay đổi map
C. Chuyển null thành sentinel để người gọi nhận giá trị mặc định
D. `ConcurrentHashMap` ném `NullPointerException`
Đáp án đúng: D

Câu 22. Iterator của `ConcurrentHashMap` khi có thread khác cập nhật thường có đặc tính nào?
A. Duyệt weakly consistent, có thể thấy cập nhật đồng thời
B. Ném `ConcurrentModificationException` khi map thay đổi
C. Khóa toàn bộ map cho đến khi iterator kết thúc
D. Chụp snapshot cố định tại lúc tạo để không thấy cập nhật
Đáp án đúng: A

Câu 23. Iterator của `CopyOnWriteArrayList` nhìn thấy những thay đổi sau khi iterator được tạo ra sao?
A. Tự khóa list trong suốt vòng đời của các iterator
B. Duyệt snapshot cũ, không thấy các sửa đổi về sau
C. Cập nhật theo trạng thái live từng lần gọi next
D. Ném ConcurrentModificationException khi có thêm phần tử
Đáp án đúng: B

Câu 24. Khi duyệt `Collections.synchronizedList(list)` bằng iterator, cách nào bảo đảm đồng bộ truy cập phù hợp?
A. Chỉ đồng bộ riêng lời gọi `iterator()` trước vòng lặp
B. Không cần đồng bộ vì iterator tự dùng khóa tại mỗi next
C. Dùng `volatile` cho biến tham chiếu tới syncList
D. Đặt toàn bộ vòng duyệt trong `synchronized(syncList)`
Đáp án đúng: D

Câu 25. Điều nào đúng về `List.of("a", "b")`?
A. List không sửa được và từ chối phần tử `null`
B. List giữ được `null` và cho phép xóa phần tử bằng remove
C. List là view sửa được của mảng tham số truyền vào
D. List thêm được phần tử nhưng không sửa được phần tử cũ
Đáp án đúng: A

Câu 26. Nếu `mutable` là ArrayList, `List.copyOf(mutable)` tạo danh sách có hành vi nào?
A. Bản sao không sửa được, độc lập với thay đổi của nguồn
B. Danh sách kết quả liên kết cùng backing array của nguồn
C. Danh sách kết quả là view cập nhật khi nguồn thêm phần tử
D. Danh sách kết quả cho phép add nhưng cấm set lên phần tử cũ
Đáp án đúng: A

Câu 27. Với `Collections.unmodifiableList(backing)`, thay đổi trực tiếp từ `backing` có tác động gì?
A. Không thể xảy ra vì wrapper sao chép backing lúc tạo
B. Có thể hiện ra trong view dù view cấm các thao tác sửa
C. Wrapper biến backing thành immutable đối với các tham chiếu khác
D. Wrapper tự ném lỗi khi có thread đọc nội dung đã đổi
Đáp án đúng: B

Câu 28. Với `List<String> list = Arrays.asList(arr)`, thao tác nào có thể thành công?
A. `list.remove(0)` làm mảng `arr` giảm kích thước
B. `list.clear()` xóa các slot và giảm chiều dài mảng
C. `list.add("x")` mở rộng `arr` bằng một phần tử mới
D. `list.set(0, "x")` sửa phần tử của cả `arr`
Đáp án đúng: D

Câu 29. Với `List.subList(from,to)`, quan hệ giữa sublist và list gốc là gì?
A. Đây là stream một lần và không cho phép set phần tử
B. Sublist là view, thay đổi thể hiện trên list gốc
C. Đây là bản sao độc lập được đóng băng tại thời điểm lấy
D. Đây là Set duy trì thứ tự chỉ số của phần tử trong list gốc
Đáp án đúng: B

Câu 30. Khi muốn xóa phần tử hiện tại trong lúc duyệt `ArrayList` bằng iterator, cách nào đúng?
A. Dùng `Iterator.remove()` sau lần `next()` tương ứng
B. Gọi `list.remove(item)` từ trong vòng foreach rồi tiếp tục
C. Gọi `list.clear()` mỗi khi iterator gặp phần tử cần xóa
D. Gọi `list.subList(0,1).clear()` để bảo toàn iterator
Đáp án đúng: A

Câu 31. Phát biểu nào đúng về fail-fast iterator của `ArrayList`?
A. Tự giữ read-lock trong toàn bộ thời gian iterator tồn tại
B. Không cho phép `Iterator.remove()` trong bất kỳ trường hợp nào
C. Có thể ném `ConcurrentModificationException` nhưng không bảo đảm đồng bộ
D. Đảm bảo phát hiện race khi list bị thread khác sửa
Đáp án đúng: C

Câu 32. Để sắp `List<Person>` tăng theo tuổi và sau đó theo tên khi cùng tuổi, comparator nào phù hợp?
A. `Comparator.comparingInt(Person::age).thenComparing(Person::name)`
B. `Comparator.comparing(Person::name).reversed()`
C. `Comparator.comparing(Person::name).thenComparingInt(Person::age)`
D. `Comparator.comparingInt(Person::age).reversed()`
Đáp án đúng: A

Câu 33. Trước khi gọi `Collections.binarySearch(list, key, comp)`, điều kiện quan trọng nào cần có?
A. List phải là LinkedList để duyệt từ giữa tối ưu
B. Các phần tử của list phải có hashCode khác nhau
C. List phải được bọc bằng Collections.synchronizedList
D. List đã được sắp theo cùng comparator dùng để tìm
Đáp án đúng: D

Câu 34. Với `PriorityQueue<Integer>` mặc định chứa 8, 2, 5, kết quả `poll()` đầu tiên là gì?
A. Trả `5` do phần tử chèn cuối được ưu tiên
B. Trả `null` do iterator chưa được khởi tạo
C. `2` vì head của heap là giá trị nhỏ nhất
D. Trả `8` do queue theo thứ tự chèn vào trước
Đáp án đúng: C

Câu 35. Tại sao không nên dùng iterator của `PriorityQueue` để xuất dữ liệu theo thứ tự ưu tiên?
A. Iterator bỏ phần tử đầu tiên để tối ưu cấu trúc heap
B. Iterator tự thay đổi comparator sau mỗi lần gọi next
C. Iterator chỉ trả các phần tử có cùng mức ưu tiên
D. Iterator không bảo đảm duyệt theo độ ưu tiên
Đáp án đúng: D

Câu 36. Khi gọi `new ArrayDeque<String>().add(null)`, điều gì xảy ra?
A. Lưu phần tử null hợp lệ ở vị trí đầu của deque
B. Bỏ qua phần tử null và trả về kết quả false
C. Thay null bằng chuỗi rỗng trước khi đưa vào deque
D. Ném `NullPointerException` vì Deque này không nhận null
Đáp án đúng: D

Câu 37. Với `Queue` đang rỗng, khác biệt giữa `poll()` và `remove()` là gì?
A. `poll()` trả null, còn `remove()` ném NoSuchElementException
B. Cả hai đều trả null mà không làm thay đổi hàng đợi
C. Cả hai đều chờ đến khi có phần tử để lấy ra
D. `poll()` ném lỗi, còn `remove()` trả null
Đáp án đúng: A

Câu 38. Vì sao không thể gán trực tiếp `List<String>` cho biến `List<Object>` trong Java?
A. List<String> bị xóa kiểu nên compiler cấm các phép gán
B. String không kế thừa Object trong generic type system
C. List<Object> chỉ có thể được tạo bởi các factory methods
D. Tham số kiểu của `List<T>` có tính invariant
Đáp án đúng: D

Câu 39. Với biến `List<? extends Number> nums`, thao tác nào được bảo đảm hợp lệ?
A. Thêm Integer vì wildcard extends nhận subtype trực tiếp
B. Thêm Number vì danh sách khai báo extends Number
C. Đọc phần tử dưới kiểu Number; không thêm Integer tùy ý
D. Đọc phần tử dưới kiểu Integer vì wildcard là Number
Đáp án đúng: C

Câu 40. Với biến `List<? super Integer> out`, cách sử dụng nào đúng?
A. Chỉ được thêm Number, không được thêm Integer
B. Không thể thêm Integer vì wildcard super chỉ hỗ trợ đọc
C. Có thể thêm Integer và đọc kết quả dưới kiểu Object
D. Có thể đọc phần tử dưới kiểu Integer mà không cast
Đáp án đúng: C
