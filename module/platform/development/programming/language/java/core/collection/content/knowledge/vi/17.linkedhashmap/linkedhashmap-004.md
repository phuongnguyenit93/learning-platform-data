# LinkedHashMap: chi phí duyệt, lưu trữ và lựa chọn so với HashMap

Một map có thể phục vụ hai công việc khác nhau: tìm giá trị theo khóa và lần lượt xử lý toàn bộ các ánh xạ. Khi chọn giữa `HashMap` và `LinkedHashMap`, cần xét cả hai công việc, cùng yêu cầu thứ tự và giới hạn bộ nhớ.

Ví dụ, bộ đếm sản phẩm chỉ dùng để trả lời “mã này xuất hiện bao nhiêu lần?” có thể không cần thứ tự. Báo cáo phải xuất các mã theo lần đầu chúng xuất hiện lại có một yêu cầu khác: thứ tự là một phần của kết quả. `LinkedHashMap` chế độ mặc định diễn đạt được yêu cầu đó trực tiếp.

Sau bài này, bạn cần giải thích được vì sao duyệt `LinkedHashMap` phụ thuộc số ánh xạ, phần lưu trữ nào được thêm vào, và khi nào những đặc điểm đó đáng để lựa chọn thay cho `HashMap`. Không nên biến một dòng Big O thành lời hứa về tốc độ trên mọi dữ liệu.

Bài dùng API Java 17. Những chi tiết từ mã nguồn OpenJDK 17 được đánh dấu là cách triển khai cụ thể, không phải yêu cầu chung cho mọi JVM.

## 1. Mô hình cần nhớ: bảng băm và chuỗi thứ tự

### 1.1. Bảng băm phục vụ tra cứu

`HashMap` dùng cấu trúc bảng băm để tìm một ánh xạ từ khóa. `LinkedHashMap` vẫn có nền tảng ấy; nó không thay việc tra cứu bằng cách đi tuần tự từ phần tử đầu đến cuối.

Vì thế, chất lượng `hashCode`, sự nhất quán với `equals` và tính ổn định của khóa vẫn quan trọng. Đổi sang `LinkedHashMap` không sửa một khóa có quy tắc bằng nhau sai, cũng không làm mọi phân bố băm có thời gian tra cứu như nhau.

### 1.2. Chuỗi liên kết phục vụ thứ tự duyệt

`LinkedHashMap` duy trì thêm chuỗi liên kết hai chiều đi qua các ánh xạ. Có thể nhìn cùng một map theo hai hướng:

~~~text
Đường tìm theo khóa:
khóa -> giá trị băm -> vị trí trong bảng -> ánh xạ phù hợp

Đường duyệt theo thứ tự của LinkedHashMap:
đầu -> ánh xạ A <-> ánh xạ B <-> ánh xạ C -> cuối
~~~

Đây là sơ đồ khái niệm. Các ánh xạ được truy cập qua bảng và qua chuỗi không phải hai bản sao đầy đủ, độc lập của mọi khóa và giá trị. Thông tin bổ sung là thông tin giúp giữ và duy trì quan hệ thứ tự.

Chế độ mặc định giữ thứ tự chèn. Gán lại giá trị của khóa đang tồn tại không đưa khóa đó xuống cuối. Xóa một khóa rồi thêm lại là lần chèn mới nên vị trí của nó trở thành cuối chuỗi.

Nếu tạo bằng constructor có `accessOrder=true`, chuỗi giữ thứ tự truy cập theo những thao tác được API quy định. Một `get` thành công có thể đổi vị trí. Các thao tác trên góc nhìn tập hợp không tự tạo lượt truy cập kiểu này. [Java 17: LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html)

### 1.3. Có thứ tự không có nghĩa được sắp xếp

Chèn `30, 10, 20` vào `LinkedHashMap` mặc định cho thứ tự duyệt `30, 10, 20`. Nó không tự sắp thành `10, 20, 30`.

Trước khi chọn cấu trúc, hãy gọi đúng tên yêu cầu:

| Yêu cầu | Ý nghĩa |
|---|---|
| Theo lần đầu xuất hiện | Thứ tự chèn có thể đáp ứng |
| Theo lần truy cập gần nhất | Có thể cần chế độ thứ tự truy cập |
| Theo khóa tăng dần | Cần thứ tự khóa, chẳng hạn TreeMap hoặc bước sắp xếp riêng |
| Không yêu cầu thứ tự | Có thể bắt đầu với HashMap |

Đặt tên yêu cầu trước giúp tránh trả chi phí để giữ một thứ tự mà ứng dụng không dùng, hoặc chọn một cấu trúc có thứ tự nhưng sai loại thứ tự.

## 2. Hai đại lượng quyết định cách đọc độ phức tạp

Gọi:

- `N` là số ánh xạ hiện có, tức `map.size()`.
- `C` là số vị trí của bảng băm trong cách triển khai đang xét.
- `M` là số lần ứng dụng duyệt toàn bộ map trong giai đoạn phân tích.

`N` và `C` không phải cùng một số. Một map có ít ánh xạ vẫn có thể gắn với bảng lớn, chẳng hạn do yêu cầu sức chứa ban đầu lớn. Kích thước dữ liệu hiện tại không đủ để mô tả mọi chi phí của cấu trúc bảng.

API công khai của `HashMap` không có phương thức trả về sức chứa mảng nội bộ. Tham số constructor là yêu cầu khởi tạo; không nên dùng riêng con số truyền vào để khẳng định đã quan sát đúng số vị trí đang được cấp phát. Cách làm tròn và thời điểm cấp phát thuộc cách triển khai.

