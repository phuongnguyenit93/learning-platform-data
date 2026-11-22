# Tranh chấp khi nhiều luồng đọc và ghi collection

## 1. Vấn đề bắt đầu từ trạng thái được dùng chung

Một collection giữ nhiều thông tin liên quan: các phần tử, số lượng, vị trí hoặc liên kết giữa phần tử, và những trạng thái nội bộ phục vụ tìm kiếm hoặc duyệt. Khi nhiều luồng cùng truy cập, một thao tác ở mức mã nguồn có thể cần nhiều lần đọc–ghi bên trong.

Ví dụ, ý định “tăng bộ đếm của mã A thêm một” thường bị viết thành:

~~~java
int oldValue = counts.get("A");
counts.put("A", oldValue + 1);
~~~

Hai dòng này không tự trở thành một hành động không thể chen ngang. Một luồng khác có thể đọc cùng giá trị cũ rồi cũng ghi kết quả tăng một, khiến một lần cập nhật bị mất.

Với collection không được thiết kế cho truy cập đồng thời, còn có vấn đề ở cấp cấu trúc và khả năng nhìn thấy dữ liệu. Với collection an toàn đa luồng, vẫn có thể sai ở **chuỗi thao tác nghiệp vụ** nếu từng bước riêng được bảo vệ nhưng cả chuỗi không được bảo vệ.

Bài học cần phân biệt bốn câu hỏi:

1. Các phương thức riêng có được gọi đồng thời an toàn không?
2. Nhiều bước có cần được xem như một thao tác nguyên tử không?
3. Luồng đọc có được nhìn thấy các cập nhật theo một quan hệ đồng bộ hợp lệ không?
4. Lượt duyệt cần thấy dữ liệu sống, ảnh chụp hay một trạng thái nhất quán toàn bộ?

Không có một câu trả lời “dùng List” hoặc “đổi thành Map concurrent” giải quyết đồng thời tất cả các câu hỏi ấy.

## 2. Hai tầng tranh chấp: dữ liệu bên trong và logic bên ngoài

### 2.1. Tranh chấp trên dữ liệu chia sẻ không được đồng bộ đúng

Theo mô hình bộ nhớ Java, các truy cập xung đột lên biến chia sẻ, có ít nhất một lần ghi và không được sắp thứ tự phù hợp bởi happens-before, tạo thành data race. Quan hệ happens-before mô tả những bảo đảm về thứ tự và khả năng nhìn thấy giữa các hành động. [Java Language Specification 17 — Happens-before Order](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5).

Trong một collection thông thường, việc đọc các trường nội bộ trong khi luồng khác sửa chúng mà không có giao thức phù hợp không phải một cách sử dụng hợp lệ chỉ vì mỗi phần tử là một tham chiếu Java.

Kết quả không nên được dự đoán bằng cách tưởng tượng rằng mọi câu lệnh của mọi luồng chỉ xen kẽ như những khối hoàn chỉnh. Mã tối ưu và mô hình bộ nhớ còn ảnh hưởng tới điều một luồng được phép nhìn thấy.

### 2.2. Các phương thức an toàn vẫn có thể kết hợp thành một thuật toán sai

Một ConcurrentHashMap bảo vệ các thao tác của nó. Tuy nhiên:

~~~java
int oldValue = map.get("item");
map.put("item", oldValue + 1);
~~~

vẫn có khe thời gian giữa đọc và ghi. Mỗi phương thức có thể đúng theo hợp đồng riêng, nhưng cả yêu cầu “tăng một” không được biểu diễn bằng một phép cập nhật nguyên tử.

Đó là lý do cần phân biệt **an toàn của cấu trúc dữ liệu** và **đúng đắn của bất biến nghiệp vụ**. Một thuật toán có thể không làm hỏng nội bộ collection mà vẫn tạo kết quả sai.

Chương trình ở phần minh chứng chủ động dùng những collection có phương thức an toàn để tái lập các tranh chấp ở tầng chuỗi thao tác. Nó không cần gây hỏng một ArrayList không được bảo vệ rồi trông chờ một kết quả ngẫu nhiên.

## 3. ArrayList và HashMap không tự bảo vệ các lần đọc–ghi đồng thời

`ArrayList` và `HashMap` thông thường không có cơ chế đồng bộ nội bộ cho việc dùng tùy ý từ nhiều luồng. Tài liệu yêu cầu đồng bộ bên ngoài trong trường hợp nhiều luồng truy cập và có sửa đổi cấu trúc. [Java SE 17 — ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), [Java SE 17 — HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html).

Ví dụ sau chỉ minh họa một cách sử dụng sai, không phải chương trình để dựa vào stdout cố định:

~~~java
// shared là cùng một ArrayList được nhiều luồng truy cập không có bảo vệ.
// Luồng ghi:
shared.add("new");

// Luồng đọc:
for (String value : shared) {
    consume(value);
}
~~~

