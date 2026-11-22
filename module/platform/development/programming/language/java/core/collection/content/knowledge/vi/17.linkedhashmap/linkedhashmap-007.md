# LinkedHashMap: tương tác giữa access-order, iterator và thay đổi cấu trúc

Một vòng lặp tưởng như chỉ đọc dữ liệu vẫn có thể làm thay đổi `LinkedHashMap` nếu map được tạo ở chế độ thứ tự truy cập (`access-order`). Nguyên nhân là ứng dụng đang đọc giá trị, nhưng map đồng thời ghi nhận lần truy cập ấy vào thứ tự duyệt.

Hãy hình dung một bộ đệm có ba khóa `A, B, C`, từ ít được truy cập gần đây nhất đến mới nhất. Khi đọc `A`, ứng dụng muốn nhận giá trị của A; cấu trúc giữ thứ tự còn phải đưa A xuống cuối. Nếu một iterator đang đi theo chuỗi cũ, hai hoạt động này có thể xung đột dù số ánh xạ không đổi và chương trình chỉ có một luồng.

Bài này giúp bạn nhận ra thay đổi cấu trúc, đọc đúng ý nghĩa của fail-fast, chọn cách duyệt hoặc cập nhật phù hợp và tránh dùng ngoại lệ như cơ chế bảo đảm tính đúng. Ví dụ dùng Java 17+; những chi tiết về `modCount` được trình bày riêng như cơ chế của OpenJDK 17.

## 1. Một map có nhiều loại trạng thái

Đừng chỉ nhìn map như tập cặp khóa–giá trị. Với `LinkedHashMap`, cần phân biệt ít nhất ba loại trạng thái:

| Trạng thái | Ví dụ thay đổi |
|---|---|
| Thành phần ánh xạ | Thêm D hoặc xóa B |
| Giá trị của ánh xạ tồn tại | Thay giá trị A từ 1 thành 10 |
| Thứ tự duyệt | Chuyển A từ đầu xuống cuối |

`size()` chỉ đếm số ánh xạ. Nó không cho biết thứ tự vừa thay đổi hay không, cũng không cho biết có một khóa bị xóa rồi khóa khác được thêm để giữ nguyên số lượng.

Do đó, suy luận “size trước và sau bằng nhau nên iterator vẫn hợp lệ” thiếu thông tin. Một chương trình theo dõi cấu trúc cần quan tâm lịch sử thao tác trong khoảng iterator còn hoạt động.

### 1.1. Hai chế độ thứ tự

Constructor có tham số boolean cuối cùng chọn cách giữ thứ tự:

~~~java
LinkedHashMap<String, Integer> insertion =
        new LinkedHashMap<>(16, 0.75f, false);

LinkedHashMap<String, Integer> access =
        new LinkedHashMap<>(16, 0.75f, true);
~~~

Đây là hai khai báo minh họa, chưa phải chương trình độc lập.

Ở chế độ thứ tự chèn, vị trí phản ánh lần chèn khóa; cập nhật giá trị một khóa đang tồn tại không đổi vị trí đó. Ở chế độ thứ tự truy cập, những phương thức được API quy định là truy cập có thể đưa ánh xạ về phía mới nhất.

Vì vậy, cùng một lời gọi `put("A", 10)` lên khóa A đã có không nhất thiết có cùng tác động thứ tự trong hai chế độ.

### 1.2. Dòng thời gian của một lần đọc

Với thứ tự ban đầu `[A, B, C]`:

~~~text
T0: tạo iterator trên chuỗi A -> B -> C
T1: gọi get("A") trên map thứ tự truy cập
T2: thứ tự map thành B -> C -> A, size vẫn bằng 3
T3: tiếp tục dùng iterator được tạo tại T0
~~~

Tại T3, iterator không tự biến thành một lượt duyệt mới bắt đầu ở B. Nó đã được tạo trong một trạng thái trước đó. Cần xem việc thay đổi ở T1 là sửa đổi trong lúc duyệt, thay vì coi đó là thao tác đọc hoàn toàn độc lập.

API `LinkedHashMap` xác định thay đổi cấu trúc gồm thêm, xóa ánh xạ và, với chế độ thứ tự truy cập, tác động đến thứ tự duyệt. Các iterator của góc nhìn có cơ chế fail-fast khi phát hiện thay đổi không phù hợp. [Java 17: LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html)

## 2. “Access” là quy tắc API, không phải tên gọi nghiệp vụ

Một phương thức có tên nghe như đọc hoặc cập nhật nhẹ vẫn có thể tạo lượt truy cập theo quy tắc của lớp.

### 2.1. Các trường hợp điển hình

Bảng sau xét map có `accessOrder=true`; “có thể đổi thứ tự” nghĩa là phải tính đến khả năng ánh xạ được chuyển vị trí, không phải mọi lời gọi luôn dịch chuyển một nút:

| Thao tác | Điều cần nghĩ đến khi iterator đang hoạt động |
|---|---|
| get khóa đang có | Có lượt truy cập; không coi là chỉ đọc cấu trúc |
| get khóa không có | Không có ánh xạ tương ứng để chuyển xuống cuối |
| getOrDefault với khóa đang có | Không phải cách né việc cập nhật thứ tự |
| put khóa mới | Thêm ánh xạ, thay đổi cấu trúc |
| put khóa đã có | Có thể đổi thứ tự dù chỉ gán lại giá trị |
| putIfAbsent với ánh xạ đang có giá trị khác null | Có thể ghi nhận truy cập dù không thay giá trị |
| replace thành công | Có thể ghi nhận truy cập |
| replace có điều kiện nhưng điều kiện không khớp | Không có lần thay giá trị thành công theo quy tắc đó |
| containsKey, containsValue | Không tạo lượt truy cập giữ độ mới |
| Đọc qua keySet, values, entrySet | Không tự tạo lượt truy cập kiểu get |