Tài liệu Java 17 mô tả chi phí duyệt các góc nhìn tập hợp của `HashMap` tỷ lệ với sức chứa cộng kích thước. Với `LinkedHashMap`, chi phí này tỷ lệ với kích thước, bất kể sức chứa. Đây là cơ sở của hai mô hình:

~~~text
Duyệt toàn bộ HashMap:        O(C + N)
Duyệt toàn bộ LinkedHashMap:  O(N)
~~~

[Java 17: HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html), [Java 17: LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html)

Đó là mô hình tăng trưởng, không phải công thức thời gian tính bằng nano giây. Nó không nói mỗi vị trí bảng trống và mỗi ánh xạ tốn đúng một đơn vị công việc.

## 3. Vì sao LinkedHashMap có chi phí duyệt O(N)?

### 3.1. HashMap chịu ảnh hưởng của bảng trống

Để tìm hết ánh xạ, bộ duyệt `HashMap` phải đi qua cấu trúc tổ chức dữ liệu của bảng. Những vị trí không có dữ liệu ảnh hưởng việc tìm vị trí có ánh xạ tiếp theo. Bởi vậy, mô hình chứa cả `C` và `N`.

Khi bảng được giữ tương xứng với dữ liệu, có thể xem `C = Θ(N)`. Khi ấy `O(C + N)` cũng là `O(N)` theo N. Vì vậy, không có mâu thuẫn giữa câu “HashMap duyệt tuyến tính trong trường hợp sức chứa tương xứng” và công thức đầy đủ `O(C + N)`.

Nếu bảng rất thưa, việc bỏ `C` khỏi phân tích lại có thể bỏ sót yếu tố đáng kể. Hai map cùng `size()` chưa chắc có cùng mức tác động từ việc tìm qua bảng.

### 3.2. LinkedHashMap đi theo chuỗi ánh xạ

Bộ duyệt `LinkedHashMap` có thể đi từ ánh xạ đầu đến ánh xạ cuối qua liên kết. Nó không cần tìm ánh xạ tiếp theo bằng cách quét các vị trí bảng trống. Số ánh xạ trên đường đi là N.

Điều này lý giải vì sao sức chứa quá lớn ít gây bất lợi cho riêng đường duyệt hơn so với `HashMap`. Nhưng bộ duyệt vẫn đọc các đối tượng và lần theo tham chiếu. Bố trí đối tượng, bộ nhớ đệm của CPU, JIT và công việc trong thân vòng lặp vẫn ảnh hưởng thời gian thực tế.

`O(N)` không có nghĩa mỗi map có N ánh xạ luôn mất đúng cùng một thời gian duyệt trên mọi máy hoặc ở mọi thời điểm.

### 3.3. Big O không cho tỷ lệ nhanh chậm

Giả sử một mô hình có `N = 100` và `C = 1.000.000`. `C + N` cho thấy việc quét bảng có thể lớn hơn nhiều so với lượng dữ liệu cần xử lý. Chuỗi của `LinkedHashMap` loại bỏ thành phần quét các vị trí trống đó khỏi đường duyệt.

Tuy nhiên, không thể nói nó nhanh hơn đúng `(1.000.000 + 100) / 100 = 10.001` lần. Hai loại bước không nhất thiết có cùng chi phí; thuật toán và môi trường thực thi còn nhiều khác biệt.

Nếu có M lượt duyệt, phần mô hình là `M × (C + N)` hoặc `M × N`. Công thức giúp nhận ra tải công việc nhạy với duyệt, nhưng chưa tính đầy đủ xây dựng map, cập nhật, cấp phát, thu gom rác và xử lý từng phần tử.

| Bối cảnh | Điều có thể kết luận |
|---|---|
| C cùng bậc với N | Cả hai đường duyệt cùng bậc tuyến tính theo N |
| C lớn hơn N rất nhiều | LinkedHashMap có lợi thế cấu trúc ở việc không quét bảng trống |
| Thân vòng lặp xử lý rất nặng | Chênh lệch duyệt cấu trúc có thể chỉ là phần nhỏ của tổng thời gian |
| Cần con số tốc độ cụ thể | Phải đo trên tải công việc và môi trường đại diện |

Một vòng lặp cộng số nguyên và một vòng lặp gọi dịch vụ mạng cho mỗi ánh xạ không có cùng tỷ trọng chi phí cấu trúc dữ liệu. Cần đặt lựa chọn map trong toàn bộ tác vụ.

## 4. Duy trì thứ tự cũng có công việc phải làm

Các thao tác cơ bản như `get`, `put` và `remove` của `LinkedHashMap` vẫn dựa trên bảng băm. Tài liệu nêu hiệu năng thời gian hằng số khi giá trị băm phân bố tốt, đồng thời mô tả việc duy trì liên kết thường làm các thao tác này tốn thêm công việc so với `HashMap`. Ngoại lệ đáng chú ý là lợi thế ở đường duyệt. [Java 17: LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html)

Cần phân biệt:

- Thời gian hằng số kỳ vọng khi phân bố băm tốt với cam kết cho mọi dữ liệu.
- Chi phí trung bình phân bổ qua nhiều lần chèn với một lần chèn phải mở rộng bảng.
- Cùng bậc Big O với cùng thời gian thực tế.

