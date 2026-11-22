# emptyList, singleton, nCopies và các trường hợp dùng

Không phải kết quả collection nào cũng cần một danh sách được xây bằng nhiều lần `add`. Có những phương thức luôn trả về không có phần tử, có đúng một phần tử, hoặc một giá trị lặp lại ở nhiều vị trí. Lớp tiện ích `java.util.Collections` cung cấp các cách tạo diễn đạt trực tiếp những hình dạng dữ liệu ấy.

Ba tên cần nhận diện là `emptyList`, `singleton` và `nCopies`. Chúng không có cùng kiểu kết quả: `emptyList` trả list rỗng; `singleton` trả **set** một phần tử; `nCopies` trả list có `n` vị trí cùng giữ phần tử đã truyền. Họ `singletonList` và `singletonMap` bổ sung trường hợp một phần tử list và một ánh xạ map.

Phần quan trọng nhất của bài là hiểu quyền sửa và sự chia sẻ tham chiếu. `nCopies(3, object)` không gọi hàm tạo ba lần và không nhân bản sâu đối tượng. Một kết quả không cho thêm, xóa hay thay ô vẫn có thể chứa đối tượng sửa được.

Các ví dụ dùng Java 17, không cần thư viện ngoài. Cần biết `List`, `Set`, `Map` và tham chiếu đối tượng trước khi chạy chương trình.

## 1. Chọn cách tạo theo hình dạng kết quả

Hãy bắt đầu bằng ý nghĩa dữ liệu cần trả hoặc truyền:

| Nhu cầu | Cách tạo phù hợp | Kiểu kết quả | Số phần tử/ánh xạ |
| --- | --- | --- | --- |
| Không có phần tử trong một dãy | `Collections.emptyList()` | `List<T>` | 0 |
| Không có thành viên trong một tập | `Collections.emptySet()` | `Set<T>` | 0 |
| Không có ánh xạ | `Collections.emptyMap()` | `Map<K,V>` | 0 |
| Một thành viên của tập | `Collections.singleton(value)` | `Set<T>` | 1 |
| Một phần tử của dãy | `Collections.singletonList(value)` | `List<T>` | 1 |
| Một cặp khóa–giá trị | `Collections.singletonMap(key, value)` | `Map<K,V>` | 1 |
| Cùng một phần tử lặp ở `n` vị trí | `Collections.nCopies(n, value)` | `List<T>` | `n` nếu `n >= 0` |

Đây là các phương thức tạo tĩnh. Người dùng kết quả làm việc qua kiểu giao diện, không cần phụ thuộc lớp triển khai bên trong.

Tài liệu gọi các kết quả này là collection “immutable”. Khi áp dụng, cần hiểu đúng phạm vi: cấu trúc phần tử/ánh xạ của kết quả không cho sửa; đối tượng được giữ bên trong không tự bị đóng băng hay sao chép sâu. Xem các khai báo và hợp đồng trong [API Collections, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html).

Không chọn theo độ ngắn tên hàm. Nếu API cần list có chỉ số 0, `singleton` không thay thế `singletonList` vì kiểu trả về khác. Nếu mục tiêu là có `n` đối tượng mới độc lập, `nCopies` không đáp ứng dù tên có chữ “copies”.

## 2. `emptyList`: một list tồn tại nhưng không có phần tử

### Rỗng khác với `null`

~~~java
List<String> result = Collections.emptyList();
~~~

Đây là mã minh họa trong một phương thức có đủ import. `result` là một đối tượng list hợp lệ, có `size() == 0` và `isEmpty() == true`. Có thể duyệt bằng vòng lặp; vòng lặp sẽ không thực hiện thân lần nào.

`null` lại có nghĩa không có đối tượng list để gọi phương thức. Một API hứa “trả về tất cả nhãn tìm được, có thể không có nhãn” thường diễn đạt hợp lý bằng một list rỗng. Người gọi có thể dùng cùng một đoạn duyệt cho cả trường hợp có và không có kết quả.

Không dùng list rỗng để che lỗi. Nếu truy vấn thất bại, chưa tải dữ liệu hoặc người gọi không có quyền truy cập, việc biến mọi trường hợp thành “không có phần tử” có thể làm mất thông tin quan trọng. Hợp đồng của API phải phân biệt trạng thái nghiệp vụ cần thiết.

### Rỗng không có nghĩa là danh sách để tiếp tục thêm

Đoạn cố ý sai:

~~~java
List<String> names = Collections.emptyList();
names.add("Lan"); // UnsupportedOperationException
~~~

Nếu cần tích lũy dần các tên, tạo `new ArrayList<>()`. Nếu cần trả một kết quả không có phần tử và không cho người nhận thêm vào chính kết quả ấy, `emptyList` diễn đạt rõ ý định.

Cũng không có phần tử ở vị trí 0. `emptyList.get(0)` không trả `null`; nó ném `IndexOutOfBoundsException`. “Không có phần tử” khác với “có một phần tử mà giá trị của nó là `null`”.

### Có kiểu dù chưa có phần tử

~~~java
List<String> a = Collections.emptyList();
List<String> b = Collections.<String>emptyList();
~~~

Cách đầu dùng kiểu đích để suy luận `T`. Cách sau ghi rõ tham số kiểu khi ngữ cảnh cần làm rõ. Không phải đưa một phần tử giả vào list để giúp trình biên dịch hiểu kiểu.

Nên dùng phương thức có generic thay vì trường raw type `Collections.EMPTY_LIST` trong mã mới. Trường raw có thể dẫn tới cảnh báo chuyển đổi không được kiểm tra; `emptyList()` cho phép giữ thông tin kiểu trong mã nguồn.