Nhóm phương thức `compute`, `computeIfAbsent`, `computeIfPresent` và `merge` cũng nằm trong quy tắc truy cập của `LinkedHashMap`; cần xét kết quả và điều kiện của từng phương thức. `putAll` xử lý các ánh xạ theo thứ tự duyệt nguồn. Đừng suy ra tác động chỉ từ việc “giá trị cuối cùng có vẻ không đổi”. [Quy tắc access-order trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html)

Bài sử dụng các trường hợp thông thường, có giá trị khác null, khi minh họa nhóm cập nhật. Các phương thức tính toán còn có quy tắc riêng về null, thêm và xóa; không nên gom chúng thành một thao tác “đọc rồi gán” duy nhất.

### 2.2. Đọc null không chứng minh không có truy cập

Nếu một khóa đang ánh xạ tới null, `get` trả về null nhưng vẫn đã tìm được ánh xạ. “Trả về null” và “không có khóa” là hai trạng thái khác nhau.

Ví dụ ở phần chương trình đầy đủ đặt giá trị B thành null qua `Map.Entry.setValue` để giữ thứ tự ban đầu, sau đó gọi `get("B")`. Thứ tự trở thành `[A, C, B]`. Ví dụ này tách được tác động của lần get khỏi tác động của một lần put trước đó.

`containsKey` giúp hỏi về sự tồn tại mà không ghi nhận truy cập như get. Tuy nhiên, ghép `containsKey` và `get` không tạo thành một thao tác nguyên tử khi có luồng khác cùng sửa map.

### 2.3. Thay giá trị bằng nhau vẫn cần nhìn vào phương thức

Không thể quyết định tính hợp lệ của vòng lặp bằng câu “tôi đã ghi lại đúng giá trị cũ”. Trong chế độ truy cập, lời gọi phương thức có thể mang ý nghĩa ghi nhận sử dụng ngay cả khi giá trị tham chiếu hoặc nội dung bằng nhau.

Cách tiếp cận đáng tin hơn là hỏi:

1. Phương thức có thể thêm hoặc xóa ánh xạ không?
2. Phương thức có thể ghi nhận truy cập và đổi thứ tự không?
3. Nếu chỉ muốn sửa giá trị của ánh xạ đang duyệt, có cách thao tác qua entry phù hợp không?

## 3. Thay đổi cấu trúc không đồng nghĩa thay đổi size

### 3.1. Cùng số ánh xạ, khác chuỗi

Ban đầu:

~~~text
A=1, B=2, C=3
thứ tự: A -> B -> C
size: 3
~~~

Sau `get("A")` ở chế độ truy cập:

~~~text
A=1, B=2, C=3
thứ tự: B -> C -> A
size: 3
~~~

Không ánh xạ nào được thêm, xóa hoặc thay giá trị, nhưng đường duyệt đã thay đổi.

Một ví dụ khác là xóa A rồi thêm D. Số lượng cuối cùng vẫn là ba, nhưng đây là hai thay đổi thành phần ánh xạ. Iterator cũ không được hợp lệ hóa chỉ vì size cuối cùng quay về số ban đầu.

### 3.2. Thứ tự cuối cùng giống ban đầu cũng chưa đủ

Giả sử lần lượt truy cập A, B, C trên map có thứ tự ban đầu A, B, C:

~~~text
ban đầu:   [A, B, C]
get(A):    [B, C, A]
get(B):    [C, A, B]
get(C):    [A, B, C]
~~~

Thứ tự cuối cùng trùng ban đầu, nhưng trong khoảng đó chuỗi đã bị sửa nhiều lần. Iterator được tạo trước các lần sửa không trở lại hợp lệ một cách tự động.

Đây là khác biệt giữa so sánh hai ảnh chụp trạng thái và tuân thủ quy tắc thao tác trong một lượt duyệt. Với iterator, lịch sử sửa đổi trong khoảng duyệt có ý nghĩa.

### 3.3. Cập nhật giá trị qua entry là trường hợp khác

Trong lượt duyệt `entrySet` của `LinkedHashMap`, `entry.getValue()` đọc giá trị đang có; `entry.setValue(newValue)` là cách được hỗ trợ để thay giá trị của ánh xạ ấy. Nó không phải một lượt get hoặc put trên map nên không dùng để ghi nhận độ mới của truy cập.

Ví dụ minh họa:

~~~java
for (Map.Entry<String, Integer> entry : cache.entrySet()) {
    entry.setValue(entry.getValue() + 1);
}
~~~

Đoạn này giả sử giá trị không null và không có sửa đổi cạnh tranh. Nó cập nhật các giá trị theo lượt duyệt hiện tại mà không chủ động đưa từng khóa xuống cuối.

Entry lấy từ góc nhìn gắn với map gốc. Không nên giữ nó để dùng tùy ý sau khi lượt duyệt kết thúc hoặc map đã bị sửa. Khi cần dữ liệu độc lập, hãy sao chép khóa và giá trị sang dạng phù hợp. [Java 17: Map.Entry](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html)

## 4. Iterator theo dõi điều gì?

### 4.1. Mô hình của OpenJDK 17

Một cách giải thích cơ chế là đặt hai bộ đếm cạnh nhau:

~~~text
map:      modCount
iterator: expectedModCount tại lúc được tạo

nếu map thay đổi cấu trúc:
    modCount có thể được tăng

khi iterator thực hiện bước có kiểm tra:
    nếu hai bộ đếm khác nhau -> phát hiện sửa đổi
~~~

Đây là mô hình diễn giải cơ chế của OpenJDK 17, không phải mã nguồn được chép lại.

Trong phiên bản này, việc chuyển một nút chưa ở cuối xuống cuối tăng `modCount`. Iterator ghi nhận giá trị kỳ vọng; đường `next` kiểm tra sự khác biệt. Xóa qua chính iterator cập nhật lại giá trị kỳ vọng của iterator đó. `hasNext` chỉ kiểm tra còn nút kế tiếp. [OpenJDK 17: LinkedHashMap.java](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/LinkedHashMap.java)

Từ đó có thể hiểu hai hiện tượng thường gây nhầm:

- `get` có thể hoàn tất bình thường; ngoại lệ chỉ xuất hiện ở bước tiếp theo của iterator.
- `hasNext()` trả về true không chứng minh iterator vẫn dùng được sau một thay đổi cấu trúc.

Không dùng thông tin về thời điểm kiểm tra để tìm cách “lách” sửa đổi. Cơ chế giải thích lỗi; hợp đồng sử dụng mới là cơ sở viết mã.

### 4.2. Get ở cuối chuỗi có thể không làm đổi liên kết

OpenJDK 17 chỉ thực hiện việc chuyển vị trí khi nút được truy cập chưa ở cuối. Truy cập khóa cuối hoặc khóa không tồn tại vì vậy có thể không làm iterator báo lỗi trong một thí nghiệm.

Điều đó không chứng minh mẫu “vừa duyệt vừa get cùng map” là hợp lệ cho mọi dữ liệu. Khi lượng dữ liệu hoặc thứ tự thay đổi, một khóa khác có thể chưa ở cuối. Một ví dụ một phần tử cũng không bao phủ trường hợp nhiều phần tử.

Lựa chọn lập trình phải chịu được dữ liệu hợp lệ nói chung. Nếu chỉ cần giá trị của entry đang duyệt, đọc từ entry là cách rõ ràng và không phụ thuộc vị trí tình cờ.

### 4.3. Iterator không phải bản sao

`keySet()`, `values()` và `entrySet()` là những góc nhìn (view) gắn với map, không phải các bản dữ liệu tách biệt. Việc tạo biến `Set<String> keys = cache.keySet()` không tạo một ảnh chụp tại thời điểm đó.

Tương tự, iterator không đóng băng chuỗi ánh xạ để ứng dụng tùy ý sửa map gốc. Nếu muốn duyệt một cấu trúc độc lập, phải tạo cấu trúc độc lập một cách rõ ràng và hiểu giới hạn sao chép của nó.

## 5. Fail-fast có ý nghĩa gì và không bảo đảm điều gì?

### 5.1. ConcurrentModificationException không đòi hỏi nhiều luồng

Tên ngoại lệ dễ khiến người học tìm một luồng thứ hai dù lỗi do chính vòng lặp:

~~~java
for (String key : cache.keySet()) {
    Integer value = cache.get(key);
    System.out.println(key + "=" + value);
}
~~~

Đây là mã minh họa có vấn đề khi `cache` giữ thứ tự truy cập. Vòng for rút gọn dùng iterator ẩn. Thân vòng lặp gọi get trên cùng map và có thể đổi chuỗi mà iterator đang đi.

Chương trình có thể chạy hoàn toàn trên một luồng. “Sửa trong lúc duyệt” ở đây là hai hoạt động chồng lên cùng khoảng đời iterator, không nhất thiết là hai bộ xử lý cùng thực thi.

### 5.2. Ngoại lệ là tín hiệu phát hiện lỗi

Fail-fast là cơ chế phát hiện một số sửa đổi không phù hợp. Nó không phải khóa, giao dịch, ảnh chụp hay hợp đồng map đồng thời.

Không viết thuật toán dạng:

~~~java
try {
    // Duyệt trong khi vẫn sửa map theo cách không phù hợp.
} catch (ConcurrentModificationException exception) {
    // Coi như mọi dữ liệu đã được xử lý an toàn.
}
~~~

Đoạn trên chỉ minh họa lối xử lý sai; không phải giải pháp.

Một phần công việc có thể đã xảy ra trước ngoại lệ. Bắt lỗi rồi chạy lại có thể lặp tác dụng phụ, gửi dữ liệu hai lần hoặc xử lý thiếu phần tử nếu thuật toán không có thiết kế riêng cho việc thử lại.

Không có ngoại lệ cũng không chứng minh đúng. Cần kiểm tra các thao tác thực tế và hợp đồng dữ liệu, không dùng sự im lặng của cơ chế phát hiện làm bằng chứng an toàn. [Java 17: chính sách fail-fast của LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html)

### 5.3. Không tiếp tục “sửa chữa” iterator cũ

Nếu đã thay đổi cấu trúc map theo cách làm lượt duyệt mất hợp lệ, không nên gọi `iterator.remove` với hy vọng nó tự đồng bộ mọi thứ. Cách xóa hợp lệ qua iterator đòi hỏi chính lượt duyệt vẫn tuân thủ quy tắc.

Khi thuật toán cần một giai đoạn sửa đổi riêng, hãy kết thúc lượt duyệt cũ, áp dụng thay đổi rồi tạo lượt duyệt mới nếu cần. Việc tạo iterator mới phải nằm ở điểm thuật toán có trạng thái rõ ràng, không phải một cách thử lại mù để né lỗi.