Thêm vài bước nối hoặc tháo liên kết có thể không đổi bậc độ phức tạp, nhưng vẫn thêm công việc.

| Công việc | HashMap | LinkedHashMap |
|---|---|---|
| Tìm theo khóa | Bảng băm | Vẫn là bảng băm |
| Thêm ánh xạ mới | Cập nhật cấu trúc băm, có thể mở rộng | Thêm việc nối vào chuỗi thứ tự |
| Xóa ánh xạ | Loại khỏi cấu trúc băm | Thêm việc tháo khỏi chuỗi thứ tự |
| Duyệt toàn bộ góc nhìn | O(C + N) | O(N) |
| Thứ tự | Không được cam kết | Theo chế độ đã chọn |
| Trạng thái giữ thứ tự | Không có chuỗi thứ tự như LinkedHashMap | Có thông tin liên kết và trạng thái bổ sung |

Ở chế độ thứ tự truy cập, một `get` thành công có thể chuyển ánh xạ xuống cuối. Nếu ánh xạ đã ở cuối, không cần chuyển vị trí; nếu chưa, cấu trúc liên kết có thể phải thay đổi.

Điều này không đủ để thiết kế một bộ đệm có giới hạn. Chủ đề ở đây là chi phí và lựa chọn: chỉ chọn `accessOrder=true` khi cần đúng ngữ nghĩa đó, và nhớ rằng “đọc theo khóa” có thể gây công việc duy trì thứ tự.

## 5. Chi phí lưu trữ: cùng bậc không có nghĩa cùng số byte

### 5.1. Tách cấu trúc map khỏi dữ liệu được tham chiếu

Một mô hình lưu trữ thô gồm:

~~~text
đối tượng map
+ mảng tham chiếu của bảng băm
+ các đối tượng biểu diễn ánh xạ
+ các đối tượng khóa và giá trị được tham chiếu tới
~~~

Nếu tạm tách kích thước khóa và giá trị, phần cấu trúc của cả hai map có thể mô hình hóa theo `O(C + N)`. `LinkedHashMap` thêm thông tin giữ chuỗi nên có thể tốn hơn về hệ số lưu trữ dù cùng bậc tăng trưởng.

Với hàng triệu ánh xạ nhỏ, phần cấu trúc bổ sung có thể đáng kể. Nếu mỗi giá trị tham chiếu một đồ thị đối tượng rất lớn, tỷ lệ của phần cấu trúc trên tổng dung lượng có thể nhỏ hơn. Phải nói rõ đang tính riêng cấu trúc hay toàn bộ dữ liệu còn được giữ sống.

### 5.2. Có thể thấy gì trong OpenJDK 17?

Trong mã nguồn OpenJDK 17, nút thông thường `LinkedHashMap.Entry` mở rộng `HashMap.Node` và có thêm `before`, `after`. Map duy trì cả đầu và cuối chuỗi. Các trường này giải thích cụ thể việc giữ thứ tự cần thêm thông tin. [OpenJDK 17: LinkedHashMap.java](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/LinkedHashMap.java)

Không được biến quan sát đó thành một số byte cố định cho mọi ánh xạ trên mọi JVM. Tiêu đề đối tượng, độ rộng tham chiếu, nén tham chiếu, căn chỉnh và dạng nút đều có thể ảnh hưởng.

Ngay trong OpenJDK 17, các nút dạng cây của `HashMap` có quan hệ kế thừa với `LinkedHashMap.Entry`. Vì vậy, câu “mọi nút LinkedHashMap luôn chỉ lớn hơn mọi nút HashMap đúng hai tham chiếu” quá rộng. Có thể mô tả hai tham chiếu bổ sung khi so sánh các nút thông thường của cách triển khai này, rồi đo môi trường cụ thể nếu cần số byte. [OpenJDK 17: HashMap.java](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/HashMap.java)

### 5.3. Không quét C khi duyệt không có nghĩa không lưu C

`LinkedHashMap` vẫn dùng bảng băm để tra cứu. Vì vậy, yêu cầu sức chứa quá lớn vẫn có thể làm tăng dung lượng mảng và ảnh hưởng hệ thống bộ nhớ, dù đường duyệt không đi qua các vị trí trống đó.

Đây là hai câu hỏi độc lập:

1. Cần đi qua những thành phần nào để duyệt toàn bộ?
2. Cần giữ những thành phần nào trong bộ nhớ?

Câu trả lời của câu thứ nhất không được dùng thay cho câu thứ hai.

Hệ số tải và lượng ánh xạ dự kiến giúp lập kế hoạch sức chứa. Trong mô hình ngưỡng mở rộng, để giữ khoảng N ánh xạ với hệ số tải f, có thể xét mức khoảng `N / f` trước quy tắc làm tròn và cấp phát. Đây không phải công thức API bảo đảm chính xác kích thước mảng.

Đừng cho rằng constructor nhận 100.000 là chắc chắn chứa 100.000 ánh xạ mà không mở rộng. Cũng đừng đặt một con số cực lớn chỉ để tránh suy nghĩ về dữ liệu dự kiến.

### 5.4. Sao chép có thể làm tăng bộ nhớ tạm thời

Tạo `LinkedHashMap` từ map có sẵn tạo cấu trúc map mới chứa các ánh xạ tương ứng. Việc sao chép ánh xạ dùng các tham chiếu khóa và giá trị; nó không tự sao chép sâu toàn bộ đối tượng.