Không kiểm tra list rỗng bằng `result == Collections.emptyList()`. Cách triển khai có thể tái sử dụng đối tượng; sự tồn tại của tái sử dụng không biến định danh đối tượng thành điều kiện nghiệp vụ. Dùng `isEmpty()` khi cần biết có phần tử không.

### Hai họ hàng thường dùng

~~~java
Set<String> noPermissions = Collections.emptySet();
Map<String, Integer> noOverrides = Collections.emptyMap();
~~~

Ý nghĩa “rỗng” giống nhau ở số lượng nhưng thao tác và hợp đồng bình đẳng vẫn theo từng giao diện. Một list rỗng và một set rỗng không phải hai kiểu có thể thay nhau chỉ vì đều có `size() == 0`.

## 3. `singleton`: một phần tử của set, không phải mẫu thiết kế Singleton

### Tên hàm nói về số thành viên

~~~java
Set<String> requested = Collections.singleton("report");
~~~

Set có một thành viên `"report"`. Thường có thể truyền nó vào một API nhận nhiều mã khi lần gọi hiện tại chỉ cần một mã.

Từ “singleton” ở đây không khẳng định chỉ có một đối tượng trên toàn ứng dụng, không quy định một hàm `getInstance` và không biến phần tử thành biến toàn cục. Nó nói rằng tập kết quả có đúng một phần tử.

Nếu một phương thức nhận `Set<String>`, cách tạo này giúp diễn đạt yêu cầu một thành viên mà không cần tạo `HashSet` rồi `add`. Nếu phương thức nhận `List<String>`, cần chọn `singletonList` thay vì cố ép kiểu.

### `singletonList` có vị trí 0

~~~java
List<String> oneStep = Collections.singletonList("validate");
~~~

List có kích thước 1 và `oneStep.get(0)` là `"validate"`. Nó không cho thay bằng `set(0, other)`, không cho thêm phần tử thứ hai hoặc xóa phần tử duy nhất.

Đừng nhầm với một list kích thước cố định còn hỗ trợ thay phần tử. Từ “một phần tử” chưa tự quyết định quyền sửa; quyền sửa ở đây đến từ hợp đồng của factory.

### `singletonMap` có một ánh xạ

~~~java
Map<String, String> override =
        Collections.singletonMap("mode", "fast");
~~~

Map có đúng một khóa `"mode"` ánh xạ tới `"fast"`. Nó không cho `put` để thay giá trị hay thêm khóa khác.

Hữu ích khi truyền đúng một tùy chọn cho API nhận map, tạo dữ liệu kiểm thử có một ánh xạ, hoặc công bố một bảng tra cứu chỉ có một mục. Khi cần cập nhật tùy chọn sau đó, hãy tạo map sửa được phù hợp thay vì dựa vào kiểu giao diện `Map` rồi giả định `put` sẽ thành công.

### Phần tử vẫn có thể là đối tượng sửa được

Nếu `singletonList` giữ một `StringBuilder`, gọi `get(0).append(...)` sửa đối tượng ấy. Nếu `singletonMap` giữ một list làm giá trị, list đó có thể tiếp tục nhận phần tử qua tham chiếu khác.

Cấu trúc một phần tử không thay đổi nhưng trạng thái quan sát bên trong có thể đổi. Đối với phần tử set hoặc khóa map, cần đặc biệt giữ ổn định dữ liệu tham gia `equals`/`hashCode` trong thời gian đối tượng đang được lưu. Đây là yêu cầu của [Set](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html) và [Map](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html), không được loại bỏ bởi số phần tử bằng một.

## 4. `nCopies`: lặp một phần tử ở nhiều vị trí

### Số lượng và giá trị lặp

~~~java
List<String> states = Collections.nCopies(4, "pending");
~~~

Kết quả có kích thước 4. Mỗi vị trí hợp lệ từ 0 đến 3 trả cùng phần tử đã truyền. Khi in, nó biểu diễn `[pending, pending, pending, pending]`.

Quy tắc với số lượng:

- `n > 0`: có `n` phần tử.
- `n == 0`: list rỗng.
- `n < 0`: ném `IllegalArgumentException`.

Chỉ số hợp lệ vẫn theo `List`: `0 <= index < size()`. `nCopies(0, value)` không có vị trí 0 dù đã truyền một giá trị vào lời gọi.

Kết quả không hỗ trợ thay phần tử bằng `set`. Nếu cần từng vị trí nhận trạng thái khác nhau về sau, hãy tạo vật chứa làm việc từ dữ liệu ban đầu, như phần tiếp theo.

### “Copies” không có nghĩa gọi hàm tạo nhiều lần

Xét:

~~~java
List<StringBuilder> buffers =
        Collections.nCopies(3, new StringBuilder("start"));
~~~

Biểu thức `new StringBuilder("start")` được đánh giá một lần để tạo đối số. `nCopies` nhận một tham chiếu ấy rồi biểu diễn nó ở ba vị trí.

Có thể mô tả quan hệ như sau:

~~~text
vị trí 0 ─┐
vị trí 1 ─┼──> cùng một StringBuilder("start")
vị trí 2 ─┘
~~~

Không có ba `StringBuilder` khác nhau. Sửa qua `buffers.get(0)` sẽ được quan sát khi đọc ở vị trí 1 và 2 vì cả ba cùng trỏ tới một đối tượng.

Đối với chuỗi `String` hoặc một giá trị đã bất biến, dùng chung tham chiếu thường là điều mong muốn. Đối với bộ đệm, list con, đối tượng phiên làm việc hay ô có setter, điều đó dễ tạo lỗi dùng chung ngoài ý muốn.

### Biểu diễn gọn không xóa chi phí của các bước sau

