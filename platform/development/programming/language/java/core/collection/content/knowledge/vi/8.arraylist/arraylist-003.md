# Độ phức tạp truy cập, tìm kiếm, chèn và xóa trong ArrayList

## 1. Từ một mảng có thể lớn lên đến chi phí của từng thao tác

`ArrayList<E>` là một cách triển khai `List<E>` bằng mảng có thể thay đổi sức chứa. Dữ liệu đang dùng được giữ thành một dãy liên tục theo chỉ số trong mảng bên trong. Khi cần thêm chỗ, danh sách có thể cấp phát mảng lớn hơn và chuyển các tham chiếu sang mảng mới.

Cấu trúc này giải thích đồng thời hai đặc điểm:

- Biết chỉ số thì có thể đi thẳng đến ô tương ứng: đọc hoặc thay thế một phần tử không cần đi qua các phần tử trước nó.
- Chèn hoặc xóa ở giữa mà vẫn giữ thứ tự thì phải dịch phần phía sau: chi phí phụ thuộc vào độ dài đoạn phải dịch.

Vì vậy, câu “ArrayList nhanh” chưa đủ để chọn thuật toán. Cần nói rõ **nhanh với thao tác nào, ở vị trí nào, trên một lần gọi hay cả chuỗi thao tác**.

Ví dụ một danh sách kết quả đọc tuần tự, thường thêm cuối và đôi lúc đọc theo chỉ số thường rất phù hợp với ArrayList. Nếu dùng cùng danh sách làm hàng đợi bằng cách liên tục xóa phần tử đầu, mỗi lần xóa lại phải kéo phần còn lại sang trái.

Bài này phân tích ArrayList trong một luồng, với chỉ số hợp lệ và thao tác thực hiện thành công. Việc khóa, tranh chấp giữa các luồng, thời gian nhập/xuất, lỗi cấp phát bộ nhớ và công việc nghiệp vụ bên ngoài thao tác được tách khỏi mô hình đếm.

Tài liệu [ArrayList của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html) xác nhận truy cập theo chỉ số có chi phí hằng số và thêm cuối có chi phí hằng số khấu hao. Những công thức dịch chuyển bên dưới được suy ra từ cách giữ thứ tự của dãy; các chi tiết về thao tác hàng loạt sẽ được ghi rõ khi dựa trên triển khai OpenJDK 17.

## 2. Đọc ký hiệu trước khi đọc bảng độ phức tạp

### 2.1. Các biến dùng trong bài

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `n` | `size()` ngay trước thao tác, tức số phần tử thực sự đang có |
| `C` | Sức chứa của mảng bên trong; luôn có `C >= n` |
| `i` | Chỉ số chèn, đọc, thay hoặc xóa, tùy phương thức |
| `k` | Số phần tử trong một lô được thêm hoặc xóa |
| `m` | Số thao tác trong một chuỗi; trong bài toán hai collection có thể dùng làm kích thước collection đối chiếu và sẽ nêu riêng |
| `E` | Chi phí của một lần kiểm tra bằng `equals` |
| `P` | Chi phí của một lần chạy điều kiện lọc |

Không trộn `size` với `capacity`. Danh sách có thể chứa 20 phần tử nhưng đã dành chỗ cho 1.000 phần tử. Một lần `contains` vẫn chỉ xét tối đa 20 phần tử đang dùng, không tìm trong toàn bộ 1.000 ô dự phòng.

### 2.2. O(1), O(n) và Θ(n) nói điều gì?

`O(1)` nghĩa là số bước cơ bản bị chặn bởi một hằng số không tăng theo `n`; không có nghĩa là đúng một lệnh máy hay luôn mất cùng một số nano giây.

`O(n)` mô tả một chặn trên tăng tuyến tính theo `n`. Khi biết chi phí tăng tuyến tính cả về chặn trên lẫn chặn dưới trong trường hợp đang xét, bài dùng `Θ(n)`. Chẳng hạn, dịch đúng `n - 1` tham chiếu khi xóa đầu một danh sách không rỗng có chi phí `Θ(n)` trong mô hình này.

`O(n²)` thường xuất hiện khi một thao tác tuyến tính được lặp lại theo kích thước danh sách. Một vòng lặp có `n` lượt không tự động là `O(n)`: phải tính cả công việc trong mỗi lượt.

### 2.3. Trường hợp xấu nhất khác với khấu hao

- **Một lần gọi ở trường hợp xấu nhất:** tìm lần gọi tốn nhiều công việc nhất ở kích thước hiện tại.
- **Chi phí khấu hao:** xét tổng công việc của cả chuỗi thao tác rồi phân bổ cho mỗi thao tác.
- **Chi phí trung bình theo dữ liệu:** cần giả định phân bố dữ liệu hoặc xác suất; không đồng nghĩa với khấu hao.

Với thêm cuối, khấu hao không dựa vào giả định “ít khi gặp dữ liệu xấu”. Nó dựa vào việc một lần mở rộng mảng tạo ra chỗ trống để nhiều lần thêm sau đó không phải mở rộng nữa.

## 3. Bảng tra cứu cốt lõi

Bảng sau giả sử đọc/ghi một tham chiếu và so sánh phần tử đều có chi phí hằng số. `n` là kích thước trước thao tác. Khi `equals` đắt, phải cộng chi phí so sánh như phần 5.

| Thao tác trên ArrayList | Công việc chính | Chi phí cần nhớ |
| --- | --- | --- |
| `size()`, `isEmpty()` | Đọc thông tin kích thước | `Θ(1)` |
| `get(i)` | Kiểm tra chỉ số rồi đọc một ô | `Θ(1)` |
| `set(i, value)` | Kiểm tra chỉ số, đọc giá trị cũ và thay một ô | `Θ(1)` |
| `contains(value)`, `indexOf(value)` | Tìm từ đầu tới lần xuất hiện đầu tiên | Tốt nhất `Θ(1)`; xấu nhất `Θ(n)` |
| `lastIndexOf(value)` | Tìm từ cuối về lần xuất hiện cuối cùng | Tốt nhất `Θ(1)`; xấu nhất `Θ(n)` |
| `add(value)` | Ghi cuối; đôi lúc mở rộng mảng | Không mở rộng: `Θ(1)`; một lần mở rộng: `Θ(n)`; khấu hao: `O(1)` |
| `add(i, value)` | Dịch `n - i` phần tử; có thể còn phải mở rộng | Không mở rộng: `Θ(n - i + 1)`; xấu nhất `Θ(n)` |
| `remove(i)` | Dịch `n - i - 1` phần tử, bỏ tham chiếu cuối | `Θ(n - i)`; xóa cuối là `Θ(1)`, xóa đầu là `Θ(n)` |
| `remove(value)` | Tìm lần xuất hiện đầu tiên rồi dịch phần sau | Xấu nhất `Θ(n)`; không thể coi là xóa cuối `O(1)` dù giá trị nằm cuối |
| Duyệt toàn danh sách một lượt | Đọc từng phần tử | `Θ(n)`, chưa tính phần xử lý từng phần tử |
| `clear()` trong OpenJDK 17 | Bỏ các tham chiếu đang dùng | `Θ(n)` với danh sách không rỗng |