Khi hai map cùng tồn tại, ứng dụng giữ cả hai cấu trúc. Nếu chuyển đổi map lớn chỉ để xuất một lần, hãy tính cả cấp phát và đỉnh dùng bộ nhớ, không chỉ thời gian vòng lặp ở cuối.

Sao chép `HashMap` sang `LinkedHashMap` cũng không khôi phục lịch sử chèn đã không được lưu. Map mới giữ trình tự nó gặp khi duyệt nguồn. Nếu nguồn không có thứ tự nghiệp vụ được cam kết, việc sao chép không làm thứ tự đó tự xuất hiện.

## 6. Lựa chọn từ yêu cầu và tải công việc

### 6.1. Tra cứu là chính, không yêu cầu thứ tự

Một bộ đếm chỉ được hỏi theo từng mã và hầu như không được duyệt toàn bộ có thể bắt đầu với `HashMap`. Ứng dụng không cần duy trì thứ tự chèn trong suốt vòng đời của bảng.

Nếu cuối cùng chỉ cần xuất theo mã tăng dần một lần, có thể sắp xếp kết quả ở bước xuất. Không nhất thiết phải giữ một thứ tự chèn rồi bỏ nó đi khi sắp xếp.

Đây là điểm xuất phát hợp lý theo yêu cầu, không phải lời hứa `HashMap` luôn nhanh nhất.

### 6.2. Cần theo lần đầu xuất hiện

Nếu mỗi mã chỉ xuất một lần và phải theo vị trí gặp lần đầu, `LinkedHashMap` mặc định phù hợp. Đoạn sau là mã minh họa một phần, giả sử `codes` là danh sách mã đã có:

~~~java
Map<String, Integer> counts = new LinkedHashMap<>();
for (String code : codes) {
    counts.merge(code, 1, Integer::sum);
}
for (Map.Entry<String, Integer> entry : counts.entrySet()) {
    System.out.println(entry.getKey() + ": " + entry.getValue());
}
~~~

Cập nhật số đếm của khóa tồn tại không làm đổi thứ tự chèn. Với đầu vào `B, A, B, C, A`, các khóa được xuất theo `B, A, C`.

Nếu dữ liệu đầu vào đến từ một nguồn không cam kết thứ tự, phải xác định quy tắc đầu vào trước. Cấu trúc giữ thứ tự chỉ giữ được trình tự mà chương trình thực sự cung cấp.

### 6.3. Có nhiều lần duyệt trên bảng thưa

Đây là tình huống đáng xem xét `LinkedHashMap` vì đường duyệt không quét các vị trí bảng trống. Tuy nhiên, cũng cần xem tại sao bảng thưa: cấu hình khởi tạo quá lớn có thể là vấn đề cần sửa.

Cân nhắc đồng thời số ánh xạ, mức thưa, số lượt duyệt, tỷ lệ cập nhật, phần việc trong thân vòng lặp và giới hạn bộ nhớ. Nếu yêu cầu cho phép, sửa cách tạo map có thể giải quyết gốc lãng phí tốt hơn việc chỉ đổi lớp.

### 6.4. Cần thứ tự khóa hoặc truy cập đồng thời

Thứ tự khóa tăng dần là bài toán khác với thứ tự chèn. `TreeMap` phù hợp với nhiều nhu cầu duy trì thứ tự khóa; sắp xếp danh sách kết quả có thể phù hợp khi chỉ cần một bản xuất cuối cùng. Cần phân biệt duy trì thứ tự suốt vòng đời với tạo kết quả có thứ tự tại một thời điểm.

Cả `HashMap` và `LinkedHashMap` đều không tự cung cấp đồng bộ hóa. Chọn lớp giữ thứ tự không giải quyết truy cập đồng thời.

Đặc biệt, với chế độ thứ tự truy cập, `get` có thể làm thay đổi thứ tự cấu trúc. Lập luận “các luồng chỉ đọc” cần xem lại nếu các lần đọc đó là truy cập như vậy. Quy tắc đồng bộ hóa phải bao phủ cách dùng thực tế, kể cả duyệt. [Java 17: LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html)

Nếu cần hợp đồng đồng thời, hãy chọn thiết kế đáp ứng yêu cầu đó rồi đánh giá lại thứ tự. Không có một lớp map tự động giải quyết tất cả các yêu cầu cùng lúc.

## 7. Duyệt theo dữ liệu cần dùng

### 7.1. Cần khóa và giá trị: ưu tiên entrySet

Hai đoạn minh họa một phần sau tính tổng trên map `scores` không có giá trị null:

~~~java
int total = 0;
for (String key : scores.keySet()) {
    total += scores.get(key);
}
~~~

~~~java
int total = 0;
for (Map.Entry<String, Integer> entry : scores.entrySet()) {
    total += entry.getValue();
}
~~~

Đoạn thứ nhất đã có khóa từ bộ duyệt rồi lại yêu cầu tra cứu theo khóa để lấy giá trị. Đoạn thứ hai lấy trực tiếp từ ánh xạ đang được duyệt.

Không nên gọi đoạn thứ nhất là bậc hai chỉ vì có thêm `get`: trong điều kiện băm tốt, các lượt tra cứu bổ sung vẫn có chi phí kỳ vọng hằng số mỗi lượt. Tuy vậy, chúng là công việc không cần làm khi đã có ánh xạ.

Nếu chỉ cần khóa, chọn `keySet()`. Nếu chỉ cần giá trị, chọn `values()`. Nếu cần cả hai, `entrySet()` thể hiện mục đích rõ ràng.