API mô tả dữ liệu biểu diễn của `nCopies` là nhỏ và chỉ giữ một tham chiếu tới phần tử. Vì thế không nên tưởng rằng nó luôn cấp phát một mảng gồm `n` tham chiếu ngay khi gọi. [API nCopies, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#nCopies(int,T)).

Tuy nhiên, nếu sau đó thực sự duyệt từng vị trí, chuyển thành mảng hoặc tạo `ArrayList` chứa toàn bộ `n` vị trí, các bước ấy vẫn phải xử lý dữ liệu theo công việc mà chúng làm. Một biểu diễn lặp gọn không bảo đảm mọi thao tác sau đều rẻ hoặc không cấp phát.

Chương trình minh chứng tạo một list lặp có một triệu vị trí nhưng chỉ in `size` và đọc vị trí cuối. Nó không in cả một triệu phần tử và không tạo bản sao lớn để chứng minh khái niệm này.

## 5. Tạo các ô ban đầu cho một list sửa được

Một ứng dụng có thể cần bốn ô trạng thái ban đầu là `"pending"`, sau đó đổi từng ô và thêm ô mới.

~~~java
List<String> slots =
        new ArrayList<>(Collections.nCopies(4, "pending"));

slots.set(2, "done");
slots.add("extra");
~~~

`nCopies` tạo dữ liệu ban đầu; hàm tạo `ArrayList(Collection)` tạo vật chứa mới có các phần tử ấy. Vật chứa mới hỗ trợ `set` và `add`.

Không có sự thay đổi quyền sửa của list nguồn. List nguồn do `nCopies` tạo vẫn không sửa được; đối tượng `ArrayList` là một vật chứa khác.

Hàm tạo sao chép phần tử theo thứ tự duyệt của collection nguồn. Với phần tử sửa được, các tham chiếu vẫn có thể được chia sẻ; tạo list mới không tự tạo lại từng phần tử. [Các hàm tạo của ArrayList, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html).

### Cách này khác với chỉ đặt capacity

~~~java
List<String> reserved = new ArrayList<>(4);
~~~

Đối số 4 trong hàm tạo này là sức chứa ban đầu (capacity), không phải số phần tử hiện có. `reserved.size()` vẫn là 0. Do đó `reserved.set(2, "done")` không có ô thứ 2 để thay.

So sánh:

| Biểu thức | `size()` lúc đầu | Thay bằng `set(0, ...)` | Có thể thêm? |
| --- | --- | --- | --- |
| `new ArrayList<String>(4)` | 0 | Chưa có vị trí 0 | Có |
| `Collections.nCopies(4, "pending")` | 4 | Không hỗ trợ sửa | Không |
| `new ArrayList<>(Collections.nCopies(4, "pending"))` | 4 | Có | Có |

Một cách khác là tạo list rỗng rồi `add` đủ số phần tử. Lựa chọn phụ thuộc việc thật sự cần “các ô đã tồn tại” hay chỉ cần dự trữ bộ nhớ để bổ sung dần.

Đừng dùng `nCopies` chỉ để làm tăng capacity khi không cần các phần tử ban đầu; nó thay đổi cả `size` của bản sao khi dùng để khởi tạo `ArrayList`.

## 6. Đệm dữ liệu và tương tác với các thuật toán list

### Thêm nhiều lần cùng giá trị bằng `addAll`

~~~java
List<String> columns = new ArrayList<>(List.of("Ada", "Lin"));
columns.addAll(Collections.nCopies(2, "-"));
~~~

List đích trở thành `[Ada, Lin, -, -]`. Dữ liệu lặp chỉ làm nguồn cho `addAll`; list đích phải hỗ trợ thêm.

Nếu muốn đệm tới độ dài đích, tính **số ô thiếu**, không truyền nhầm tổng độ dài cần có:

~~~java
int targetSize = 6;
int missing = targetSize - columns.size();
if (missing > 0) {
    columns.addAll(Collections.nCopies(missing, "-"));
}
~~~

Đoạn này chỉ thêm khi thiếu; nó không cắt bớt nếu list đã dài hơn đích. Nếu yêu cầu là độ dài chính xác, trường hợp dài hơn phải được xử lý theo quy tắc nghiệp vụ riêng.

Đối với đầu vào kích thước từ bên ngoài, kiểm tra giới hạn có ý nghĩa cho ứng dụng trước khi tạo nhiều phần tử. Không chuyển mọi số âm thành 0 nếu số âm thật sự là lỗi cấu hình cần báo.

### `Collections.copy` cần số ô sẵn có và quyền thay ô

`Collections.copy(dest, src)` thay các phần tử đích theo chỉ số, không tự `add` để nới list đích. `dest.size()` phải ít nhất bằng `src.size()` và đích phải hỗ trợ thao tác thay phần tử.

Vì thế hai lỗi độc lập có thể xuất hiện:

1. `new ArrayList<>(source.size())` có capacity nhưng `size` bằng 0: chưa có đủ ô, nên không làm đích hợp lệ cho phép copy nguồn không rỗng.
2. `Collections.nCopies(source.size(), initial)` có đủ ô nhưng không cho thay, nên cũng chưa là đích hợp lệ.

Cách chuẩn bị phù hợp cho thí nghiệm này:

~~~java
List<String> source = List.of("A", "B", "C");
List<String> destination =
        new ArrayList<>(Collections.nCopies(source.size(), "?"));

Collections.copy(destination, source);
~~~

Kết quả đích là `[A, B, C]`. Nếu chỉ muốn một bản sao mới ngay từ đầu, `new ArrayList<>(source)` đơn giản hơn. Ví dụ dùng `copy` ở đây để hiểu yêu cầu của thuật toán thay vị trí và vai trò của những ô khởi tạo.

`Collections.copy` cũng không phải thao tác nhân bản sâu các phần tử; nó chuyển các giá trị phần tử sang các vị trí đích theo hợp đồng list.

### `nCopies` và `fill` giải quyết hai việc khác nhau

`nCopies` tạo một list biểu diễn sự lặp. `Collections.fill(existing, value)` thay phần tử ở các vị trí hiện có của một list đã tồn tại. `fill` không làm `size` từ 0 thành `n`.

Nếu list đang rỗng, việc fill không tự tạo ô. Nếu list không hỗ trợ thay phần tử, việc fill để thực sự thay dữ liệu không phải một cách phá quyền sửa. Chọn cách tạo hoặc thuật toán theo thao tác cần thực hiện, không chỉ theo ý tưởng chung “điền giá trị”.

## 7. Bẫy list lồng nhau: nhiều vị trí cùng một hàng

Một ý tưởng dễ xuất hiện khi tạo bảng ba hàng:

~~~java
List<List<String>> rows = new ArrayList<>(
        Collections.nCopies(3, new ArrayList<String>()));
~~~

List ngoài là `ArrayList` nên có thể sửa. Nhưng ba phần tử bên trong đều là cùng **một** `ArrayList<String>`. Lớp bọc sao chép ở ngoài không thay quan hệ tham chiếu này.

~~~java
rows.get(0).add("X");
~~~

Sau lời gọi, in `rows` cho ra `[[X], [X], [X]]`. Không phải vòng lặp trong `add` đã sửa ba hàng. Chỉ một hàng thực sự tồn tại và nó được hiển thị qua ba vị trí.

Để có ba hàng độc lập, tạo một đối tượng hàng trong mỗi lượt:

~~~java
List<List<String>> rows = new ArrayList<>();
for (int i = 0; i < 3; i++) {
    rows.add(new ArrayList<>());
}
~~~

Bây giờ thêm `"X"` vào hàng đầu chỉ làm kết quả `[[X], [], []]`.

Điều quyết định là **vị trí đặt lời gọi tạo đối tượng mới**. Nó phải được thực hiện riêng cho mỗi phần tử. Không đủ để chỉ bao list ngoài bằng `new ArrayList<>(...)` hoặc gọi lại một phương thức vẫn trả cùng đối tượng con.

Mẫu sai tương tự còn xuất hiện khi tạo nhiều bộ đệm bằng một `StringBuilder`, nhiều giỏ hàng bằng một đối tượng giỏ, hoặc nhiều cấu hình chỉnh sửa bằng cùng một bản cấu hình có setter. Trước khi dùng `nCopies`, hãy quyết định việc dùng chung phần tử là chủ đích hay lỗi.

Nếu các hàng chỉ là dữ liệu đã chốt và không sửa được, chia sẻ có thể hoàn toàn phù hợp. “Cùng tham chiếu” không tự là lỗi; lỗi nằm ở việc cần độc lập nhưng lại cho phép cập nhật chung.

## 8. `null`, kiểu dữ liệu và khác biệt với `of`

### Các factory nhỏ này có thể chứa `null`

Các trường hợp sau đều tạo được:

~~~java
Set<String> oneNull = Collections.singleton(null);
List<String> nullItem = Collections.singletonList(null);
Map<String, String> nullPair = Collections.singletonMap(null, null);
List<String> nullSlots = Collections.nCopies(3, null);
~~~

`nullItem` có kích thước 1, không phải 0. `nullSlots` có kích thước 3. `nullPair` có một ánh xạ với khóa `null` và giá trị `null`.

Với map, `get(null) == null` tự nó chưa phân biệt khóa vắng và giá trị `null`; dùng `containsKey` nếu cần xác định có ánh xạ. Chương trình sẽ in cả hai thông tin.

Khả năng chứa `null` không có nghĩa nên dùng `null` trong mọi mô hình. Chỉ dùng khi hợp đồng phần tử và các bước xử lý phía sau hiểu rõ ý nghĩa của nó.

### Đổi sang factory mới có thể đổi hành vi

Các cách viết sau không có cùng chính sách `null`:

| Cách tạo | Với một phần tử `null` |
| --- | --- |
| `Collections.singletonList(null)` | Tạo list kích thước 1 |
| `List.of((String) null)` | `NullPointerException` |
| `Collections.singleton(null)` | Tạo set kích thước 1 |
| `Set.of((String) null)` | `NullPointerException` |
| `Collections.singletonMap(null, null)` | Tạo một ánh xạ |
| `Map.of((String) null, (String) null)` | `NullPointerException` |

`List.of`, `Set.of` và `Map.of` từ chối `null` theo các hợp đồng riêng của chúng. Vì thế chuyển mã cũ từ các factory nhỏ sang `of` cần kiểm tra dữ liệu đầu vào; không coi đó là thay cú pháp không ảnh hưởng hành vi. [Hợp đồng List.of](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#unmodifiable), [Set.of](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#unmodifiable), [Map.of](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#unmodifiable).

Tương tự, `List.copyOf(nullItem)` bị từ chối vì nguồn có phần tử `null`. Một list hợp lệ với factory này chưa chắc hợp lệ khi chuyển qua factory khác.

### Generic có thể cần được ghi rõ

Với nhiều chỗ dùng `null` hoặc kết quả chưa có phần tử, kiểu đích giúp trình biên dịch hiểu kiểu mong muốn:

~~~java
List<String> slots = Collections.nCopies(3, null);
List<String> explicit = Collections.<String>nCopies(3, null);
~~~

Cả hai mô tả list chuỗi theo kiểu khai báo. Không cần ép kiểu raw để làm việc đó.

Cũng cần xác định phần tử đang là gì. `Collections.singletonList(array)` luôn tạo list có một phần tử là mảng đã truyền; nó không có dạng varargs để tự lấy mỗi ô mảng làm một phần tử. Dùng `Arrays.toString` khi muốn in nội dung mảng đó, không dự đoán từ chuỗi hiển thị mặc định của một đối tượng mảng.

## 9. Chương trình minh chứng chạy được

Lưu toàn bộ mã vào **`SmallCollectionsDemo.java`**. Hàm `rejects` chỉ chấp nhận đúng loại ngoại lệ được mong đợi. Nếu thao tác bất ngờ thành công hoặc ném một loại khác, chương trình dừng bằng `AssertionError`.

Các phép kiểm tra quyền sửa đều nhằm những thay đổi thực sự: thêm một phần tử vào list rỗng, thay phần tử đang tồn tại hoặc thay ánh xạ. Chương trình không dùng những thao tác không làm gì như `clear` trên list đã rỗng để suy ra hợp đồng.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class SmallCollectionsDemo {
    private static void rejects(
            String label,
            Class<? extends RuntimeException> expected,
            Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + " unexpectedly succeeded");
        } catch (RuntimeException ex) {
            if (!expected.isInstance(ex)) {
                throw new AssertionError(label + " wrong exception", ex);
            }
            System.out.println(label + "=" + ex.getClass().getSimpleName());
        }
    }

    private static List<String> labelsFor(boolean enabled) {
        if (!enabled) {
            return Collections.emptyList();
        }
        return Collections.singletonList("active");
    }

    public static void main(String[] args) {
        List<String> empty = Collections.emptyList();
        System.out.println("empty.isEmpty=" + empty.isEmpty());
        System.out.println("empty.family.sizes="
                + empty.size() + "/"
                + Collections.emptySet().size() + "/"
                + Collections.emptyMap().size());
        rejects("empty.add", UnsupportedOperationException.class,
                () -> empty.add("x"));
        rejects("empty.get", IndexOutOfBoundsException.class,
                () -> empty.get(0));

        Set<String> oneSet = Collections.singleton("solo");
        List<String> oneList = Collections.singletonList("solo");
        Map<String, String> oneMap =
                Collections.singletonMap("mode", "fast");
        System.out.println("singleton.set=" + oneSet);
        System.out.println("singleton.list=" + oneList);
        System.out.println("singleton.map=" + oneMap);
        rejects("singleton.add", UnsupportedOperationException.class,
                () -> oneSet.add("other"));
        rejects("singletonList.set", UnsupportedOperationException.class,
                () -> oneList.set(0, "other"));
        rejects("singletonMap.put", UnsupportedOperationException.class,
                () -> oneMap.put("mode", "safe"));

        Set<String> nullSet = Collections.singleton(null);
        List<String> nullList = Collections.singletonList(null);
        Map<String, String> nullMap =
                Collections.singletonMap(null, null);
        System.out.println("null.set.contains=" + nullSet.contains(null));
        System.out.println("null.list=" + nullList);
        System.out.println("null.map.containsKey=" + nullMap.containsKey(null));
        System.out.println("null.map.value=" + nullMap.get(null));

        List<String> repeated = Collections.nCopies(3, "idle");
        System.out.println("repeat=" + repeated);
        System.out.println("repeat.size=" + repeated.size());
        rejects("repeat.set", UnsupportedOperationException.class,
                () -> repeated.set(1, "done"));
        System.out.println("repeat.zero.size="
                + Collections.nCopies(0, "unused").size());
        rejects("repeat.negative", IllegalArgumentException.class,
                () -> Collections.nCopies(-1, "idle"));
        System.out.println("repeat.null="
                + Collections.<String>nCopies(2, null));

        StringBuilder shared = new StringBuilder("start");
        List<StringBuilder> aliases = Collections.nCopies(3, shared);
        System.out.println("repeat.shared="
                + (aliases.get(0) == aliases.get(2)));
        aliases.get(0).append("!");
        System.out.println("repeat.afterEdit=" + aliases);

        List<String> slots =
                new ArrayList<>(Collections.nCopies(4, "pending"));
        slots.set(2, "done");
        slots.add("extra");
        System.out.println("slots=" + slots);

        List<String> padded = new ArrayList<>(List.of("Ada", "Lin"));
        padded.addAll(Collections.nCopies(2, "-"));
        System.out.println("padding=" + padded);

        List<String> source = List.of("A", "B", "C");
        List<String> capacityOnly = new ArrayList<>(3);
        System.out.println("capacity.size=" + capacityOnly.size());
        rejects("capacity.copy", IndexOutOfBoundsException.class,
                () -> Collections.copy(capacityOnly, source));
        List<String> destination =
                new ArrayList<>(Collections.nCopies(3, "?"));
        Collections.copy(destination, source);
        System.out.println("copy.destination=" + destination);
        rejects("copy.readonlyDestination", UnsupportedOperationException.class,
                () -> Collections.copy(
                        Collections.nCopies(3, "?"), source));

        List<List<String>> sharedRows = new ArrayList<>(
                Collections.nCopies(3, new ArrayList<String>()));
        sharedRows.get(0).add("X");
        System.out.println("grid.shared=" + sharedRows);

        List<List<String>> independentRows = new ArrayList<>();
        for (int i = 0; i < 3; i++) {
            independentRows.add(new ArrayList<>());
        }
        independentRows.get(0).add("X");
        System.out.println("grid.independent=" + independentRows);

        List<String> compact = Collections.nCopies(1_000_000, "same");
        System.out.println("compact.size=" + compact.size());
        System.out.println("compact.last=" + compact.get(999_999));

        System.out.println("return.none=" + labelsFor(false));
        System.out.println("return.one=" + labelsFor(true));
        rejects("List.of.null", NullPointerException.class,
                () -> List.of((String) null));
        rejects("List.copyOf.null", NullPointerException.class,
                () -> List.copyOf(nullList));
    }
}
~~~

