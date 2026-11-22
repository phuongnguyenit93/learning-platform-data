# Vector và Stack: hợp đồng cũ và lựa chọn thay thế

Vector và Stack vẫn xuất hiện trong thư viện, giao diện cũ và mã Java đã tồn tại lâu. Hiểu chúng giúp đọc đúng hành vi hiện tại và chọn cấu trúc phù hợp khi viết mới hoặc chuyển đổi.

Không nên chỉ thay tên lớp. Vector là một List có các đặc điểm về đồng bộ hóa và API lịch sử. Stack kế thừa Vector, bổ sung cách dùng vào sau ra trước nhưng vẫn mang cả các thao tác danh sách. Thay chúng có thể đổi thứ tự duyệt, cách báo rỗng, khả năng chứa null và cả phạm vi đồng bộ hóa.

Bài dùng Java 17. “Cũ” ở đây nói về lịch sử thiết kế và hướng lựa chọn API; không có nghĩa hai lớp đã biến mất hoặc cứ gặp là phải sửa ngay.

## 1. Hai kiểu trừu tượng cần phân biệt

### 1.1. Danh sách có chỉ số

Vector là một mảng đối tượng có thể tăng giảm kích thước và truy cập bằng chỉ số. Nó triển khai List, nên có ý nghĩa danh sách: giữ thứ tự phần tử, chấp nhận phần tử trùng và hỗ trợ vị trí.

Một đối tượng Vector có thể được dùng như:

~~~java
List<String> names = new Vector<>();
names.add("A");
names.add("B");
String first = names.get(0);
~~~

Đây là đoạn minh họa một phần. Kiểu biến List giúp nói nhu cầu danh sách, nhưng đối tượng cụ thể vẫn là Vector.

### 1.2. Ngăn xếp vào sau ra trước

Ngăn xếp là quy tắc thao tác: thêm ở đỉnh và lấy ra ở cùng đỉnh. Với chuỗi đẩy A, B, C, thứ tự lấy ra là C, B, A.

~~~text
đẩy A, rồi B, rồi C

đỉnh -> C
        B
đáy  -> A

lấy ra: C, B, A
~~~

Stack mở rộng Vector để cung cấp push, pop, peek, empty và search. Tài liệu Java khuyến nghị dùng Deque và các cách triển khai của nó cho bộ thao tác ngăn xếp mới. [Java 17: Stack](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Stack.html)

Nhu cầu “danh sách theo chỉ số” và “ngăn xếp chỉ thao tác ở đỉnh” không phải cùng một hợp đồng. Đây là điểm bắt đầu để chọn thay thế.

## 2. Vector mang theo những hợp đồng nào?

Vector có từ Java 1.0 và được đưa vào Java Collections Framework bằng cách triển khai List ở các phiên bản sau. Vì vậy, nó có cả tên phương thức lịch sử và tên theo giao diện List.

### 2.1. Tên cũ và cách đọc theo List

| API cũ | API List tương ứng về mục đích | Điểm cần chú ý |
|---|---|---|
| addElement(x) | add(x) | AddElement trả void; add trả boolean |
| elementAt(i) | get(i) | Đọc theo chỉ số |
| insertElementAt(x, i) | add(i, x) | Thứ tự hai đối số khác nhau |
| setElementAt(x, i) | set(i, x) | Set trả giá trị cũ; API cũ trả void |
| removeElement(x) | remove(Object) | Xóa theo đối tượng |
| removeElementAt(i) | remove(i) | Xóa theo chỉ số; kiểu trả về khác |
| removeAllElements() | clear() | Loại mọi phần tử |

Bảng nói về mục đích thao tác, không hứa rằng có thể đổi chuỗi tên trong mọi biểu thức mà bỏ qua kiểu trả về hoặc cách xử lý lỗi.

Với List<Integer>, remove(i) còn dễ bị hiểu nhầm giữa xóa chỉ số và xóa giá trị Integer. Đó là lý do phải đọc kiểu đối số, không chỉ tên phương thức.

### 2.2. Size khác capacity

Size là số phần tử thực tế. Capacity là sức chứa của mảng nền, ít nhất bằng size.

`ensureCapacity(n)` chuẩn bị khả năng lưu trữ và không tự thêm n phần tử. Ngược lại, `setSize(n)` thay số phần tử: tăng size thêm các phần tử null; giảm size bỏ phần tử ở phía cuối.

Ví dụ:

~~~text
ban đầu có A, B: size = 2
ensureCapacity(8): vẫn có A, B
setSize(4): A, B, null, null
~~~

Không dùng setSize chỉ để “đặt trước bộ nhớ”. Các null mới thêm trở thành phần tử danh sách và có thể ảnh hưởng xử lý hoặc việc chuyển sang cấu trúc cấm null.

Vector còn có capacityIncrement và các phương thức như trimToSize. Khi thay thế, phải xác định mã cũ có thật sự phụ thuộc những API riêng đó hay chỉ cần một List. [Java 17: Vector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Vector.html)