Có thể gặp lỗi khi duyệt hoặc dữ liệu quan sát không đáp ứng yêu cầu. Không được biến một biểu hiện cụ thể thành kết luận rằng mọi lần chạy sai đều phải ném cùng ngoại lệ.

### Đọc một vị trí cũng không tự an toàn chỉ vì không duyệt Iterator

`get`, `size` hoặc `contains` đều đọc trạng thái. Trong lúc nguồn thay đổi mà không có hợp đồng phù hợp, chuyển từ vòng lặp foreach sang vòng lặp chỉ số không tự chữa tranh chấp.

Ngay cả việc không tăng/giảm kích thước chưa đủ để khẳng định mọi cập nhật đều an toàn. Một `set` thay tham chiếu phần tử hoặc một `put` thay giá trị vẫn là việc ghi dữ liệu chia sẻ; cần bảo đảm nhìn thấy và phối hợp phù hợp với ứng dụng.

### Chỉ đọc có thể đơn giản hơn nếu không còn ghi

Nhiều luồng có thể cùng đọc một cấu trúc đã được xây dựng xong, được công bố an toàn và không còn bị sửa. Điều kiện “không còn sửa” phải bao gồm mọi đường tham chiếu có khả năng thay đổi phần liên quan.

Nếu phần tử bên trong là đối tượng sửa được, collection không đổi cấu trúc vẫn chưa giải quyết việc nhiều luồng đọc–ghi trạng thái của phần tử. Collection và đối tượng phần tử là hai tầng cần xem riêng.

## 4. Mất cập nhật: hai lần tăng nhưng chỉ còn một

Giả sử bộ đếm đang là `0`. Hai luồng thực hiện chuỗi get–put:

| Thời điểm | Luồng thứ nhất | Luồng thứ hai | Giá trị trong Map |
| --- | --- | --- | --- |
| 1 | Đọc `0` | | `0` |
| 2 | | Đọc `0` | `0` |
| 3 | Ghi `1` | | `1` |
| 4 | | Ghi `1` | `1` |

Không lần ghi nào tăng từ `1` lên `2` vì cả hai luồng đã tính từ cùng giá trị cũ. Đây là mất cập nhật.

Đổi Map thành ConcurrentHashMap làm get và put có hợp đồng truy cập đồng thời, nhưng không gộp chúng thành một phép đọc–sửa–ghi duy nhất.

Với bộ đếm theo khóa, có thể dùng:

~~~java
counts.merge("item", 1, Integer::sum);
~~~