Biên dịch và chạy tại thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 SmallCollectionsDemo.java
java SmallCollectionsDemo
~~~

Cần JDK 17 trở lên cho lệnh biên dịch này. `--release 17` giới hạn cú pháp và API ở Java 17; mã đã được biên dịch với tùy chọn ấy và chạy trên OpenJDK 24.0.2, thoát thành công. Stdout chính xác:

~~~text
empty.isEmpty=true
empty.family.sizes=0/0/0
empty.add=UnsupportedOperationException
empty.get=IndexOutOfBoundsException
singleton.set=[solo]
singleton.list=[solo]
singleton.map={mode=fast}
singleton.add=UnsupportedOperationException
singletonList.set=UnsupportedOperationException
singletonMap.put=UnsupportedOperationException
null.set.contains=true
null.list=[null]
null.map.containsKey=true
null.map.value=null
repeat=[idle, idle, idle]
repeat.size=3
repeat.set=UnsupportedOperationException
repeat.zero.size=0
repeat.negative=IllegalArgumentException
repeat.null=[null, null]
repeat.shared=true
repeat.afterEdit=[start!, start!, start!]
slots=[pending, pending, done, pending, extra]
padding=[Ada, Lin, -, -]
capacity.size=0
capacity.copy=IndexOutOfBoundsException
copy.destination=[A, B, C]
copy.readonlyDestination=UnsupportedOperationException
grid.shared=[[X], [X], [X]]
grid.independent=[[X], [], []]
compact.size=1000000
compact.last=same
return.none=[]
return.one=[active]
List.of.null=NullPointerException
List.copyOf.null=NullPointerException
~~~