Giới hạn chỉ số:

- `get`, `set`, `remove(int)`: `0 <= i < n`.
- `add(int, E)`: `0 <= i <= n`, vì được phép chèn vào vị trí ngay sau phần tử cuối.

Những kết luận trên gắn với **ArrayList**. Biến có kiểu khai báo `List<E>` không làm thay đổi đối tượng thực tế, nhưng giao diện List không bảo đảm mọi cách triển khai đều có cùng chi phí truy cập theo chỉ số.

## 4. Truy cập theo chỉ số: vì sao get và set là O(1)?

Có thể hình dung phần dữ liệu đang dùng như sau:

```text
index:     0     1     2     3
element:  [A]   [B]   [C]   [D]
size = 4; các ô dự phòng nếu có nằm phía sau
```
Với `get(2)`, danh sách đã biết ô cần đọc. Nó không cần kiểm tra A rồi B để đến C.

`set(2, "X")` thay tham chiếu ở ô 2, trả về giá trị cũ và không đổi kích thước. Cũng không có phần đuôi nào phải dịch.

Phân biệt ba thao tác dễ nhầm:

```java
// Đoạn minh họa, giả sử items đã có ít nhất ba phần tử.
items.get(2);       // Đọc phần tử đang ở vị trí 2.
items.set(2, "X");  // Thay phần tử ở vị trí 2.
items.add(2, "X");  // Chèn X, đẩy phần tử cũ ở vị trí 2 sang phải.
```
Cùng một chỉ số nhưng `set` và `add` có công việc khác nhau. Không được lấy chi phí `set` để suy ra chi phí chèn.

Nếu sau khi gọi `get(i)` ta xử lý một tài liệu lớn, phân tích chuỗi hoặc gọi dịch vụ mạng, chi phí đó thuộc công việc sử dụng phần tử. `get(i)` có chi phí hằng số không biến toàn bộ biểu thức nghiệp vụ thành hằng số.

Tương tự, ép kiểu, tự động bỏ hộp một `Integer`, hoặc gọi phương thức trên đối tượng lấy ra có thể có hành vi riêng. Bảng độ phức tạp chỉ đang mô tả thao tác của cấu trúc dữ liệu.

## 5. Tìm kiếm theo giá trị: không biết chỉ số thì phải tìm

### 5.1. contains không tận dụng được “truy cập ngẫu nhiên” để tìm ngay một giá trị

Có chỉ số 7 và hỏi “giá trị tại chỉ số 7 là gì?” khác với có giá trị X và hỏi “X nằm ở đâu?”.

ArrayList không duy trì một bảng tra cứu tự động từ mọi giá trị sang chỉ số. `contains` và `indexOf` tìm tuyến tính; việc danh sách có thứ tự không có nghĩa là nó đã được sắp xếp theo giá trị.

Nếu tìm từ đầu và gặp ở chỉ số `i`, cần xét `i + 1` vị trí. Nếu không có giá trị đó, phải xét cả `n` vị trí.

`lastIndexOf` tìm theo hướng ngược lại. Khi vị trí khớp cuối cùng là `i`, số vị trí được xét là `n - i`. Đó vẫn là tìm tuyến tính theo trường hợp xấu nhất.

`null` cũng không cần một loại cấu trúc dữ liệu khác: ArrayList có thể chứa null và tìm null bằng kiểm tra thích hợp. Chi phí vẫn phụ thuộc số vị trí phải xét.

### 5.2. Chi phí equals không phải lúc nào cũng hằng số

Với một khóa nhỏ chứa một số nguyên, so sánh có thể xem là hằng số. Nhưng nếu `equals` duyệt nội dung một chuỗi dài, một mảng hoặc một cấu trúc lồng nhau, mỗi lần so sánh có thể tốn nhiều bước hơn.

Cách phân tích tổng quát hơn là:

```text
Chi phí tìm kiếm
= chi phí đi qua các vị trí
+ tổng chi phí kiểm tra bằng nhau tại các vị trí đã xét.

Nếu mỗi lần equals bị chặn bởi E:
trường hợp xấu nhất có chặn trên O(n + n * E).
```
Trong bảng tra nhanh người ta thường giả sử `E = O(1)` rồi ghi `O(n)`. Khi mô hình dữ liệu không thỏa giả định đó, phải đưa chi phí so sánh trở lại.

### 5.3. Chương trình đếm phép so sánh

Lưu đoạn sau vào `ArrayListSearchCostDemo.java`. Lớp Key chỉ so sánh một số nguyên; bộ đếm giúp nhìn số lần gọi equals, không đo thời gian máy chạy.

```java
import java.util.ArrayList;
import java.util.List;

public class ArrayListSearchCostDemo {
    static final class Key {
        private final int id;
        static int equalsCalls;

        Key(int id) {
            this.id = id;
        }

        @Override
        public boolean equals(Object other) {
            equalsCalls++;
            return other instanceof Key key && id == key.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    static void checkContains(ArrayList<Key> keys, int id) {
        Key.equalsCalls = 0;
        boolean found = keys.contains(new Key(id));
        System.out.println("contains " + id + " = " + found
                + ", equals calls = " + Key.equalsCalls);
    }

    public static void main(String[] args) {
        ArrayList<Key> keys = new ArrayList<>(List.of(
                new Key(1), new Key(2), new Key(3),
                new Key(4), new Key(5)));

        checkContains(keys, 1);
        checkContains(keys, 5);
        checkContains(keys, 99);

        Key.equalsCalls = 0;
        int index = keys.indexOf(new Key(3));
        System.out.println("indexOf 3 = " + index
                + ", equals calls = " + Key.equalsCalls);

        Key.equalsCalls = 0;
        boolean removed = keys.remove(new Key(5));
        System.out.println("remove value 5 = " + removed
                + ", equals calls = " + Key.equalsCalls);

        Key.equalsCalls = 0;
        Key removedByIndex = keys.remove(0);
        System.out.println("remove index 0 id = " + removedByIndex.id
                + ", equals calls = " + Key.equalsCalls);
    }
}
```
Biên dịch và chạy:

```shell
javac --release 17 ArrayListSearchCostDemo.java
java ArrayListSearchCostDemo
```
Kết quả:

```text
contains 1 = true, equals calls = 1
contains 5 = true, equals calls = 5
contains 99 = false, equals calls = 5
indexOf 3 = 2, equals calls = 3
remove value 5 = true, equals calls = 5
remove index 0 id = 1, equals calls = 0
```
Giải thích:

- Tìm 1 gặp ngay phần tử đầu nên có một phép so sánh.
- Tìm 5 ở cuối và tìm 99 không tồn tại đều đi qua đủ năm phần tử.
- `indexOf(3)` trả về chỉ số 2 nhưng phải xét ba vị trí.
- Xóa theo giá trị 5 vẫn phải tìm đủ năm phần tử, dù sau khi tìm thấy không còn phần tử nào phía sau để dịch.
- Xóa theo chỉ số 0 không gọi equals để tìm. Tuy vậy, sau khi 5 đã bị xóa, thao tác này phải dịch ba tham chiếu còn lại: không gọi equals không đồng nghĩa với chi phí hằng số.

Bộ đếm là minh họa hành vi tìm kiếm của ArrayList trong triển khai được chạy, phù hợp với cách tìm tuyến tính trong OpenJDK 17. Không dùng số lần gọi equals của ví dụ làm hợp đồng cho mọi loại List hoặc cho các đối tượng tự thay đổi trong lúc so sánh.

Nếu lặp lại `contains` trên danh sách `n` phần tử cho `q` truy vấn, chặn trên trở thành `O(q * n)` khi coi so sánh là hằng số. Khi `q` tăng cùng `n`, công việc có thể là bậc hai. Cần xem xét toàn bộ mẫu sử dụng, không chỉ một lời gọi riêng lẻ.

## 6. Thêm cuối: O(1) khấu hao không phải O(1) cho mọi lần gọi

### 6.1. Khi còn sức chứa

Nếu `n < C`, một lần `add(value)` chỉ cần ghi phần tử vào ô cuối đang trống và tăng size. Không phải dịch các phần tử đã có.

```text
Trước: [A, B, C, _, _, _]  size = 3
Sau:   [A, B, C, D, _, _]  size = 4

Phần tử cũ không đổi chỉ số.
```
Dấu `_` trong hình biểu diễn chỗ dự phòng, không phải một phần tử mà người dùng có thể get.

### 6.2. Khi mảng đã đầy

Nếu hết sức chứa, cần có mảng đủ lớn để chứa phần tử mới. Việc cấp phát và chuyển dữ liệu làm một lần thêm có chi phí tuyến tính theo kích thước hiện tại trong quá trình tăng trưởng thông thường.

```text
Mảng cũ: [A, B, C, D]         size = capacity = 4
Mảng mới lớn hơn: [A, B, C, D, E, _, ...]
                   sao chép       thêm mới
```
Việc chuyển ở đây là chuyển các **tham chiếu**, không gọi constructor để nhân bản sâu từng đối tượng A, B, C, D. Đối tượng phần tử không tự đổi danh tính vì ArrayList mở rộng mảng.

### 6.3. Vì sao tổng thêm m phần tử vẫn tuyến tính?

Hãy xét một mô hình mảng động minh họa tăng gấp đôi khi đầy. Đây là mô hình dùng để giải thích khấu hao, **không phải cam kết rằng ArrayList luôn tăng gấp đôi**.

Khi sức chứa lần lượt là `1, 2, 4, 8, 16`, số tham chiếu cũ phải chép để đạt sức chứa 16 là:

```text
1 + 2 + 4 + 8 = 15
```
Để có 16 phần tử còn có 16 lần ghi phần tử mới. Tổng công việc theo mô hình đếm này là 31 đơn vị, thay vì 16 lần đều phải chép lại gần 16 phần tử.

Tổng một cấp số nhân tăng theo hệ số lớn hơn 1 có cùng bậc với số phần tử cuối cùng. Vì vậy, trên chuỗi chỉ thêm cuối từ danh sách mới, công việc mở rộng được phân bổ cho nhiều lần thêm: tổng `m` lần thêm là `O(m)`, chi phí khấu hao mỗi lần là `O(1)`.

Tài liệu API không quy định chi tiết hệ số tăng sức chứa. Không viết thuật toán phụ thuộc vào việc “lần sau capacity chính xác bằng bao nhiêu”. Điều cần dựa vào là bảo đảm khấu hao của thao tác thêm cuối.

Nếu bắt đầu từ một danh sách đã rất lớn và ngay lần thêm tiếp theo phải mở rộng, lần đó vẫn có thể tốn `Θ(n)`. Nhìn riêng một đoạn đo rất ngắn không thay thế được phân tích tổng của quá trình tăng trưởng.

### 6.4. Dành trước sức chứa giúp điều gì?

```java
// Đoạn minh họa: expectedCount là ước lượng số kết quả sẽ thu được.
ArrayList<String> results = new ArrayList<>(expectedCount);

// size vẫn bằng 0; mỗi add mới làm tăng số phần tử.
results.add("first");
```
Dành trước đủ chỗ có thể tránh một số lần cấp phát và sao chép trong quá trình thêm. Nó không tạo sẵn các phần tử, không cho phép `get(0)` trên danh sách rỗng và không làm chèn đầu hết phải dịch.

Chi phí cấp phát mảng dự phòng cũng là công việc thật. Nếu dành trước một lượng rất lớn chỉ để dùng vài phần tử, ta đánh đổi bộ nhớ và chi phí khởi tạo để giảm việc mở rộng sau này.