`ConcurrentHashMap.merge` thực hiện lần cập nhật theo khóa một cách nguyên tử theo hợp đồng của lớp. Nếu chưa có giá trị thì đặt `1`; nếu đã có thì gộp với `1`. [Java SE 17 — ConcurrentHashMap.merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#merge(K,V,java.util.function.BiFunction)).

Không suy ra cùng tính nguyên tử từ việc gọi `merge` trên một Map bất kỳ chỉ vì giao diện Map có phương thức ấy. Phải xem hợp đồng của cách cài đặt đang dùng.

Hàm gộp nên ngắn, đơn giản và không sửa lại các ánh xạ khác theo cách vi phạm hợp đồng. Một phép nguyên tử theo một khóa cũng không tự tạo giao dịch cho nhiều khóa, chẳng hạn chuyển số dư giữa hai tài khoản.

## 5. Kiểm tra rồi hành động: contains–add và size–get

### 5.1. contains rồi add có thể thêm trùng

Xét yêu cầu “chỉ thêm X nếu chưa có”:

~~~java
if (!list.contains("X")) {
    list.add("X");
}
~~~

Nếu hai luồng cùng kiểm tra trước khi luồng nào thêm, cả hai đều thấy chưa có `X`, rồi cả hai đều thêm. Kết quả có thể là `[X, X]`.

Điều này vẫn xảy ra với `Collections.synchronizedList` nếu chỉ dựa vào khóa riêng trong từng phương thức. Khóa của `contains` được nhả trước khi gọi `add`; luồng khác có thể đi qua giữa hai bước.

Nếu dùng danh sách bọc đồng bộ và cần bất biến này, bảo vệ cả đoạn:

~~~java
synchronized (list) {
    if (!list.contains("X")) {
        list.add("X");
    }
}
~~~

Tất cả các nơi liên quan phải tuân thủ giao thức truy cập trên cùng đối tượng bọc. Một luồng khác sửa trực tiếp danh sách nền hoặc dùng một khóa khác có thể phá điều kiện bảo vệ.

Với yêu cầu tập hợp duy nhất, một Set phù hợp truy cập đồng thời có thể diễn tả mô hình tốt hơn. Với CopyOnWriteArrayList, phương thức `addIfAbsent` cung cấp đúng thao tác cần thiết; không nên tự tách thành contains và add nếu cần tính nguyên tử tương ứng.

### 5.2. size rồi get có thể dùng một chỉ số đã hết hiệu lực

~~~java
int lastIndex = list.size() - 1;
String value = list.get(lastIndex);
~~~

Giữa hai dòng, luồng khác có thể xóa phần tử hoặc clear danh sách. `lastIndex` được tính từ trạng thái trước, còn `get` đọc trạng thái sau.

Trong chương trình, danh sách bọc đồng bộ ban đầu có một phần tử. Luồng đọc lấy chỉ số `0`, luồng ghi xóa hết, rồi luồng đọc gọi get và gặp IndexOutOfBoundsException. Các phương thức riêng vẫn được bảo vệ; điều kiện sử dụng giữa chúng đã thay đổi.

Cách xử lý tùy ý nghĩa yêu cầu: khóa cả chuỗi nếu phải đọc một phần tử theo trạng thái đã kiểm tra, dùng một snapshot, hoặc chọn API nguyên tử phù hợp. Với hàng đợi concurrent, chẳng hạn, thường nên dùng phép lấy phần tử có hợp đồng rõ như poll thay vì tách isEmpty rồi remove.

## 6. Một khóa chỉ có tác dụng khi mọi bên dùng cùng giao thức

Một khóa chung có hai vai trò quan trọng:

- Ngăn các đoạn được bảo vệ chạy chen vào nhau theo cách phá bất biến.
- Thiết lập quan hệ đồng bộ để cập nhật trước lần nhả khóa được nhìn thấy bởi lần lấy cùng khóa tiếp theo.

Khóa phần ghi nhưng để phần đọc đi ngoài giao thức không tự cung cấp toàn bộ bảo đảm cần có. Khóa các đối tượng khác nhau cũng không bảo vệ cùng một vùng trạng thái.

Ví dụ lỗi thiết kế:

~~~text
luồng 1 khóa lockA rồi sửa shared
luồng 2 khóa lockB rồi đọc shared
~~~

Hai luồng không tranh cùng khóa nên các khối vẫn có thể chạy đồng thời. Việc cả hai đều có từ khóa synchronized trong mã chưa đủ.

Một lớp quản lý collection có thể dùng khóa riêng và chỉ cho truy cập qua các phương thức của lớp. Điều quan trọng là không để lộ tham chiếu nền cho mã khác sửa bên ngoài giao thức ấy.

### Không giữ khóa lâu hơn yêu cầu

Đoạn cần tính nguyên tử nên đủ rộng để giữ bất biến nhưng tránh kéo theo công việc không cần thiết như I/O chậm, callback không kiểm soát hoặc chờ một luồng khác đang cần cùng khóa.

Không đặt một điểm chờ “cả hai luồng phải tới” bên trong khóa mà chỉ một luồng được vào. Khi luồng đầu giữ khóa và chờ, luồng thứ hai không vào được để tới điểm chờ: chương trình tự tạo tình huống không thể tiến triển.

Ví dụ minh chứng đặt barrier **trước** khối khóa trong ca sửa đúng. Nhờ vậy, việc phối hợp khởi đầu không làm hai luồng chờ nhau trong vùng loại trừ.

## 7. Duyệt là một chuỗi truy cập, không phải một lần gọi đơn

Một vòng foreach tạo và dùng Iterator qua nhiều bước. Nếu nguồn được bọc bởi synchronizedList, không được coi việc gọi `iterator()` là đã giữ khóa cho toàn bộ vòng lặp.

Cách dùng đúng theo hợp đồng lớp bọc:

~~~java
synchronized (list) {
    for (String value : list) {
        consume(value);
    }
}
~~~

Đây là đoạn minh họa cần `list` là danh sách bọc tương ứng và `consume` tuân thủ thiết kế của ứng dụng.

Tài liệu của synchronizedList yêu cầu đồng bộ trên chính danh sách trả về khi duyệt qua Iterator, Spliterator hoặc Stream. Mọi truy cập tới nguồn nền phải đi qua lớp bọc để bảo đảm giao thức. [Java SE 17 — Collections.synchronizedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedList(java.util.List)).

Với synchronizedMap, khi duyệt keySet, values hoặc entrySet phải khóa Map bọc theo hợp đồng của nó, không tự đổi sang khóa một khung nhìn vừa lấy ra.

### Stream không tự khóa nguồn cho cả lượt xử lý

`list.stream().filter(...).toList()` vẫn phải duyệt nguồn. Đổi cú pháp foreach sang Stream không biến một nguồn sửa được dùng chung thành ảnh chụp hoặc nguồn an toàn.

Nếu cần giữ khóa suốt một lượt Stream tuần tự, vùng khóa phải bao trùm thời gian thực hiện terminal theo chính sách lớp bọc. Với xử lý chậm hoặc cần chạy song song, thường nên tạo snapshot dưới khóa rồi xử lý snapshot bên ngoài thay vì giữ khóa qua toàn bộ công việc.

Cũng tránh để pipeline song song chạy các tác vụ lại cố lấy một khóa mà luồng gọi đang giữ trong khi chờ chúng hoàn thành. Chọn chiến lược nguồn và quyền sở hữu rõ ràng trước khi thêm parallelStream.

## 8. ConcurrentModificationException giúp phát hiện lỗi, không thay cơ chế bảo vệ

Iterator fail-fast của những collection như ArrayList có thể ném `ConcurrentModificationException` khi phát hiện sửa đổi không phù hợp.

Nhưng không được suy ra:

~~~text
không ném ngoại lệ => mọi truy cập đều an toàn
~~~

Việc phát hiện chỉ theo khả năng tốt nhất. Một lần chạy không gặp ngoại lệ có thể do lịch chạy chưa bộc lộ lỗi hoặc dạng ghi không được phép không bị cơ chế đó phát hiện theo cách đang tưởng.

Ngoại lệ này cũng không chứng minh chắc chắn có hai luồng. Ngay trong một luồng, sửa trực tiếp collection bằng cách không phù hợp trong khi Iterator đang duyệt cũng có thể làm Iterator phát hiện thay đổi.

Bắt ngoại lệ rồi lặp lại vô hạn không tạo được một thuật toán đúng. Phải quyết định dữ liệu cần được đọc theo ảnh chụp, theo trạng thái sống có chính sách đồng thời, hay dưới khóa giữ một trạng thái nhất quán.

## 9. Ba mô hình đọc dữ liệu khi có cập nhật

| Mô hình | Điều người đọc cần hiểu | Đổi lại |
| --- | --- | --- |
| Đọc dưới khóa chung | Trạng thái liên quan được giữ ổn định trong vùng khóa nếu mọi bên tuân thủ | Có thể chặn các luồng khác |
| Đọc snapshot | Người đọc dùng một tập phần tử đã cố định cho lượt xử lý | Phải trả chi phí tạo/giữ bản sao và chấp nhận dữ liệu có thể cũ |
| Duyệt nguồn concurrent | Cập nhật có thể tiếp tục theo hợp đồng cấu trúc | Không mặc nhiên có ảnh chụp nguyên tử toàn bộ |

### 9.1. Tạo snapshot cũng phải đọc nguồn hợp lệ

Với một synchronizedList:

~~~java
List<String> snapshot;
synchronized (source) {
    snapshot = List.copyOf(source);
}
~~~

Việc chép được làm trong vùng bảo vệ tương ứng. Sau đó có thể xử lý snapshot ngoài khóa nếu những bảo đảm về phần tử và công bố kết quả phù hợp.

`List.copyOf` trả danh sách không cho sửa và không phản ánh các thay đổi vị trí tiếp theo của nguồn; nó không chấp nhận phần tử null. Nếu dữ liệu hợp lệ có null, phải chọn cách sao chép và công bố khác thích hợp. [Java SE 17 — List.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).

Không lấy một ArrayList đang bị ghi không đồng bộ rồi gọi copyOf để “làm nó an toàn”. Trước khi có bản sao, thao tác sao chép vẫn phải đọc nguồn đang có tranh chấp.

### 9.2. CopyOnWriteArrayList giữ snapshot cho Iterator

Iterator của CopyOnWriteArrayList dùng trạng thái mảng tại lúc tạo. Các cập nhật sau không làm Iterator ấy nhìn thấy phần tử mới. [Java SE 17 — CopyOnWriteArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CopyOnWriteArrayList.html).

Trong ca thử, Iterator được tạo từ `[A, B]`, sau đó collection thêm `C`. Iterator vẫn thu `[A, B]`, còn collection hiện tại là `[A, B, C]`.

Cách này có ích khi đọc nhiều hơn ghi rất nhiều, nhưng mỗi cập nhật có chi phí sao chép cấu trúc. Không chọn nó làm đáp án mặc định cho một tập dữ liệu lớn bị ghi liên tục.

### 9.3. ConcurrentHashMap không đóng băng mọi khóa trong một lượt duyệt

Các lượt duyệt của ConcurrentHashMap có tính nhất quán yếu, phù hợp với cập nhật đồng thời theo hợp đồng của lớp. Chúng không tự tạo ảnh chụp toàn cục tại một thời điểm duy nhất. [Java SE 17 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html).

Một phép tăng nguyên tử theo khóa có thể đúng, nhưng tính tổng nhiều khóa trong lúc các luồng khác cập nhật vẫn cần xem yêu cầu nhất quán của báo cáo. Không gộp bảo đảm nguyên tử của một phương thức thành bảo đảm giao dịch cho toàn bộ Map.

## 10. Công bố dữ liệu, final, volatile và đối tượng phần tử

### 10.1. Công bố an toàn là điều kiện để bên đọc dùng trạng thái đã tạo

Xây dựng một collection rồi đưa cho luồng khác cần một đường công bố phù hợp, chẳng hạn quan hệ qua Thread.start, khóa chung, tham chiếu volatile hoặc các cấu trúc truyền dữ liệu có hợp đồng bộ nhớ.

Các tiện ích concurrent mô tả những quan hệ happens-before cho việc chuyển công việc hoặc dữ liệu giữa các luồng. [Java SE 17 — Memory consistency properties](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/package-summary.html#MemoryVisibility).

Chương trình minh chứng khởi tạo dữ liệu trước khi start các luồng, dùng barrier/latch để phối hợp và chờ các luồng kết thúc trước khi in kết quả. Nó không dùng sleep để đoán rằng “chắc luồng kia đã ghi xong”.

### 10.2. final không làm collection trở thành bất biến

~~~java
final List<String> names = new ArrayList<>();
names.add("A");
~~~

Đây là đoạn minh họa hợp lệ. `final` ngăn gán lại biến `names`, không cấm gọi add, clear hoặc sửa trạng thái phần tử.

Đừng coi việc trường giữ collection là final như một sự thay thế cho hợp đồng sửa dữ liệu. Cần xét trạng thái nào còn có thể thay đổi sau khi đối tượng được xây dựng và ai được phép thay đổi nó.

### 10.3. volatile trên tham chiếu không khóa nội dung collection

Một trường `volatile List<String>` có thể dùng để công bố việc thay cả tham chiếu tới một snapshot mới. Nhưng nó không biến các phép add/get trên cùng ArrayList thành các thao tác được tuần tự hóa.

Mô hình phù hợp là chuẩn bị một phiên bản dữ liệu không tiếp tục sửa rồi công bố tham chiếu mới. Nếu vẫn cho nhiều bên sửa cùng collection được tham chiếu, cần một cơ chế riêng cho những lần sửa đó.

### 10.4. Map an toàn không tự bảo vệ ArrayList được giữ làm giá trị

Ví dụ minh họa cần thận trọng:

~~~java
map.computeIfAbsent(key, ignored -> new ArrayList<>()).add(value);
~~~

Nếu `map` là ConcurrentHashMap, việc thiết lập ánh xạ có hợp đồng nguyên tử của Map. Nhưng đối tượng ArrayList được trả về vẫn có thể bị nhiều luồng cùng gọi add. Map không khóa mọi hành động tương lai lên giá trị.

Có thể chọn cấu trúc giá trị phù hợp, một khóa riêng theo thiết kế, hoặc thay thế giá trị bằng các đối tượng dữ liệu mới trong phép cập nhật nguyên tử. Phải xác định rõ quyền sở hữu và trạng thái bên trong, không chỉ nhìn lớp của Map ngoài cùng.

## 11. Tái lập lỗi bằng lịch phối hợp, không dựa vào may rủi

Một chương trình đa luồng chạy sai không nhất thiết sai trong mọi lần chạy. Chạy một vòng lặp lớn rồi chờ “thỉnh thoảng ra số khác” có thể khó học và khó kiểm tra.

Phần minh chứng dùng hai cơ chế:

- `CyclicBarrier` buộc cả hai luồng đã đọc/kiểm tra xong rồi mới cho chúng ghi.
- `CountDownLatch` buộc thao tác xóa xảy ra sau khi đã đọc kích thước nhưng trước khi đọc phần tử.

Các công cụ này tạo ra một lịch xen kẽ hợp lệ làm lộ khe giữa những phương thức riêng. Chúng không biến phép get–put thành nguyên tử; chúng chỉ làm cho lịch gây lỗi được chủ động tái lập. [Java SE 17 — CyclicBarrier](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CyclicBarrier.html), [Java SE 17 — CountDownLatch](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CountDownLatch.html).

Mỗi ca kiểm tra đều đợi hai luồng kết thúc và đưa lỗi trong luồng phụ về luồng gọi. Nếu không làm vậy, luồng chính có thể in số liệu khi tác vụ chưa xong hoặc chỉ thấy kết quả có vẻ đúng trong khi một luồng đã dừng do ngoại lệ.

Các giới hạn chờ trong helper dùng để phát hiện một ví dụ không tiến triển, không để xác định thứ tự nghiệp vụ. Thứ tự được tạo bởi barrier và latch, không bởi tốc độ CPU hoặc một khoảng sleep ước chừng.

## 12. Chương trình minh chứng đầy đủ

Lưu mã sau thành **CollectionRaceDemo.java**. Chương trình dùng API Java 17 và thư viện chuẩn.

Ba ca lỗi logic được tạo trên collection có phương thức riêng an toàn: mất cập nhật get–put, thêm trùng contains–add và chỉ số hết hiệu lực size–get. Chương trình không cố tạo data race nội bộ trên ArrayList thường rồi khẳng định một stdout ngẫu nhiên.

Ca sửa đúng bảo vệ cả check–add bằng một khóa và dùng ConcurrentHashMap.merge cho việc tăng theo khóa. Ca addIfAbsent dùng đúng thao tác của CopyOnWriteArrayList. Những phần snapshot và đối tượng phần tử giúp kiểm tra phạm vi bảo đảm còn lại.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Iterator;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class CollectionRaceDemo {
    @FunctionalInterface
    interface CheckedTask {
        void run() throws Exception;
    }

    private static Thread taskThread(CheckedTask task, AtomicReference<Throwable> failure) {
        return new Thread(() -> {
            try {
                task.run();
            } catch (Throwable problem) {
                failure.compareAndSet(null, problem);
            }
        });
    }

    private static void runPair(CheckedTask first, CheckedTask second) throws Exception {
        AtomicReference<Throwable> failure = new AtomicReference<>();
        Thread a = taskThread(first, failure);
        Thread b = taskThread(second, failure);
        a.start();
        b.start();
        a.join(8000);
        b.join(8000);
        if (a.isAlive() || b.isAlive()) {
            a.interrupt();
            b.interrupt();
            throw new AssertionError("Tasks did not finish");
        }
        if (failure.get() != null) {
            throw new AssertionError("Task failed", failure.get());
        }
    }

    private static void await(CountDownLatch latch) throws InterruptedException {
        if (!latch.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Timed out at latch");
        }
    }

    public static void main(String[] args) throws Exception {
        ConcurrentHashMap<String, Integer> counts = new ConcurrentHashMap<>();
        counts.put("item", 0);
        CyclicBarrier bothRead = new CyclicBarrier(2);
        CheckedTask splitIncrement = () -> {
            int oldValue = counts.get("item");
            bothRead.await(5, TimeUnit.SECONDS);
            counts.put("item", oldValue + 1);
        };
        runPair(splitIncrement, splitIncrement);
        System.out.println("lost-update=" + counts.get("item"));

        List<String> separate = Collections.synchronizedList(new ArrayList<>());
        CyclicBarrier bothChecked = new CyclicBarrier(2);
        CheckedTask checkThenAdd = () -> {
            boolean absent = !separate.contains("X");
            bothChecked.await(5, TimeUnit.SECONDS);
            if (absent) {
                separate.add("X");
            }
        };
        runPair(checkThenAdd, checkThenAdd);
        System.out.println("separate-check-add=" + separate);

        List<String> locked = Collections.synchronizedList(new ArrayList<>());
        CyclicBarrier ready = new CyclicBarrier(2);
        CheckedTask lockedAdd = () -> {
            ready.await(5, TimeUnit.SECONDS);
            synchronized (locked) {
                if (!locked.contains("X")) {
                    locked.add("X");
                }
            }
        };
        runPair(lockedAdd, lockedAdd);
        System.out.println("locked-check-add=" + locked);

        ConcurrentHashMap<String, Integer> atomicCounts = new ConcurrentHashMap<>();
        CheckedTask atomicIncrement = () -> {
            for (int i = 0; i < 1000; i++) {
                atomicCounts.merge("item", 1, Integer::sum);
            }
        };
        runPair(atomicIncrement, atomicIncrement);
        System.out.println("atomic-merge=" + atomicCounts.get("item"));

        List<String> shrinking = Collections.synchronizedList(
                new ArrayList<>(List.of("A")));
        CountDownLatch sizeRead = new CountDownLatch(1);
        CountDownLatch cleared = new CountDownLatch(1);
        AtomicReference<String> readOutcome = new AtomicReference<>();
        runPair(() -> {
            int index = shrinking.size() - 1;
            sizeRead.countDown();
            await(cleared);
            try {
                readOutcome.set(shrinking.get(index));
            } catch (IndexOutOfBoundsException expected) {
                readOutcome.set("IndexOutOfBoundsException");
            }
        }, () -> {
            await(sizeRead);
            shrinking.clear();
            cleared.countDown();
        });
        System.out.println("size-then-get=" + readOutcome.get());

        List<String> source = Collections.synchronizedList(
                new ArrayList<>(List.of("A", "B")));
        List<String> snapshot;
        synchronized (source) {
            snapshot = List.copyOf(source);
        }
        source.add("C");
        System.out.println("snapshot=" + snapshot);
        System.out.println("source-after-snapshot=" + source);

        CopyOnWriteArrayList<String> copyOnWrite =
                new CopyOnWriteArrayList<>(List.of("A", "B"));
        Iterator<String> iterator = copyOnWrite.iterator();
        copyOnWrite.add("C");
        List<String> seen = new ArrayList<>();
        iterator.forEachRemaining(seen::add);
        System.out.println("copy-on-write-iterator=" + seen);
        System.out.println("copy-on-write-current=" + copyOnWrite);

        CopyOnWriteArrayList<String> unique = new CopyOnWriteArrayList<>();
        CheckedTask addIfAbsent = () -> unique.addIfAbsent("X");
        runPair(addIfAbsent, addIfAbsent);
        System.out.println("add-if-absent=" + unique);

        StringBuilder sharedItem = new StringBuilder("seed");
        List<StringBuilder> objectSnapshot = List.copyOf(List.of(sharedItem));
        sharedItem.append("!");
        System.out.println("shallow-snapshot-element=" + objectSnapshot.get(0));
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 -encoding UTF-8 CollectionRaceDemo.java
java CollectionRaceDemo
~~~

Stdout chính xác:

~~~text
lost-update=1
separate-check-add=[X, X]
locked-check-add=[X]
atomic-merge=2000
size-then-get=IndexOutOfBoundsException
snapshot=[A, B]
source-after-snapshot=[A, B, C]
copy-on-write-iterator=[A, B]
copy-on-write-current=[A, B, C]
add-if-absent=[X]
shallow-snapshot-element=seed!
~~~

Mã đã biên dịch bằng `--release 17` và chạy trên JDK 24.0.2. Cờ biên dịch kiểm tra mức ngôn ngữ/API Java 17; lần chạy được xác nhận trên JVM đã nêu.

Giải thích kết quả:

| Dòng kết quả | Điều đã được kiểm tra |
| --- | --- |
| `lost-update=1` | Hai luồng cùng lấy 0, cùng tính 1 rồi ghi; một lần tăng bị mất |
| `separate-check-add=[X, X]` | contains và add an toàn riêng nhưng khe giữa chúng cho phép hai lần thêm |
| `locked-check-add=[X]` | Cả chuỗi kiểm tra–thêm được bảo vệ bằng cùng một khóa |
| `atomic-merge=2000` | Hai luồng, mỗi luồng 1000 lần cập nhật nguyên tử theo khóa |
| `size-then-get=IndexOutOfBoundsException` | Chỉ số được tính trước khi danh sách bị xóa không còn hợp lệ lúc get |
| `snapshot=[A, B]` | Bản sao vị trí giữ dữ liệu của lượt sao chép |
| `source-after-snapshot=[A, B, C]` | Nguồn có thể tiếp tục thay đổi sau đó |
| Nhóm `copy-on-write` | Iterator giữ ảnh chụp, khác trạng thái collection hiện tại |
| `add-if-absent=[X]` | Hai luồng dùng đúng thao tác không thêm trùng của CopyOnWriteArrayList |
| `shallow-snapshot-element=seed!` | Sao chép cấu trúc không nhân bản StringBuilder bên trong |

Các kết quả là minh chứng cho những lịch đã được điều phối và các API được dùng. Chúng không chứng minh mọi thuật toán dùng các lớp này đều an toàn, cũng không phải một phép đo hiệu năng.

## 13. Chọn cách xử lý theo bất biến cần giữ

| Nhu cầu | Hướng thiết kế |
| --- | --- |
| Dữ liệu xây xong rồi chỉ đọc | Công bố an toàn và ngăn mọi cập nhật không hợp lệ |
| Nhiều thao tác phải thấy cùng trạng thái | Một giao thức khóa bao trùm toàn bộ bất biến hoặc một API nguyên tử phù hợp |
| Cập nhật độc lập theo khóa | ConcurrentHashMap với merge/compute/putIfAbsent theo đúng hợp đồng |
| Duyệt nhiều, cập nhật ít và chấp nhận snapshot | Cân nhắc CopyOnWriteArrayList hoặc phiên bản dữ liệu không sửa |
| Xử lý lâu nhưng không muốn giữ khóa lâu | Sao chép nguồn hợp lệ dưới khóa rồi xử lý ngoài khóa |
| Chuyển phần tử giữa bên sản xuất và bên tiêu thụ | Cấu trúc hàng đợi có hợp đồng concurrent/blocking phù hợp |

Việc chọn cấu trúc nên xuất phát từ điều dữ liệu phải luôn đúng, không chỉ từ số lượng luồng. Một collection concurrent có thể hỗ trợ hàng nghìn lời gọi riêng an toàn nhưng không giữ được một quy tắc liên quan tới nhiều collection nếu quy tắc đó chưa được biểu diễn.

Với khóa ngoài, cần ghi rõ khóa nào bảo vệ trạng thái nào. Với snapshot, cần ghi rõ thời điểm chụp và mức sao chép. Với cấu trúc concurrent, cần đọc phạm vi nguyên tử và chính sách duyệt. Những thông tin ấy giúp người sửa mã sau này không vô tình dùng một đường truy cập phá giao thức.

## 14. Thực hành có đáp án

### Bài 1 — ConcurrentHashMap nhưng vẫn mất lần tăng

Hai luồng đều chạy `map.put(k, map.get(k) + 1)`. Vì sao Map không hỏng mà bộ đếm vẫn có thể sai?

**Đáp án:** Get và put có hợp đồng riêng nhưng cả chuỗi không nguyên tử. Hai luồng có thể cùng đọc giá trị cũ rồi cùng ghi một kết quả. Dùng phép cập nhật nguyên tử theo khóa như merge nếu phù hợp yêu cầu.

### Bài 2 — synchronizedList đã đủ cho contains–add chưa?

Một danh sách được bọc bằng synchronizedList. Hai luồng chạy kiểm tra chưa có X rồi thêm X. Vì sao vẫn có thể chứa hai X?

**Đáp án:** Khóa của contains không bao trùm tới add. Hai luồng có thể cùng kiểm tra trước khi bên nào thêm. Bảo vệ cả đoạn bằng cùng khóa hoặc chọn cấu trúc/API cung cấp đúng thao tác duy nhất cần có.

### Bài 3 — Có từ synchronized ở cả hai phía

Luồng ghi khóa lockA, luồng đọc khóa lockB nhưng cùng truy cập một danh sách. Có đủ bảo vệ không?

**Đáp án:** Không. Hai khóa độc lập không loại trừ nhau và không thiết lập giao thức chung cho dữ liệu ấy. Mọi truy cập liên quan phải tuân thủ cùng cơ chế bảo vệ được thiết kế.

### Bài 4 — Không có ConcurrentModificationException

Một lần chạy đọc–ghi ArrayList không ném ngoại lệ. Có thể kết luận rằng vòng duyệt chỉ số hoặc lịch hiện tại làm nó an toàn không?

**Đáp án:** Không. Fail-fast chỉ phát hiện theo khả năng tốt nhất và không thay thế đồng bộ. Không gặp lỗi trong một lần chạy không chứng minh tuân thủ hợp đồng bộ nhớ hoặc bất biến nghiệp vụ.

### Bài 5 — Chép để an toàn

Có thể gọi List.copyOf trên một ArrayList đang bị sửa không đồng bộ rồi coi mọi rủi ro đã được giải quyết không?

**Đáp án:** Không. Quá trình sao chép vẫn phải đọc nguồn hợp lệ. Cần giữ nguồn ổn định bằng giao thức phù hợp trong lúc tạo snapshot, rồi công bố kết quả đúng cách. Bản sao cấu trúc vẫn có thể dùng chung đối tượng phần tử.

### Bài 6 — volatile List có khóa add không?

Một trường volatile trỏ tới ArrayList. Hai luồng cùng add vào ArrayList đó có tự được tuần tự hóa không?

**Đáp án:** Không. Volatile trên tham chiếu không biến nội dung collection thành vùng được khóa. Nó có thể phù hợp để công bố một phiên bản dữ liệu mới không tiếp tục sửa; các cập nhật trên cùng đối tượng vẫn cần cơ chế riêng.

### Bài 7 — Giá trị bên trong Map concurrent

Vì sao `concurrentMap.computeIfAbsent(k, x -> new ArrayList<>()).add(v)` chưa bảo đảm nhiều luồng cùng thêm vào danh sách giá trị an toàn?

**Đáp án:** Map bảo vệ việc tạo/đặt ánh xạ theo hợp đồng, nhưng ArrayList được giữ làm giá trị vẫn là đối tượng riêng không tự an toàn. Phải thiết kế cấu trúc giá trị hoặc giao thức cập nhật phù hợp.

### Bài 8 — Đọc snapshot hay dữ liệu mới nhất?

Iterator của CopyOnWriteArrayList được tạo trước khi thêm C. Vì sao nó vẫn trả A, B? Nếu báo cáo phải phản ánh một trạng thái nhất quán mới hơn, có thể chỉ khẳng định “collection an toàn đa luồng” là đủ không?

**Đáp án:** Iterator giữ ảnh chụp tại lúc tạo, nên không có C trong lượt ấy. An toàn đa luồng không tự xác định yêu cầu độ mới và nhất quán của báo cáo. Phải chọn thời điểm đọc, phạm vi khóa hoặc phiên bản snapshot phù hợp yêu cầu.

## 15. Cách nhận diện tranh chấp trong mã thực tế

Tìm nơi trạng thái được chia sẻ, rồi đánh dấu tất cả các đoạn đọc–kiểm tra–ghi hoặc các lượt duyệt phụ thuộc nhiều lần đọc. Với mỗi đoạn, hỏi điều gì có thể thay đổi giữa các bước và cơ chế nào giữ bất biến.

Tiếp theo kiểm tra quyền truy cập: có đường nào sửa trực tiếp collection nền, dùng khóa khác, giữ đối tượng giá trị để sửa bên ngoài, hoặc công bố một tham chiếu trước khi trạng thái sẵn sàng không. Đừng chỉ kiểm tra một phương thức đang được sửa rồi bỏ qua các bên dùng chung dữ liệu.

Mô hình quan trọng của bài là: **collection an toàn bảo vệ đúng phần hợp đồng của nó; thuật toán vẫn phải bảo vệ cả chuỗi thao tác mà nghiệp vụ cần xem là một hành động.** Kết hợp quyền sở hữu rõ ràng, công bố đúng, thao tác nguyên tử và chính sách duyệt phù hợp mới tạo thành một thiết kế đọc–ghi nhiều luồng đáng tin.