### Đối chiếu kết quả với cơ chế

**`empty.isEmpty` và `empty.family.sizes`:** có các vật chứa hợp lệ, đều có số phần tử/ánh xạ bằng 0. `empty.add` bị chặn; `empty.get` cho thấy rỗng không có vị trí 0.

**Ba dòng `singleton`:** tên `singleton` không tự hàm ý list. Set, list và map được tạo bằng đúng ba hàm khác nhau. Các thao tác sửa thực sự đều bị từ chối.

**Nhóm `null`:** một set chứa `null` vẫn có thể tìm thành viên `null`; list chứa một phần tử `null` vẫn có một vị trí. Map có khóa `null` trả giá trị `null` nhưng `containsKey` xác nhận ánh xạ tồn tại.

**Nhóm `repeat`:** số lượng bằng 3, 0 và âm được thử riêng. Danh sách lặp cho phép `null`, nhưng không cho `set`. Phép so `==` giữa hai phần tử trong thí nghiệm này kiểm tra đúng quan hệ cùng tham chiếu mà `nCopies` tạo ra, không dùng để dự đoán định danh của chính các list factory.

**`repeat.afterEdit`:** cùng một `StringBuilder` đã đổi thành `"start!"`, nên ba vị trí đều biểu diễn văn bản mới. Không có lời gọi nào thay ô trong list.