Không gọi `trimToSize()` sau mỗi lần thêm:

```java
// Đoạn minh họa một mẫu sử dụng cần tránh khi liên tục tăng danh sách.
for (String value : input) {
    results.add(value);
    results.trimToSize();
}
```
Thu sức chứa về sát size liên tục có thể làm lần thêm tiếp theo lại phải mở rộng và sao chép. Cả chuỗi có thể thành `Θ(m²)`. Bảo đảm thêm cuối khấu hao không có nghĩa là có thể tùy ý chen các thao tác phá bỏ sức chứa dự phòng mà vẫn giữ tổng chi phí đó.

## 7. Chèn theo chỉ số: đếm đoạn phía sau, rồi xét mở rộng

Với `add(i, value)`, các phần tử cũ ở chỉ số `i` đến `n - 1` phải dịch sang phải để nhường chỗ.

Số tham chiếu phải dịch do việc chèn là:

```text
n - i
```
Ví dụ có `[A, B, C, D]`, `n = 4`, chèn X ở `i = 2`:

```text
Trước: [A, B, C, D]
Dịch:        C -> vị trí 3
                D -> vị trí 4
Sau:   [A, B, X, C, D]

Số phần tử thuộc đoạn dịch: 4 - 2 = 2.
```
Mô tả các mũi tên thể hiện quan hệ vị trí trước–sau; phần sao chép nội bộ phải xử lý vùng chồng lấp đúng cách, không phải một vòng gán tùy tiện từ trái sang phải.

| Vị trí chèn | Số phần tử phải dịch | Hệ quả khi chưa cần mở rộng |
| --- | --- | --- |
| Đầu, `i = 0` | `n` | `Θ(n)` |
| Giữa, `i` xấp xỉ `n / 2` | Xấp xỉ `n / 2` | Vẫn là `Θ(n)` |
| Ngay trước phần tử cuối | 1 | `Θ(1)` cho phần dịch |
| Sau phần tử cuối, `i = n` | 0 | Giống thêm cuối |

Nếu cần mở rộng, phải cộng thêm chi phí cấp phát và sao chép sang mảng lớn hơn. Vì vậy, chèn sát cuối chỉ có chi phí hằng số **khi không phải mở rộng**; trường hợp xấu nhất của một lần chèn vẫn có thể tuyến tính.

Dành trước sức chứa chỉ loại bớt việc mở rộng. Nó không loại bỏ `n - i` phần tử phải dịch để giữ thứ tự.

Một lỗi phân tích phổ biến là cho rằng đã biết chỉ số thì chèn là O(1). Biết chỉ số chỉ giúp xác định điểm chèn nhanh; việc nhường chỗ cho phần tử mới là công việc riêng.

## 8. Xóa: phân biệt chỉ số, giá trị và phần tử cuối

### 8.1. remove(int index)

Sau khi bỏ phần tử ở chỉ số `i`, các phần tử từ `i + 1` đến `n - 1` phải dịch sang trái.

Số tham chiếu phải dịch là:

```text
n - i - 1
```
Ngoài ra còn có công việc hằng số để cập nhật size, trả về phần tử cũ và bỏ tham chiếu thừa ở ô cuối.

Ví dụ:

```text
Trước: [A, B, X, C, D, E]  n = 6
Xóa i = 2:
Sau:   [A, B, C, D, E]

C, D, E phải đổi vị trí: 6 - 2 - 1 = 3 phần tử.
```
Xóa cuối bằng `remove(size() - 1)` không có phần tử phía sau để dịch nên có chi phí hằng số trong ArrayList. Xóa đầu bằng `remove(0)` dịch `n - 1` phần tử nên tuyến tính.

Trong triển khai OpenJDK 17, xóa phần tử không tự thu nhỏ mảng bên trong. Việc bỏ tham chiếu cuối giúp danh sách không giữ một tham chiếu thừa đến đối tượng đã xóa. Nó không bảo đảm đối tượng được thu gom rác ngay: đối tượng có thể còn được tham chiếu ở nơi khác.

### 8.2. remove(Object value)

Phương thức này phải tìm lần xuất hiện đầu tiên bằng quan hệ bằng nhau trước, rồi mới xóa vị trí đã tìm.

Nếu phần tử ở chỉ số `i`:

```text
Chi phí = tìm tới i + dịch đoạn sau i + cập nhật danh sách.

Với so sánh hằng số:
tìm xét i + 1 vị trí;
dịch n - i - 1 tham chiếu.
```
Khi tìm thấy gần đầu, tìm ngắn nhưng đoạn dịch dài. Khi tìm thấy ở cuối, không phải dịch nhưng đoạn tìm dài. Vì vậy, đừng ghi “remove(value) ở cuối là O(1)”: điều đó nhầm với `remove(int)` khi đã có chỉ số cuối.

Nếu không tìm thấy, danh sách không đổi nhưng vẫn có thể đã tìm đủ `n` phần tử. Với equals có chi phí `E`, chặn trên tổng quát là `O(n * E + n)`.

### 8.3. Cẩn thận với List<Integer>

```java
// Đoạn minh họa hai overload, bắt đầu từ hai bản sao khác nhau.
ArrayList<Integer> byIndex = new ArrayList<>(List.of(10, 20, 10));
byIndex.remove(1);                 // Xóa chỉ số 1: còn [10, 10].

ArrayList<Integer> byValue = new ArrayList<>(List.of(10, 20, 10));
byValue.remove(Integer.valueOf(10)); // Xóa giá trị 10 đầu tiên: còn [20, 10].
```
Đây vừa là vấn đề tính đúng vừa là vấn đề chi phí: một phương thức đi thẳng đến chỉ số, phương thức còn lại phải tìm theo giá trị.

### 8.4. Chương trình quan sát trạng thái và chiều dài đoạn dịch