### 2.3. Đồng bộ hóa không phải phép ghép nguyên tử tự động

Vector được đồng bộ hóa. Nhưng nhiều lời gọi liên tiếp không tự trở thành một thao tác không thể bị xen vào.

Ví dụ:

~~~java
if (!values.contains(item)) {
    values.add(item);
}
~~~

Đây là mẫu minh họa có thể sai với yêu cầu “chỉ thêm nếu chưa có” khi nhiều luồng cùng thao tác. Hai luồng có thể đều thấy chưa có trước khi một trong hai thêm.

Không được suy ra rằng dữ liệu mảng bên trong Vector chắc chắn bị hỏng trong ví dụ đó. Vấn đề là điều kiện nghiệp vụ trải qua nhiều lời gọi, còn phạm vi bảo vệ của từng lời gọi không bao phủ cả điều kiện và cập nhật.

## 3. Enumeration và Iterator: đọc hợp đồng duyệt

Vector cung cấp `elements()` trả Enumeration với hasMoreElements/nextElement. Nó cũng hỗ trợ Iterator và ListIterator theo Collections Framework.

Iterator có cơ chế fail-fast theo nỗ lực tốt nhất. Enumeration của Vector không fail-fast; nếu Vector bị thay đổi cấu trúc trong lúc enumeration hoạt động, kết quả duyệt không được xác định theo hợp đồng đó.

Vì vậy, không đổi Iterator sang Enumeration chỉ để “hết ConcurrentModificationException”. Không có ngoại lệ không chứng minh một lượt duyệt đang thấy dữ liệu nhất quán.

Khi cần lượt duyệt được bảo vệ, phải tổ chức cả phạm vi duyệt theo chính sách khóa phù hợp. Khi cần bản dữ liệu tách cấu trúc để xử lý ở ngoài vùng được bảo vệ, có thể tạo bản sao trong lúc nguồn ở trạng thái hợp lệ.

Bản sao danh sách vẫn giữ tham chiếu phần tử; nó không tự sao chép sâu các đối tượng.

## 4. Stack: các thao tác ngăn xếp và phần kế thừa

### 4.1. Năm phương thức cần đọc đúng

| Phương thức Stack | Ý nghĩa |
|---|---|
| push(x) | Thêm x ở đỉnh và trả lại x |
| pop() | Lấy và xóa đỉnh; rỗng ném EmptyStackException |
| peek() | Xem đỉnh, không xóa; rỗng ném EmptyStackException |
| empty() | Hỏi không có phần tử |
| search(x) | Vị trí tính từ đỉnh, bắt đầu 1; không thấy trả -1 |

Search dùng quy tắc bằng nhau của phần tử và tìm lần xuất hiện gần đỉnh nhất. Nó không phải chỉ số List bắt đầu từ 0.

Với Stack chứa A, B, C theo thứ tự chỉ số từ 0:

~~~text
indexOf(B) = 1
search(B)  = 2
peek()     = C
~~~

Search và indexOf trả hai loại tọa độ khác nhau. Khi chuyển đổi, không được dùng nguyên một kết quả search làm chỉ số truy cập danh sách. [Java 17: phương thức của Stack](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Stack.html)

### 4.2. Stack vẫn lộ thao tác Vector

Do kế thừa Vector, Stack vẫn có add(index, value), get, set, remove(index), setSize và nhiều thao tác danh sách.

Ví dụ minh họa:

~~~java
Stack<Integer> stack = new Stack<>();
stack.push(10);
stack.push(20);
stack.add(0, 99);
~~~

Dữ liệu thành 99, 10, 20. Lệnh thêm theo chỉ số đã sửa phần đáy; nó không phải thao tác chỉ ở đỉnh của một ngăn xếp trừu tượng.

Điều này không làm các phương thức push/pop mất quy tắc, nhưng bề mặt API rộng hơn nhu cầu LIFO. Khai báo bằng Deque giúp diễn đạt thao tác hai đầu mà không mang API truy cập chỉ số của List.

## 5. Thay Vector bằng gì?

### 5.1. Danh sách không cần đồng bộ hóa nội bộ

Với danh sách được giữ cục bộ hoặc có chính sách truy cập khác đã rõ, ArrayList thường là lựa chọn tự nhiên. Tài liệu Vector cũng hướng đến ArrayList khi không cần cách triển khai đồng bộ hóa của Vector.

ArrayList vẫn có chỉ số, thứ tự và khả năng chứa null, nhưng không tự đồng bộ hóa. Đừng thay trong mã dùng chung nhiều luồng rồi vô tình bỏ một cơ chế bảo vệ mà mã cũ đang phụ thuộc. [Java 17: ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html)

Chuyển cấu trúc bằng `new ArrayList<>(vector)` tạo danh sách mới theo thứ tự duyệt nguồn. Nó không tạo alias của cấu trúc Vector, nhưng phần tử bên trong vẫn có thể là cùng các đối tượng.

### 5.2. Danh sách dùng chung với khóa

