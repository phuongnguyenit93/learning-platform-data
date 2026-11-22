# ORDERED, SORTED, DISTINCT, SIZED, IMMUTABLE và CONCURRENT

## 1. Đặc tính là cam kết cho người dùng bộ duyệt

Một Spliterator có thể đưa phần tử ra từng bước, duyệt phần còn lại và chia nguồn thành các phần. Để thuật toán biết có thể dựa vào điều gì, nó còn công bố những **đặc tính** qua `characteristics()`.

Sáu đặc tính trong bài trả lời những nhóm câu hỏi khác nhau:

| Đặc tính | Câu hỏi được trả lời |
| --- | --- |
| `ORDERED` | Các phần tử có một thứ tự gặp được xác định không? |
| `SORTED` | Thứ tự gặp có tuân theo một quy tắc sắp xếp không? |
| `DISTINCT` | Các phần tử gặp được có khác nhau theo quan hệ equals không? |
| `SIZED` | Có cam kết biết chính xác số phần tử trong điều kiện quy định không? |
| `IMMUTABLE` | Nguồn mà bộ duyệt bao quát có tránh được việc thêm, xóa, thay phần tử trong lúc duyệt không? |
| `CONCURRENT` | Nguồn có chính sách cho phép thay đổi đồng thời an toàn trong lúc duyệt không? |

Các bit này là thông tin về nguồn, cấu trúc và phần tử mà thuật toán có thể tận dụng. Chúng không phải lệnh yêu cầu Spliterator tự sắp xếp, tự loại trùng hoặc tự khóa dữ liệu. [Java SE 17 — Spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html).

Ví dụ một danh sách `[3, 1, 3]` có thứ tự chỉ số rõ ràng nhưng chưa tăng dần và có phần tử trùng. Một TreeSet có thể vừa có thứ tự, vừa được sắp xếp, vừa không trùng. Một khung nhìn khóa của ConcurrentHashMap có thể không có thứ tự gặp được cam kết, nhưng lại hỗ trợ nguồn thay đổi đồng thời.

Muốn dùng đúng, phải đọc từng đặc tính theo phạm vi cam kết của nó, thay vì coi mọi tính chất thuận lợi là cùng một loại “an toàn”.

## 2. Đọc bit đúng cách bằng hasCharacteristics

`characteristics()` trả về một `int` chứa nhiều bit được kết hợp bằng phép OR. Khi chỉ cần kiểm tra, dùng phương thức tiện ích:

~~~java
boolean ordered = source.hasCharacteristics(Spliterator.ORDERED);
~~~

Đây là đoạn minh họa với `source` là một `Spliterator<?>`. `ordered` bằng `true` khi bộ duyệt công bố đặc tính đó.

Để yêu cầu đồng thời nhiều đặc tính:

~~~java
boolean both = source.hasCharacteristics(
        Spliterator.ORDERED | Spliterator.SORTED);
~~~

`both` có nghĩa là **có cả ORDERED lẫn SORTED**, không phải có ít nhất một trong hai.

Nếu tự dùng phép toán bit, cách kiểm tra đầy đủ là:

~~~java
int required = Spliterator.ORDERED | Spliterator.SORTED;
boolean all = (source.characteristics() & required) == required;
~~~

So sánh `(flags & required) != 0` chỉ xác nhận có ít nhất một bit đang bật. Nhầm hai cách kiểm tra có thể khiến thuật toán đi vào nhánh cần dữ liệu đã sắp xếp dù nguồn chỉ có thứ tự chỉ số.

Không so sánh `source.characteristics() == Spliterator.ORDERED` để hỏi có ORDERED không. Một Spliterator có thể đồng thời báo `ORDERED`, `SIZED` và `SUBSIZED` nên giá trị toàn bộ mặt nạ khác riêng hằng `ORDERED`.

### Không có bit không chứng minh tính chất đối nghịch

Một ArrayList đang chứa `[1, 2, 3]` có thể không công bố `SORTED`. Dữ liệu cụ thể nhìn tăng dần không có nghĩa cách cài đặt Spliterator đã công bố quy tắc sắp xếp ấy.

Tương tự, một danh sách hiện có ba số khác nhau chưa chắc báo `DISTINCT`. Thuật toán phải phân biệt:

- Quan sát được tính chất ở một bộ dữ liệu cụ thể.
- Có đặc tính được bộ duyệt công bố để dựa vào như một hợp đồng.

Thông tin đặc tính có thể mang tính bảo thủ. Không tự suy ra bit chỉ bằng một lần nhìn kết quả in, và không tự gắn bit để mong Stream chạy nhanh hơn.

## 3. ORDERED: thứ tự gặp, không phải thứ tự tăng dần

`ORDERED` nghĩa là nguồn xác định một **thứ tự gặp** cho các phần tử. Với List, đó là thứ tự chỉ số tăng dần.

Ví dụ:

~~~text
List:       [3, 1, 3]
thứ tự gặp: 3 rồi 1 rồi 3
~~~

Thứ tự này rõ ràng nhưng không phải thứ tự số tăng dần. Đây là ví dụ điển hình của `ORDERED` mà không cần `SORTED`.

Với Spliterator có ORDERED:

- `tryAdvance` lấy phần tử kế tiếp theo thứ tự gặp.
- `forEachRemaining` gọi hành động theo thứ tự gặp của phần nguồn đang bao quát.
- `trySplit` khi chia thành công phải trả về một tiền tố của phần chưa duyệt.

Nhờ quy tắc tiền tố, thuật toán có thể xử lý phần đầu và phần sau riêng rồi ghép đúng thứ tự. Tuy nhiên, bản thân việc chia không làm thời điểm hoàn tất giữa nhiều luồng tự xếp theo thứ tự nguồn.

### Các nguồn khác nhau có các cam kết khác nhau

`LinkedHashSet` vừa giữ các phần tử không trùng vừa có thứ tự chèn. Nếu chèn `3`, `1` rồi `3` lần nữa, kết quả duyệt là `[3, 1]`: có thứ tự nhưng không tự sắp tăng dần. [Java SE 17 — LinkedHashSet.spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html#spliterator()).

`HashSet` không cam kết thứ tự duyệt. Một lần chạy có thể in ra những con số trông tăng dần, nhưng điều đó không phải hợp đồng để dựa vào khi hiển thị, kiểm thử hoặc phân trang. [Java SE 17 — HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html).

Không có ORDERED cũng không có nghĩa mỗi lần duyệt bắt buộc phải khác lần trước hoặc dữ liệu bị xáo ngẫu nhiên. Nó chỉ nghĩa là không có một thứ tự gặp được cam kết theo đặc tính này.

## 4. SORTED: thứ tự tuân theo một phép so sánh

`SORTED` mạnh hơn ORDERED: không chỉ có thứ tự gặp, mà thứ tự ấy còn tuân theo một quy tắc sắp xếp.

Quan hệ bắt buộc:

~~~text
SORTED  =>  ORDERED
~~~

Một bộ duyệt báo SORTED phải đồng thời báo ORDERED. Chiều ngược lại không đúng.

### 4.1. getComparator phân biệt thứ tự tự nhiên và comparator riêng

Nếu nguồn được sắp theo thứ tự tự nhiên của các phần tử Comparable:

~~~java
Comparator<? super Integer> cmp = source.getComparator();
~~~

`cmp` có thể là `null` để biểu thị thứ tự tự nhiên. `null` trong trường hợp này không phải lỗi thiếu quy tắc sắp xếp.

Nếu nguồn dùng comparator riêng, `getComparator` trả về comparator tương ứng. Nếu bộ duyệt không báo SORTED, gọi `getComparator` sẽ gây `IllegalStateException` theo hợp đồng.

Để sử dụng an toàn:

~~~java
if (source.hasCharacteristics(Spliterator.SORTED)) {
    Comparator<? super Integer> cmp = source.getComparator();
    // cmp == null nghĩa là thứ tự tự nhiên.
}
~~~

Đây là đoạn minh họa cần các import và kiểu nguồn phù hợp, không phải một chương trình độc lập.

### 4.2. Sắp xếp không đồng nghĩa luôn tăng dần tự nhiên

Một TreeSet tạo bằng `Comparator.reverseOrder()` có thể duyệt `[3, 1]` và vẫn báo SORTED. Nó được sắp xếp theo comparator đảo chiều.

`TreeSet` công bố thứ tự dựa trên thứ tự tự nhiên hoặc comparator tại lúc tạo. Comparator cần nhất quán với equals để tuân thủ đầy đủ hợp đồng Set. [Java SE 17 — TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html).

Nếu mục tiêu là tăng dần tự nhiên, không được thấy SORTED rồi bỏ qua yêu cầu so sánh. Trong chương trình minh chứng, Stream từ TreeSet đảo chiều vẫn được gọi `sorted()` để cho `[1, 3]` theo thứ tự tự nhiên.

### 4.3. SORTED và DISTINCT là hai cam kết riêng

Một dãy đã sắp xếp vẫn có thể chứa các giá trị bằng nhau, như `[1, 1, 3]`. SORTED không tự loại trùng.

Ngược lại, một HashSet có thể không trùng nhưng không có thứ tự sắp xếp. Do đó, không suy ra DISTINCT từ SORTED và cũng không suy ra SORTED từ DISTINCT.

## 5. DISTINCT: không trùng theo equals

`DISTINCT` công bố rằng các phần tử được gặp khác nhau theo quan hệ `equals`. Nó không chỉ nói rằng chúng là những đối tượng có địa chỉ khác nhau.

Hai đối tượng `String` được tạo riêng nhưng có cùng nội dung vẫn có thể bằng nhau theo equals. Một nguồn không trùng theo danh tính tham chiếu chưa đủ để tự công bố DISTINCT theo nghĩa chung này.

Một Set dùng đúng hợp đồng là ví dụ quen thuộc. Với dữ liệu đầu vào `[3, 1, 3]`, HashSet hoặc LinkedHashSet giữ hai giá trị `3` và `1`. Đặc tính DISTINCT cho thuật toán biết không cần xem hai lần `3` như hai phần tử nguồn riêng nữa.

### DISTINCT không có nghĩa NONNULL

Một HashSet có thể chứa một phần tử `null` mà vẫn không có phần tử trùng. Cho phép một `null` và bảo đảm không trùng là hai điều kiện không mâu thuẫn.

`NONNULL` là đặc tính riêng nói rằng những phần tử được gặp không bao giờ null. Khi một thuật toán cần bỏ kiểm tra null, nó phải có bảo đảm phù hợp; DISTINCT không cung cấp bảo đảm đó.

### Phép ánh xạ có thể phá tính không trùng

Nguồn `[1, 3]` là các giá trị khác nhau. Nhưng phép biến đổi `n -> 0` cho ra `[0, 0]`. Nếu cứ giữ DISTINCT sau một phép ánh xạ tùy ý thì thuật toán có thể bỏ một bước loại trùng dù kết quả đã có trùng.

Đây là lý do phải xét đặc tính của **nguồn hoặc pipeline đang dùng**, không chỉ nhìn lớp collection ban đầu. Một phép biến đổi có thể bảo toàn số phần tử nhưng làm mất một cam kết khác.

Với các đối tượng có equals phụ thuộc trạng thái sửa được, việc sửa đối tượng trong lúc duyệt còn có thể phá những giả định của nguồn. Đặc tính không phải giấy phép thay đổi dữ liệu theo cách làm quan hệ bằng nhau biến đổi không kiểm soát.

## 6. SIZED: biết chính xác trong điều kiện của hợp đồng

`SIZED` nói rằng trước khi duyệt hoặc chia, giá trị `estimateSize()` là số lượng hữu hạn chính xác sẽ được gặp khi duyệt thành công, nếu không có sửa đổi nguồn làm mất điều kiện đó.

Không được rút gọn thành “estimateSize lúc nào cũng là số phần tử còn lại chính xác”. Trạng thái đã duyệt một phần, đã chia và các đặc tính của phần con đều cần được xét.

Ví dụ với ArrayList ba phần tử, trước khi duyệt:

~~~java
Spliterator<Integer> source = numbers.spliterator();
long size = source.getExactSizeIfKnown();
~~~

Trong chương trình minh chứng, `size` là `3`. Nếu không có SIZED, `getExactSizeIfKnown` trả `-1` thay vì biến một ước lượng thành số đếm chắc chắn.

### 6.1. SIZED không có nghĩa nguồn không thay đổi

Một ArrayList sửa được vẫn có Spliterator báo SIZED. Điều đó không làm nó bất biến hoặc an toàn khi nhiều luồng cùng thay đổi.

Cần tách:

- Có thể biết kích thước đúng trong điều kiện ổn định.
- Có bảo đảm nguồn giữ nguyên trong toàn bộ quá trình hay không.

Hai câu hỏi thuộc hai đặc tính hoặc chính sách khác nhau.

### 6.2. SUBSIZED là bảo đảm cho các phần sau khi chia

`SUBSIZED` liên quan trực tiếp tới SIZED: những Spliterator được tạo bởi các lần chia sẽ có các bảo đảm kích thước cần thiết, bao gồm tiếp tục báo SIZED và SUBSIZED theo hợp đồng.

Một nguồn biết tổng số phần tử chưa chắc biết chính xác kích thước từng nhánh được chia. Vì vậy:

~~~text
SUBSIZED => SIZED
SIZED không tự suy ra SUBSIZED
~~~

Spliterator của ArrayList báo cả ORDERED, SIZED và SUBSIZED. [Java SE 17 — ArrayList.spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#spliterator()).

Trong ví dụ chưa duyệt phần tử nào, tách một phần rồi cộng hai `estimateSize` vẫn được tổng `3`. Đây là ca phù hợp để minh họa việc phân chia kích thước đã biết. Không dùng phép thử trên một loại nguồn để mặc định mọi cây, bảng băm hoặc nguồn I/O đều có cùng bảo đảm.

### 6.3. Không có SIZED không đồng nghĩa vô hạn

Nguồn có thể hữu hạn nhưng khó biết trước kích thước, hoặc có thay đổi đồng thời làm số đếm cố định không phù hợp. `estimateSize` vẫn có thể cho một ước lượng hữu ích.

`Long.MAX_VALUE` có thể biểu thị không biết, quá đắt để tính hoặc nguồn không hữu hạn. Chỉ nhìn con số đó không đủ để kết luận nguồn chắc chắn vô hạn.

Đặc tính giúp người dùng biết có được coi một con số là cam kết hay chỉ là thông tin ước lượng.

## 7. IMMUTABLE: nguồn ổn định đối với bộ duyệt, không phải sao chép sâu

Trong nghĩa của đặc tính này, nguồn mà Spliterator bao quát không thể bị thêm, xóa hoặc thay thế phần tử theo cách gây thay đổi trong lúc duyệt. Đó là cam kết về **nguồn phần tử**, không phải khẳng định mọi đối tượng phần tử đều có trạng thái bất biến.

### 7.1. CopyOnWriteArrayList cho thấy vì sao phải nói rõ phạm vi nguồn

`CopyOnWriteArrayList` là collection có thể được sửa. Tuy nhiên, Spliterator của nó giữ một ảnh chụp của trạng thái danh sách tại lúc tạo và báo IMMUTABLE, ORDERED, SIZED, SUBSIZED. [Java SE 17 — CopyOnWriteArrayList.spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html#spliterator()).

Ví dụ:

~~~java
CopyOnWriteArrayList<String> values =
        new CopyOnWriteArrayList<>(List.of("A", "B"));

Spliterator<String> snapshot = values.spliterator();
values.set(0, "X");
values.add("C");
~~~

Khi duyệt `snapshot`, ta vẫn nhận `[A, B]`. Danh sách hiện tại là `[X, B, C]`. Collection không bị khóa vĩnh viễn hoặc biến thành đối tượng cấm sửa; bộ duyệt giữ một nguồn ảnh chụp không bị các lần cập nhật ấy thay thế.

Đây là điểm dễ nhầm nếu chỉ đọc tên lớp hoặc chỉ nhìn chữ IMMUTABLE rồi nói “collection này không thể gọi add”.

### 7.2. Đối tượng phần tử vẫn có thể sửa được

Nếu ảnh chụp chứa một `StringBuilder`, tham chiếu trong ảnh chụp không tự được nhân bản:

~~~java
StringBuilder item = new StringBuilder("seed");
CopyOnWriteArrayList<StringBuilder> values = new CopyOnWriteArrayList<>();
values.add(item);

Spliterator<StringBuilder> snapshot = values.spliterator();
item.append("!");
~~~

Nguồn ảnh chụp vẫn giữ cùng tham chiếu, nên duyệt sẽ thấy đối tượng biểu diễn `seed!`. Không có phần tử mới được thêm hoặc tham chiếu phần tử bị thay trong ảnh chụp; chính trạng thái bên trong đối tượng đã đổi.

Muốn dữ liệu bất biến ở cấp nội dung nghiệp vụ, cần kiểu phần tử bất biến hoặc quy tắc sao chép đối tượng riêng. IMMUTABLE không tự cung cấp bản sao sâu.

### 7.3. Khung nhìn chỉ đọc không tự thành nguồn IMMUTABLE

`Collections.unmodifiableList(backing)` cấm sửa qua khung nhìn ấy, nhưng bên giữ `backing` vẫn có thể sửa nguồn. Với khung nhìn trên ArrayList trong chương trình, Spliterator không báo IMMUTABLE, và thêm `B` qua backing được nhìn thấy khi đọc khung nhìn.

Không được gộp ba khái niệm:

| Khái niệm | Điều đang nói tới |
| --- | --- |
| Không cho sửa qua một tham chiếu khung nhìn | Quyền thao tác qua đường truy cập đó |
| IMMUTABLE của Spliterator | Nguồn mà bộ duyệt bao quát không bị thay phần tử trong quá trình liên quan |
| Đối tượng phần tử bất biến | Trạng thái bên trong đối tượng không thay đổi |

Một danh sách kích thước cố định nhưng cho phép `set` cũng không đủ để tự suy ra IMMUTABLE. Chỉ không tăng/giảm số vị trí chưa giải quyết việc thay tham chiếu tại những vị trí ấy.

## 8. CONCURRENT: nguồn chấp nhận cập nhật đồng thời theo chính sách của nó

`CONCURRENT` nói rằng nguồn cho phép những thay đổi đồng thời được hỗ trợ diễn ra an toàn mà không cần bên ngoài tự khóa toàn bộ nguồn cho lượt duyệt. Spliterator phải đi cùng một chính sách mô tả ảnh hưởng của các thay đổi ấy.

Ví dụ quan trọng là các khung nhìn của ConcurrentHashMap:

| Khung nhìn | Những đặc tính được tài liệu nêu |
| --- | --- |
| Khóa | CONCURRENT, DISTINCT, NONNULL |
| Giá trị | CONCURRENT, NONNULL |
| Entry | CONCURRENT, DISTINCT, NONNULL |

Khóa không trùng, nhưng nhiều khóa có thể cùng giá trị nên khung nhìn giá trị không tự có DISTINCT. Các bộ duyệt của những khung nhìn này có tính nhất quán yếu. [Java SE 17 — ConcurrentHashMap views](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#keySet()).

### 8.1. Không phải ảnh chụp tại một thời điểm duy nhất

Một lượt duyệt trên nguồn đồng thời có thể nhìn thấy trạng thái qua thời gian duyệt theo chính sách của cấu trúc. Nó không nhất thiết đóng băng mọi khóa và giá trị tại cùng một thời điểm.

Do đó, không dùng CONCURRENT để cam kết một báo cáo tổng hợp giữa nhiều khóa là ảnh chụp nguyên tử. Nếu nghiệp vụ đòi hỏi tính nhất quán toàn cục, cần thiết kế cơ chế riêng.

### 8.2. Không có nghĩa nhiều luồng cùng dùng một đối tượng Spliterator

Đặc tính này thuộc **nguồn dữ liệu**, không làm đối tượng bộ duyệt tự trở thành an toàn cho nhiều luồng cùng gọi `tryAdvance` hoặc `trySplit`.

Mô hình xử lý song song thường giao mỗi phần chia cho một bên xử lý tại một thời điểm. Nơi nhận kết quả và các hành động cũng phải có thiết kế phù hợp; dùng một ArrayList đầu ra chung từ nhiều luồng vẫn không được làm an toàn chỉ nhờ nguồn báo CONCURRENT.

### 8.3. Không bổ sung các quyền sửa mà API khác không hỗ trợ

Một khung nhìn khóa có nguồn đồng thời không vì vậy mà hỗ trợ mọi phép `add`. Quyền thêm/xóa qua một API cụ thể và khả năng nguồn chịu thay đổi đồng thời là hai hợp đồng khác nhau.

Đặc tính giúp quản lý sự can thiệp lên nguồn trong lúc duyệt, không thay thế toàn bộ tài liệu của Collection hoặc Map đang cung cấp khung nhìn.

## 9. Các quan hệ và tổ hợp cần đọc đúng

Các quan hệ quan trọng:

~~~text
SORTED  => ORDERED
SUBSIZED => SIZED

ORDERED không suy ra SORTED
SORTED không suy ra DISTINCT
DISTINCT không suy ra NONNULL
SIZED không suy ra IMMUTABLE
CONCURRENT không suy ra đối tượng Spliterator an toàn đa luồng
IMMUTABLE không suy ra phần tử bất biến sâu
~~~

Ở Spliterator cấp gốc, CONCURRENT không nên được ghép đồng thời với SIZED vì kích thước có thể đổi khi nguồn được cập nhật. Nó cũng không nên được ghép với IMMUTABLE như hai lời hứa trái ngược về cùng nguồn. Những phần con có thể có bảo đảm riêng nếu phạm vi đã được cố định; không suy rộng tổ hợp của cấp gốc thành một quy tắc đơn giản cho mọi phần con.

Nếu bộ duyệt không báo IMMUTABLE hoặc CONCURRENT, cần đọc chính sách nguồn về thời điểm liên kết dữ liệu và phát hiện sửa đổi. “Fail-fast” thường chỉ là phát hiện theo khả năng tốt nhất, không phải cơ chế đồng bộ và không phải bằng chứng rằng chưa ném ngoại lệ thì không có lỗi truy cập.

### Không có một “bit tốt nhất” cho mọi việc

Một nguồn IMMUTABLE giữ ổn định tập phần tử của lượt duyệt nhưng có thể phải trả chi phí tạo ảnh chụp. Một nguồn CONCURRENT cho phép tiếp tục cập nhật nhưng không tự cung cấp ảnh chụp toàn cục. Nguồn ORDERED hữu ích khi kết quả cần đúng thứ tự nhưng có thể làm một số xử lý song song phải giữ thêm ràng buộc.

Chọn đặc tính để hiểu đúng hợp đồng nguồn, không dùng chúng như một thang điểm chất lượng chung của collection.

## 10. Đặc tính của pipeline có thể khác đặc tính của nguồn ban đầu

Khi Stream tiếp nhận Spliterator, các phép xử lý trung gian có thể giữ hoặc làm mất những cam kết.

### filter có thể làm mất việc biết trước kích thước

Một ArrayList ba phần tử biết kích thước đầu vào. Sau `filter(n -> n > 0)`, với dữ liệu cụ thể `[3, 1, 3]` thì cả ba đều đạt. Tuy nhiên, một phép lọc tổng quát cần kiểm tra phần tử mới biết bao nhiêu phần tử đi tiếp.

Trong chương trình, Spliterator của pipeline lọc chỉ báo ORDERED, không tiếp tục báo SIZED và SUBSIZED của ArrayList nguồn. Đó không phải lỗi đếm thiếu; pipeline không hứa biết số đầu ra trước khi thực hiện điều kiện.

### map có thể làm mất SORTED và DISTINCT

TreeSet nguồn giữ các số khác nhau và có thứ tự sắp xếp. Sau `map(n -> 0)`, nhiều phần tử trở thành cùng giá trị. Một phép ánh xạ tùy ý cũng có thể đảo lộn quan hệ so sánh.

Trong ca thử, Spliterator của pipeline ánh xạ vẫn báo ORDERED và SIZED nhưng không báo SORTED hoặc DISTINCT. Thứ tự gặp được giữ và mỗi đầu vào sinh một đầu ra, còn những bảo đảm về giá trị đã mất.

Những quan sát này giúp phân biệt hợp đồng đầu vào và hợp đồng đầu ra. Khi viết thuật toán tiếp theo, xem phần dữ liệu hoặc bộ duyệt đang thật sự được chuyển tới nó, không chỉ tra đặc tính của collection ở đầu chương trình.

## 11. Vì sao khai báo sai có thể gây kết quả sai?

Các thuật toán thư viện có thể tin vào đặc tính đã công bố. Nếu một nguồn nói sai rằng không có phần tử trùng, bước loại trùng có thể được xem là không cần thiết. Nếu nguồn nói sai kích thước, thuật toán cấp phát hoặc ghép kết quả có thể dựa trên một giả định không đúng.

Các bit vì thế là **nghĩa vụ của người cài đặt Spliterator**, không phải gợi ý mà thư viện buộc phải tự duyệt kiểm tra lại từ đầu.

Nếu tạo nguồn tùy biến:

- Chỉ báo ORDERED khi có thứ tự gặp thực sự và cách chia giữ đúng ràng buộc tiền tố.
- Chỉ báo SORTED khi thứ tự và `getComparator` cùng tuân thủ hợp đồng.
- Chỉ báo DISTINCT khi bảo đảm theo equals cho phần tử được gặp.
- Chỉ báo SIZED, SUBSIZED khi phép ước lượng và mọi phần chia liên quan đáp ứng điều kiện.
- Chỉ báo IMMUTABLE hoặc CONCURRENT theo đúng mô hình nguồn, không dựa vào việc “chưa thấy lỗi”.

`StreamSupport` là cầu nối cho nguồn cấp thấp; dạng nhận supplier yêu cầu tập đặc tính khai báo khớp với bộ duyệt do supplier tạo. Thư viện không thể tự sửa mọi cam kết sai của nguồn. [Java SE 17 — StreamSupport](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/StreamSupport.html).

Khi chỉ dùng collection chuẩn, thường không cần tự xây dựng Spliterator. Nhưng hiểu nghĩa của các bit vẫn cần thiết để giải thích vì sao một pipeline giữ thứ tự, mất số lượng biết trước hoặc có chính sách duyệt khác khi nguồn thay đổi.

## 12. Chương trình minh chứng đầy đủ

Lưu mã sau thành **SpliteratorCharacteristicsDemo.java**. Chương trình tương thích Java 17 và dùng thư viện chuẩn.

Hàm `flags` chỉ in tên những bit được báo theo một thứ tự cố định để dễ đọc; thứ tự tên trong chuỗi không phải thứ tự phần tử nguồn. Hàm `drain` tiêu thụ bộ duyệt, nên mỗi ví dụ cần một Spliterator phù hợp cho lượt duyệt của nó.

Chương trình không in thứ tự phần tử của HashSet hoặc ConcurrentHashMap để tránh biến một thứ tự không được cam kết thành stdout giả định. Những ví dụ về đa luồng chỉ kiểm tra đặc tính đã được tài liệu công bố, không dùng một lần chạy tuần tự để chứng minh an toàn đồng thời.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Spliterator;
import java.util.TreeSet;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;

public class SpliteratorCharacteristicsDemo {
    private static String flags(Spliterator<?> source) {
        int[] bits = {
            Spliterator.ORDERED, Spliterator.SORTED, Spliterator.DISTINCT,
            Spliterator.SIZED, Spliterator.IMMUTABLE, Spliterator.CONCURRENT,
            Spliterator.SUBSIZED, Spliterator.NONNULL
        };
        String[] names = {
            "ORDERED", "SORTED", "DISTINCT", "SIZED",
            "IMMUTABLE", "CONCURRENT", "SUBSIZED", "NONNULL"
        };
        List<String> result = new ArrayList<>();
        for (int i = 0; i < bits.length; i++) {
            if (source.hasCharacteristics(bits[i])) {
                result.add(names[i]);
            }
        }
        return result.toString();
    }

    private static <T> List<T> drain(Spliterator<T> source) {
        List<T> result = new ArrayList<>();
        source.forEachRemaining(result::add);
        return result;
    }

    public static void main(String[] args) {
        List<Integer> numbers = new ArrayList<>(List.of(3, 1, 3));
        Spliterator<Integer> listSource = numbers.spliterator();
        System.out.println("array-list=" + flags(listSource));
        System.out.println("array-values=" + drain(listSource));

        System.out.println("hash-set="
                + flags(new HashSet<>(numbers).spliterator()));
        LinkedHashSet<Integer> linked = new LinkedHashSet<>(numbers);
        System.out.println("linked-set=" + flags(linked.spliterator()));
        System.out.println("linked-values=" + drain(linked.spliterator()));

        TreeSet<Integer> natural = new TreeSet<>(numbers);
        Spliterator<Integer> naturalSource = natural.spliterator();
        System.out.println("tree-set=" + flags(naturalSource));
        System.out.println("natural-comparator-null=" + (naturalSource.getComparator() == null));
        System.out.println("tree-values=" + drain(naturalSource));

        TreeSet<Integer> reverse = new TreeSet<>(Comparator.reverseOrder());
        reverse.addAll(numbers);
        Spliterator<Integer> reverseSource = reverse.spliterator();
        System.out.println("reverse-comparator-1-3=" + reverseSource.getComparator().compare(1, 3));
        System.out.println("reverse-values=" + drain(reverseSource));
        System.out.println("natural-sort-from-reverse=" + reverse.stream().sorted().toList());

        Spliterator<Integer> sortedLooking =
                new ArrayList<>(List.of(1, 2, 3)).spliterator();
        System.out.println("sorted-looking-sorted="
                + sortedLooking.hasCharacteristics(Spliterator.SORTED));
        System.out.println("sorted-looking-distinct="
                + sortedLooking.hasCharacteristics(Spliterator.DISTINCT));
        System.out.println("ordered-and-sorted="
                + sortedLooking.hasCharacteristics(Spliterator.ORDERED | Spliterator.SORTED));
        try {
            sortedLooking.getComparator();
            throw new AssertionError("Expected missing SORTED");
        } catch (IllegalStateException expected) {
            System.out.println("unsorted-getComparator -> IllegalStateException");
        }

        Spliterator<Integer> sized = numbers.spliterator();
        System.out.println("list-exact-before=" + sized.getExactSizeIfKnown());
        Spliterator<Integer> split = sized.trySplit();
        if (split == null) {
            throw new AssertionError("Expected ArrayList split");
        }
        System.out.println("split-sized="
                + split.hasCharacteristics(Spliterator.SIZED | Spliterator.SUBSIZED));
        System.out.println("split-total=" + (split.estimateSize() + sized.estimateSize()));

        CopyOnWriteArrayList<String> copyOnWrite =
                new CopyOnWriteArrayList<>(List.of("A", "B"));
        Spliterator<String> snapshot = copyOnWrite.spliterator();
        System.out.println("copy-on-write=" + flags(snapshot));
        copyOnWrite.set(0, "X");
        copyOnWrite.add("C");
        System.out.println("snapshot-values=" + drain(snapshot));
        System.out.println("current-list=" + copyOnWrite);

        StringBuilder item = new StringBuilder("seed");
        CopyOnWriteArrayList<StringBuilder> objects = new CopyOnWriteArrayList<>();
        objects.add(item);
        Spliterator<StringBuilder> objectSnapshot = objects.spliterator();
        item.append("!");
        System.out.println("immutable-flag="
                + objectSnapshot.hasCharacteristics(Spliterator.IMMUTABLE));
        System.out.println("mutable-element=" + drain(objectSnapshot));

        List<String> backing = new ArrayList<>(List.of("A"));
        List<String> readOnly = Collections.unmodifiableList(backing);
        System.out.println("read-only-immutable="
                + readOnly.spliterator().hasCharacteristics(Spliterator.IMMUTABLE));
        backing.add("B");
        System.out.println("read-only-values=" + readOnly);

        ConcurrentHashMap<String, Integer> concurrent = new ConcurrentHashMap<>();
        concurrent.put("A", 1);
        concurrent.put("B", 1);
        Spliterator<String> concurrentKeys = concurrent.keySet().spliterator();
        System.out.println("concurrent-keys=" + flags(concurrentKeys));
        System.out.println("concurrent-values=" + flags(concurrent.values().spliterator()));
        System.out.println("concurrent-exact=" + concurrentKeys.getExactSizeIfKnown());

        System.out.println("filtered-list="
                + flags(numbers.stream().filter(n -> n > 0).spliterator()));
        System.out.println("mapped-tree="
                + flags(natural.stream().map(n -> 0).spliterator()));
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 -encoding UTF-8 SpliteratorCharacteristicsDemo.java
java SpliteratorCharacteristicsDemo
~~~

Stdout chính xác:

~~~text
array-list=[ORDERED, SIZED, SUBSIZED]
array-values=[3, 1, 3]
hash-set=[DISTINCT, SIZED]
linked-set=[ORDERED, DISTINCT, SIZED, SUBSIZED]
linked-values=[3, 1]
tree-set=[ORDERED, SORTED, DISTINCT, SIZED]
natural-comparator-null=true
tree-values=[1, 3]
reverse-comparator-1-3=1
reverse-values=[3, 1]
natural-sort-from-reverse=[1, 3]
sorted-looking-sorted=false
sorted-looking-distinct=false
ordered-and-sorted=false
unsorted-getComparator -> IllegalStateException
list-exact-before=3
split-sized=true
split-total=3
copy-on-write=[ORDERED, SIZED, IMMUTABLE, SUBSIZED]
snapshot-values=[A, B]
current-list=[X, B, C]
immutable-flag=true
mutable-element=[seed!]
read-only-immutable=false
read-only-values=[A, B]
concurrent-keys=[DISTINCT, CONCURRENT, NONNULL]
concurrent-values=[CONCURRENT, NONNULL]
concurrent-exact=-1
filtered-list=[ORDERED]
mapped-tree=[ORDERED, SIZED]
~~~

Mã đã biên dịch bằng `--release 17` và chạy trên JDK 24.0.2. Đây là mức API/ngôn ngữ khi biên dịch và phiên bản JVM đã chạy; không phải tuyên bố đã chạy bằng JVM 17.

Đối chiếu các nhóm:

- `array-list` và `array-values` cho thấy ORDERED đi cùng dữ liệu chưa tăng dần và còn trùng.
- `hash-set` và `linked-set` tách tính không trùng khỏi thứ tự gặp.
- `tree-set`, `natural-comparator-null` và `reverse-values` phân biệt hai quy tắc sắp xếp.
- `sorted-looking` cho thấy dữ liệu đang có tính chất chưa đủ để khẳng định bit được báo.
- `ordered-and-sorted` kiểm tra đồng thời hai đặc tính.
- Nhóm `list-exact`, `split-sized` và `split-total` minh họa kích thước với nguồn ArrayList chưa duyệt.
- Nhóm `copy-on-write` giữ ảnh chụp cũ dù collection hiện tại thay đổi.
- `mutable-element` cho thấy ảnh chụp cấu trúc không làm đối tượng phần tử bất biến sâu.
- `read-only` phân biệt khung nhìn không cho sửa với nguồn ổn định.
- Hai dòng `concurrent` về khung nhìn phân biệt khóa không trùng với các giá trị có thể trùng.
- Hai dòng cuối minh họa sự thay đổi cam kết sau filter và map.

## 13. Thực hành có đáp án

### Bài 1 — ORDERED có bắt buộc tăng dần không?

ArrayList chứa `[9, 2, 9]` có Spliterator báo ORDERED. Điều đó có sai vì dãy không tăng dần không?

**Đáp án:** Không. ORDERED nói về thứ tự gặp theo chỉ số của List. Nó không hứa tăng dần hoặc không trùng. Muốn biết có thứ tự so sánh được công bố hay không phải kiểm tra SORTED và quy tắc tương ứng.

### Bài 2 — getComparator trả null

Một TreeSet số nguyên dùng thứ tự tự nhiên. Spliterator của nó báo SORTED nhưng `getComparator()` trả null. Có phải thiếu comparator gây lỗi không?

**Đáp án:** Không. Với nguồn SORTED, null biểu thị thứ tự tự nhiên. Nếu không báo SORTED thì gọi getComparator gây IllegalStateException; cần phân biệt hai trường hợp thay vì coi mọi null đều là lỗi.

### Bài 3 — Một bit hay cả hai bit?

`s.hasCharacteristics(ORDERED | SORTED)` có trả true khi `s` chỉ báo ORDERED không? Nếu viết `(flags & mask) != 0` thì đang kiểm tra điều gì?

**Đáp án:** hasCharacteristics yêu cầu mọi bit trong mask nên trả false. Biểu thức khác chỉ hỏi có ít nhất một bit giao nhau, không đủ để khẳng định nguồn đã được sắp xếp.

### Bài 4 — DISTINCT và null

Một HashSet chứa `null` và `"A"` có thể báo DISTINCT không? Có thể dựa vào đó để bỏ kiểm tra null ở hành động xử lý không?

**Đáp án:** Có thể báo DISTINCT vì không có hai phần tử bằng nhau. Nhưng DISTINCT không bảo đảm NONNULL; hành động vẫn phải xử lý null nếu không có hợp đồng khác loại trừ nó.

### Bài 5 — Có SIZED thì mọi phần chia đều chính xác?

Một Spliterator báo SIZED. Có được tự suy ra nó báo SUBSIZED và mọi phần con sau trySplit giữ kích thước chính xác như ArrayList không?

**Đáp án:** Không. SIZED có điều kiện về thời điểm và nguồn ổn định; biết kích thước toàn bộ không tự biết chính xác mọi phần chia. SUBSIZED mới bổ sung các cam kết liên quan tới các phần con theo hợp đồng.

### Bài 6 — Collection sửa được nhưng Spliterator IMMUTABLE

Vì sao CopyOnWriteArrayList vẫn gọi add được, trong khi Spliterator đã tạo từ nó báo IMMUTABLE?

**Đáp án:** Bộ duyệt giữ một ảnh chụp nguồn ổn định tại lúc tạo. Các cập nhật tạo trạng thái mới của collection, không thay các vị trí trong ảnh chụp mà bộ duyệt đang giữ. Điều này không biến mọi đối tượng phần tử thành bất biến sâu.

### Bài 7 — CONCURRENT có cho dùng chung một bộ duyệt không?

Nguồn báo CONCURRENT. Hai luồng có thể cùng gọi tryAdvance trên cùng một đối tượng Spliterator và cùng thêm vào một ArrayList đầu ra mà không cần thiết kế gì thêm không?

**Đáp án:** Không. CONCURRENT là cam kết về khả năng nguồn chịu cập nhật đồng thời, không phải bảo đảm an toàn cho đối tượng bộ duyệt hoặc nơi thu kết quả. Cần phân chia quyền xử lý và phối hợp kết quả phù hợp.

### Bài 8 — Giữ nguyên bit sau map

TreeSet nguồn báo SORTED và DISTINCT. Sau `map(n -> 0)`, nếu một bộ duyệt tùy biến cứ giữ nguyên hai bit đó thì có vấn đề gì?

**Đáp án:** Kết quả có thể chứa nhiều số 0 nên DISTINCT không còn đúng; một phép map tùy ý cũng không bảo toàn quy tắc sắp xếp. Khai báo sai có thể khiến thuật toán thư viện áp dụng tối ưu không hợp lệ. Phải công bố đặc tính của đầu ra thực sự.

## 14. Cách sử dụng các đặc tính khi đọc và viết mã

Trước tiên xác định bộ duyệt đang bao quát nguồn nào, ở thời điểm nào. Sau đó dùng hasCharacteristics để hỏi đúng cam kết mà thuật toán cần: thứ tự, quy tắc sắp xếp, tính không trùng, số lượng hay chính sách thay đổi nguồn.

Không suy ra một bit từ tên collection hoặc từ dữ liệu tình cờ đang có. Khi đi qua phép lọc, ánh xạ hoặc chia nguồn, đánh giá lại phạm vi cam kết. Khi có nhiều luồng, tách tính an toàn của nguồn khỏi quyền sở hữu bộ duyệt và trạng thái dùng chung trong hành động.

Hiểu sáu đặc tính theo những trục riêng giúp giải thích đúng hành vi của Stream và Spliterator: có thứ tự chưa chắc đã sắp xếp; biết kích thước chưa chắc bất biến; ảnh chụp cấu trúc chưa chắc sao chép sâu; nguồn đồng thời chưa chắc là ảnh chụp nguyên tử.
