# ArrayList: chi phí dịch chuyển khi thêm hoặc xóa ở đầu và giữa

`ArrayList` thuận tiện khi cần một danh sách có thứ tự và truy cập nhanh bằng chỉ số. Nhưng “truy cập nhanh tới vị trí i” không đồng nghĩa với “chèn hoặc xóa tại i cũng nhanh”. Truy cập chỉ đọc một vị trí; chèn hoặc xóa còn phải duy trì cách các phần tử được xếp liên tiếp và giữ đúng thứ tự.

Ví dụ, danh sách công việc đang là `[A, B, C, D]`. Nếu thêm `X` trước `B`, kết quả phải là `[A, X, B, C, D]`; ba phần tử B, C, D đổi chỉ số. Nếu xóa `B`, các phần tử phía sau phải dồn lại để danh sách không có lỗ hổng.

Bài này giải thích phần việc dịch chuyển đó, cách tính theo vị trí, tác động khi thao tác lặp nhiều lần, và những cách giảm công việc mà vẫn giữ đúng kết quả. Các ví dụ dùng Java 17 trở lên; chỗ nào phân tích thuật toán cụ thể của OpenJDK sẽ được nêu rõ.

## 1. Mô hình cần nhớ: các phần tử nằm liên tiếp trong mảng nền

Một `ArrayList` có hai đại lượng khác nhau:

- **Kích thước (size):** số phần tử đang có trong danh sách.
- **Dung lượng (capacity):** số vị trí mảng nền có thể chứa trước khi cần tăng mảng.

Nếu kích thước là n, các phần tử logic chiếm các vị trí từ 0 đến n−1. Dung lượng có thể lớn hơn n, nhưng phần dự trữ nằm sau đoạn đang dùng, không phải những lỗ trống rải ở giữa.

~~~text
size = 5, capacity = 8

chi so:     0   1   2   3   4   5   6   7
mang nen:  [A] [B] [C] [D] [E] [ ] [ ] [ ]
           <--- danh sach ---> <du tru>
~~~

Phần trống bên phải giúp thêm cuối. Nó không tạo sẵn một vị trí trống giữa B và C. Muốn chèn ở đó mà vẫn giữ thứ tự, phải mở một khoảng trống bằng cách dời đoạn phía sau.

Trong bài, n luôn là **kích thước ngay trước thao tác đang phân tích**, i là chỉ số được truyền vào. Khi có nhiều thao tác, n có thể thay đổi sau mỗi lần.

### 1.1. Dịch chuyển là chuyển tham chiếu, không sao chép sâu đối tượng

Mảng nền của `ArrayList<E>` chứa các tham chiếu đối tượng. Dời phần tử từ chỉ số 3 sang 4 chủ yếu là chép tham chiếu sang vị trí khác; không gọi lại constructor và không tự tạo một bản sao sâu của đối tượng.

Một đối tượng có dữ liệu nội bộ lớn không có nghĩa là toàn bộ dữ liệu của nó được sao chép mỗi lần danh sách dịch chuyển. Tuy nhiên, dời một triệu tham chiếu vẫn là công việc đáng kể: cần đọc và ghi nhiều vị trí bộ nhớ.

Các đối tượng phần tử giữ nguyên danh tính. Chỉ số của chúng trong danh sách có thể thay đổi; biến bên ngoài đang giữ tham chiếu tới một phần tử vẫn trỏ tới đối tượng đó.

### 1.2. Thứ tự là lý do phải trả chi phí

Nếu không cần giữ thứ tự, một cấu trúc khác hoặc một thuật toán đặc biệt có thể xử lý khoảng trống theo cách khác. Nhưng `List` biểu diễn một dãy có thứ tự. `ArrayList.remove(i)` phải giữ nguyên thứ tự tương đối của những phần tử còn lại.

Tự đưa phần tử cuối vào chỗ vừa xóa rồi bỏ cuối có thể giảm công việc, nhưng thay đổi kết quả của dãy. Chỉ có thể cân nhắc thuật toán đó khi yêu cầu nghiệp vụ cho phép đổi thứ tự; nó không phải hành vi của `ArrayList.remove(i)`.

## 2. Thêm tại chỉ số i: dịch n−i phần tử sang phải

`add(i, value)` chèn một phần tử trước phần tử đang ở i. Phần tử cũ tại i và mọi phần tử phía sau tăng chỉ số thêm 1.

Điều kiện chỉ số:

~~~text
0 <= i <= n
~~~

i = n là thêm cuối. i = 0 là thêm đầu. Danh sách rỗng n = 0 vẫn cho phép thêm tại i = 0.