`Collections.synchronizedList(new ArrayList<>())` cung cấp một List được bọc đồng bộ. Việc ghép nhiều thao tác và duyệt vẫn cần chính sách bao phủ phạm vi cần tính nhất quán.

Tài liệu yêu cầu đồng bộ hóa trên chính danh sách bọc khi duyệt bằng iterator, spliterator hoặc stream; mọi truy cập phải đi qua cơ chế được chọn. [Java 17: Collections.synchronizedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List))

Nó không phải phép biến đổi tự động làm mọi đoạn check-then-act đúng. Nếu đổi từ Vector sang wrapper chỉ để đổi tên lớp mà giữ nguyên lỗi ghép thao tác, lỗi logic vẫn còn.

### 5.3. Nhiều lượt đọc, ít thay đổi

CopyOnWriteArrayList là lựa chọn cần cân nhắc cho một số danh sách dùng chung có lượng duyệt vượt xa lượng sửa. Các thao tác sửa sao chép mảng, còn iterator thấy ảnh chụp tại lúc tạo và không hỗ trợ sửa qua iterator.

Đổi lại là chi phí sao chép và bộ nhớ khi cập nhật; nó không phù hợp mặc định cho mọi danh sách nhiều luồng, nhất là tải ghi thường xuyên. [Java 17: CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html)

Chọn từ tải công việc và hợp đồng quan sát cần có, không từ nhãn “có hỗ trợ nhiều luồng” chung chung.

## 6. Thay Stack bằng Deque: chọn đúng đầu

### 6.1. Quy ước đỉnh ở đầu deque

Cách phổ biến:

~~~java
Deque<String> stack = new ArrayDeque<>();
stack.push("A");
stack.push("B");
String top = stack.pop();
~~~

Push tương ứng addFirst; pop tương ứng removeFirst. Khi dùng nhất quán, chuỗi trên lấy B trước.

ArrayDeque là mảng có thể mở rộng cho Deque, không tự đồng bộ hóa và không cho phép null. Nhiều thao tác ở hai đầu có chi phí hằng số phân bổ; không cần dùng một LinkedList chỉ vì mô hình khái niệm ngăn xếp thường được vẽ bằng các nút. [Java 17: ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html)

### 6.2. Peek không có cùng hợp đồng rỗng

| Stack cũ | Với Deque, đỉnh ở đầu | Khác biệt cần giữ |
|---|---|---|
| push(x) | push(x), tương đương addFirst(x) | Stack trả x; Deque.push trả void |
| pop() | pop() hoặc removeFirst() | Rỗng: EmptyStackException đổi thành NoSuchElementException |
| peek() | peekFirst() hoặc peek() | Deque trả null khi rỗng |
| peek() muốn dạng ném lỗi khi rỗng | getFirst() | Ném NoSuchElementException, vẫn khác loại lỗi cũ |
| empty() | isEmpty() | Cùng mục đích hỏi rỗng |
| search(x) | Không có phương thức trực tiếp cùng tên và hợp đồng | Phải xác định có thật sự cần vị trí từ đỉnh không |

Cùng tên peek không đủ để kết luận hai phương thức có thể thay trực tiếp ở mọi nơi. Mã bắt EmptyStackException hoặc dùng null như dữ liệu cần được xem xét riêng. [Java 17: Deque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html)

### 6.3. Không trộn push với add nếu chưa xác định ý nghĩa

Trên Deque, push thêm ở đầu, còn add theo hợp đồng Queue thêm ở cuối. Nếu mã gọi cả hai theo thói quen “đều là thêm”, nó có thể không còn tạo chuỗi LIFO mong muốn.

Có thể chọn đỉnh ở cuối và dùng addLast/removeLast/peekLast nhất quán. Nhưng khi đã chọn quy ước đó, push/pop của Deque lại tác động ở đầu, không ở cuối.

Giữ một quy ước rõ ràng trong API của lớp sở hữu dữ liệu giúp tránh việc người gọi trộn hai kiểu thao tác.

## 7. Chuyển dữ liệu Stack sang ArrayDeque không chỉ là constructor

### 7.1. Thứ tự iterator khác chiều ngăn xếp

Sau khi push A, B, C:

~~~text
Stack theo chỉ số và iterator:  [A, B, C]
đáy                            A
đỉnh                                 C

ArrayDeque dùng push ở đầu:
iterator:                     [C, B, A]
đỉnh                           C
~~~

Cả hai có thể pop theo C, B, A, nhưng thứ tự iterator khác nhau.

Nếu tạo `new ArrayDeque<>(oldStack)`, constructor tiếp nhận thứ tự iterator của nguồn, nên deque có A ở đầu. Gọi pop ngay sẽ lấy A, đảo ngữ nghĩa lấy ra so với oldStack.

### 7.2. Cách giữ đỉnh ở đầu

Duyệt nguồn từ đáy lên đỉnh và push từng phần tử:

~~~java
Deque<String> replacement = new ArrayDeque<>();
for (String item : oldStack) {
    replacement.push(item);
}
~~~

Kết quả đầu deque là C, rồi B, A. Pop đi theo C, B, A. Vòng lặp không làm cạn nguồn.

Ví dụ xét nguồn ổn định và không chứa null. Nếu dữ liệu cũ có null hoặc đang có sửa đổi cạnh tranh, cần xử lý các điều kiện ấy trước hoặc trong chính sách chuyển đổi; không lặng lẽ bỏ phần tử.

### 7.3. Cách giữ biểu diễn đáy trước, đỉnh cuối

Có thể sao chép theo iterator:

~~~java
Deque<String> replacement = new ArrayDeque<>(oldStack);
String top = replacement.removeLast();
~~~

Cách này lấy C ở cuối. Các thao tác về sau phải dùng đầu cuối nhất quán. Nó không tương đương với việc sau constructor tiếp tục gọi Deque.pop.

Hai cách đều có thể đúng nếu ý định rõ. Khi chuyển đổi, kiểm tra chuỗi lấy ra, không chỉ kiểm tra số phần tử hoặc chuỗi toString.

### 7.4. Hợp đồng equals cũng khác

Stack thừa hưởng quan hệ bằng nhau theo nội dung và thứ tự của List. ArrayDeque không cung cấp equals dựa trên chuỗi phần tử như List; hai deque khác đối tượng có thể cùng phần tử nhưng equals vẫn false.

Không chuyển các kiểm tra nội dung sang deque.equals rồi tưởng dữ liệu đã bị mất. Nếu muốn so một chuỗi theo thứ tự duyệt, hãy tạo hoặc so chuỗi phần tử theo một hợp đồng rõ ràng; nếu muốn so thứ tự pop, hãy kiểm tra đúng thứ tự đó.

Tương tự, không đổi đối tượng dùng làm khóa của bảng băm mà bỏ qua thay đổi equals/hashCode.

## 8. Đồng bộ từng phương thức chưa đủ cho một thuật toán

### 8.1. Check rồi pop vẫn có thể thất bại

Mẫu có vấn đề:

~~~java
if (!shared.empty()) {
    shared.pop();
}
~~~

Hai lời gọi có thể được đồng bộ riêng nhưng lịch xen kẽ vẫn là:

~~~text
luồng 1: thấy không rỗng
luồng 2: thấy không rỗng
luồng 1: pop phần tử duy nhất
luồng 2: pop trên ngăn xếp đã rỗng
~~~

Không có bước nào đòi một lần pop nội bộ bị hỏng. Mỗi pop thực hiện đúng tại trạng thái nó nhận. Điều sai là kỳ vọng kiểm tra rỗng còn hiệu lực tới lần pop sau đó.

### 8.2. Bảo vệ cả thao tác ghép khi giữ Stack cũ

Một cách tổ chức trong mô hình dùng chung khóa:

~~~java
synchronized (shared) {
    if (!shared.empty()) {
        shared.pop();
    }
}
~~~

Những thao tác liên quan khác phải tuân thủ cùng chính sách bảo vệ. Không chỉ đặt synchronized ở một nơi rồi cho các đường gọi khác bỏ qua những bất biến nghiệp vụ cần giữ.

Khóa ở đây giải thích phạm vi nguyên tử mong muốn. Nó không phải lý do giữ Stack cho mọi mã mới; lựa chọn cấu trúc và thiết kế thao tác vẫn cần được tách ra.

### 8.3. Với cấu trúc đồng thời, ưu tiên thao tác đã gộp đúng mục đích

Nếu dùng một deque đồng thời không cho null, pollFirst là một thao tác lấy nếu có và trả null nếu rỗng. Nó tránh ghép isEmpty rồi pop chỉ để hỏi “có thì lấy”.

Một loạt nhiều thao tác vẫn không tự trở thành giao dịch chỉ vì từng thao tác của cấu trúc là an toàn đồng thời. Ví dụ, chuyển phần tử giữa hai cấu trúc hoặc kiểm tra một điều kiện liên quan nhiều đối tượng cần thiết kế riêng.

## 9. Chọn thay thế theo yêu cầu

| Nhu cầu | Lựa chọn để cân nhắc |
|---|---|
| List cục bộ hoặc không cần khóa nội bộ | ArrayList |
| List dùng chung với chính sách khóa tường minh | SynchronizedList hoặc cấu trúc dưới cùng khóa đã thiết kế |
| List duyệt rất nhiều, sửa ít, cần ảnh chụp iterator | CopyOnWriteArrayList |
| Ngăn xếp không chia sẻ cạnh tranh, không lưu null | Deque với ArrayDeque |
| Deque dùng chung, thao tác không cần chờ dữ liệu | ConcurrentLinkedDeque |
| Deque có phối hợp chờ phần tử hoặc chờ chỗ trống | BlockingDeque thích hợp, chẳng hạn LinkedBlockingDeque |
| API bên ngoài bắt buộc Vector/Stack cụ thể | Giữ tương thích tại ranh giới và đánh giá cách dùng nội bộ |