## 6. Chọn cách duyệt theo mục đích

### 6.1. Chỉ đọc cặp khóa–giá trị

Dùng entry đang được duyệt:

~~~java
for (Map.Entry<String, Integer> entry : cache.entrySet()) {
    System.out.println(entry.getKey() + "=" + entry.getValue());
}
~~~

Cách này tránh lượt tra cứu theo khóa và tránh việc get ghi nhận truy cập trên map. Nó không cần giữ một giả định về khóa nào đang ở cuối.

Nếu chỉ cần khóa, duyệt `keySet`. Nếu chỉ cần giá trị, duyệt `values`. Góc nhìn đúng giúp tránh làm thêm việc không cần thiết.

### 6.2. Sửa giá trị nhưng giữ nguyên thứ tự

Có thể dùng `entry.setValue` trong lượt duyệt entrySet như ở phần trước. Cần quyết định rõ đó có đúng nghiệp vụ không.

Ví dụ, tác vụ điều chỉnh giá của mọi mặt hàng có thể không được xem là một lần người dùng sử dụng mặt hàng. Giữ nguyên thứ tự truy cập là hợp lý. Ngược lại, nếu nghiệp vụ yêu cầu việc cập nhật đó phải làm mới độ gần đây, không dùng setValue chỉ để tránh ngoại lệ rồi vô tình thay đổi ngữ nghĩa. Hãy tách thao tác thành giai đoạn phù hợp.

### 6.3. Xóa trong chính lượt duyệt

Khi cần loại bỏ một số ánh xạ, dùng iterator tường minh và xóa qua chính iterator đó:

~~~java
Iterator<Map.Entry<String, Integer>> iterator =
        cache.entrySet().iterator();

while (iterator.hasNext()) {
    Map.Entry<String, Integer> entry = iterator.next();
    if (entry.getValue() < 0) {
        iterator.remove();
    }
}
~~~

Đoạn minh họa giả sử giá trị khác null và không có thao tác khác sửa map. Không gọi `cache.remove(entry.getKey())` thay cho `iterator.remove()` trong cùng lượt duyệt.

`remove` của iterator chỉ được gọi sau `next` và tối đa một lần cho mỗi lần next. Gọi trước next hoặc gọi hai lần liên tiếp là lỗi trạng thái, khác với lỗi phát hiện thay đổi cấu trúc. [Java 17: Iterator.remove](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html)

### 6.4. Ngoại lệ cho chính iterator không lan sang iterator khác

Giả sử có hai iterator cùng map. Iterator thứ nhất xóa bằng chính `remove` của nó. Lượt duyệt thứ nhất được phép tiếp tục theo quy tắc ấy; iterator thứ hai không tự được cập nhật theo.

Vì vậy, câu “tôi đã dùng iterator.remove nên mọi iterator đều an toàn” sai. Quyền sửa được gắn với chính lượt duyệt đang thực hiện thao tác, không phải giấy phép chung cho mọi lượt duyệt khác.

## 7. Nếu thật sự cần get hoặc put từng khóa thì sao?

### 7.1. Duyệt bản sao danh sách khóa

Nếu cần các lời gọi get làm mới thứ tự, có thể duyệt một danh sách khóa độc lập:

~~~java
List<String> keys = new ArrayList<>(cache.keySet());
for (String key : keys) {
    Integer value = cache.get(key);
    process(key, value);
}
~~~

Đoạn này là mẫu minh họa; `process` đại diện cho hàm xử lý do ứng dụng định nghĩa. Ví dụ xét một luồng và không có thay đổi khác trong lúc tạo danh sách.

Iterator của vòng for thuộc danh sách, không thuộc map đang đổi thứ tự. Đây là lý do mẫu tránh xung đột cấu trúc giữa chính vòng lặp đó và get trên map.

Nhưng cần hiểu kết quả:

- Danh sách là ảnh chụp các tham chiếu khóa, không phải ảnh chụp mọi giá trị.
- Get đọc giá trị của map tại lúc gọi.
- Get vẫn chủ động làm mới thứ tự map.
- Nếu có thay đổi khác, khóa trong danh sách có thể không còn trong map.
- Tạo danh sách từ map đang bị sửa cạnh tranh vẫn cần chính sách đồng bộ hóa.

Bản sao giải quyết một ranh giới cụ thể, không tự giải quyết mọi vấn đề đồng thời hoặc tính nhất quán.

### 7.2. Nếu muốn báo cáo mà không làm mới thứ tự

Đọc qua entrySet có thể đã đủ khi lượt duyệt được bảo vệ phù hợp. Nếu muốn xử lý báo cáo lâu ở ngoài phần được bảo vệ, có thể sao chép các ánh xạ vào một `LinkedHashMap` mới rồi duyệt bản sao.

Constructor từ map tạo một map thứ tự chèn chứa các ánh xạ theo thứ tự gặp ở nguồn. Bản sao không tự trở thành một access-order map chỉ vì nguồn dùng chế độ đó. Trong tình huống này, nó giúp giữ thứ tự hiện có để đọc độc lập.

Cần sao chép khi nguồn ở trạng thái ổn định; nếu có nhiều luồng, thực hiện bước sao chép trong chính sách đồng bộ hóa của ứng dụng. Khóa và giá trị vẫn là các tham chiếu được dùng lại; đối tượng có thể thay đổi bên trong không tự được sao chép sâu.

### 7.3. Sao chép danh sách entry chưa chắc tách dữ liệu