Lưu vào `ArrayListMovementDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ArrayListMovementDemo {
    public static void main(String[] args) {
        ArrayList<String> items = new ArrayList<>(16);
        System.out.println("size after capacity reservation = " + items.size());

        items.addAll(List.of("A", "B", "C", "D"));
        System.out.println("initial = " + items);
        System.out.println("get(2) = " + items.get(2));

        String previous = items.set(1, "B*");
        System.out.println("set returned = " + previous);
        System.out.println("after set = " + items);

        int index = 2;
        int shiftedForInsert = items.size() - index;
        items.add(index, "X");
        System.out.println("insert suffix length = " + shiftedForInsert);
        System.out.println("after insert = " + items);

        items.add("E");
        System.out.println("after append = " + items);

        int shiftedForRemove = items.size() - index - 1;
        String removed = items.remove(index);
        System.out.println("removed at index 2 = " + removed);
        System.out.println("remove suffix length = " + shiftedForRemove);
        System.out.println("after remove = " + items);

        String removedLast = items.remove(items.size() - 1);
        System.out.println("removed last = " + removedLast);
        System.out.println("final = " + items);
    }
}
```
Biên dịch và chạy:

```shell
javac --release 17 ArrayListMovementDemo.java
java ArrayListMovementDemo
```
Kết quả:

```text
size after capacity reservation = 0
initial = [A, B, C, D]
get(2) = C
set returned = B
after set = [A, B*, C, D]
insert suffix length = 2
after insert = [A, B*, X, C, D]
after append = [A, B*, X, C, D, E]
removed at index 2 = X
remove suffix length = 3
after remove = [A, B*, C, D, E]
removed last = E
final = [A, B*, C, D]
```
Các biến `shiftedForInsert` và `shiftedForRemove` tính chiều dài đoạn phải dịch theo công thức. Chương trình không đọc mảng nội bộ, không đo số lệnh máy và không đếm phần sao chép do mở rộng.

Danh sách được dành trước sức chứa 16, còn ví dụ chỉ dùng tối đa sáu phần tử, nên không phải mở rộng trong chuỗi này. Nhờ đó có thể tập trung vào khác biệt giữa thay một ô, chèn, thêm cuối và xóa.

## 9. Từ một thao tác đến cả thuật toán

### 9.1. Thêm cuối n phần tử

```java
// Đoạn minh họa; input có n phần tử.
ArrayList<String> output = new ArrayList<>();
for (String value : input) {
    output.add(value);
}
```
Tổng thêm là `O(n)` theo khấu hao, giả sử việc lấy từng phần tử từ input có chi phí phù hợp và không chen thao tác thu sức chứa liên tục.

### 9.2. Thêm đầu n lần

```java
// Đoạn minh họa xây dựng danh sách bằng cách chèn đầu.
ArrayList<String> output = new ArrayList<>();
for (String value : input) {
    output.add(0, value);
}
```
Lần lượt phải dịch `0, 1, 2, ..., n - 1` phần tử. Tổng là:

```text
0 + 1 + ... + (n - 1) = n * (n - 1) / 2 = Θ(n²)
```
Tổng chi phí mở rộng mảng không cứu được phần dịch bậc hai này. Ngoài ra, thứ tự kết quả bị đảo so với thứ tự input. Nếu muốn đảo một danh sách đã có, nên chọn thuật toán diễn đạt rõ mục tiêu thay vì vô tình tạo ra chi phí chèn đầu lặp lại.

### 9.3. Xóa đầu đến khi rỗng

```java
// Đoạn minh họa.
while (!items.isEmpty()) {
    items.remove(0);
}
```
Số phần tử phải dịch là `n - 1, n - 2, ..., 0`, tổng `Θ(n²)`. Nếu mục tiêu chỉ là bỏ toàn bộ nội dung, `clear()` diễn đạt đúng mục tiêu và duyệt các tham chiếu đang dùng một lần trong OpenJDK 17.

Nếu mục tiêu là lấy phần tử theo cơ chế hàng đợi, nên chọn cấu trúc có thao tác ở đầu phù hợp, chẳng hạn Deque. Không dùng `clear()` để thay một nghiệp vụ cần xử lý từng phần tử.

### 9.4. Xóa cuối đến khi rỗng

```java
// Đoạn minh họa.
while (!items.isEmpty()) {
    items.remove(items.size() - 1);
}
```
Mỗi lần xóa cuối có chi phí hằng số; `n` lần là `Θ(n)`. Thứ tự lấy ra là từ cuối về đầu, nên chỉ áp dụng nếu phù hợp yêu cầu.

### 9.5. Duyệt bằng get có tuyến tính không?

```java
// Đoạn minh họa; xử lý mỗi phần tử trong O(1).
for (int i = 0; i < items.size(); i++) {
    String value = items.get(i);
    consume(value);
}
```
Trên ArrayList, size và get đều hằng số nên một lượt đọc như vậy là `Θ(n)`, chưa tính `consume`. Duyệt foreach hoặc iterator cũng tuyến tính cho một lượt đi qua toàn bộ dữ liệu.

Kết luận này không được chuyển nguyên sang mọi List. Đặc biệt, không chọn một thuật toán dùng nhiều get(i) chỉ vì tham số có kiểu List; phải biết đặc điểm của cách triển khai hoặc chọn cách duyệt phù hợp.

## 10. Thao tác hàng loạt: một lời gọi vẫn có thể làm nhiều việc

Các phân tích chi tiết trong phần này dựa trên [mã nguồn ArrayList của OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/ArrayList.java), với collection nguồn thông thường, không bị thay đổi đồng thời. Chúng giúp hiểu công việc nội bộ, không phải lời hứa về mọi cách triển khai Collection hay mọi phiên bản tương lai.

### 10.1. addAll ở cuối

Giả sử thêm lô `k` phần tử. Ít nhất phải lấy và ghi `k` phần tử mới:

- Đủ sức chứa: thông thường `O(k)`.
- Phải mở rộng: thông thường `O(n + k)`.

Phải tính cả việc lấy dữ liệu từ collection nguồn. Nếu collection nguồn có cách chuyển sang mảng đắt hoặc có hành vi đặc biệt, không thể tự coi phần này miễn phí.

Không ghi `addAll(batch)` là `O(1)` chỉ vì nó là một lời gọi. Bảo đảm khấu hao hằng số của `add(value)` áp dụng cho thêm **một** phần tử cuối, không có nghĩa thêm một lô tùy ý là hằng số.

### 10.2. addAll(i, batch)

Nếu chưa cần mở rộng, chèn cả lô cần:

```text
lấy và ghi k phần tử mới
+ dịch n - i phần tử cũ phía sau điểm chèn.

Chi phí thông thường: O(k + n - i).
```
Khi phải mở rộng, chặn trên thông thường là `O(n + k)`.