ConcurrentLinkedDeque cung cấp thao tác đồng thời, không cho null và có iterator nhất quán yếu. Nó không hứa các thao tác hàng loạt là nguyên tử, và size không phải phép đếm hằng số như có thể quen ở danh sách. [Java 17: ConcurrentLinkedDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentLinkedDeque.html)

LinkedBlockingDeque có thể có giới hạn dung lượng. Nếu cần chờ, dùng họ put/take hoặc thao tác có timeout phù hợp; push không tự biến thành lệnh chờ chỉ vì đối tượng triển khai BlockingDeque. [Java 17: LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html)

Không chọn một cấu trúc có cơ chế mạnh hơn chỉ theo thói quen. Cần xác định dạng dữ liệu, quy tắc rỗng/null, tải đọc ghi và cách các luồng phối hợp.

## 10. Ranh giới tương thích cần đọc trước khi thay

Trong mã cũ, có thể có API nhận hoặc trả Vector cụ thể, hợp đồng dữ liệu tuần tự hóa, lớp con dùng trường protected hoặc người gọi phụ thuộc Enumeration. Đổi biến nội bộ sang List không tự làm tất cả ranh giới đó tương thích.

Một quy trình xem xét hợp lý là:

1. Xác định mã đang dùng List hay thật sự cần các API riêng của Vector.
2. Với Stack, ghi rõ đỉnh nằm ở đâu và thứ tự lấy ra.
3. Kiểm tra dữ liệu null, lỗi rỗng, giá trị trả về và search.
4. Xác định iterator hoặc thứ tự hiển thị có phải phần của hợp đồng không.
5. Xác định các thao tác ghép và chính sách đồng thời.
6. Đổi cấu trúc tại phạm vi đã hiểu, rồi kiểm chứng hành vi cần giữ.

Đó là đánh giá hợp đồng, không phải yêu cầu sửa mọi lớp cũ ngay lập tức. Hai lớp vẫn có thể cần được duy trì ở một ranh giới tương thích cụ thể.

## 11. Chương trình Java đầy đủ

Lưu mã sau vào `LegacyCollectionsDemo.java`. Chương trình dùng dữ liệu riêng cho các tình huống để các phép lấy ra không làm nhiễu tình huống khác.

Phần hai luồng dùng CountDownLatch để cả hai cùng hoàn tất kiểm tra không rỗng trước khi pop. Không dùng sleep để đoán lịch chạy. Chỉ in tổng kết sau khi join, nên stdout không phụ thuộc luồng nào lấy được phần tử.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.EmptyStackException;
import java.util.Enumeration;
import java.util.List;
import java.util.Stack;
import java.util.Vector;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