**`slots` và `padding`:** dữ liệu lặp được dùng để khởi tạo hoặc nối vào list đích sửa được. Các giá trị chuỗi được chia sẻ an toàn vì không có thao tác đổi nội dung chuỗi.

**`capacity` và `copy`:** chỉ cấp capacity chưa tạo phần tử. Bản `ArrayList` có các ô khởi tạo nhận được dữ liệu nguồn; list `nCopies` dùng trực tiếp làm đích thì không hỗ trợ thay ô.

**Hai dòng `grid`:** sao chép list ngoài không nhân bản các list con. Chỉ vòng lặp tạo `new ArrayList<>()` cho từng lượt mới cho các hàng độc lập trong ví dụ này.

**`compact`:** list lặp biểu diễn một triệu vị trí, nhưng thí nghiệm chỉ đọc hai thông tin nhỏ. Không suy ra từ đây rằng chuyển cả list ấy sang mảng hoặc xuất hết thành văn bản cũng có cùng chi phí.

**`return.none` và `return.one`:** một API có kết quả 0 hoặc 1 phần tử có thể trả collection hợp lệ ở cả hai nhánh. Hai dòng ngoại lệ cuối cho thấy một list có `null` không chuyển trực tiếp sang chính sách không `null` của `List.of`/`List.copyOf` được.

## 10. Các trường hợp dùng thực tế

### Trả không có kết quả nhưng giữ hợp đồng collection

Một bộ phân tích có thể tìm được nhiều cảnh báo hoặc không có cảnh báo. Nếu API hứa trả về một list và không cho sửa kết quả, nhánh không có cảnh báo có thể trả `Collections.emptyList()`.

Cần giữ hợp đồng giữa các nhánh. Nếu nhánh rỗng không cho thêm nhưng nhánh có dữ liệu lại trả trực tiếp `ArrayList` nội bộ, người gọi có thể vô tình phụ thuộc quyền sửa thay đổi theo dữ liệu.

Không nhất thiết ép mọi API trả collection. Nếu nghiệp vụ là “có hoặc không một đối tượng”, một kiểu biểu diễn sự vắng mặt có thể rõ hơn. `emptyList` và `singletonList` hợp lý khi API thực sự được thiết kế để xử lý dãy kết quả, kể cả dãy 0 hoặc 1 phần tử.

### Truyền đúng một giá trị cho API nhận nhiều giá trị