### 7.2. Mẫu keySet rồi get có thể đổi thứ tự truy cập

Trên `LinkedHashMap` có `accessOrder=true`, `get(key)` có thể chuyển ánh xạ xuống cuối ngay lúc bộ duyệt đang hoạt động. Mẫu vòng lặp đó có thể gặp `ConcurrentModificationException`.

Không xây dựng tính đúng của chương trình bằng cách trông chờ ngoại lệ chắc chắn xuất hiện. Cơ chế phát hiện sửa đổi của bộ duyệt chỉ là nỗ lực tốt nhất, không phải công cụ đồng bộ hóa. [Java 17: LinkedHashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashMap.html)

Duyệt `entrySet` và đọc `entry.getValue()` tránh cả lượt tra cứu thừa và lượt truy cập theo khóa có thể đổi thứ tự. Điều này không cho phép luồng khác tự do sửa map cùng lúc; đó vẫn là vấn đề riêng.

Khi cần quan sát thứ tự hiện tại, cũng đừng gọi `get` liên tiếp chỉ để in các giá trị trên một map thứ tự truy cập. Chính thao tác quan sát có thể làm đổi thứ tự bạn đang quan tâm.

## 8. Chương trình đầy đủ và kết quả đã kiểm chứng

Lưu mã sau vào `LinkedHashMapCostDemo.java`. Chương trình Java 17+ không cần thư viện ngoài.