Quy tắc chèn và miền chỉ số được mô tả trong [hợp đồng add(int, E) của ArrayList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#add(int,E)).

### 2.1. Ví dụ chèn giữa

Đang có `[A, B, C, D, E]`, n = 5, chèn X tại i = 2:

~~~text
truoc:
chi so:     0   1   2   3   4
           [A] [B] [C] [D] [E]

mo cho tai i = 2:
chi so:     0   1   2   3   4   5
           [A] [B] [ ] [C] [D] [E]
                      C,D,E dich sang phai

ghi X:
           [A] [B] [X] [C] [D] [E]
~~~

Đoạn phải chuyển là các vị trí cũ 2, 3, 4, nên số tham chiếu dịch chuyển là:

~~~text
n - i = 5 - 2 = 3
~~~

Sau đó còn một lượt ghi phần tử mới và cập nhật kích thước. Nếu mảng đã đủ chỗ, mô hình công việc là **Θ(n−i+1)**. Ký hiệu Θ ở đây diễn đạt số lượng công việc cùng bậc với độ dài đoạn phải xử lý, gồm cả phần việc hằng số.

### 2.2. Đầu, giữa và cuối khác nhau thế nào?

| Vị trí chèn | Số phần tử cũ phải dịch | Khi đã đủ dung lượng |
|---|---:|---|
| Đầu, i = 0 | n | Θ(n+1) |
| Giữa, i xấp xỉ n/2 | Xấp xỉ n/2 | Θ(n) |
| Gần cuối, trước một số phần tử cố định | Số cố định đó | Θ(1) theo n |
| Cuối, i = n | 0 | Θ(1) |

Nếu danh sách có 100.000 phần tử, chèn ở chính giữa cần dịch khoảng 50.000 tham chiếu. “Chỉ chuyển một nửa” vẫn là tuyến tính: hệ số 1/2 không làm thay đổi bậc tăng.

Không nên nói mọi lần `add(i, x)` đều cần dịch n phần tử. Con số phụ thuộc i. Phát biểu “chèn theo chỉ số có trường hợp xấu nhất O(n)” đúng, còn công thức n−i giúp phân biệt từng vị trí.

### 2.3. Thêm khác thay thế

Đoạn thân phương thức minh họa:

~~~java
ArrayList<String> values = new ArrayList<>(List.of("A", "B", "C"));
values.set(1, "X");  // [A, X, C]: thay the, size khong doi
values.add(1, "Y");  // [A, Y, X, C]: chen, phan duoi doi chi so
~~~

`set` ghi đè một vị trí đã tồn tại; nó không mở khoảng trống và không dịch cả đuôi. Nếu yêu cầu chỉ là thay giá trị tại một vị trí, dùng `set` thay vì xóa rồi chèn lại.

Với `set`, chỉ số phải nhỏ hơn n. Dung lượng dự trữ không làm `set(n, x)` hợp lệ.

## 3. Xóa tại chỉ số i: dịch n−i−1 phần tử sang trái

`remove(i)` trả về phần tử bị xóa và giữ thứ tự các phần tử còn lại. Các phần tử nằm sau i giảm chỉ số đi 1.

Điều kiện chỉ số:

~~~text
0 <= i < n
~~~

Vì phải có phần tử để xóa, i = n không hợp lệ và danh sách rỗng không có chỉ số xóa hợp lệ. Xem [hợp đồng remove(int) của ArrayList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#remove(int)).

### 3.1. Ví dụ xóa giữa

Đang có `[A, B, C, D, E]`, n = 5, xóa i = 2:

~~~text
truoc:
chi so:     0   1   2   3   4
           [A] [B] [C] [D] [E]

xoa C va don phan duoi:
chi so:     0   1   2   3   4
           [A] [B] [D] [E] [ ]
                    D,E dich sang trai

size moi = 4
~~~

Đoạn phải chuyển bắt đầu tại i+1 và kết thúc tại n−1, nên số phần tử dịch là:

~~~text
n - i - 1 = 5 - 2 - 1 = 2
~~~

Trong triển khai OpenJDK dùng ở bài, sau khi dồn đoạn đuôi, vị trí cuối cũ được gán `null` để không giữ thừa tham chiếu. Việc cập nhật kích thước, trả về phần tử đã xóa và xóa tham chiếu cuối là phần việc hằng số ngoài đoạn dịch.

Mô hình chi phí của xóa theo chỉ số là **Θ(n−i)**. Với phần tử cuối, n−i = 1, nên công việc vẫn là hằng số dù số tham chiếu phải dịch bằng 0.

### 3.2. Bảng vị trí xóa

| Vị trí xóa | Số phần tử phải dịch | Bậc công việc theo n |
|---|---:|---|
| Đầu, i = 0 | n−1 | Θ(n) với n lớn |
| Giữa, i xấp xỉ n/2 | Xấp xỉ n/2 | Θ(n) |
| Áp cuối, i = n−2 | 1 | Θ(1) |
| Cuối, i = n−1 | 0 | Θ(1) |

Không có bước “tìm từ đầu đến chỉ số i” trong `ArrayList.remove(int)`: truy cập mảng bằng chỉ số là trực tiếp. Phần tuyến tính đến từ việc dồn đuôi, không phải đi tìm ô có chỉ số.

### 3.3. Không dịch không có nghĩa là không làm gì

Xóa cuối vẫn cần lấy giá trị cũ, giảm kích thước và bỏ tham chiếu ở ô cuối. Xóa một phần tử không bảo đảm đối tượng đó bị thu gom ngay:

- Nơi khác có thể vẫn giữ tham chiếu.
- Giá trị trả về của `remove` có thể đang được mã gọi giữ lại.
- Thời điểm bộ gom rác chạy do JVM quyết định.

Xóa phần tử cũng không đồng nghĩa với thu nhỏ mảng nền sau từng lần. Việc bỏ nội dung, dồn thứ tự và điều chỉnh dung lượng là các vấn đề khác nhau.

## 4. Dịch phần đuôi và tăng dung lượng là hai loại công việc

Khi chèn, có thể đồng thời phát sinh:

1. **Tăng mảng:** cần một vùng chứa lớn hơn nếu hết chỗ.
2. **Dịch đoạn đuôi:** cần mở đúng vị trí chèn trong dãy có thứ tự.

Đặt trước dung lượng giúp tránh loại thứ nhất trong phạm vi đã dự trữ. Nó không loại bỏ loại thứ hai.

Ví dụ, `new ArrayList<>(1_000_000)` đang có 100.000 phần tử vẫn phải dịch 100.000 tham chiếu nếu chèn ở đầu. Phần trống sau vị trí 99.999 không thay thế được khoảng trống trước vị trí 0.

Ở [mã nguồn ArrayList OpenJDK 17, bản jdk-17+35](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/ArrayList.java), chèn theo chỉ số thực hiện bước tăng nếu cần, rồi chuyển đoạn đuôi; xóa theo chỉ số dồn đoạn đuôi và bỏ tham chiếu cuối. Đây là cơ sở triển khai cụ thể cho mô hình phân tích của bài.

### 4.1. Thêm cuối khấu hao không suy rộng sang thêm đầu

Một chuỗi thêm cuối từ rỗng có tổng chi phí quản lý mảng tuyến tính dưới chính sách tăng thông thường: các lần tăng đắt được phân bổ cho nhiều lần thêm khác. Vì vậy, thêm cuối có chi phí hằng số khấu hao.

Nhưng với thêm đầu, **mỗi lần** đều phải dời các phần tử đang có. Chỗ dự trữ tạo bởi lần tăng mảng không làm biến mất yêu cầu dịch ở lần thêm đầu kế tiếp. Do đó, không dùng kết luận khấu hao của thêm cuối để kết luận thêm đầu cũng O(1).

### 4.2. arraycopy nhanh vẫn phải xử lý một đoạn dài

Triển khai có thể dùng `System.arraycopy` thay cho một vòng lặp Java viết tay. Hàm này hỗ trợ sao chép giữa những đoạn chồng lấn của cùng một mảng với kết quả đúng, như mô tả tại [System.arraycopy trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#arraycopy(java.lang.Object,int,java.lang.Object,int,int)).

Việc JVM tối ưu sao chép khối có thể làm hằng số thời gian tốt hơn. Nó không biến việc chuyển một đoạn k tham chiếu thành số lượng công việc độc lập với k.

“Dịch sang phải thì ghi từ cuối về đầu” là cách nghĩ hữu ích khi tự viết vòng lặp để tránh ghi đè dữ liệu chưa đọc. Với `ArrayList`, thư viện đã xử lý tính đúng của đoạn chồng lấn; ứng dụng không cần tự thao tác vào mảng riêng.

## 5. Khi lặp thao tác, chi phí có thể thành bậc hai

Đánh giá một dòng lệnh riêng lẻ chưa đủ. Cần cộng số phần tử phải chuyển của cả vòng lặp.

### 5.1. Xây danh sách bằng cách thêm đầu liên tiếp

Tạo danh sách từ rỗng bằng n lần `add(0, value)`:

~~~text
lan thu 1:  dang co 0 phan tu -> dich 0
lan thu 2:  dang co 1 phan tu -> dich 1
lan thu 3:  dang co 2 phan tu -> dich 2
...
lan thu n:  dang co n-1 phan tu -> dich n-1
~~~

Tổng số tham chiếu dịch:

~~~text
0 + 1 + 2 + ... + (n - 1) = n(n - 1)/2
~~~

Chỉ riêng dịch đoạn đã là Θ(n²), kể cả khi đặt trước đủ dung lượng để không tăng mảng lần nào.

Với n = 8, tổng là 28. Với n = 100.000, tổng là 4.999.950.000 lượt dịch theo mô hình. Đây là số lượt xử lý vị trí, không phải số nano giây.

Nếu viết phép tính bằng `int`, tích `n * (n - 1)` có thể tràn trước khi chia 2. Ví dụ thực hành dùng `long` ngay từ toán hạng đầu tiên. Cần phân biệt lỗi tràn của phép đếm trong ví dụ với giới hạn kích thước danh sách thật.

Thêm các giá trị 1, 2, 3 lần lượt ở đầu cũng đảo thứ tự thành `[3, 2, 1]`. Thay đổi thuật toán để nhanh hơn phải giữ đúng thứ tự mà yêu cầu cuối cùng cần.

Nếu mục tiêu là tạo thứ tự đảo, có thể cân nhắc thêm cuối rồi đảo một lần, hoặc duyệt nguồn theo chiều phù hợp rồi thêm cuối. Lợi ích đến từ việc tránh dời phần đuôi lặp đi lặp lại, không chỉ từ đổi tên phương thức.

### 5.2. Xóa đầu cho đến rỗng

Bắt đầu với n phần tử, liên tục gọi `remove(0)`:

~~~text
(n - 1) + (n - 2) + ... + 1 + 0 = n(n - 1)/2
~~~

Vì vậy, dùng `ArrayList` làm hàng đợi bằng cách thêm cuối và lấy/xóa đầu có thể phát sinh tổng dịch bậc hai khi tháo hết một lô lớn.

Đổi sang đọc `get(cursor++)` có thể tránh dồn mảng trong một số thiết kế chỉ duyệt một lượt, nhưng phần đã đọc vẫn được danh sách giữ nếu chưa được giải phóng theo cách khác. Đây không phải phép thay thế hoàn toàn tương đương cho mọi hàng đợi dài hạn.

### 5.3. Xóa từ cuối cho đến rỗng

Liên tục xóa tại `size()-1` không phải dịch tham chiếu nào. Có n thao tác hằng số, nên tổng công việc xóa là Θ(n).

Hai vòng lặp “xóa đến rỗng” có mục tiêu cuối giống nhau nhưng cách làm khác nhau về số lượng công việc. Nếu chỉ muốn bỏ toàn bộ nội dung, `clear()` còn diễn đạt mục đích trực tiếp hơn; không cần viết một vòng lặp chỉ để làm danh sách rỗng.

### 5.4. Xóa gần giữa nhiều lần cũng cần cộng tổng

Nếu liên tục xóa một vị trí gần đầu trong khi phía sau còn nhiều phần tử, nhiều phần tử sống sót sẽ bị dời lặp lại. Nếu mỗi lần đều xóa ở giữa danh sách hiện tại, độ dài đoạn dịch vẫn tỷ lệ với kích thước còn lại; lặp đủ nhiều lần có thể cho tổng bậc hai.

Không phải mọi chuỗi k lần xóa đều tốn đúng k×n. Một giới hạn thô là O(kn), nhưng công thức cụ thể phụ thuộc vị trí và kích thước ở từng bước. Khi xóa phần đuôi, số dịch có thể bằng 0 suốt chuỗi.

## 6. Gom chèn thành một lô để dịch phần đuôi ít lần hơn

Giả sử danh sách ban đầu có n phần tử, cần chèn k phần tử tại vị trí p, giữ nguyên thứ tự của lô.

### 6.1. Chèn từng phần tử theo vị trí tăng dần

Một đoạn minh họa:

~~~java
for (int offset = 0; offset < block.size(); offset++) {
    values.add(p + offset, block.get(offset));
}
~~~

Sau mỗi lần, kích thước danh sách tăng 1 và vị trí chèn cũng tăng 1. Đoạn đuôi cũ sau p vẫn có n−p phần tử và bị dịch lại k lần.

Số lượt dịch phần đuôi cũ là:

~~~text
k * (n - p)
~~~

Nếu k và n−p cùng lớn, đây là nguồn công việc đáng kể. Công thức này chỉ đếm dịch đoạn, chưa cộng chi phí tăng mảng, đọc nguồn và ghi k phần tử mới.

Nếu thay vào đó cứ chèn mọi phần tử tại cùng p theo thứ tự duyệt nguồn, các phần tử mới trước đó cũng bị đẩy đi và thứ tự lô bị đảo. Khi ấy số lượt dịch là:

~~~text
k * (n - p) + k(k - 1)/2
~~~

Cùng là “vòng lặp chèn k phần tử”, nhưng vị trí chèn vừa ảnh hưởng kết quả vừa ảnh hưởng chi phí.

### 6.2. Dùng addAll(p, block)

Với một collection nguồn riêng, ổn định, `addAll(p, block)` diễn đạt yêu cầu chèn cả lô theo thứ tự nguồn.

Ở triển khai OpenJDK được xét, phần đuôi cũ được mở chỗ cho cả lô trong một bước, thay vì dịch lại cho từng phần tử. Khi không phải tăng mảng và nguồn có thể được xử lý tuyến tính, công việc chính gồm:

~~~text
doc/chuyen k phan tu nguon
+ dich n-p phan tu duoi mot lan
+ ghi k phan tu vao khoang da mo
~~~

Chi phí có dạng O(k + n−p), thay vì phần dịch O(k(n−p)) của cách chèn từng phần tử. Nếu phải tăng mảng, còn thêm chi phí của mảng mới và dữ liệu chuyển sang đó.

Ví dụ `[10, 20, 30, 40]`, p = 1, lô `[7, 8, 9]`:

- Chèn từng phần tử theo p+offset: dịch 3 tham chiếu đuôi mỗi lần, tổng 9.
- Chèn theo lô: dịch 3 tham chiếu đuôi một lần, rồi đặt 3 phần tử mới.
- Cả hai cho `[10, 7, 8, 9, 20, 30, 40]`.

Đừng đọc “3 lượt dịch” thành toàn bộ chi phí của `addAll`: phương thức vẫn phải xử lý lô, có thể cấp bộ nhớ trung gian và có thể tăng mảng. Kết quả so sánh ở đây chỉ cô lập phần công việc do đuôi cũ bị dịch.

Dùng nguồn riêng, không bị thay đổi trong lúc thao tác. Nếu lô là một view chia sẻ cấu trúc với danh sách đích, hãy tạo bản sao nguồn ổn định trước thay vì suy đoán hành vi khi đang chèn vào chính cấu trúc đó.

## 7. Xóa nhiều phần tử: phân biệt xóa đoạn và xóa theo điều kiện

### 7.1. Xóa một đoạn liên tiếp

Muốn xóa chỉ số từ a đến trước b, có thể dùng:

~~~java
values.subList(a, b).clear();
~~~

Điều kiện: `0 <= a <= b <= size()`. `subList` là một view của danh sách gốc, nên `clear` qua view xóa thật các phần tử tương ứng của danh sách gốc; nó không chỉ xóa một bản sao.

Với đoạn không rỗng, k = b−a, triển khai mảng có thể:

1. Dời n−b phần tử phía sau đoạn về bên trái một lần.
2. Bỏ k tham chiếu ở phần cuối cũ.
3. Cập nhật kích thước và trạng thái cấu trúc liên quan.

Phần công việc chính có bậc O((n−b)+k), tức O(n−a). Khoảng xóa và phần đuôi quyết định lượng công việc; không phải xóa k phần tử là chỉ làm k thao tác độc lập vị trí.

Ví dụ n = 10, xóa `[2, 6)`:

~~~text
truoc: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
              <--- xoa ---> <giu va dich>

sau:   [0, 1, 6, 7, 8, 9]
~~~

Chỉ cần dịch bốn phần tử 6, 7, 8, 9 một lần, rồi bỏ bốn tham chiếu cuối cũ.

Nếu gọi `remove(2)` bốn lần, số lượt dịch là 7 + 6 + 5 + 4 = 22. Cùng kết quả nhưng đuôi đã bị dời nhiều lần.

View không phải một danh sách độc lập để giữ rồi tiếp tục thay đổi cấu trúc danh sách gốc tùy ý. Sau khi xóa đoạn, nên tiếp tục thao tác theo thiết kế rõ ràng trên danh sách gốc; không dựa vào các view hoặc bộ lặp cũ để giữ nguyên chỉ số trước đó.

### 7.2. Xóa theo điều kiện

Nếu muốn xóa tất cả phần tử thỏa một điều kiện, có thể dùng:

~~~java
values.removeIf(value -> value % 2 == 0);
~~~

Đây là ví dụ dành cho danh sách số nguyên không chứa `null`. Với dữ liệu có `null`, điều kiện phải xử lý trường hợp đó theo yêu cầu.

Ở OpenJDK 17, `ArrayList` có cách thực hiện `removeIf` riêng: xác định phần tử cần loại rồi nén các phần tử còn giữ. Nó tránh cách gọi xóa từng phần tử khiến cùng một đuôi bị dịch nhiều lần.

Với điều kiện có chi phí O(1), một lượt lọc toàn bộ danh sách có chi phí O(n) theo triển khai này. Phải tính thêm công việc của điều kiện nếu nó làm tìm kiếm, I/O hoặc tính toán nặng. Triển khai cũng có bộ nhớ phụ để đánh dấu; không nên mặc định mọi phép lọc đều dùng O(1) bộ nhớ.

Không khái quát chi tiết này thành lời hứa rằng `removeIf` trên mọi `Collection` đều dùng cùng thuật toán. Khi đánh giá chi phí, cần biết cấu trúc thật đang dùng.

Điều kiện nên chỉ quyết định giữ hay xóa dựa trên dữ liệu, không tự chèn/xóa trong chính danh sách đang lọc. Một phép tối ưu dịch chuyển không thay thế yêu cầu về tính đúng của thao tác.

### 7.3. clear không phải xóa đầu lặp lại

Trong triển khai `ArrayList` đang xét, `clear()` bỏ các tham chiếu đang dùng trong một lượt và đặt kích thước về 0. Nó không cần bảo toàn phần tử sống sót vì không có phần tử nào cần giữ.

Do đó, bỏ toàn bộ n phần tử có thể được làm tuyến tính thay vì gọi `remove(0)` n lần với tổng dịch bậc hai. Không có dịch đuôi vẫn có thể có O(n) công việc xóa tham chiếu; đừng chỉ đếm dịch rồi kết luận `clear` luôn O(1).

## 8. Tính đúng khi xóa trong lúc duyệt

### 8.1. Duyệt tiến rồi tăng chỉ số có thể bỏ sót

Xét `[2, 4, 6, 7, 8]`. Khi đang ở chỉ số 0 và xóa 2, giá trị 4 dịch vào chỉ số 0. Nếu vòng lặp lập tức tăng chỉ số thành 1, nó không kiểm tra 4 nữa.

Đoạn sau **cố ý minh họa lỗi**:

~~~java
for (int index = 0; index < values.size(); index++) {
    if (values.get(index) % 2 == 0) {
        values.remove(index);
    }
}
~~~

Không phải “xóa trong vòng lặp chỉ số luôn sai”; vấn đề là quy tắc cập nhật chỉ số phải tính đến việc đuôi vừa dồn lại. Có thể giữ nguyên chỉ số sau khi xóa, nhưng cách đó vẫn phải trả chi phí dịch cho từng lần xóa.

### 8.2. Duyệt từ cuối giúp giữ chỉ số của phần chưa xét

Nếu chỉ xóa các vị trí đã kiểm tra, duyệt chỉ số giảm dần giúp các phần tử phía trước chưa xét không bị đổi chỉ số. Đây là một cách viết đúng cho nhiều bài toán xóa theo điều kiện.

Tuy nhiên, nó không bảo đảm mọi trường hợp trở thành O(n). Ví dụ danh sách có n phần tử; muốn xóa k phần tử đầu nhưng giữ n−k phần tử cuối. Dù xóa các chỉ số cần xóa từ phải sang trái, phần đuôi sống sót vẫn có thể bị dịch k lần, tạo k(n−k) lượt dịch. Khi k xấp xỉ n/2, lượng công việc vẫn bậc hai.

Duyệt ngược giải quyết một vấn đề về chỉ số; nén theo lô giải quyết một vấn đề khác về công việc lặp.

### 8.3. Iterator.remove giúp thao tác hợp lệ, không đổi mảng thành danh sách liên kết

Dùng `Iterator.remove()` đúng quy tắc có thể xóa phần tử đang duyệt mà phối hợp được trạng thái bộ lặp. Nhưng với `ArrayList`, phía dưới vẫn phải dồn đoạn đuôi khi xóa từng phần tử.

Vì vậy, một vòng lặp iterator xóa nhiều phần tử có thể vẫn có tổng chi phí bậc hai. Sửa lỗi `ConcurrentModificationException` và giảm số tham chiếu bị dịch là hai mục tiêu riêng.

Không sửa cấu trúc trực tiếp qua danh sách trong vòng `for-each` rồi dựa vào việc có hoặc không có ngoại lệ để quyết định đúng sai. Fail-fast chỉ giúp phát hiện một số lỗi sử dụng, không phải cơ chế đồng bộ hay cách bỏ qua chi phí dịch.

### 8.4. remove(1) có thể không xóa giá trị 1

Với `ArrayList<Integer>`:

~~~java
values.remove(1);                   // chon remove(int): xoa chi so 1
values.remove(Integer.valueOf(1));  // chon remove(Object): tim va xoa gia tri 1
~~~

Hai phương thức có cả ý nghĩa và mô hình chi phí khác nhau. Xóa theo giá trị còn phải tìm phần tử phù hợp; nếu tìm được, mới dồn đoạn đuôi sau nó. Không được chỉ nhìn vị trí phần tử cuối cùng để kết luận thao tác tìm-xóa là O(1).

Ví dụ, xóa một giá trị nằm ở cuối bằng `remove(Object)` có thể không cần dịch tham chiếu nào nhưng vẫn phải duyệt nhiều phần tử để tìm. Nếu phép `equals` của phần tử tốn kém, cần cộng cả chi phí so sánh đó.

## 9. Chương trình hoàn chỉnh: kiểm tra kết quả và đếm số dịch theo mô hình

Chương trình sau chạy các thao tác thật trên `ArrayList`, đồng thời tính số dịch từ kích thước và chỉ số trước mỗi thao tác.

Các biến `shifts` là **bộ đếm theo công thức của bài**, không phải số đọc từ một bộ đo nội bộ của JVM. Chương trình không dùng reflection và không đo thời gian. Với các ca chèn nhỏ, dung lượng được dự trữ đủ để tách việc dịch khỏi việc tăng mảng.

### 9.1. Mã nguồn

Lưu thành `ArrayListShiftDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.List;

public class ArrayListShiftDemo {
    static <E> ArrayList<E> reservedCopy(List<E> source) {
        ArrayList<E> result = new ArrayList<>(32);
        result.addAll(source);
        return result;
    }

    static <E> void addAt(ArrayList<E> list, int index, E value) {
        int before = list.size();
        int logicalShifts = before - index;
        list.add(index, value);
        System.out.printf("add(%d, %s): shifts=%d, values=%s%n",
                index, value, logicalShifts, list);
    }

    static <E> void removeAt(ArrayList<E> list, int index) {
        int before = list.size();
        int logicalShifts = before - index - 1;
        E removed = list.remove(index);
        System.out.printf("remove(%d): removed=%s, shifts=%d, values=%s%n",
                index, removed, logicalShifts, list);
    }

    static ArrayList<Integer> numbers(int n) {
        ArrayList<Integer> result = new ArrayList<>(n);
        for (int value = 0; value < n; value++) {
            result.add(value);
        }
        return result;
    }

    public static void main(String[] args) {
        ArrayList<String> trace = reservedCopy(List.of("A", "B", "C", "D", "E"));
        System.out.println("start: " + trace);
        addAt(trace, 0, "X");
        addAt(trace, 3, "Y");
        removeAt(trace, 0);
        removeAt(trace, 2);
        removeAt(trace, trace.size() - 1);

        ArrayList<Integer> front = new ArrayList<>(8);
        long frontInsertShifts = 0;
        for (int value = 1; value <= 8; value++) {
            frontInsertShifts += front.size();
            front.add(0, value);
        }
        System.out.printf("prepend 8: shifts=%d, values=%s%n",
                frontInsertShifts, front);
        long frontRemoveShifts = 0;
        while (!front.isEmpty()) {
            frontRemoveShifts += front.size() - 1;
            front.remove(0);
        }
        System.out.printf("drain front: shifts=%d, remaining=%s%n",
                frontRemoveShifts, front);

        ArrayList<Integer> back = numbers(8);
        long backRemoveShifts = 0;
        while (!back.isEmpty()) {
            int index = back.size() - 1;
            backRemoveShifts += back.size() - index - 1;
            back.remove(index);
        }
        System.out.printf("drain back: shifts=%d, remaining=%s%n",
                backRemoveShifts, back);
        long n = 100_000L;
        System.out.println("formula only, n=100000: " + n * (n - 1) / 2);

        List<Integer> base = List.of(10, 20, 30, 40);
        List<Integer> block = List.of(7, 8, 9);
        ArrayList<Integer> repeated = reservedCopy(base);
        long repeatedShifts = 0;
        for (int offset = 0; offset < block.size(); offset++) {
            int index = 1 + offset;
            repeatedShifts += repeated.size() - index;
            repeated.add(index, block.get(offset));
        }
        ArrayList<Integer> bulk = reservedCopy(base);
        int bulkTailShifts = bulk.size() - 1;
        bulk.addAll(1, block);
        System.out.printf("insert one by one: shifts=%d, values=%s%n",
                repeatedShifts, repeated);
        System.out.printf("insert addAll: tailShifts=%d, values=%s%n",
                bulkTailShifts, bulk);
        System.out.println("same insert result: " + repeated.equals(bulk));

        ArrayList<Integer> repeatedRemoval = numbers(10);
        long repeatedRemovalShifts = 0;
        for (int count = 0; count < 4; count++) {
            repeatedRemovalShifts += repeatedRemoval.size() - 2 - 1;
            repeatedRemoval.remove(2);
        }
        ArrayList<Integer> rangeRemoval = numbers(10);
        int rangeTailShifts = rangeRemoval.size() - 6;
        rangeRemoval.subList(2, 6).clear();
        System.out.printf("remove one by one: shifts=%d, values=%s%n",
                repeatedRemovalShifts, repeatedRemoval);
        System.out.printf("remove range: tailShifts=%d, values=%s%n",
                rangeTailShifts, rangeRemoval);
        System.out.println("same remove result: " + repeatedRemoval.equals(rangeRemoval));

        ArrayList<Integer> wrong = new ArrayList<>(List.of(2, 4, 6, 7, 8));
        for (int index = 0; index < wrong.size(); index++) {
            if (wrong.get(index) % 2 == 0) {
                wrong.remove(index);
            }
        }
        System.out.println("buggy forward i++: " + wrong);
        ArrayList<Integer> backward = new ArrayList<>(List.of(2, 4, 6, 7, 8));
        for (int index = backward.size() - 1; index >= 0; index--) {
            if (backward.get(index) % 2 == 0) {
                backward.remove(index);
            }
        }
        ArrayList<Integer> filtered = new ArrayList<>(List.of(2, 4, 6, 7, 8));
        boolean changed = filtered.removeIf(value -> value % 2 == 0);
        System.out.println("backward removal: " + backward);
        System.out.printf("removeIf: changed=%s, values=%s%n", changed, filtered);

        ArrayList<Integer> byIndex = new ArrayList<>(List.of(1, 2, 3));
        ArrayList<Integer> byValue = new ArrayList<>(List.of(1, 2, 3));
        byIndex.remove(1);
        byValue.remove(Integer.valueOf(1));
        System.out.println("remove(int 1): " + byIndex);
        System.out.println("remove(Integer 1): " + byValue);
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 ArrayListShiftDemo.java
java ArrayListShiftDemo
~~~

### 9.2. Kết quả stdout

~~~text
start: [A, B, C, D, E]
add(0, X): shifts=5, values=[X, A, B, C, D, E]
add(3, Y): shifts=3, values=[X, A, B, Y, C, D, E]
remove(0): removed=X, shifts=6, values=[A, B, Y, C, D, E]
remove(2): removed=Y, shifts=3, values=[A, B, C, D, E]
remove(4): removed=E, shifts=0, values=[A, B, C, D]
prepend 8: shifts=28, values=[8, 7, 6, 5, 4, 3, 2, 1]
drain front: shifts=28, remaining=[]
drain back: shifts=0, remaining=[]
formula only, n=100000: 4999950000
insert one by one: shifts=9, values=[10, 7, 8, 9, 20, 30, 40]
insert addAll: tailShifts=3, values=[10, 7, 8, 9, 20, 30, 40]
same insert result: true
remove one by one: shifts=22, values=[0, 1, 6, 7, 8, 9]
remove range: tailShifts=4, values=[0, 1, 6, 7, 8, 9]
same remove result: true
buggy forward i++: [4, 7]
backward removal: [7]
removeIf: changed=true, values=[7]
remove(int 1): [1, 3]
remove(Integer 1): [2, 3]
~~~

### 9.3. Đọc từng nhóm kết quả

Nhóm `start` đến `remove(4)` cho thấy n được lấy trước từng thao tác, không giữ cố định bằng kích thước ban đầu:

- Thêm đầu khi có 5 phần tử: dịch 5.
- Sau đó thêm tại chỉ số 3 khi có 6 phần tử: dịch 6−3 = 3.
- Xóa đầu khi có 7 phần tử: dịch 7−0−1 = 6.
- Xóa tại 2 khi có 6 phần tử: dịch 6−2−1 = 3.
- Xóa cuối khi có 5 phần tử: dịch 5−4−1 = 0.

Nhóm thêm đầu và tháo đầu có cùng tổng 28 với 8 phần tử. Tháo cuối có tổng dịch bằng 0. Cả hai cách tháo đều làm danh sách rỗng, nhưng lượng công việc khác nhau.

Dòng có n = 100.000 chỉ tính công thức bằng `long`; chương trình không thật sự chạy một vòng lặp dịch hàng tỷ lượt. Nhờ vậy, ví dụ không biến thành một phép thử hiệu năng tốn thời gian để chứng minh phép cộng.

Hai cặp `same ... result: true` xác nhận cách làm từng phần tử và cách theo lô cho cùng nội dung, cùng thứ tự trong dữ liệu thử. `tailShifts` của cách theo lô chỉ đếm phần đuôi cũ, không tính thao tác sao chép nguồn hoặc xóa tham chiếu cuối.

Dòng `buggy forward i++: [4, 7]` cho thấy một số chẵn bị bỏ sót. Duyệt ngược và `removeIf` đều cho `[7]`; việc hai cách đúng cùng kết quả chưa có nghĩa chúng có cùng chi phí trên mọi dữ liệu.

Hai dòng cuối phân biệt overload: `remove(1)` xóa phần tử 2 ở chỉ số 1, còn `remove(Integer.valueOf(1))` xóa giá trị 1.

### 9.4. Phạm vi của bằng chứng

Kết quả chạy xác nhận nội dung, chỉ số và các phép cộng trong những trường hợp đã cho. Nó không tự đo số byte được đọc/ghi, số lệnh máy hay thời gian từng thao tác.

Kết luận bậc tăng đến từ phân tích độ dài đoạn phải xử lý. Hiệu năng thực còn chịu ảnh hưởng JVM, bộ nhớ đệm, kích thước dữ liệu, cấp phát và tải máy. Muốn so sánh thời gian, cần thiết kế phép đo riêng có kiểm soát; không suy ra một tỷ lệ tốc độ cố định từ các bộ đếm này.

## 10. Chọn cách biểu diễn phù hợp với kiểu thao tác

### 10.1. Nhiều đọc theo chỉ số, thêm cuối và duyệt

Đây là kiểu sử dụng phù hợp để cân nhắc `ArrayList`. Các thay đổi thỉnh thoảng ở giữa có thể chấp nhận được, nhất là khi dữ liệu nhỏ hoặc được gom thành lô.

Không cần đổi cấu trúc chỉ vì thấy một thao tác có O(n). Cần xét số lần, quy mô thực tế và phần việc chiếm ưu thế của toàn thuật toán.

### 10.2. Thêm/xóa thường xuyên ở hai đầu

Nếu bài toán là hàng đợi hoặc hàng đợi hai đầu, có thể xem xét `ArrayDeque` và dùng các thao tác như `addLast`, `pollFirst`, `addFirst`, `pollLast`. Cấu trúc này tránh cách phải dồn toàn bộ dãy về chỉ số 0 sau mỗi lần lấy đầu.

`ArrayDeque` có phần lớn thao tác với chi phí hằng số khấu hao, nhưng không cung cấp truy cập phần tử tùy ý bằng chỉ số như `List` và không cho phép `null`. Vì vậy, chuyển cấu trúc cần phù hợp cả yêu cầu API lẫn dữ liệu, theo [tài liệu ArrayDeque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

### 10.3. Chèn/xóa giữa: đừng đổi sang LinkedList theo khẩu hiệu

`LinkedList` có thể cập nhật liên kết với chi phí hằng số khi đã có vị trí thông qua bộ lặp phù hợp. Nhưng `linkedList.add(i, x)` hoặc `remove(i)` còn phải tìm nút ở chỉ số i.

Tài liệu [LinkedList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html) nêu rằng các thao tác theo chỉ số đi từ đầu hoặc cuối, tùy bên nào gần hơn. Vì vậy, thay `ArrayList` bằng `LinkedList` mà giữ nguyên vòng lặp truy cập chỉ số có thể chỉ đổi chi phí dịch mảng thành chi phí đi qua nút.

Cần xét cách tìm vị trí, kiểu duyệt, cấp phát nút, bộ nhớ và tải thực tế. “Chèn giữa O(1)” chỉ có ý nghĩa khi nêu rõ đã có quyền truy cập tới vị trí thích hợp bằng cách nào.

### 10.4. Nhiều thay đổi nhưng có thể xây kết quả mới

Nếu đầu vào không cần bị sửa tại chỗ, đôi khi một lượt duyệt tạo danh sách kết quả rồi thêm cuối dễ hiểu hơn một loạt chèn/xóa ở giữa. Cách này đổi bộ nhớ của danh sách kết quả lấy việc tránh dời cùng phần tử nhiều lần.

Phải kiểm tra ngữ nghĩa: các nơi đang giữ tham chiếu tới danh sách cũ có cần nhìn thấy thay đổi trực tiếp không? Có cần bảo toàn chính đối tượng danh sách không? Tối ưu bằng cách tạo danh sách khác không tự động thay thế được cập nhật tại chỗ.

### 10.5. Tìm vị trí nhanh không làm bước cập nhật nhanh theo cùng bậc

Trong danh sách đã sắp xếp, tìm điểm chèn bằng tìm kiếm nhị phân có thể dùng O(log n) phép so sánh. Sau khi tìm được chỉ số, `ArrayList` vẫn phải mở khoảng trống bằng cách dịch đuôi.

Vì vậy, một lần tìm rồi chèn vẫn có thể là O(n) do bước cập nhật. Hãy tách **tìm vị trí**, **dịch dữ liệu** và **xử lý phần tử** khi phân tích; đừng lấy bậc của bước nhanh nhất làm bậc của toàn thao tác.

## 11. Các lỗi suy luận thường gặp

| Nhận định | Điều cần sửa |
|---|---|
| Truy cập chỉ số O(1), nên chèn tại chỉ số cũng O(1) | Chèn phải mở khoảng trống và giữ thứ tự |
| Đã đặt trước dung lượng thì thêm đầu không phải dịch | Khoảng dự trữ ở cuối không nằm tại vị trí chèn |
| Chèn giữa chỉ dịch một nửa nên không tuyến tính | Một nửa n vẫn có bậc Θ(n) |
| Xóa cuối bằng giá trị chắc chắn O(1) | Tìm theo giá trị có thể cần duyệt cả danh sách |
| Dùng arraycopy thì dịch khối là O(1) | Số vị trí xử lý vẫn tăng theo chiều dài khối |
| Dùng Iterator.remove thì xóa hàng loạt luôn O(n) | Mỗi lần xóa trên ArrayList vẫn có thể dồn đuôi |
| Duyệt ngược làm mọi phép xóa nhanh tuyến tính | Nó giữ chỉ số chưa xét, nhưng có thể dời đuôi sống sót nhiều lần |
| addAll không phải dịch gì vì thêm theo lô | Nó vẫn phải mở chỗ; lợi ích là dịch đuôi ít lần hơn |
| Xóa một đoạn qua subList chỉ ảnh hưởng một bản sao | subList là view, clear tác động tới danh sách gốc |
| Dịch tham chiếu đồng nghĩa sao chép sâu đối tượng | Danh tính các đối tượng phần tử thường được giữ |
| Thêm cuối khấu hao O(1) suy ra thêm đầu cũng vậy | Dịch đầu phát sinh ở từng lần, khác với tăng dung lượng theo đợt |
| Không có tham chiếu dịch thì toàn thao tác bằng 0 chi phí | Còn tìm kiếm, cập nhật, ghi/xóa tham chiếu và công việc khác |

## 12. Bài tập tự kiểm tra

### Bài 1: đếm theo chỉ số

Danh sách có n = 12. Chèn tại i = 4 phải dịch bao nhiêu phần tử? Xóa tại i = 4 trên một danh sách khác cũng có n = 12 phải dịch bao nhiêu?

**Giải thích:** Chèn dịch 12−4 = 8 phần tử. Xóa dịch 12−4−1 = 7. Hai danh sách độc lập được dùng trong câu hỏi để n không thay đổi giữa hai phép tính.

### Bài 2: dung lượng lớn có giúp không?

Danh sách có size = 1.000, đã dành dung lượng 10.000. Thêm một phần tử ở đầu có cần dịch không?

**Giải thích:** Có, cần dịch 1.000 tham chiếu đang có. Dung lượng đủ chỉ giúp tránh tăng mảng cho lần thêm này.

### Bài 3: xóa một đoạn

Danh sách có 20 phần tử. Xóa đoạn `[5, 12)` bằng thao tác theo lô cần dời bao nhiêu phần tử đuôi và bỏ bao nhiêu tham chiếu cuối cũ?

**Giải thích:** Có 20−12 = 8 phần tử đuôi cần dời, và 12−5 = 7 vị trí cuối cũ cần bỏ tham chiếu. Đây là hai phần công việc khác nhau; cả hai đều cần được tính.

### Bài 4: duyệt ngược

Có thể kết luận “xóa các phần tử có chỉ số chẵn bằng vòng lặp chỉ số giảm dần trên ArrayList luôn O(n)” không?

**Giải thích:** Không. Duyệt giảm dần tránh bỏ sót do chỉ số của phần chưa xét, nhưng nhiều phần tử còn giữ phía sau vẫn có thể bị dời nhiều lần. Cần cộng độ dài đoạn đuôi của từng lần xóa, hoặc dùng cách lọc/nén phù hợp.

### Bài 5: chèn lô

Danh sách có n = 1.000, chèn k = 100 phần tử tại p = 200. Nếu chèn từng phần tử theo p+offset, riêng đuôi cũ bị dịch tổng bao nhiêu lượt? Nếu chèn cả lô trong một bước mở chỗ?

**Giải thích:** Đuôi cũ dài 800. Chèn từng phần tử tạo 100×800 = 80.000 lượt dịch đuôi cũ. Mở chỗ cho cả lô chỉ dịch 800 tham chiếu đuôi một lần. Cả hai còn phải xử lý 100 phần tử nguồn; nếu cần tăng mảng, phải cộng công việc đó.

### Bài 6: giữ đúng yêu cầu khi tối ưu

Nếu yêu cầu phải giữ thứ tự `[A, B, C, D]` sau khi xóa B thành `[A, C, D]`, có thể thay B bằng D rồi xóa cuối để thu được `[A, D, C]` nhằm giảm dịch không?

**Giải thích:** Không, kết quả khác thứ tự được yêu cầu. Một phép tối ưu chỉ hợp lệ khi bảo toàn những điều ứng dụng cần quan sát.

Khi gặp vòng lặp thêm hoặc xóa ở đầu và giữa, hãy xác định đoạn đuôi nào phải dịch, độ dài của nó tại từng bước, rồi cộng cho cả chuỗi. Đây là cách thấy được chi phí thật của cấu trúc mảng và chọn việc gom lô, thay thuật toán hoặc đổi cấu trúc bằng một lý do cụ thể.