Một API tìm kiếm theo tập mã có thể nhận `Collections.singleton(code)`. Một API xử lý dãy bước có thể nhận `Collections.singletonList(step)`. Một API nhận tùy chọn có thể nhận `Collections.singletonMap(key, value)`.

Điều kiện là API nhận phải tôn trọng quyền đọc, không thử thêm/xóa vào đầu vào. Một tham số có kiểu `Collection` hay `List` không tự cam kết nó sửa được.

Nếu phương thức cần tự sửa dữ liệu để tính toán, nó nên tạo bản làm việc phù hợp hoặc ghi rõ yêu cầu đầu vào sửa được. Hợp đồng rõ giúp người gọi không phải đoán loại list nội bộ.

### Dữ liệu lặp cho khởi tạo và trình bày

`nCopies` phù hợp để tạo các ô ban đầu có cùng giá trị bất biến, thêm dấu đệm vào một dãy, hoặc cung cấp dữ liệu lặp cho thuật toán chỉ đọc.

Nếu các ô sẽ nhận giá trị khác nhau, dùng bản list sửa được từ dữ liệu lặp. Nếu mỗi ô sẽ chứa một đối tượng riêng có trạng thái, tạo từng đối tượng độc lập thay vì dùng `nCopies` như một bộ phát sinh đối tượng.

### Dữ liệu kiểm thử có ý nghĩa

Các hình dạng rỗng, một phần tử và nhiều lần lặp giúp thử biên của thuật toán. Nhưng hãy chọn giá trị lặp theo mục tiêu:

- Muốn thử xử lý nhiều vị trí có cùng giá trị thì `nCopies` có thể phù hợp.
- Muốn thử nhiều đối tượng bằng nhau về dữ liệu nhưng khác tham chiếu thì phải tạo nhiều đối tượng.
- Muốn thử trạng thái từng phần tử thay đổi độc lập thì càng không dùng một đối tượng lặp chung.

Một kiểm thử dùng sai quan hệ tham chiếu có thể che lỗi hoặc tạo ra hiện tượng không đại diện cho dữ liệu thực.

## 11. Các lỗi thường gặp và cách suy luận lại

### “Singleton nghĩa là đối tượng duy nhất toàn hệ thống”

Ở đây nó nghĩa là một phần tử trong collection kết quả. Số phần tử không phải số lần cấp phát, không phải mẫu thiết kế và không phải quyền sở hữu toàn cục.

### “Chỉ có một phần tử thì `set` phải được”

Quyền `set` đến từ hợp đồng list cụ thể. `singletonList` và `nCopies` không phải list chỉ chặn tăng giảm kích thước nhưng vẫn cho thay phần tử.

Nếu cần thay, dùng một bản làm việc sửa được. Đừng thử ép kiểu sang lớp khác để vượt hợp đồng.

### “Rỗng là một ô `null`”

`emptyList()` có `size() == 0`. `singletonList(null)` có `size() == 1`. `nCopies(3, null)` có `size() == 3`. Ba hình dạng khác nhau và tác động tới mọi vòng lặp, phép truy cập chỉ số và thuật toán phía sau.

### “Tạo `ArrayList` ở ngoài sẽ làm mọi phần tử độc lập”

Hàm tạo list sao chép các tham chiếu phần tử. Trong trường hợp hàng lồng nhau, nó vẫn giữ nhiều tham chiếu tới cùng hàng. Muốn độc lập phải thiết kế đúng bước tạo/sao chép phần tử.

### “Không ném lỗi với thao tác không làm gì nghĩa là sửa được”

Một số thao tác tùy chọn hoặc thuật toán sửa có thể không ném ngoại lệ khi lời gọi thực tế không tạo thay đổi. Đừng lấy `clear` trên list rỗng, loại bỏ phần tử vắng hoặc sắp xếp dữ liệu không cần đổi làm cách nhận diện quyền sửa.

Tài liệu của `Collections` nêu việc các thuật toán sửa có thể ném hoặc không ném khi lời gọi không có tác dụng. Hợp đồng API và các thao tác thực sự cần cho bài toán mới là căn cứ.

### “Không sửa được thì mọi dữ liệu chia sẻ đều an toàn đồng thời”

Một `singletonList` chứa đối tượng đang bị sửa hoặc `nCopies` lặp một đối tượng có trạng thái vẫn chia sẻ chính trạng thái ấy. Việc list không cho thay ô không điều phối các lần ghi vào phần tử.