Nó kiểm tra cùng dữ liệu trong bốn map, ghi nhận các lần gọi `hashCode` trong hai cách duyệt, rồi đối chiếu thứ tự chèn và thứ tự truy cập. Đây là ví dụ chức năng, không phải phép đo thời gian.

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class LinkedHashMapCostDemo {
    private static final class Key {
        private static int hashCalls;
        private final int id;

        private Key(int id) {
            this.id = id;
        }

        @Override
        public int hashCode() {
            hashCalls++;
            return id;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Key key && id == key.id;
        }
    }

    private static void fill(Map<Key, Integer> map) {
        map.put(new Key(30), 3);
        map.put(new Key(10), 1);
        map.put(new Key(20), 2);
    }

    private static List<Integer> ids(Map<Key, Integer> map) {
        List<Integer> result = new ArrayList<>();
        for (Key key : map.keySet()) {
            result.add(key.id);
        }
        return result;
    }

    private static int entrySum(Map<Key, Integer> map) {
        int sum = 0;
        for (Map.Entry<Key, Integer> entry : map.entrySet()) {
            sum += entry.getValue();
        }
        return sum;
    }

    private static void inspect(String label, Map<Key, Integer> map) {
        fill(map);
        Key.hashCalls = 0;
        int fromEntries = entrySum(map);
        int iteratorHashCalls = Key.hashCalls;

        Key.hashCalls = 0;
        int fromKeys = 0;
        for (Key key : map.keySet()) {
            fromKeys += map.get(key);
        }
        int keyThenGetHashCalls = Key.hashCalls;

        if (map.size() != 3 || fromEntries != 6 || fromKeys != 6) {
            throw new AssertionError("Unexpected mappings");
        }
        System.out.println(label + ": size=" + map.size()
                + ", sum=" + fromEntries
                + ", iteratorHashCalls=" + iteratorHashCalls
                + ", keyThenGetHashCalls=" + keyThenGetHashCalls);
    }

    private static void requireIds(Map<Key, Integer> map, List<Integer> expected) {
        if (!ids(map).equals(expected)) {
            throw new AssertionError("Unexpected LinkedHashMap order");
        }
    }

    public static void main(String[] args) {
        inspect("HashMap(requested=16)", new HashMap<Key, Integer>(16));
        inspect("HashMap(requested=4096)", new HashMap<Key, Integer>(4096));
        inspect("LinkedHashMap(requested=16)",
                new LinkedHashMap<Key, Integer>(16));
        inspect("LinkedHashMap(requested=4096)",
                new LinkedHashMap<Key, Integer>(4096));

        LinkedHashMap<Key, Integer> insertion = new LinkedHashMap<>();
        fill(insertion);
        requireIds(insertion, List.of(30, 10, 20));
        System.out.println("insertion/start=" + ids(insertion));
        insertion.put(new Key(30), 30);
        requireIds(insertion, List.of(30, 10, 20));
        System.out.println("insertion/replace=" + ids(insertion));
        insertion.remove(new Key(10));
        insertion.put(new Key(10), 10);
        requireIds(insertion, List.of(30, 20, 10));
        System.out.println("insertion/reinsert=" + ids(insertion));

        LinkedHashMap<Key, Integer> access =
                new LinkedHashMap<>(16, 0.75f, true);
        fill(access);
        System.out.println("access/start=" + ids(access));
        access.get(new Key(10));
        requireIds(access, List.of(30, 20, 10));
        System.out.println("access/afterGet10=" + ids(access));
        Key.hashCalls = 0;
        int accessSum = entrySum(access);
        int accessIteratorHashCalls = Key.hashCalls;
        requireIds(access, List.of(30, 20, 10));
        if (accessSum != 6) {
            throw new AssertionError("Unexpected access-order sum");
        }
        System.out.println("access/entrySum=" + accessSum
                + ", iteratorHashCalls=" + accessIteratorHashCalls);
        System.out.println("access/afterEntries=" + ids(access));
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 -encoding UTF-8 LinkedHashMapCostDemo.java
java LinkedHashMapCostDemo
~~~

Stdout của lần chạy kiểm chứng:

~~~text
HashMap(requested=16): size=3, sum=6, iteratorHashCalls=0, keyThenGetHashCalls=3
HashMap(requested=4096): size=3, sum=6, iteratorHashCalls=0, keyThenGetHashCalls=3
LinkedHashMap(requested=16): size=3, sum=6, iteratorHashCalls=0, keyThenGetHashCalls=3
LinkedHashMap(requested=4096): size=3, sum=6, iteratorHashCalls=0, keyThenGetHashCalls=3
insertion/start=[30, 10, 20]
insertion/replace=[30, 10, 20]
insertion/reinsert=[30, 20, 10]
access/start=[30, 10, 20]
access/afterGet10=[30, 20, 10]
access/entrySum=6, iteratorHashCalls=0
access/afterEntries=[30, 20, 10]
~~~

Mã đã biên dịch với `--release 17` và chạy thành công. Các kiểm tra trong chương trình xác nhận số ánh xạ, tổng và các thứ tự yêu cầu. Lựa chọn `--release 17` xác định mức API và mã đích tương thích; nó không có nghĩa JVM thực thi nhất thiết phải là đúng bản JDK 17.

### 8.1. Vì sao bốn tổng đều bằng sáu?

Hàm `fill` thêm ba cặp `30 -> 3`, `10 -> 1` và `20 -> 2`. Cả bốn map giữ cùng dữ liệu. Tính tổng giúp kiểm tra nội dung mà không giả định thứ tự duyệt `HashMap`.

Trong lần chạy này, duyệt `entrySet` để lấy giá trị không gọi lại `hashCode` của các khóa; bộ đếm bằng không. Duyệt `keySet` rồi gọi `get` cho mỗi khóa tạo ba lần gọi `hashCode`.

Đây là quan sát về các lời gọi vào phương thức khóa trên cách triển khai đã chạy. Hợp đồng `Map` không yêu cầu mọi cách triển khai phải có đúng bộ đếm như ví dụ.

Quan trọng hơn, bộ đếm không quan sát số vị trí bảng đã được quét. Bộ duyệt có thể đi qua cấu trúc nội bộ mà không gọi lại `hashCode`. Vì thế, hai dòng cùng in số không không chứng minh hai map có chi phí duyệt bằng nhau.

Chương trình không đo sức chứa thực, số byte, thời gian hay tỷ lệ tốc độ. Nhãn `requested` chủ động nói đây là tham số yêu cầu, không phải kết quả đọc mảng riêng tư.

### 8.2. Thứ tự chèn thay đổi khi nào?

Ba dòng `insertion` cho thấy:

1. Sau khi chèn ba khóa, thứ tự là `[30, 10, 20]`.
2. Thay giá trị khóa `30` vẫn giữ thứ tự đó.
3. Xóa khóa `10` rồi thêm lại làm thứ tự thành `[30, 20, 10]`.

Map không thêm một vị trí mới cho mỗi lần gọi `put` bất kể kết quả. Nó vẫn chỉ có một ánh xạ cho mỗi khóa bằng nhau. Việc duy trì liên kết phải phù hợp với ánh xạ thực sự được thêm, xóa hoặc cập nhật.

Hàm `requireIds` chỉ kiểm tra thứ tự của `LinkedHashMap`. Không có kiểm tra áp đặt thứ tự tương tự lên `HashMap`.

### 8.3. Đọc theo khóa khác với duyệt ánh xạ

Map `access` dùng chế độ thứ tự truy cập. `get(10)` đưa khóa `10` xuống cuối. Hàm `entrySum` sau đó đọc giá trị từ các ánh xạ mà không gọi `get` của map; thứ tự không đổi.

Hàm `ids` duyệt `keySet` và chỉ đọc mã trong khóa, không gọi `map.get`. Nhờ vậy, thao tác in thứ tự không tự tạo một lượt truy cập theo khóa.

Chương trình không cố ý vừa duyệt vừa gọi `get` trên map thứ tự truy cập. Ví dụ giữ hành vi ổn định để chứng minh rõ hai loại đọc có tác động khác nhau, thay vì phụ thuộc thời điểm phát sinh ngoại lệ.

### 8.4. Vì sao không dùng khóa đếm hashCode để đo tốc độ?

Bản thân thao tác tăng bộ đếm đã thêm công việc vào `hashCode`. Khóa đơn giản trong ví dụ giúp quan sát một cơ chế, nhưng không nhất thiết đại diện cho khóa thực tế của ứng dụng.

Một ví dụ chứng minh được tổng, thứ tự và các lời gọi đã quan sát không tự trở thành phép đo hiệu năng có thể suy rộng. Hãy dùng ví dụ để hiểu, rồi dùng phương pháp đo phù hợp khi cần quyết định từ số liệu.

## 9. Khi quyết định cần số liệu thời gian hoặc bộ nhớ

### 9.1. Viết rõ câu hỏi trước khi đo

“Lớp nào nhanh hơn?” là câu hỏi thiếu điều kiện. Có thể thay bằng:

- Với N ánh xạ và phân bố khóa xác định, thời gian duyệt toàn bộ thay đổi thế nào theo cách chuẩn bị bảng?
- Với tỷ lệ đọc, ghi và duyệt của dịch vụ, đổi map ảnh hưởng tổng tác vụ ra sao?
- Với cùng đối tượng khóa và giá trị, cấu trúc map trên JVM cụ thể giữ bao nhiêu bộ nhớ?

Đo riêng duyệt khác với đo cả xây dựng và duyệt. Đo phần cấu trúc khác với tính toàn bộ đồ thị đối tượng còn được tham chiếu. Phạm vi đo phải đi cùng kết quả.

### 9.2. Thời gian trên JVM có nhiều yếu tố gây nhiễu

Một vòng `System.nanoTime` quanh đoạn rất ngắn có thể bị ảnh hưởng bởi khởi động JVM, biên dịch JIT, loại bỏ tính toán không dùng và tải hệ thống. Nếu vừa tạo map vừa duyệt, phép đo có cả cấp phát và xây dựng.

Khi cần thí nghiệm vi mô, JMH là bộ công cụ OpenJDK để xây dựng và chạy phép đo trên JVM. Công cụ không tự sửa giả thuyết hoặc dữ liệu sai, nhưng hỗ trợ cách tổ chức đo phù hợp môi trường JVM. [OpenJDK: JMH](https://github.com/openjdk/jmh)

Cần ghi rõ phiên bản JVM, dữ liệu, loại khóa, cách băm, lượng ánh xạ, cấu hình map, tỷ lệ thao tác, cách dùng kết quả và phạm vi có tính cấp phát hay không. Đo cả hai phương án với điều kiện tương đương và diễn giải trong đúng phạm vi ấy.

### 9.3. Số byte cần quan sát bố cục thực tế

JOL của OpenJDK cung cấp công cụ phân tích bố cục và dung lượng đối tượng Java. Nếu cần con số byte, hãy gắn kết quả với phiên bản, cấu hình JVM và cách tính đối tượng chia sẻ. [OpenJDK: JOL](https://github.com/openjdk/jol)

Không lấy một hiệu số `Runtime.freeMemory` trước và sau một lần tạo map rồi coi đó là kích thước chính xác. Thu gom rác, vùng nhớ JVM và các đối tượng ngoài phạm vi có thể ảnh hưởng.

Bài này không yêu cầu cài các công cụ đó. Mục đích là phân biệt kiến thức có thể lập luận từ hợp đồng và cấu trúc với kết quả cần đo trên môi trường cụ thể.

## 10. Những kết luận dễ sai

| Kết luận | Cách sửa |
|---|---|
| LinkedHashMap luôn nhanh hơn vì duyệt O(N) | Nó có đường duyệt không quét bảng trống; thao tác khác và hằng số vẫn cần xét |
| HashMap luôn duyệt chậm | Khi C tương xứng N, đường duyệt cũng tuyến tính theo N; cần tải công việc cụ thể |
| LinkedHashMap không cần quan tâm sức chứa | Duyệt không phụ thuộc quét C, nhưng bảng vẫn chiếm bộ nhớ |
| Cùng O(C + N) nên bộ nhớ bằng nhau | Cùng bậc không có nghĩa cùng hệ số hoặc số byte |
| Mọi ánh xạ luôn tốn thêm đúng một số byte cố định | Phải xác định dạng nút, bố cục và cấu hình JVM |
| Giữ thứ tự nghĩa là sắp xếp khóa | Phải phân biệt thứ tự chèn, truy cập và thứ tự khóa |
| Sao chép sang LinkedHashMap khôi phục lịch sử chèn | Chỉ giữ được thứ tự gặp ở nguồn, không phục hồi thông tin đã mất |
| get chỉ đọc nên không thể sửa cấu trúc | Với chế độ truy cập, get có thể đổi thứ tự |
| hashCode không được gọi nghĩa là không quét bảng | Bộ đếm đó không quan sát mọi bước nội bộ |
| Một lần đo quyết định cho mọi dữ liệu | Kết quả gắn với dữ liệu, tác vụ và môi trường đã đo |

## 11. Thực hành và lời giải

### Bài 1. Kích thước không phải sức chứa

Một map có `size() = 200` nhưng được chuẩn bị cho lượng dữ liệu lớn hơn nhiều. Vì sao không thể thay mọi đại lượng trong chi phí duyệt bằng 200?

**Lời giải:** `size()` chỉ cho N, không cho C. Mô hình `HashMap` chứa cả C + N nên biết N chưa đủ mô tả tác động của bảng thưa. Đường duyệt `LinkedHashMap` theo N, nhưng phần lưu trữ của nó vẫn có bảng băm. Không được dùng kết luận về đường duyệt thay cho kết luận về dung lượng.

### Bài 2. Tra cứu theo khóa là chính

Ứng dụng chỉ hỏi tổng số lần xuất hiện của từng mã, ít duyệt toàn bộ và không yêu cầu thứ tự. Điểm xuất phát hợp lý là gì? Khi nào xem lại?

**Lời giải:** Có thể bắt đầu với `HashMap` vì thứ tự không phục vụ yêu cầu. Xem lại nếu đầu ra cần thứ tự chèn, tác vụ chuyển sang nhiều lượt duyệt trên bảng thưa hoặc số liệu đại diện chỉ ra vấn đề cần tối ưu. Nếu có truy cập đồng thời, phải đánh giá hợp đồng đồng thời riêng.

### Bài 3. Thứ tự lần đầu xuất hiện

Đầu vào là `B, A, B, C, A`. Cần đếm và xuất theo lần đầu gặp. Chọn gì và kết quả theo thứ tự nào?

**Lời giải:** `LinkedHashMap` mặc định cho thứ tự `B, A, C` với số đếm `2, 2, 1`. Các lần cập nhật số đếm không đổi vị trí chèn. Không chọn chế độ truy cập nếu muốn giữ lần đầu xuất hiện bất chấp các lượt cập nhật về sau.

### Bài 4. Rút gọn mô hình

Trong một họ dữ liệu có `C = 2N`, hãy rút gọn chi phí duyệt HashMap. Có thể kết luận thời gian bằng LinkedHashMap không?

**Lời giải:** `O(C + N) = O(3N) = O(N)`. Hai đường duyệt cùng bậc tuyến tính dưới giả định ấy. Không thể kết luận thời gian bằng nhau vì Big O bỏ qua hệ số và cách truy cập bộ nhớ.

### Bài 5. Tỷ số mô hình không phải tỷ số tốc độ

Với `N = 100` và `C = 1.000.000`, một người nói LinkedHashMap nhanh hơn đúng 10.001 lần. Hãy sửa câu đó.

**Lời giải:** Có thể nói mô hình HashMap có thành phần quét bảng rất lớn so với số ánh xạ; LinkedHashMap không có phần quét vị trí trống đó khi duyệt. Không thể đổi tỷ số số hạng thành tỷ số thời gian. Cần đo nếu cần một con số tốc độ.

### Bài 6. Sửa vòng lặp có công việc thừa

Bạn cần cả khóa và giá trị trên `LinkedHashMap` thứ tự truy cập, nhưng đang duyệt `keySet` rồi gọi `get`. Nêu hai lý do đổi sang `entrySet`.

**Lời giải:** Có thể lấy trực tiếp cả khóa và giá trị từ ánh xạ, tránh lượt tra cứu thừa. Đồng thời, `get` có thể đổi thứ tự trong khi bộ duyệt hoạt động; `entry.getValue()` không tạo truy cập kiểu đó. Việc đổi cách duyệt không tự giải quyết sửa đổi từ luồng khác.

Mẫu minh họa:

~~~java
for (Map.Entry<String, Integer> entry : scores.entrySet()) {
    System.out.println(entry.getKey() + ": " + entry.getValue());
}
~~~

### Bài 7. Duyệt và lưu trữ là hai câu hỏi

Một báo cáo nói: “LinkedHashMap duyệt độc lập sức chứa nên đặt sức chứa một triệu cho vài chục ánh xạ không tốn gì thêm.” Sai ở đâu?

**Lời giải:** Báo cáo trộn chi phí đường duyệt với chi phí lưu trữ. Chuỗi giúp tránh quét bảng trống, nhưng bảng vẫn tồn tại để tra cứu. Sức chứa quá lớn có thể tăng dung lượng cấu trúc và ảnh hưởng hệ thống bộ nhớ.

### Bài 8. Giới hạn của bộ đếm

Chương trình in `iteratorHashCalls=0` cho hai yêu cầu sức chứa. Điều gì được quan sát và điều gì chưa được đo?

**Lời giải:** Đã quan sát số lần gọi phương thức `hashCode` của Key trong đoạn đang đếm và kiểm tra dữ liệu bằng tổng. Chưa đo số vị trí quét, sức chứa thực, thời gian, số byte hoặc thu gom rác. Kết quả bằng không không chứng minh chi phí duyệt bằng nhau.

### Bài 9. Sao chép không khôi phục lịch sử

Bạn chỉ nhận một HashMap, không có lịch sử, rồi tạo LinkedHashMap từ nó. Có thể hứa đầu ra theo thứ tự nhập ban đầu không?

**Lời giải:** Không. Map mới giữ thứ tự gặp khi duyệt nguồn. Nguồn không cam kết thứ tự ấy là lịch sử nhập. Muốn hứa thứ tự nhập, phải giữ thông tin ngay khi nhập hoặc có dữ liệu thứ tự riêng.

### Bài 10. Quyết định dựa vào tải công việc

Dịch vụ giữ map nhỏ, đọc theo khóa rất nhiều, mỗi giờ xuất toàn bộ một lần, không yêu cầu thứ tự. Đồng nghiệp muốn đổi chỉ vì “LinkedHashMap duyệt O(N)”. Cần kiểm tra gì?

**Lời giải:** Xác định phần thời gian đáng kể của dịch vụ, số ánh xạ, mức thưa, tỷ lệ thao tác, việc trong lần xuất và giới hạn bộ nhớ. Một lượt xuất mỗi giờ có thể không phải chỗ cần tối ưu. Nếu có vấn đề thực, đo tác vụ đại diện. Nếu sau này xuất hiện yêu cầu thứ tự, đó là lý do chức năng mới để đánh giá lại.

## 12. Tự kiểm tra lập luận lựa chọn

Trước khi đề xuất thay lớp map, hãy điền được câu:

“Ứng dụng cần ... về thứ tự, chủ yếu thực hiện ... với khoảng ... ánh xạ, duyệt ... lần và có giới hạn bộ nhớ ...; vì vậy chọn ... và sẽ đo ... nếu cần số liệu.”

`LinkedHashMap` đem lại hợp đồng thứ tự và đường duyệt theo số ánh xạ, đồng thời cần thêm thông tin liên kết và công việc duy trì. `HashMap` vẫn phù hợp với nhiều bảng tra cứu không yêu cầu thứ tự. Lựa chọn đúng nối được yêu cầu, mô hình chi phí và bằng chứng trong đúng phạm vi sử dụng.