Chèn cả lô một lần thường tránh việc dịch đi dịch lại cùng phần đuôi như khi gọi `add(i + offset, value)` nhiều lần. Phải giữ đúng thứ tự lô theo yêu cầu; không đánh đổi tính đúng để giảm phép dịch.

### 10.3. Xóa một đoạn bằng subList(...).clear()

Với đoạn `[from, to)`, số phần tử xóa là `k = to - from`. Khi `k > 0`, triển khai OpenJDK 17 có thể dồn phần đuôi sau `to` sang trái một lần, rồi bỏ các tham chiếu thừa.

Công việc tỷ lệ với:

```text
(n - to) + k
= phần đuôi cần dồn + các ô tham chiếu cần bỏ.
```
Đây có thể tốt hơn xóa từng phần tử ở cùng một vị trí rồi lặp lại việc dịch đuôi. Với đoạn rỗng, không suy ra rằng vẫn cần dịch toàn danh sách; phải xét trường hợp không có phần tử để xóa riêng.

`subList` là một vùng nhìn vào danh sách gốc. Lệnh clear trên vùng nhìn này thay đổi danh sách gốc; nó không tạo một bản sao độc lập của đoạn.

### 10.4. removeIf

Với ArrayList của OpenJDK 17, removeIf xác định các vị trí cần xóa rồi dồn các phần tử còn lại, tránh dịch toàn phần đuôi sau từng lần xóa riêng lẻ.

Nếu điều kiện lọc có chi phí `P`, phân tích thông thường là `O(n * P + n)`; khi `P = O(1)` thì tuyến tính. Triển khai có thể dùng bộ nhớ đánh dấu bổ sung khi có phần tử cần xóa. Đừng suy ra rằng một lời gọi removeIf luôn không cần thêm bộ nhớ.

Điều kiện lọc nên mô tả việc giữ/xóa phần tử, không tự sửa cấu trúc của chính danh sách đang được lọc. Nếu điều kiện gọi `otherList.contains(value)` và otherList dài, chi phí kiểm tra lồng nhau vẫn có thể làm toàn phép lọc thành bậc hai.

Đây là chi phí của cách ArrayList triển khai thao tác, không phải bảo đảm chung rằng removeIf của mọi Collection đều tuyến tính.

### 10.5. removeAll và retainAll phụ thuộc collection đối chiếu

Hai thao tác này phải kiểm tra các phần tử của danh sách có thuộc collection đối chiếu hay không. Nếu collection đối chiếu cũng là một danh sách dài `m`, và mỗi lần contains phải tìm tuyến tính, chặn trên có thể là `O(n * m)` khi so sánh hằng số.

Không kết luận “xóa hàng loạt luôn O(n)” chỉ từ tên phương thức. Cần nhìn cả cấu trúc nhận thao tác và cấu trúc được dùng để kiểm tra thuộc tập.

Nếu cần kiểm tra thuộc tập nhiều lần, có thể cân nhắc tạo một cấu trúc tra cứu phù hợp trước. Phải tính cả chi phí xây dựng, bộ nhớ và quy tắc bằng nhau của cấu trúc đó; không tự đổi quy tắc nhận diện phần tử.

## 11. Tính đúng khi xóa và chi phí khi xóa là hai câu hỏi riêng

Khi xóa bằng chỉ số trong một vòng lặp tiến, phần tử kế tiếp bị kéo vào vị trí vừa xóa. Nếu vẫn tăng chỉ số, có thể bỏ qua phần tử đó.

Một iterator cho phép xóa thông qua `iterator.remove()` theo đúng quy tắc duyệt. Nhưng trên ArrayList, nó vẫn phải thực hiện công việc xóa và dịch của mảng. Iterator giúp quản lý vị trí duyệt; nó không biến xóa giữa ArrayList thành thao tác hằng số.

Lưu chương trình sau vào `ArrayListRemovalPatternsDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public class ArrayListRemovalPatternsDemo {
    public static void main(String[] args) {
        List<Integer> source = List.of(2, 4, 6, 1, 3, 8);

        ArrayList<Integer> skipped = new ArrayList<>(source);
        for (int i = 0; i < skipped.size(); i++) {
            if (skipped.get(i) % 2 == 0) {
                skipped.remove(i);
            }
        }
        System.out.println("incorrect forward removal = " + skipped);

        ArrayList<Integer> byIterator = new ArrayList<>(source);
        for (Iterator<Integer> it = byIterator.iterator(); it.hasNext();) {
            if (it.next() % 2 == 0) {
                it.remove();
            }
        }
        System.out.println("iterator removal = " + byIterator);

        ArrayList<Integer> byPredicate = new ArrayList<>(source);
        int[] tested = {0};
        byPredicate.removeIf(value -> {
            tested[0]++;
            return value % 2 == 0;
        });
        System.out.println("removeIf = " + byPredicate);
        System.out.println("predicate calls = " + tested[0]);

        ArrayList<String> letters = new ArrayList<>(
                List.of("A", "B", "C", "D", "E", "F"));
        letters.subList(1, 4).clear();
        System.out.println("after clearing [1, 4) = " + letters);

        ArrayList<Integer> fromFront = new ArrayList<>(source);
        long frontShiftCount = 0;
        while (!fromFront.isEmpty()) {
            frontShiftCount += fromFront.size() - 1L;
            fromFront.remove(0);
        }

        ArrayList<Integer> fromEnd = new ArrayList<>(source);
        long endShiftCount = 0;
        while (!fromEnd.isEmpty()) {
            int last = fromEnd.size() - 1;
            endShiftCount += fromEnd.size() - last - 1L;
            fromEnd.remove(last);
        }
        System.out.println("front removal suffix total = " + frontShiftCount);
        System.out.println("end removal suffix total = " + endShiftCount);
    }
}
```
Biên dịch và chạy:

```shell
javac --release 17 ArrayListRemovalPatternsDemo.java
java ArrayListRemovalPatternsDemo
```
Kết quả:

```text
incorrect forward removal = [4, 1, 3]
iterator removal = [1, 3]
removeIf = [1, 3]
predicate calls = 6
after clearing [1, 4) = [A, E, F]
front removal suffix total = 15
end removal suffix total = 0
```
Đọc kết quả theo hai góc:

1. **Tính đúng:** vòng lặp tiến sai còn sót 4. Sau khi xóa 2 ở vị trí 0, giá trị 4 đã dịch về 0 nhưng lượt kế tiếp đi thẳng đến vị trí 1.
2. **Cơ chế xóa:** iterator.remove cho đúng `[1, 3]`, nhưng mỗi lần vẫn có thể phải dịch phần đuôi.
3. **Lọc hàng loạt:** removeIf cũng cho `[1, 3]`; với điều kiện đơn giản, ArrayList có thể xử lý theo các lượt tuyến tính thay vì một chuỗi dịch đuôi sau từng phần tử.
4. **Xóa đoạn:** `subList(1, 4).clear()` bỏ B, C, D; cận phải 4 không nằm trong đoạn.
5. **Tổng dịch chuyển:** sáu lần xóa từ đầu có `5 + 4 + 3 + 2 + 1 + 0 = 15` phần tử thuộc các đoạn dịch; xóa từ cuối không cần dịch phần tử nào.

Các tổng trong chương trình là số tham chiếu thuộc đoạn cần dịch được tính bằng công thức, không phải thời gian chạy thực tế. Các phép xóa cuối vẫn có công việc cập nhật size và bỏ tham chiếu, nên tổng số dịch bằng 0 không có nghĩa toàn thuật toán không tốn công việc.

Duyệt từ cuối về đầu có thể tránh bỏ sót khi xóa theo chỉ số, nhưng không bảo đảm mọi mẫu xóa trở thành tuyến tính. Nếu xóa nhiều phần tử ở giữa mà phía sau vẫn còn nhiều phần tử được giữ, cùng phần đuôi vẫn có thể bị dịch nhiều lần.

## 12. Sức chứa, bộ nhớ và thời gian đo thực tế

### 12.1. clear không nhất thiết giải phóng toàn bộ mảng dự phòng

Trong OpenJDK 17, clear bỏ tham chiếu của các phần tử đang dùng và đặt size về 0, nhưng giữ mảng bên trong để có thể tái sử dụng sức chứa. Vì thế:

- clear có thể làm các đối tượng phần tử đủ điều kiện thu gom rác nếu không còn tham chiếu nào khác.
- Không suy ra rằng toàn bộ bộ nhớ dành cho mảng đã được trả ngay.
- Có thể cân nhắc `trimToSize()` khi thực sự muốn giảm sức chứa giữ lại; đây là một thao tác có chi phí và không nên lặp theo từng lần thêm.

Nếu thay cả biến bằng một ArrayList mới, mảng cũ chỉ có thể được thu gom khi không còn tham chiếu giữ nó. Các vùng nhìn hoặc đối tượng khác còn giữ danh sách có thể làm vòng đời dữ liệu dài hơn dự kiến.

### 12.2. Big O không thay thế phép đo, phép đo cũng không thay thế Big O

Hai thao tác cùng O(n) có thể có hằng số rất khác. Sao chép một đoạn tham chiếu liên tục có thể được JVM tối ưu tốt, nhưng vẫn có công việc tăng theo số tham chiếu. Các yếu tố như bố trí bộ nhớ, bộ nhớ đệm, cấp phát, thu gom rác và JIT ảnh hưởng thời gian đo.

Không dùng một lần `System.nanoTime()` quanh thao tác trên danh sách rất nhỏ để kết luận độ phức tạp. Ở kích thước nhỏ, nhiễu đo và chi phí gọi hàm có thể che khuất xu hướng.

Một quy trình đánh giá hợp lý là:

1. Xác định chính xác thao tác, vị trí và kích thước đầu vào.
2. Đếm công việc theo mô hình để dự đoán xu hướng khi n tăng.
3. Nếu cần đo thời gian, chuẩn bị dữ liệu và môi trường kiểm thử có kiểm soát; tách việc tạo dữ liệu hoặc in kết quả khỏi phần đo khi chúng không thuộc công việc cần đánh giá.
4. Đo trên nhiều kích thước và kiểm tra kết quả có phù hợp dự đoán không.
5. Dùng công cụ benchmark JVM phù hợp khi cần so sánh hiệu năng đáng tin cậy.

Các chương trình trong bài cố ý in kết quả và đếm phép so sánh/chiều dài đoạn dịch để học cơ chế. Chúng không phải benchmark so sánh tốc độ các collection.

## 13. Chọn thuật toán dựa trên mẫu thao tác

| Nhu cầu | Nhận định với ArrayList |
| --- | --- |
| Đọc nhiều theo chỉ số, thay giá trị tại chỉ số | Phù hợp vì get/set hằng số |
| Gom kết quả bằng cách thêm cuối | Phù hợp; xét sức chứa và chi phí khấu hao |
| Duyệt toàn bộ một hoặc vài lượt | Một lượt tuyến tính; giữ phần xử lý từng phần tử trong phân tích |
| Chèn/xóa giữa nhiều lần | Phải tính phần đuôi bị dịch trong từng lần |
| Tìm theo giá trị liên tục trên dữ liệu lớn | Tìm tuyến tính có thể trở thành phần tốn công nhất |
| Thường xuyên lấy và bỏ phần tử đầu | Xóa đầu lặp lại dễ tạo tổng bậc hai; nên xem xét cấu trúc hàng đợi |
| Xóa tất cả theo một điều kiện | Cân nhắc removeIf thay cho nhiều lệnh remove riêng lẻ |
| Chèn một lô hoặc xóa một đoạn | Dùng thao tác hàng loạt có thể giảm việc dịch đi dịch lại |