Nếu cần chia sẻ dữ liệu ổn định, chọn phần tử bất biến hoặc áp dụng một cơ chế phối hợp phù hợp cho dữ liệu sửa được. Cách phân biệt vật chứa và phần tử được giải thích trong [Collection, Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#unmodcoll).

### “Có số lượng `n` thì mọi thao tác đều giống một `ArrayList` kích thước `n`”

Hai cấu trúc có thể bằng nhau về phần tử khi so `equals` nhưng khác quyền sửa và cách biểu diễn. Đừng viết mã phụ thuộc tên lớp nội bộ hoặc kỳ vọng mọi thao tác có cùng chi phí.

Một list lặp gọn cũng có thể dẫn tới lượng công việc lớn nếu bạn xuất toàn bộ nội dung hoặc vật chất hóa mọi vị trí. Chọn thuật toán theo thao tác thực tế.

## 12. Thực hành có đáp án

### Bài 1 — Ba dạng không có dữ liệu giống nhau không?

So sánh:

~~~java
List<String> a = Collections.emptyList();
List<String> b = Collections.singletonList(null);
List<String> c = Collections.nCopies(3, null);
~~~

**Câu hỏi:** Kích thước từng list là bao nhiêu? List nào có thể gọi `get(0)` mà không lỗi chỉ số?

**Đáp án:** Kích thước lần lượt là 0, 1 và 3. `a.get(0)` ném `IndexOutOfBoundsException`; `b.get(0)` và `c.get(0)` đều trả `null`. Có một phần tử `null` vẫn là có một vị trí trong dãy, khác với dãy rỗng.

### Bài 2 — Cần một list cho API có chỉ số

Một hàm nhận `List<String>` và đọc phần tử ở vị trí 0 sau khi kiểm tra kích thước.

**Câu hỏi:** Có thể truyền trực tiếp `Collections.singleton("x")` không? Cách tạo nào trong bài đúng kiểu?

**Đáp án:** Không, vì `singleton` trả `Set<String>`. Dùng `Collections.singletonList("x")`. Không ép một set thành list chỉ vì nó có đúng một phần tử; kiểu và hợp đồng truy cập khác nhau.

### Bài 3 — Hai vị trí có hai bộ đệm không?

~~~java
List<StringBuilder> items =
        Collections.nCopies(2, new StringBuilder("a"));
items.get(1).append("b");
~~~

**Câu hỏi:** Khi đọc văn bản ở vị trí 0 và 1, thấy gì? List có bị thay ô không?

**Đáp án:** Cả hai đều biểu diễn `"ab"` vì giữ cùng một `StringBuilder`. Không có ô nào được thay; đối tượng được chia sẻ đổi trạng thái. Nếu cần hai bộ đệm độc lập, gọi `new StringBuilder("a")` riêng cho mỗi phần tử khi xây list.

### Bài 4 — Capacity chưa phải kích thước

~~~java
List<String> a = new ArrayList<>(5);
List<String> b =
        new ArrayList<>(Collections.nCopies(5, "pending"));
~~~

**Câu hỏi:** `a.set(4, "done")` và `b.set(4, "done")` có cùng kết quả không?

**Đáp án:** Không. `a` vẫn rỗng nên không có chỉ số 4 và ném `IndexOutOfBoundsException`. `b` có 5 phần tử thật và hỗ trợ thay nên phép `set` thành công. Nếu chỉ cần thêm dần, `a` hợp lý; nếu cần các vị trí đã tồn tại, phải tạo các phần tử như `b` hoặc thêm đủ bằng vòng lặp.

### Bài 5 — Sao chép list ngoài có sửa lỗi chung hàng không?

~~~java
List<List<Integer>> grid = new ArrayList<>(
        Collections.nCopies(2, new ArrayList<Integer>()));

grid.get(0).add(7);
~~~

**Câu hỏi:** Kết quả biểu diễn của `grid` là gì? Viết cách tạo hai hàng độc lập.

**Đáp án:** Kết quả là `[[7], [7]]`. List ngoài mới không nhân bản hàng. Có thể tạo như sau trong một phương thức:

~~~java
List<List<Integer>> grid = new ArrayList<>();
for (int i = 0; i < 2; i++) {
    grid.add(new ArrayList<>());
}
~~~

Với cách tạo này, thêm 7 vào hàng đầu cho kết quả `[[7], []]`.

### Bài 6 — Đệm tới độ dài đích

Một list đã có 3 phần tử; muốn thêm `"-"` để có 8 phần tử.

**Câu hỏi:** Truyền 8 hay 5 vào `nCopies` trong `addAll`? Nếu list đang có 10 phần tử thì sao?

**Đáp án:** Truyền số còn thiếu là 5. Truyền 8 sẽ làm list dài thành 11. Nếu đã có 10, đoạn mã “chỉ đệm khi thiếu” không thêm gì; muốn cắt còn 8 cần một yêu cầu và thao tác riêng. Không để số âm đi vào `nCopies` rồi coi ngoại lệ là cách điều khiển nhánh bình thường.

### Bài 7 — Đích cho `Collections.copy` cần gì?

Nguồn có ba chuỗi. Có hai ứng viên đích:

~~~java
List<String> a = new ArrayList<>(3);
List<String> b = Collections.nCopies(3, "?");
~~~

**Câu hỏi:** Tại sao cả hai chưa phù hợp? Cách tạo đích phù hợp là gì?

**Đáp án:** `a` có size 0 nên chưa có ô nhận dữ liệu; `b` có size 3 nhưng không cho thay ô. Có thể dùng `new ArrayList<>(Collections.nCopies(3, "?"))` để vừa đủ ô vừa sửa được. Nếu chỉ muốn tạo ngay một bản sao nguồn, `new ArrayList<>(source)` đơn giản hơn việc chuẩn bị ô rồi gọi `Collections.copy`.

### Bài 8 — Đổi sang `List.of` có luôn giữ hành vi không?

Một hàm có hợp đồng chấp nhận một phần tử `null` và đang trả `Collections.singletonList(value)`. Một thay đổi định dùng `List.of(value)` để thay thế.

**Câu hỏi:** Cần kiểm tra điều gì trước khi thay? Có thể dùng việc cả hai đều không sửa được làm bằng chứng tương đương không?

**Đáp án:** Phải kiểm tra chính sách `null`. Với `value == null`, cách cũ trả list kích thước 1 còn cách mới ném `NullPointerException`. Cùng quyền sửa vật chứa không chứng minh mọi hành vi giống nhau. Nếu muốn đổi hợp đồng để cấm `null`, phải xử lý như một thay đổi API có chủ đích và cập nhật phía gọi tương ứng.

Khi dùng các factory nhỏ này, hãy xác định rõ số phần tử cần có, kiểu collection cần trả và việc phần tử được chia sẻ hay phải độc lập. Ba thông tin ấy giúp phân biệt một kết quả gọn, đúng mục đích với một list nhìn có vẻ hợp lý nhưng sai quyền sửa hoặc sai quan hệ tham chiếu.