`new ArrayList<>(cache.entrySet())` tạo một danh sách mới, nhưng các phần tử có thể vẫn là entry gắn với map. Đừng coi đó là bản ghi độc lập chỉ vì đối tượng List mới được tạo.

Khi cần các cặp độc lập, có thể tạo từng `AbstractMap.SimpleImmutableEntry` từ khóa và giá trị. Bản ghi cặp độc lập vẫn không sao chép sâu đối tượng khóa hoặc giá trị.

Điều cần chọn là mức độ tách biệt thực sự cần: tách cấu trúc duyệt, tách cặp ánh xạ hay tách toàn bộ dữ liệu có thể thay đổi. Ba yêu cầu này không giống nhau.

## 8. Hàm gọi lại, forEach và stream không tự loại bỏ vấn đề

Đổi cú pháp vòng lặp không thay đổi bản chất nếu phần xử lý vẫn gọi ngược vào map:

~~~java
cache.forEach((key, value) -> {
    cache.get(key);
});
~~~

Đây là mẫu minh họa có vấn đề trên access-order map. `forEach` đã cung cấp value; gọi get không cần thiết và có thể thay đổi thứ tự trong chính quá trình duyệt.

Một lời gọi gián tiếp cũng có tác động tương tự. Ví dụ, hàm tạo báo cáo nhận key rồi tự gọi dịch vụ tra cứu cùng map. Thân vòng lặp nhìn ngắn và “chỉ ghi log”, nhưng chuỗi lời gọi có thể vẫn chứa get.

Với stream, các hàm xử lý phải tuân thủ yêu cầu không can thiệp nguồn theo hợp đồng của pipeline. Chuyển từ for sang `stream().forEach(...)` không cho phép tùy ý thay đổi cấu trúc nguồn. Đặc biệt, `parallelStream` không biến LinkedHashMap thành map đồng thời. [Java 17: yêu cầu không can thiệp của stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html)

Các hàm gọi lại (callback) của `compute` và `merge` cũng không nên tự sửa lại cùng map trong quá trình tính toán. Trên access-order map, cả lời gọi tưởng như chỉ tra cứu cũng cần được xét vì nó có thể sửa thứ tự. Hãy tính từ tham số callback đã nhận hoặc dữ liệu bên ngoài được tổ chức phù hợp. [Java 17: Map.compute và Map.merge](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html)

## 9. Đồng bộ hóa phải bao phủ cả thứ tự truy cập

### 9.1. Không coi get là thao tác giữ nguyên cấu trúc

`LinkedHashMap` không tự đồng bộ hóa. Nếu thiết kế có nhiều luồng, cần tính cả những lời gọi get có thể đổi thứ tự vào nhóm thao tác cần bảo vệ.

Ví dụ, một thiết kế dùng khóa đọc–ghi rồi cho phép nhiều get trên access-order map cùng giữ “khóa đọc” có thể dựa trên giả định sai: các lời gọi này không nhất thiết chỉ đọc cấu trúc. Cần thiết kế quy tắc khóa theo trạng thái thực sự bị sửa.

### 9.2. SynchronizedMap không khóa trọn vòng lặp tự động