Một ArrayList đã được sắp xếp có thể dùng tìm kiếm nhị phân với số phép so sánh logarit bằng API thích hợp. Điều kiện bắt buộc là dữ liệu được sắp theo cùng quy tắc tìm; phải cộng chi phí sắp xếp và duy trì thứ tự nếu dữ liệu thay đổi. `contains` và `indexOf` không tự chuyển sang tìm kiếm nhị phân chỉ vì nội dung tình cờ đã tăng dần. Xem điều kiện của [Collections.binarySearch trong Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#binarySearch(java.util.List,T)).

Đừng vội đổi sang danh sách liên kết chỉ từ câu “chèn/xóa nhanh hơn”. Nếu phải tìm vị trí trước mỗi lần chèn/xóa, chi phí tìm cũng là một phần của thuật toán. Cần so tổng công việc với mẫu thao tác thực tế, đồng thời giữ đúng yêu cầu về thứ tự, phần tử trùng và cách truy cập.

Nếu tạo thêm một chỉ mục để tra cứu nhanh bên cạnh ArrayList, việc thêm/xóa có thể làm chỉ số các phần tử thay đổi. Chỉ mục đó cần được cập nhật đúng; tiết kiệm thời gian tìm kiếm không cho phép để dữ liệu phụ lệch khỏi danh sách.

## 14. Các lỗi phân tích phổ biến

| Nhận định sai | Cách phân tích đúng |
| --- | --- |
| “add của ArrayList luôn O(1)” | Thêm cuối O(1) khấu hao; một lần mở rộng có thể O(n); chèn giữa còn phải dịch |
| “Biết i nên add(i, x) và remove(i) đều O(1)” | Biết vị trí không loại bỏ công việc giữ thứ tự của phần đuôi |
| “set(i, x) cũng phải dịch” | set thay một ô; size và chỉ số phần còn lại giữ nguyên |
| “contains O(1) vì ArrayList có RandomAccess” | RandomAccess liên quan truy cập theo chỉ số; tìm theo giá trị vẫn tuyến tính |
| “Xóa giá trị nằm cuối là O(1)” | remove(value) phải tìm; remove(size() - 1) mới đi thẳng đến vị trí cuối |
| “Dùng iterator.remove nên xóa giữa không phải dịch” | Iterator quản lý trạng thái duyệt; mảng vẫn cần dồn phần tử |
| “Một vòng for nghĩa là O(n)” | Phải nhân/cộng chi phí trong mỗi lượt, kể cả tìm và dịch |
| “removeIf luôn O(n), bất kể điều kiện” | Cộng chi phí của điều kiện; điều kiện có tìm tuyến tính lồng nhau có thể làm tổng bậc hai |
| “new ArrayList<>(1000) đã có 1000 phần tử” | Chỉ dành sức chứa; size ban đầu vẫn bằng 0 |
| “clear chỉ gán size = 0 nên O(1)” | OpenJDK 17 còn bỏ các tham chiếu đang dùng |
| “Khấu hao nghĩa là trung bình trên dữ liệu ngẫu nhiên” | Khấu hao xét tổng cả chuỗi, không cần giả định dữ liệu ngẫu nhiên |
| “Một ví dụ chạy rất nhanh chứng minh O(1)” | Thời gian ở một kích thước không chứng minh tốc độ tăng khi n thay đổi |

## 15. Tự kiểm tra bằng cách đếm công việc

### Bài 1: Cùng chỉ số, khác thao tác

Một ArrayList có `n = 1.000`, đủ sức chứa để chèn thêm. Hãy phân tích:

- `get(400)`: đọc trực tiếp một ô, hằng số.
- `set(400, x)`: thay một ô, hằng số.
- `add(400, x)`: dịch `1.000 - 400 = 600` phần tử, tuyến tính theo n khi giữ cùng tỷ lệ vị trí.
- `remove(400)` trên danh sách ban đầu: dịch `1.000 - 400 - 1 = 599` phần tử.

Phải dùng kích thước đúng tại thời điểm thao tác. Nếu thực hiện nối tiếp các lệnh trên cùng một danh sách, lệnh add làm n tăng trước lệnh remove; không được tiếp tục thay n bằng kích thước cũ một cách máy móc.

### Bài 2: Đã có chỉ số cuối hay mới có giá trị cuối?

So sánh `remove(size() - 1)` với `remove(Integer.valueOf(999))` trên ArrayList chứa các số 0 đến 999.

Đáp án: xóa bằng chỉ số cuối không tìm và không dịch nên hằng số. Xóa bằng giá trị 999 phải tìm từ đầu đến cuối nên tuyến tính, dù không cần dịch sau khi đã tìm thấy.

### Bài 3: Tổng thêm đầu

Bắt đầu từ danh sách rỗng, chèn 1.000 phần tử bằng `add(0, value)`. Riêng công việc dịch phần tử có bao nhiêu lượt?

Đáp án: `1.000 * 999 / 2 = 499.500` lượt tham chiếu thuộc các đoạn dịch. Đây chưa bao gồm cấp phát, các lần mở rộng và ghi phần tử mới. Bậc tăng của tổng vẫn là bậc hai.

### Bài 4: Một lô ở giữa

Danh sách có 10.000 phần tử, đủ sức chứa; chèn một lô 200 phần tử tại chỉ số 2.000. Phải xét những phần nào?

Đáp án: lấy/ghi 200 phần tử mới và dịch 8.000 phần tử cũ phía sau điểm chèn. Không thể gọi đây là O(1). Nếu nguồn có cách lấy dữ liệu đắt, phải cộng phần đó.

### Bài 5: Tìm kiếm lồng nhau trong điều kiện lọc

Một ArrayList có n phần tử, removeIf kiểm tra mỗi phần tử bằng `blockedList.contains(value)`; blockedList cũng có n phần tử và các giá trị thường không khớp. Vì sao toàn phép lọc có thể O(n²)?

Đáp án: có n lần chạy điều kiện, mỗi lần tìm có thể xét n phần tử của blockedList. Việc ArrayList dồn phần tử theo các lượt tuyến tính không loại bỏ công việc so sánh bậc hai đã xảy ra trong điều kiện.

### Bài 6: Chứng minh khấu hao bằng mô hình

Dùng mô hình tăng gấp đôi, bắt đầu sức chứa 1 và thêm đến 32 phần tử. Tổng số tham chiếu cũ phải sao chép khi tăng sức chứa là:

```text
1 + 2 + 4 + 8 + 16 = 31
```
Thêm 32 lần ghi phần tử mới cho tổng 63 đơn vị trong mô hình đếm giản lược. Không dùng con số 31 để khẳng định ArrayList thật có cùng các mốc capacity; điều cần rút ra là tổng cấp số nhân tăng tuyến tính theo số phần tử cuối.

Khi phân tích một đoạn mã thực tế, hãy ghi rõ **kích thước tại từng bước, vị trí thao tác, phần phải tìm, phần phải dịch và thời điểm có thể mở rộng**. Những thông tin đó cho phép tự suy ra chi phí thay vì học thuộc một bảng thiếu điều kiện.