public class LegacyCollectionsDemo {
    private static void require(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected collection result");
        }
    }

    private static String exceptionName(Supplier<?> operation) {
        try {
            operation.get();
            return "none";
        } catch (RuntimeException exception) {
            return exception.getClass().getSimpleName();
        }
    }

    private static <E> List<E> drainFirst(Deque<E> deque) {
        List<E> result = new ArrayList<>();
        while (!deque.isEmpty()) {
            result.add(deque.removeFirst());
        }
        return result;
    }

    private static <E> List<E> drainLast(Deque<E> deque) {
        List<E> result = new ArrayList<>();
        while (!deque.isEmpty()) {
            result.add(deque.removeLast());
        }
        return result;
    }

    private static void awaitBoth(CountDownLatch latch) {
        try {
            if (!latch.await(5, TimeUnit.SECONDS)) {
                throw new AssertionError("Both checks did not complete");
            }
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new AssertionError(exception);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Vector<String> vector = new Vector<>(2);
        vector.addElement("A");
        vector.add("B");
        vector.ensureCapacity(8);
        require(vector.size() == 2 && vector.capacity() >= 8);
        System.out.println("vector/size=" + vector.size()
                + ", capacityAtLeast8=" + (vector.capacity() >= 8));
        vector.setSize(4);
        require(vector.size() == 4 && vector.get(2) == null);
        System.out.println("vector/afterSetSize=" + vector);
        List<String> copiedList = new ArrayList<>(vector);
        vector.removeElement("B");
        require(copiedList.size() == 4 && copiedList.get(1).equals("B"));
        System.out.println("vector/afterRemove=" + vector
                + ", arrayListCopy=" + copiedList);
        Enumeration<String> enumeration = vector.elements();
        List<String> enumerated = new ArrayList<>();
        while (enumeration.hasMoreElements()) {
            enumerated.add(enumeration.nextElement());
        }
        System.out.println("vector/enumeration=" + enumerated);

        Stack<String> legacy = new Stack<>();
        legacy.push("A");
        legacy.push("B");
        String pushed = legacy.push("C");
        require(pushed.equals("C") && legacy.search("B") == 2);
        System.out.println("stack/pushReturn=" + pushed
                + ", top=" + legacy.peek()
                + ", searchB=" + legacy.search("B")
                + ", indexB=" + legacy.indexOf("B")
                + ", missing=" + legacy.search("missing"));
        System.out.println("stack/iteration=" + new ArrayList<>(legacy));

        Deque<String> modern = new ArrayDeque<>();
        modern.push("A");
        modern.push("B");
        modern.push("C");
        System.out.println("deque/iteration=" + new ArrayList<>(modern));

        Stack<String> emptyStack = new Stack<>();
        Deque<String> emptyDeque = new ArrayDeque<>();
        System.out.println("empty/stackPop=" + exceptionName(emptyStack::pop)
                + ", dequePop=" + exceptionName(emptyDeque::pop));
        System.out.println("empty/stackPeek=" + exceptionName(emptyStack::peek)
                + ", dequePeek=" + emptyDeque.peek());

        Stack<String> nullable = new Stack<>();
        nullable.push(null);
        String nullFromStack = nullable.pop();
        boolean dequeNullRejected = false;
        try {
            modern.push(null);
        } catch (NullPointerException exception) {
            dequeNullRejected = true;
        }
        require(dequeNullRejected && nullFromStack == null);
        System.out.println("null/stackPop=" + nullFromStack
                + ", dequeRejected=" + dequeNullRejected);

        Stack<Integer> inherited = new Stack<>();
        inherited.push(10);
        inherited.push(20);
        inherited.add(0, 99);
        List<Integer> beforePop = new ArrayList<>(inherited);
        Integer inheritedPop = inherited.pop();
        require(beforePop.equals(List.of(99, 10, 20)) && inheritedPop == 20);
        System.out.println("inheritance/afterIndexedAdd=" + beforePop
                + ", pop=" + inheritedPop);

        Deque<String> naive = new ArrayDeque<>(legacy);
        System.out.println("migration/naivePop=" + naive.pop());
        Deque<String> topFirst = new ArrayDeque<>();
        for (String item : legacy) {
            topFirst.push(item);
        }
        Deque<String> topLast = new ArrayDeque<>(legacy);
        List<String> firstSequence = drainFirst(topFirst);
        List<String> lastSequence = drainLast(topLast);
        require(firstSequence.equals(List.of("C", "B", "A"))
                && lastSequence.equals(firstSequence));
        System.out.println("migration/topFirst=" + firstSequence);
        System.out.println("migration/topLast=" + lastSequence);
        System.out.println("migration/source=" + legacy);

        Stack<String> sameStack = new Stack<>();
        sameStack.addAll(legacy);
        Deque<String> dequeA = new ArrayDeque<>(legacy);
        Deque<String> dequeB = new ArrayDeque<>(legacy);
        require(legacy.equals(sameStack) && !dequeA.equals(dequeB));
        System.out.println("equals/stack=" + legacy.equals(sameStack)
                + ", arrayDeque=" + dequeA.equals(dequeB));

        Stack<String> shared = new Stack<>();
        shared.push("only");
        CountDownLatch bothChecked = new CountDownLatch(2);
        AtomicInteger successful = new AtomicInteger();
        AtomicInteger emptyFailures = new AtomicInteger();
        Runnable separateCalls = () -> {
            if (!shared.empty()) {
                bothChecked.countDown();
                awaitBoth(bothChecked);
                try {
                    shared.pop();
                    successful.incrementAndGet();
                } catch (EmptyStackException exception) {
                    emptyFailures.incrementAndGet();
                }
            }
        };
        Thread first = new Thread(separateCalls);
        Thread second = new Thread(separateCalls);
        first.start();
        second.start();
        first.join();
        second.join();
        require(successful.get() == 1 && emptyFailures.get() == 1
                && shared.empty());
        System.out.println("compound/methodsOnlyPops=" + successful.get()
                + ", emptyFailures=" + emptyFailures.get()
                + ", remaining=" + shared.size());

        Stack<String> protectedStack = new Stack<>();
        protectedStack.push("only");
        AtomicInteger protectedPops = new AtomicInteger();
        Runnable wholeOperation = () -> {
            synchronized (protectedStack) {
                if (!protectedStack.empty()) {
                    protectedStack.pop();
                    protectedPops.incrementAndGet();
                }
            }
        };
        Thread third = new Thread(wholeOperation);
        Thread fourth = new Thread(wholeOperation);
        third.start();
        fourth.start();
        third.join();
        fourth.join();
        require(protectedPops.get() == 1 && protectedStack.empty());
        System.out.println("compound/lockedPops=" + protectedPops.get()
                + ", remaining=" + protectedStack.size());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 LegacyCollectionsDemo.java
java LegacyCollectionsDemo
~~~

Stdout của lần chạy kiểm chứng:

~~~text
vector/size=2, capacityAtLeast8=true
vector/afterSetSize=[A, B, null, null]
vector/afterRemove=[A, null, null], arrayListCopy=[A, B, null, null]
vector/enumeration=[A, null, null]
stack/pushReturn=C, top=C, searchB=2, indexB=1, missing=-1
stack/iteration=[A, B, C]
deque/iteration=[C, B, A]
empty/stackPop=EmptyStackException, dequePop=NoSuchElementException
empty/stackPeek=EmptyStackException, dequePeek=null
null/stackPop=null, dequeRejected=true
inheritance/afterIndexedAdd=[99, 10, 20], pop=20
migration/naivePop=A
migration/topFirst=[C, B, A]
migration/topLast=[C, B, A]
migration/source=[A, B, C]
equals/stack=true, arrayDeque=false
compound/methodsOnlyPops=1, emptyFailures=1, remaining=0
compound/lockedPops=1, remaining=0
~~~

Mã đã được biên dịch với `--release 17` và chạy thành công. Tùy chọn release xác định mức API và mã đích tương thích; không khẳng định JVM thực thi là đúng bản JDK 17.

## 12. Giải thích các nhóm kết quả

### 12.1. Vector và bản sao List

EnsureCapacity giữ size bằng hai; setSize tăng thành bốn và thêm hai null. ArrayListCopy được tạo trước khi nguồn bỏ B nên vẫn giữ bốn phần tử ban đầu.

Enumeration được dùng khi dữ liệu không thay đổi trong lượt duyệt. Bài không dùng kết quả ấy để hứa điều gì khi nguồn bị sửa cạnh tranh.

### 12.2. Ngăn xếp và thứ tự

Stack trả C từ push, peek C và search B bằng hai trong khi index B bằng một. Iterator của Stack đi A, B, C; iterator của deque được xây bằng push đi C, B, A.

Chèn 99 tại chỉ số 0 của Stack thể hiện các thao tác Vector kế thừa vẫn hiện diện. Pop vẫn lấy 20 ở đỉnh sau thao tác đó.

### 12.3. Rỗng, null và chuyển đổi

EmptyStackPop và emptyDequePop cho hai tên ngoại lệ khác nhau. Peek của Stack rỗng ném lỗi, còn Deque.peek cho null.

Stack có thể giữ và pop null trong ví dụ. ArrayDeque từ chối đẩy null. Đây là thay đổi hợp đồng dữ liệu cần được nhận diện khi chuyển đổi.

NaivePop lấy A vì constructor sao chép thứ tự đáy trước của Stack. Hai cách có chủ đích đều lấy C, B, A và không làm cạn nguồn. Kiểm tra không chỉ dừng ở việc cùng chứa ba phần tử.

### 12.4. Equals

Hai Stack riêng có cùng chuỗi phần tử bằng nhau theo List. Hai ArrayDeque riêng có cùng chuỗi phần tử không bằng nhau theo equals của lớp.

Chương trình kiểm tra chuỗi lấy ra bằng List kết quả khi cần bằng nhau nội dung; không dùng deque.equals cho nhiệm vụ ấy.

### 12.5. Thao tác ghép

Khi chỉ dựa vào đồng bộ hóa từng lời gọi Stack, một luồng lấy được phần tử và một luồng gặp EmptyStackException sau khi cả hai đều đã thấy không rỗng.

Khi giữ khóa suốt kiểm tra và pop, chỉ một luồng pop; luồng sau thấy rỗng rồi bỏ qua. Kết quả này chứng minh phạm vi bảo vệ của thao tác ghép, không phải phép đo hiệu năng hay mô phỏng toàn bộ một hệ thống đồng thời.

## 13. Các lỗi thường gặp

| Lỗi | Cách hiểu đúng |
|---|---|
| Vector cũ nghĩa là đã bị loại khỏi Java | Nó vẫn tồn tại; cần hiểu lý do tương thích và hướng API mới |
| Synchronized từng phương thức làm mọi thuật toán nguyên tử | Chuỗi kiểm tra–cập nhật cần phạm vi riêng |
| SetSize chỉ đặt trước dung lượng | Nó thay số phần tử và có thể thêm null |
| Enumeration không ném CME nên dùng an toàn khi sửa | Không fail-fast không có nghĩa duyệt nhất quán |
| Stack chỉ cho phép thao tác ở đỉnh | Nó còn kế thừa nhiều thao tác List từ Vector |
| Search trả chỉ số bắt đầu từ 0 | Nó trả khoảng cách từ đỉnh bắt đầu 1 |
| Push của Stack và Deque có cùng kiểu trả về | Stack trả phần tử; Deque.push trả void |
| Peek hai lớp có cùng hành vi rỗng | Stack ném lỗi; Deque.peek trả null |
| ArrayDeque giữ được mọi dữ liệu null của Stack | ArrayDeque cấm null |
| New ArrayDeque của Stack rồi pop luôn giữ LIFO cũ | Phải xem chiều iterator và đầu pop |
| Dùng add xen push không thay thứ tự | Add cuối, push đầu trên Deque |
| Deque.equals so nội dung như Stack | ArrayDeque không có equals theo List |
| Chuyển sang ArrayList vẫn tự có đồng bộ hóa của Vector | ArrayList không tự đồng bộ hóa |
| BlockingDeque.push luôn chờ khi đầy | Chờ phụ thuộc phương thức được chọn |
| Cấu trúc đồng thời làm nhiều thao tác thành giao dịch | Vẫn cần thiết kế các bất biến trải qua nhiều bước |

## 14. Thực hành và lời giải

### Bài 1. Size hay capacity?

Vector có hai phần tử. Gọi ensureCapacity(100), rồi setSize(5). Số phần tử sau từng bước là bao nhiêu và các vị trí mới chứa gì?

**Lời giải:** Sau ensureCapacity vẫn là hai. Sau setSize là năm, ba vị trí mới là null. Hai thao tác có mục đích khác nhau.

### Bài 2. Search và index

Stack được push A, B, C. Search A và indexOf A trả gì? Nếu có một A khác ở đỉnh thì search A chọn lần nào?

**Lời giải:** Ban đầu search A bằng ba, indexOf A bằng không. Nếu có A ở đỉnh, search A bằng một vì chọn lần xuất hiện gần đỉnh nhất.

### Bài 3. Đổi peek

Mã cũ bắt EmptyStackException từ peek khi không có dữ liệu. Đổi sang ArrayDeque.peek có giữ hành vi đó không? GetFirst khác gì?

**Lời giải:** Không. Peek của deque trả null. GetFirst ném NoSuchElementException khi rỗng, vẫn không cùng loại lỗi với Stack. Cần chọn và cập nhật chính sách báo vắng theo hợp đồng mong muốn.

### Bài 4. Chuyển nội dung

Stack có A, B, C theo thứ tự iterator. New ArrayDeque từ nguồn rồi pop lấy gì? Nêu hai quy ước để giữ thứ tự lấy C, B, A.

**Lời giải:** Pop lấy A. Có thể duyệt Stack rồi push từng phần tử vào deque mới để đỉnh ở đầu, hoặc sao chép theo iterator nhưng dùng removeLast/addLast/peekLast với đỉnh ở cuối. Không được trộn quy ước.

### Bài 5. Vì sao hai luồng vẫn lỗi?

Stack có một phần tử; cả hai luồng đều chạy empty rồi pop mà không có khóa bao cả chuỗi. Các phương thức đều có cơ chế đồng bộ hóa. Lỗi có thể xuất hiện ở đâu?

**Lời giải:** Cả hai kiểm tra không rỗng trước khi ai pop. Luồng thứ nhất lấy phần tử; luồng thứ hai pop trên rỗng. Từng lời gọi đúng nhưng điều kiện kiểm tra không được giữ tới cập nhật. Cần thao tác ghép được bảo vệ hoặc API gộp đúng mục đích trên cấu trúc phù hợp.

### Bài 6. Null khi thay thế

Dữ liệu Stack cũ có null như một phần tử hợp lệ. Có thể đổi ngay sang ArrayDeque rồi bỏ qua null trong lúc sao chép không?

**Lời giải:** Không thể gọi đó là chuyển đổi bảo toàn hành vi. ArrayDeque không nhận null; lặng lẽ bỏ nó thay dữ liệu và có thể thay thứ tự hoặc số tác vụ. Cần xác định biểu diễn dữ liệu phù hợp và chính sách chuyển đổi rõ ràng.

### Bài 7. Chọn danh sách dùng chung

Danh sách có rất nhiều lượt duyệt và rất ít cập nhật. Vì sao CopyOnWriteArrayList đáng xem xét nhưng không phải lựa chọn mặc định cho mọi tải ghi?

**Lời giải:** Iterator ảnh chụp cho phép duyệt không bị cập nhật cấu trúc sau đó can thiệp vào mảng đang duyệt. Đổi lại, mỗi thao tác sửa tạo mảng mới; ghi thường xuyên có thể gây chi phí sao chép và bộ nhớ lớn.

### Bài 8. So sánh sau chuyển đổi

Một bài kiểm tra trước đây dùng Stack.equals để so hai chuỗi. Sau khi thay bằng ArrayDeque, equals trả false dù phần tử in giống nhau. Có đủ kết luận chuyển dữ liệu sai không?

**Lời giải:** Không. ArrayDeque không có equals theo nội dung List. Cần so chuỗi phần tử theo thứ tự cần bảo toàn, đặc biệt là thứ tự lấy ra nếu đây là ngăn xếp.

## 15. Quyết định thay thế dựa vào hợp đồng

Hãy xác định cần List hay LIFO, có cho null không, rỗng được báo thế nào, chiều duyệt có ý nghĩa gì và có thao tác ghép giữa nhiều luồng hay không.

ArrayList và ArrayDeque giúp diễn đạt nhiều nhu cầu mới rõ ràng hơn, còn các cấu trúc đồng thời cung cấp những hợp đồng phối hợp khác nhau. Hiểu các điều đang được giữ mới cho phép thay Vector hoặc Stack mà không đổi hành vi ngoài ý định.