Với map bọc bằng `Collections.synchronizedMap`, tài liệu yêu cầu đồng bộ hóa trên chính map trả về khi duyệt các góc nhìn. Mọi truy cập cần đi qua cùng cơ chế bảo vệ, tránh giữ tham chiếu map gốc rồi truy cập vòng ngoài. [Java 17: Collections.synchronizedMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#synchronizedMap(java.util.Map))

Ví dụ minh họa, giả sử các import và việc nạp dữ liệu được thực hiện trong chương trình:

~~~java
Map<String, Integer> shared =
        Collections.synchronizedMap(
                new LinkedHashMap<String, Integer>(16, 0.75f, true));

synchronized (shared) {
    for (Map.Entry<String, Integer> entry : shared.entrySet()) {
        System.out.println(entry.getKey() + "=" + entry.getValue());
    }
}
~~~

Khóa là `shared`, không phải đối tượng `shared.entrySet()`. Đoạn duyệt lấy giá trị trực tiếp từ entry.

### 9.3. Có khóa vẫn có thể tự làm iterator mất hợp lệ

Khóa giúp ngăn những truy cập cạnh tranh tuân thủ cùng khóa. Nó không biến việc đổi thứ tự trong chính thân vòng lặp thành thao tác hợp lệ với iterator cũ.

Nếu ở trong khối synchronized mà vẫn gọi `shared.get(key)` khi đang duyệt chính access-order map đó, cùng luồng vẫn có thể làm đổi chuỗi. Do đó phải xử lý hai vấn đề riêng:

1. Cách các luồng truy cập dữ liệu.
2. Cách thuật toán của một lượt duyệt sửa chính dữ liệu đang duyệt.

Một biện pháp giải quyết vấn đề thứ nhất không tự chứng minh vấn đề thứ hai đã được giải quyết.

## 10. Chương trình Java đầy đủ

Lưu toàn bộ mã sau vào `AccessOrderIteratorDemo.java`. Chương trình dùng các map độc lập cho từng tình huống để kết quả của phần trước không làm nhiễu phần sau.

Các phép kiểm tra khẳng định thứ tự, tổng và dữ liệu của những đường dùng hợp lệ. Hàm `observedCme` chỉ ghi nhận ngoại lệ quan sát được trong các tình huống cố ý làm iterator cũ không còn phù hợp. Nó không phải công cụ quyết định tính đúng cho ứng dụng.

~~~java
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class AccessOrderIteratorDemo {
    private static LinkedHashMap<String, Integer> sample(boolean accessOrder) {
        LinkedHashMap<String, Integer> map =
                new LinkedHashMap<>(16, 0.75f, accessOrder);
        map.put("A", 1);
        map.put("B", 2);
        map.put("C", 3);
        return map;
    }

    private static List<String> keys(Map<String, Integer> map) {
        return new ArrayList<>(map.keySet());
    }

    private static void requireOrder(Map<String, Integer> map,
                                     List<String> expected) {
        if (!keys(map).equals(expected)) {
            throw new AssertionError("Unexpected order");
        }
    }

    // Observation only: application correctness must not depend on CME.
    private static boolean observedCme(Iterator<?> iterator) {
        try {
            iterator.next();
            return false;
        } catch (ConcurrentModificationException exception) {
            return true;
        }
    }

    public static void main(String[] args) {
        LinkedHashMap<String, Integer> access = sample(true);
        Iterator<String> old = access.keySet().iterator();
        access.get("A");
        requireOrder(access, List.of("B", "C", "A"));
        System.out.println("access/size=" + access.size());
        System.out.println("access/order=" + keys(access));
        System.out.println("access/oldIteratorCME=" + observedCme(old));

        LinkedHashMap<String, Integer> insertion = sample(false);
        Iterator<String> insertionIterator = insertion.keySet().iterator();
        insertion.put("A", 10);
        requireOrder(insertion, List.of("A", "B", "C"));
        System.out.println("insertion/afterPut=" + insertion);
        System.out.println("insertion/next=" + insertionIterator.next());

        LinkedHashMap<String, Integer> views = sample(true);
        Iterator<String> viewIterator = views.keySet().iterator();
        boolean containsA = views.containsKey("A");
        int sum = 0;
        for (Map.Entry<String, Integer> entry : views.entrySet()) {
            sum += entry.getValue();
        }
        requireOrder(views, List.of("A", "B", "C"));
        if (!containsA || sum != 6) {
            throw new AssertionError("Unexpected view result");
        }
        System.out.println("views/containsA=" + containsA + ", sum=" + sum);
        System.out.println("views/order=" + keys(views));
        System.out.println("views/next=" + viewIterator.next());

        LinkedHashMap<String, Integer> updated = sample(true);
        for (Map.Entry<String, Integer> entry : updated.entrySet()) {
            entry.setValue(entry.getValue() * 10);
        }
        requireOrder(updated, List.of("A", "B", "C"));
        System.out.println("setValue/map=" + updated);

        LinkedHashMap<String, Integer> removed = sample(true);
        List<String> visited = new ArrayList<>();
        Iterator<Map.Entry<String, Integer>> removalIterator =
                removed.entrySet().iterator();
        while (removalIterator.hasNext()) {
            Map.Entry<String, Integer> entry = removalIterator.next();
            visited.add(entry.getKey());
            if (entry.getValue() == 2) {
                removalIterator.remove();
            }
        }
        requireOrder(removed, List.of("A", "C"));
        System.out.println("remove/visited=" + visited);
        System.out.println("remove/map=" + removed);

        LinkedHashMap<String, Integer> two = sample(true);
        Iterator<String> first = two.keySet().iterator();
        Iterator<String> second = two.keySet().iterator();
        first.next();
        first.remove();
        requireOrder(two, List.of("B", "C"));
        System.out.println("twoIterators/otherCME=" + observedCme(second));

        LinkedHashMap<String, Integer> snapshotMap = sample(true);
        List<String> snapshot = keys(snapshotMap);
        List<List<String>> orders = new ArrayList<>();
        for (String key : snapshot) {
            snapshotMap.get(key);
            orders.add(keys(snapshotMap));
        }
        requireOrder(snapshotMap, List.of("A", "B", "C"));
        System.out.println("snapshot/keys=" + snapshot);
        System.out.println("snapshot/orders=" + orders);

        LinkedHashMap<String, Integer> sameSize = sample(true);
        Iterator<String> beforeReplacement = sameSize.keySet().iterator();
        sameSize.remove("A");
        sameSize.put("D", 4);
        requireOrder(sameSize, List.of("B", "C", "D"));
        System.out.println("sameSize/size=" + sameSize.size()
                + ", order=" + keys(sameSize));
        System.out.println("sameSize/oldIteratorCME="
                + observedCme(beforeReplacement));

        LinkedHashMap<String, Integer> nullable = sample(true);
        for (Map.Entry<String, Integer> entry : nullable.entrySet()) {
            if (entry.getKey().equals("B")) {
                entry.setValue(null);
            }
        }
        requireOrder(nullable, List.of("A", "B", "C"));
        Integer value = nullable.get("B");
        requireOrder(nullable, List.of("A", "C", "B"));
        System.out.println("nullAccess/value=" + value
                + ", order=" + keys(nullable));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 AccessOrderIteratorDemo.java
java AccessOrderIteratorDemo
~~~

Stdout của lần chạy kiểm chứng:

~~~text
access/size=3
access/order=[B, C, A]
access/oldIteratorCME=true
insertion/afterPut={A=10, B=2, C=3}
insertion/next=A
views/containsA=true, sum=6
views/order=[A, B, C]
views/next=A
setValue/map={A=10, B=20, C=30}
remove/visited=[A, B, C]
remove/map={A=1, C=3}
twoIterators/otherCME=true
snapshot/keys=[A, B, C]
snapshot/orders=[[B, C, A], [C, A, B], [A, B, C]]
sameSize/size=3, order=[B, C, D]
sameSize/oldIteratorCME=true
nullAccess/value=null, order=[A, C, B]
~~~

Mã đã được biên dịch với `--release 17` và chạy thành công. Tùy chọn release xác định mức API và mã đích tương thích; nó không khẳng định JVM thực thi là đúng bản JDK 17.

Các dòng `CME=true` là kết quả quan sát trên môi trường đã chạy, phù hợp cơ chế OpenJDK được giải thích. Không biến kết quả đó thành quy tắc “mọi sửa đổi sai luôn ném ngoại lệ đúng tại vị trí này”.

## 11. Đọc kết quả theo câu hỏi mà từng phần trả lời

### 11.1. Access: size không đổi nhưng đường duyệt đổi

Ba dòng đầu cho thấy size vẫn bằng ba, thứ tự đã thành B, C, A và lần dùng iterator cũ ghi nhận CME.

Không có luồng phụ nào trong chương trình. Không có thay đổi giá trị. Tác nhân là lần get trên chế độ thứ tự truy cập.

### 11.2. Insertion: thay giá trị một khóa tồn tại

Phần insertion tạo iterator trước khi `put("A", 10)`. Map ở chế độ thứ tự chèn, nên cập nhật giá trị không đổi thành phần ánh xạ hoặc thứ tự chèn. Iterator tiếp tục trả về A trong tình huống đó.

Không suy ra put luôn an toàn khi duyệt: thêm một khóa mới là trường hợp khác, và access-order cũng có quy tắc khác.

### 11.3. Views và setValue: đọc hoặc sửa đúng chỗ

`containsKey("A")` cùng lượt duyệt entrySet tính tổng không chuyển A xuống cuối. Iterator được tạo trước đó vẫn có thể lấy A.

Ở phần setValue, chương trình sửa giá trị từng entry thành mười lần giá trị cũ. Thứ tự vẫn là A, B, C. Nó không dùng put để cập nhật từng khóa và không dùng get để đọc giá trị.

### 11.4. Remove: đúng iterator và iterator khác

Lượt xóa đi qua A, B, C; chỉ B bị loại qua `removalIterator.remove()`. Kết quả còn A và C.

Trong tình huống có hai iterator, iterator thứ nhất xóa hợp lệ qua remove của nó. Iterator thứ hai ghi nhận CME khi được dùng tiếp. Điều đó minh họa giới hạn của ngoại lệ dành cho chính iterator.

### 11.5. Snapshot: thứ tự cuối có thể quay về ban đầu

Danh sách khóa độc lập giữ A, B, C. Vòng lặp đi trên danh sách nên có thể get từng khóa ở map mà không sửa chính cấu trúc đang được iterator danh sách duyệt.

Các ảnh chụp sau từng get lần lượt là B, C, A; C, A, B; A, B, C. Thứ tự cuối giống ban đầu nhưng có lịch sử thay đổi. Không được dùng sự trùng khớp cuối cùng để hợp lệ hóa một iterator map cũ.

### 11.6. SameSize và nullAccess

Xóa A rồi thêm D giữ size bằng ba, nhưng iterator cũ vẫn bị ảnh hưởng. Bộ đếm kích thước không thay thế việc theo dõi thay đổi.

Với nullAccess, giá trị B được đặt thành null qua entry trước khi get. Thứ tự trước get được kiểm tra là A, B, C. Sau get, kết quả trả về null và thứ tự thành A, C, B: một giá trị null không làm lượt truy cập mất tác động lên thứ tự.

## 12. Cách tìm lỗi trong mã thực tế

Khi gặp lỗi quanh iterator, hãy ghi lại một dòng thời gian thay vì chỉ nhìn dòng ném ngoại lệ:

| Mốc | Thông tin cần xác định |
|---|---|
| Tạo map | Chế độ thứ tự chèn hay truy cập? |
| Tạo iterator | Tạo trước hay sau thao tác nghi ngờ? |
| Thân vòng lặp | Có get, put, remove hoặc hàm gọi gián tiếp vào cùng map không? |
| Góc nhìn | Đây là view đang sống hay cấu trúc sao chép độc lập? |
| Phần cập nhật | Qua chính iterator, entry hay map? |
| Đồng thời | Mọi truy cập có tuân thủ cùng chính sách khóa không? |
| Xử lý lỗi | Đã có tác dụng phụ nào trước khi ngoại lệ xuất hiện? |

Nếu lỗi nằm ở `iterator.next()`, tác nhân có thể nằm ở lời gọi trước đó. Đọc cả chuỗi hàm trợ giúp, callback và hàm theo dõi trạng thái.

Không chốt nguyên nhân chỉ bằng việc đổi dữ liệu làm lỗi tạm biến mất. Một khóa tình cờ ở cuối hoặc một map chỉ có một phần tử có thể che khuất việc gọi get làm đổi thứ tự trong trường hợp khác.

## 13. Thực hành và lời giải

### Bài 1. Đọc dòng thời gian

Map access-order có thứ tự A, B, C. Tạo iterator rồi gọi get(B). Thứ tự mới là gì? Vì sao size không chứng minh iterator cũ vẫn hợp lệ?

**Lời giải:** Thứ tự thành A, C, B. Số ánh xạ vẫn là ba nhưng chuỗi đã đổi, thuộc trạng thái cấu trúc cần xét. Iterator cũ được tạo trước thay đổi; size chỉ đếm số ánh xạ.

### Bài 2. Có cần luồng thứ hai không?

Một chương trình một luồng duyệt keySet và gọi get từng khóa trên cùng map. Vì sao vẫn có thể có CME?

**Lời giải:** For rút gọn dùng iterator. Get ở chế độ truy cập có thể đổi chuỗi mà iterator đang dùng. Xung đột giữa duyệt và sửa có thể do cùng luồng tạo ra; tên ngoại lệ không đòi hỏi có luồng thứ hai.

### Bài 3. Sửa cách đọc

Bạn chỉ cần in cặp khóa–giá trị nhưng đang duyệt keySet rồi get. Hãy sửa và nêu hai lợi ích.

**Lời giải:** Duyệt entrySet, dùng entry.getKey và entry.getValue. Tránh lượt tra cứu dư và tránh get làm mới thứ tự trên map. Điều đó không tự giải quyết sửa đổi từ luồng khác.

### Bài 4. Cập nhật có đúng nghiệp vụ không?

Một tác vụ tăng giá trị mọi entry nhưng không được làm thay đổi độ mới truy cập. Dùng entry.setValue có phù hợp không? Nếu việc cập nhật phải làm mới độ gần đây thì sao?

**Lời giải:** SetValue trong lượt duyệt entrySet phù hợp với yêu cầu giữ thứ tự, khi lượt duyệt được bảo vệ đúng. Nếu cập nhật phải làm mới độ gần đây, cần tổ chức giai đoạn riêng hoặc duyệt khóa độc lập rồi thực hiện thao tác mang ngữ nghĩa truy cập; không bỏ tác động nghiệp vụ chỉ để né ngoại lệ.

### Bài 5. Xóa sai chỗ

Một vòng while dùng iterator nhưng xóa bằng cache.remove(key). Vì sao đổi sang iterator.remove có ý nghĩa? Quy tắc gọi remove là gì?

**Lời giải:** Xóa qua chính iterator cho phép lượt duyệt đó duy trì trạng thái kỳ vọng phù hợp. Remove được gọi sau next, tối đa một lần cho mỗi next. Nó không cho phép thêm sửa đổi khác tùy ý và không làm iterator thứ hai tự hợp lệ.

### Bài 6. HasNext trả về true

Sau một lần get làm đổi thứ tự, hasNext vẫn trả về true trong một thí nghiệm OpenJDK. Có nên tiếp tục vì “iterator đã xác nhận” không?

**Lời giải:** Không. Trong cơ chế đã giải thích, hasNext chỉ thấy còn nút kế tiếp; bước next mới kiểm tra bộ đếm thay đổi. Quan trọng hơn, thuật toán phải tuân thủ quy tắc duyệt, không dựa vào thời điểm phát hiện của một phương thức.

### Bài 7. Không có ngoại lệ

Một bài thử chỉ có một khóa, vừa duyệt vừa get mà không có ngoại lệ. Có đủ để giữ mẫu đó trong hệ thống nhiều khóa không?

**Lời giải:** Không. Khóa duy nhất đã ở cuối; cách triển khai có thể không phải chuyển liên kết. Dữ liệu khác có thể gây thay đổi. Sự im lặng của fail-fast không phải bằng chứng mẫu dùng hợp lệ nói chung.

### Bài 8. Ảnh chụp khóa

Đổi sang new ArrayList của keySet giúp tránh điều gì? Nó có tạo ảnh chụp mọi giá trị và bảo đảm đồng thời không?

**Lời giải:** Iterator của vòng lặp đi trên danh sách độc lập nên get trên map không sửa chính cấu trúc danh sách ấy. Giá trị vẫn được đọc ở map tại thời điểm get; khóa hoặc giá trị có thể đã đổi nếu có hoạt động khác. Bước sao chép và truy cập vẫn cần chính sách đồng thời phù hợp.

### Bài 9. Khóa đầy đủ nhưng vẫn sai

Ứng dụng giữ synchronized trên map bọc suốt vòng lặp, nhưng trong thân lại get trên chính access-order map. Vì sao khóa chưa đủ?

**Lời giải:** Khóa ngăn hoạt động cạnh tranh tuân thủ cùng khóa. Nó không ngăn chính luồng đang giữ khóa đổi thứ tự map và làm lượt duyệt của mình mất hợp lệ. Cần sửa cả thuật toán của lượt duyệt, chẳng hạn đọc value từ entry.

### Bài 10. Trạng thái cuối giống ban đầu

Tạo iterator trên A, B, C, rồi get A, get B, get C. Thứ tự cuối lại là A, B, C. Có thể dùng iterator cũ như chưa có gì xảy ra không?

**Lời giải:** Không. Có nhiều lần chuyển thứ tự trong khoảng ấy. Hợp đồng lượt duyệt xét sửa đổi trong quá trình, không chỉ so sánh hai trạng thái đầu và cuối.

## 14. Câu hỏi cần trả lời trước khi viết vòng lặp

Hãy xác định rõ dữ liệu đang duyệt là view hay bản sao, chế độ thứ tự nào đang dùng và thao tác trong thân có thể đổi những loại trạng thái nào. Nếu chỉ đọc cặp dữ liệu, dùng entry. Nếu sửa giá trị mà giữ thứ tự, cân nhắc setValue trong lượt duyệt. Nếu xóa, dùng đúng iterator của lượt duyệt. Nếu cần làm mới truy cập từng khóa, tách cấu trúc duyệt hoặc chia giai đoạn có chủ đích.

Tính đúng đến từ cách tổ chức thao tác và chính sách đồng thời phù hợp. Fail-fast giúp phát hiện lỗi; nó không thay thế những quyết định ấy.
