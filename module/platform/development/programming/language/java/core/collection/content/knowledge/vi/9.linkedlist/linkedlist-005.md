# Vì sao chèn giữa không luôn nhanh hơn ArrayList?

## 1. Phải so toàn bộ thao tác mà chương trình thực sự yêu cầu

Câu “LinkedList chèn giữa O(1), ArrayList chèn giữa O(n)” bỏ mất một điều kiện quan trọng: **LinkedList chỉ nối nút trong thời gian hằng số sau khi đã xác định được vị trí nút cần nối**.

Nếu đầu vào của chương trình là một chỉ số ở giữa, chẳng hạn `add(50_000, value)`, LinkedList vẫn phải đi đến vị trí đó. ArrayList xác định ô theo chỉ số trực tiếp nhưng phải dịch phần phía sau. Với một chỉ số ở giữa danh sách lớn, cả hai lời gọi đều có chi phí tuyến tính theo số phần tử trong mô hình thông thường.

Hai loại danh sách làm những công việc khác nhau:

| Cấu trúc | Công việc tốn nhiều bước khi chèn giữa bằng chỉ số |
| --- | --- |
| LinkedList | Lần theo liên kết để tìm vị trí; sau đó tạo và nối nút |
| ArrayList | Nhường chỗ bằng cách dịch các tham chiếu phía sau; có thể còn phải mở rộng mảng |

Cùng O(n) không có nghĩa cùng tốc độ, cũng không xác định bên nào chắc chắn thắng. Cần xét kiểu công việc, bố trí bộ nhớ, cấp phát và cả thuật toán bao quanh lời gọi.

Một ví dụ nghiệp vụ: ứng dụng có danh sách các dòng và muốn chèn một dòng ở vị trí người dùng chọn. Nếu giao diện chỉ gửi số thứ tự dòng, chi phí tìm vị trí trong LinkedList là công việc thật. Nếu bộ xử lý đang duyệt bằng một iterator và chèn ngay tại con trỏ hiện tại, tình huống đã khác.

Bài này phân tích Java 17 trở lên trong một luồng, với các danh sách có thể sửa và dữ liệu không bị thay đổi từ nơi khác trong khi dùng iterator. Các chương trình minh họa tính đúng và số công việc theo mô hình, không phải benchmark tốc độ.

## 2. Định nghĩa rõ “chèn giữa”

### 2.1. Cùng kết quả nhưng có nhiều cách biết vị trí

Giả sử bắt đầu với:

```text
[A, B, C, D]

Muốn chèn X trước C:
[A, B, X, C, D]
```
Đề bài có thể cung cấp:

1. Chỉ số 2.
2. Một giá trị cần tìm, ví dụ “chèn trước phần tử bằng C”.
3. Một ListIterator đã ở ngay trước C.
4. Một lô phần tử cần chèn một lần trước C.

Đó là các đầu vào khác nhau. Không lấy chi phí của trường hợp thứ ba để mô tả mọi lần gọi trong trường hợp thứ nhất hoặc thứ hai.

Giữ tham chiếu đến đối tượng C cũng chưa phải giữ nút nội bộ của LinkedList. C có thể xuất hiện nhiều lần trong danh sách; cùng một đối tượng phần tử có thể được nhiều nút tham chiếu. API LinkedList không cho người gọi một Node công khai để truyền trực tiếp vào lệnh chèn.

### 2.2. Các biến dùng để đếm

| Ký hiệu | Ý nghĩa |
| --- | --- |
| n | Số phần tử ban đầu, trước phép chèn đang xét |
| i | Chỉ số điểm chèn; 0 <= i <= n |
| k | Số phần tử cần chèn trong một lô |
| s = n - i | Số phần tử cũ phía sau điểm chèn |
| d | Số liên kết cần đi qua để định vị trong LinkedList |

Khi i nằm xấp xỉ n/2, s và d đều có bậc tuyến tính theo n. Khi chèn rất gần đầu hoặc cuối, chi phí tương đối có thể khác; không thay mọi vị trí bằng một nhãn “giữa” mơ hồ.

### 2.3. Thời gian một thao tác là tổng nhiều phần

```text
Tổng công việc
= tìm điểm chèn
+ tạo chỗ hoặc tạo nút
+ ghi phần tử/cập nhật liên kết
+ cập nhật trạng thái danh sách
+ công việc phụ mà thuật toán yêu cầu.
```
Việc tạo đối tượng phần tử nghiệp vụ có thể là một bước riêng. Ví dụ, xây dựng một tài liệu lớn rồi chèn vào danh sách không nên được dùng để kết luận về chi phí riêng của cấu trúc nếu hai phép đo tạo tài liệu khác nhau.

## 3. LinkedList: nối nhanh sau khi đã đến nơi

### 3.1. Việc nối nút là cục bộ

LinkedList là danh sách liên kết đôi. Một nút giữ tham chiếu đến phần tử và hai nút hàng xóm.

```text
Trước: ... <-> B <-> C <-> ...
Sau:   ... <-> B <-> X <-> C <-> ...
```
Sau khi biết nút C và nút đứng trước nó, tạo X rồi nối các hàng xóm chỉ cần số phép gán bị chặn bởi hằng số. Không phải dịch tất cả nút phía sau sang vị trí lưu trữ mới.

Nhưng điều kiện “sau khi biết nút” là phần không được bỏ qua.

### 3.2. Chỉ số không tự biến thành một nút

Theo [LinkedList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html), truy cập bằng chỉ số đi từ đầu hoặc cuối, tùy phía nào gần vị trí hơn.

Trong triển khai OpenJDK 17, với i < n, có thể hình dung số bước qua liên kết đến nút ở i là:

```text
d = min(i, n - 1 - i)
```
Để chèn trước nút đó, tổng công việc là tìm nút cộng tạo và nối nút mới:

```text
T_LinkedList(add(i, x))
= O(1 + d) + O(1)
= O(1 + d).
```
Với i xấp xỉ n/2, tổng là O(n), và số bước tìm tăng tuyến tính. Trường hợp i = n là thêm cuối, có thể dùng last trực tiếp nên không áp công thức chỉ số phần tử i < n cho điểm chèn sau cùng.

Nếu tạo `listIterator(i)` ở giữa, việc khởi tạo iterator cũng phải đến vị trí đó. Gọi constructor của iterator trước dòng đo không làm chi phí tìm biến mất khỏi tác vụ tổng thể; nó chỉ đổi phần nào của tác vụ đang được đo.

### 3.3. Nếu đã giữ một iterator hợp lệ

Khi thuật toán đang đi qua danh sách bằng một ListIterator và chèn ngay tại con trỏ hiện tại, LinkedList không cần bắt đầu lại việc tìm chỉ số. Khi đó, một lần ListIterator.add có thể tạo và nối nút với số thao tác cấu trúc hằng số.

Đây là lợi thế có thật trong mẫu thao tác phù hợp. Tuy nhiên:

- Phải tính chi phí đến vị trí ban đầu hoặc đi tuần tự đến đó.
- Iterator phải còn hợp lệ theo hợp đồng sử dụng.
- Nếu mỗi lần lại tạo một iterator mới ở giữa, có thể lặp lại chi phí tìm.
- Nếu điểm chèn nhảy xa liên tục, giữ một con trỏ không tự làm việc di chuyển đến mọi điểm mới thành hằng số.

Không nên gọi chi phí tìm là “không công bằng” nếu yêu cầu ứng dụng thật sự cung cấp vị trí bằng chỉ số. Cũng không nên ép tìm lại mỗi lần nếu thuật toán thực sự đã có một con trỏ hợp lệ. Cần mô tả đúng đầu vào và trạng thái có sẵn.

## 4. ArrayList: đi thẳng đến chỉ số nhưng phải nhường chỗ

### 4.1. Số phần tử phải dịch

ArrayList giữ một dãy tham chiếu trong mảng bên trong. Chèn x tại i cần đưa các tham chiếu cũ từ i đến n - 1 sang phải.

```text
Số tham chiếu phải dịch do chèn = n - i = s.
```
Nếu mảng đã đủ sức chứa:

```text
T_ArrayList(add(i, x)) = O(1 + n - i).
```
Chèn giữa có số tham chiếu dịch tăng tuyến tính. Chèn gần cuối dịch ít hơn. Nếu i = n, không có đoạn phía sau để dịch.

### 4.2. Khi hết sức chứa

Nếu cần mở rộng, ArrayList còn phải cấp phát mảng lớn hơn và sao chép các tham chiếu cũ. Một lần chèn có thể phải trả cả chi phí tăng sức chứa lẫn chi phí dịch đoạn đuôi.

Dành trước sức chứa có thể giảm phần mở rộng, nhưng không làm đoạn phía sau điểm chèn hết phải dịch.

Tài liệu [ArrayList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html) bảo đảm thêm cuối có chi phí hằng số khấu hao. Đừng dùng bảo đảm đó để nói rằng chèn ở một chỉ số giữa cũng có chi phí hằng số khấu hao: công việc dịch đoạn đuôi vẫn lặp lại khi chèn.

Khi tính tổng tác vụ, chi phí dành trước sức chứa cũng cần được ghi nhận ở đúng giai đoạn. Nếu chỉ muốn đo phần chèn khi đã đủ chỗ, phải nói rõ điều kiện đó.

### 4.3. Dịch tham chiếu không phải nhân bản đối tượng

Giả sử phần tử là những tài liệu rất lớn. ArrayList không phải sao chép sâu nội dung tất cả tài liệu phía sau khi chèn. Nó chuyển các tham chiếu trong mảng.

```text
Mảng trước: [ref A, ref B, ref C, ref D]
Mảng sau:   [ref A, ref B, ref X, ref C, ref D]

Các đối tượng A, B, C, D vẫn là các đối tượng cũ.
```
Kích thước sâu của tài liệu không trực tiếp trở thành số byte dữ liệu tài liệu bị sao chép trong thao tác dịch này.

Điều đó không có nghĩa đối tượng lớn không ảnh hưởng hiệu năng toàn chương trình. Đọc/xử lý chúng có thể ảnh hưởng bộ nhớ đệm và tổng thời gian; chỉ cần tách phần đó khỏi việc dịch các ô tham chiếu.

Trong [mã nguồn ArrayList của OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/ArrayList.java), phần dịch được thực hiện bằng thao tác sao chép mảng, còn phần tử mới được ghi vào ô điểm chèn.

## 5. Cùng tuyến tính nhưng những bước cơ bản không giống nhau

### 5.1. Đi qua nút khác với sao chép một vùng tham chiếu

Khi LinkedList tìm đến vị trí giữa, mỗi bước đọc liên kết để biết nút tiếp theo. Các nút là những đối tượng riêng; API không bảo đảm chúng nằm gần nhau trong bộ nhớ.

Khi ArrayList dịch đoạn đuôi, các ô tham chiếu thuộc một vùng dữ liệu mảng. Việc chuyển một vùng như vậy có thể được JVM và phần cứng thực hiện hiệu quả.

Hai công việc đều có số bước tăng theo n nhưng không có cùng hằng số hoặc cùng mẫu truy cập bộ nhớ.

Không được suy:

```text
50.000 tham chiếu phải dịch
> 49.999 liên kết phải đi qua
=> LinkedList chắc chắn nhanh hơn.
```
Một lượt dịch tham chiếu và một bước phụ thuộc qua nút không phải hai đơn vị thời gian bằng nhau. Mô hình đếm giải thích xu hướng tăng; phép đo mới đánh giá thời gian cụ thể.

### 5.2. LinkedList còn có chi phí tạo nút

Trong triển khai [LinkedList của OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/LinkedList.java), mỗi lần chèn tạo một Node giữ item, prev và next.

Nút có thông tin quản lý đối tượng và căn chỉnh tùy JVM. Chèn nhiều phần tử tạo nhiều nút, dù các phần tử cùng trỏ đến một đối tượng nghiệp vụ đã có.

ArrayList có thể chèn vào mảng đã đủ sức chứa mà không tạo một nút riêng cho mỗi phần tử. Khi cần tăng sức chứa nó lại có chi phí cấp phát mảng, nên phải so trên mẫu tăng trưởng thực tế.

Cấp phát nhỏ có thể rất nhanh trên JVM hiện đại, nhưng không miễn phí. Lưu lượng tạo nút, vòng đời nút và thu gom rác có thể ảnh hưởng tổng thời gian và bộ nhớ.

### 5.3. Không có một điểm thắng cố định cho mọi ứng dụng

Không thể từ tên lớp suy ra một quy luật “sau n = X thì LinkedList luôn thắng” mà bỏ qua:

- Vị trí chèn và cách xác định vị trí.
- Số phần tử chèn mỗi lần.
- Sức chứa hiện tại của ArrayList.
- Việc giữ hay tạo lại iterator.
- Kiểu phần tử và công việc bao quanh.
- Phiên bản JVM, phần cứng, tải và trạng thái bộ nhớ.

Một kết quả đo cụ thể có thể có ích cho một tác vụ. Nó phải được báo cùng điều kiện, thay vì biến thành một quy luật của giao diện List.

## 6. Ví dụ chạy được: một lần chèn giữa bằng chỉ số

Lưu vào `MiddleInsertCostModelDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;

public class MiddleInsertCostModelDemo {
    public static void main(String[] args) {
        List<String> seed = List.of("A", "B", "C", "D");
        ArrayList<String> array = new ArrayList<>(16);
        array.addAll(seed);
        LinkedList<String> linked = new LinkedList<>(seed);

        int index = 2;
        array.add(index, "X");
        linked.add(index, "X");

        System.out.println("ArrayList result = " + array);
        System.out.println("LinkedList result = " + linked);
        System.out.println("same result = " + array.equals(linked));

        int n = 100_000;
        int middle = n / 2;
        int arraySuffix = n - middle;
        int linkedHops = Math.min(middle, n - 1 - middle);
        System.out.println("model n = " + n + ", index = " + middle);
        System.out.println("ArrayList suffix references = " + arraySuffix);
        System.out.println("LinkedList locating links = " + linkedHops);
    }
}
```
Biên dịch và chạy:

```shell
javac --release 17 MiddleInsertCostModelDemo.java
java MiddleInsertCostModelDemo
```
Kết quả:

```text
ArrayList result = [A, B, X, C, D]
LinkedList result = [A, B, X, C, D]
same result = true
model n = 100000, index = 50000
ArrayList suffix references = 50000
LinkedList locating links = 49999
```
Phần đầu thực hiện phép chèn thật trên hai danh sách nhỏ và kiểm tra cùng thứ tự kết quả.

Phần sau chỉ tính các đại lượng trong mô hình ở n = 100.000; nó không tạo danh sách 100.000 phần tử và không đo thời gian:

- ArrayList phải dịch đoạn đuôi dài 50.000 tham chiếu nếu chèn tại 50.000.
- LinkedList của mô hình đi từ cuối qua 49.999 liên kết để đến nút ở chỉ số đó trước khi nối.

Hai con số chỉ ra rằng phần tìm của LinkedList không phải số bước hằng số trong tình huống này. Chúng không xác định bên nào chạy nhanh hơn.

ArrayList nhỏ trong chương trình được dành sức chứa 16, trong khi sau chèn chỉ có năm phần tử. Vì vậy, chuỗi minh họa này không phải ví dụ đo một lần mở rộng mảng.

## 7. Chèn nhiều phần tử: thuật toán có thể quan trọng hơn tên lớp

### 7.1. Chèn từng phần tử theo chỉ số tăng dần

Muốn chèn X, Y, Z trước C và giữ thứ tự lô:

```text
Ban đầu: [A, B, C, D]
Sau X:   [A, B, X, C, D]
Sau Y:   [A, B, X, Y, C, D]
Sau Z:   [A, B, X, Y, Z, C, D]
```
Với ArrayList, đoạn cũ C, D bị dịch ba lần. Tổng số tham chiếu thuộc các đoạn dịch là 3 * 2 = 6.

Tổng quát, nếu có k phần tử được chèn theo các chỉ số i, i + 1, ..., i + k - 1, đoạn cũ phía sau dài s = n - i vẫn phải dịch ở mỗi lần:

```text
Tổng số tham chiếu cũ bị dịch = k * s.
```
Đây chưa bao gồm ghi k phần tử mới và các lần mở rộng có thể xảy ra.

Với LinkedList, nếu cũng gọi add(index, value) riêng từng lần, mỗi lời gọi lại cần định vị. Khi điểm chèn nằm giữa và khoảng cách đến đoạn đuôi cũ vẫn lớn, tổng phần tìm có thể có bậc O(k * n), không tự biến thành O(k).

### 7.2. Giữ một ListIterator của LinkedList

Nếu tạo một iterator ở điểm chèn một lần, rồi dùng iterator.add cho cả lô:

```text
Một lần tìm vị trí: O(n) ở giữa.
k lần tạo và nối nút: O(k).
Tổng: O(n + k).
```
Trong công thức trên, O(n) là chặn cho bước định vị ở giữa; nếu đã có iterator vì một lượt duyệt cần thiết trước đó, có thể báo riêng phần k lần chèn là O(k), đồng thời mô tả rõ chi phí của lượt duyệt.

ListIterator có cả hai cách triển khai trên ArrayList và LinkedList, nhưng dùng cùng API không làm chi phí giống nhau. Iterator của ArrayList giữ vị trí logic; chèn ở giữa qua iterator vẫn phải dịch đoạn phía sau.

### 7.3. ArrayList cũng có thao tác chèn cả lô

`addAll(i, batch)` có thể chuyển đoạn phía sau sang phải một lần đủ k ô, rồi ghi k phần tử mới.

Nếu đủ sức chứa và lấy lô nguồn có chi phí thông thường:

```text
Chi phí ArrayList.addAll(i, batch)
= O((n - i) + k).
```
Nếu phải mở rộng, chặn trên thông thường là O(n + k), tính cả phần dữ liệu cũ cần chuyển.

LinkedList.addAll cũng có thể định vị một lần rồi tạo chuỗi k nút mới. Với collection nguồn thông thường, tổng có dạng O(chi phí định vị + k), tức O(n + k) khi chèn giữa.

Vì vậy, so một vòng chèn từng phần tử vào ArrayList với một lệnh chèn lô vào LinkedList mà không giải thích khác biệt thuật toán có thể dẫn đến kết luận sai về bản thân cấu trúc.

### 7.4. Đúng thứ tự lô là yêu cầu chức năng

Nếu gọi add(i, value) với **cùng chỉ số i** cho từng giá trị X, Y, Z, kết quả tại vị trí đó có thể là Z, Y, X. Đây không phải cùng tác vụ với chèn lô giữ thứ tự X, Y, Z.

Khi so hiệu năng, trước hết kiểm tra các phương án tạo cùng kết quả. Không chọn phương án chạy nhanh hơn nhưng làm sai thứ tự.

Ngoài ra, “mỗi lần chèn tại giữa danh sách hiện tại” khác với “chèn cả lô trước phần tử C đã chọn ban đầu”. Kích thước thay đổi qua mỗi lần chèn, nên các điểm chèn có thể khác nhau. Phải định nghĩa rõ quy tắc vị trí.

## 8. Ví dụ chạy được: năm cách tạo cùng một kết quả

Lưu vào `MiddleInsertBatchDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;

public class MiddleInsertBatchDemo {
    static void insertByIndexes(
            List<String> target, int index, List<String> batch) {
        int offset = 0;
        for (String value : batch) {
            target.add(index + offset, value);
            offset++;
        }
    }

    public static void main(String[] args) {
        List<String> seed = List.of("A", "B", "C", "D");
        List<String> batch = List.of("X", "Y", "Z");
        int index = 2;

        ArrayList<String> arrayRepeated = new ArrayList<>(16);
        arrayRepeated.addAll(seed);
        insertByIndexes(arrayRepeated, index, batch);

        LinkedList<String> linkedRepeated = new LinkedList<>(seed);
        insertByIndexes(linkedRepeated, index, batch);

        LinkedList<String> linkedCursor = new LinkedList<>(seed);
        ListIterator<String> cursor = linkedCursor.listIterator(index);
        for (String value : batch) {
            cursor.add(value);
        }

        ArrayList<String> arrayBulk = new ArrayList<>(16);
        arrayBulk.addAll(seed);
        arrayBulk.addAll(index, batch);

        LinkedList<String> linkedBulk = new LinkedList<>(seed);
        linkedBulk.addAll(index, batch);

        System.out.println("ArrayList repeated = " + arrayRepeated);
        System.out.println("LinkedList repeated = " + linkedRepeated);
        System.out.println("LinkedList one cursor = " + linkedCursor);
        System.out.println("ArrayList addAll = " + arrayBulk);
        System.out.println("LinkedList addAll = " + linkedBulk);

        List<String> expected = List.of("A", "B", "X", "Y", "Z", "C", "D");
        boolean allMatch = arrayRepeated.equals(expected)
                && linkedRepeated.equals(expected)
                && linkedCursor.equals(expected)
                && arrayBulk.equals(expected)
                && linkedBulk.equals(expected);
        System.out.println("all results match = " + allMatch);

        long repeatedSuffixCount = (long) batch.size() * (seed.size() - index);
        long bulkSuffixCount = seed.size() - index;
        System.out.println("ArrayList repeated suffix model = "
                + repeatedSuffixCount);
        System.out.println("ArrayList addAll suffix model = " + bulkSuffixCount);
    }
}
```
Biên dịch và chạy:

```shell
javac --release 17 MiddleInsertBatchDemo.java
java MiddleInsertBatchDemo
```
Kết quả:

```text
ArrayList repeated = [A, B, X, Y, Z, C, D]
LinkedList repeated = [A, B, X, Y, Z, C, D]
LinkedList one cursor = [A, B, X, Y, Z, C, D]
ArrayList addAll = [A, B, X, Y, Z, C, D]
LinkedList addAll = [A, B, X, Y, Z, C, D]
all results match = true
ArrayList repeated suffix model = 6
ArrayList addAll suffix model = 2
```
Chương trình có năm phương án:

1. Chèn từng phần tử bằng chỉ số trên ArrayList.
2. Chèn từng phần tử bằng chỉ số trên LinkedList.
3. Dùng một ListIterator của LinkedList cho cả lô.
4. Dùng ArrayList.addAll.
5. Dùng LinkedList.addAll.

Các phương án đều chèn X, Y, Z trước C và giữ thứ tự. Kiểm tra allMatch xác nhận tính đúng trên dữ liệu ví dụ.

Hai dòng suffix model tính số tham chiếu cũ trong đoạn đuôi phải dịch theo mô hình ArrayList:

- Lặp ba lần: C, D bị chuyển ba lần, tổng 6.
- addAll một lần: C, D chỉ cần chuyển sang sau cả lô, tổng 2.

Chúng không đếm các lần ghi phần tử mới, mảng tạm lấy từ collection nguồn hoặc mọi công việc JVM. Không gọi hai giá trị 6 và 2 là số lần cấp phát hoặc tỷ lệ tốc độ.

Trong [hợp đồng ListIterator.add của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html#add(E)), phần tử được chèn trước phần tử sẽ được next trả về. Con trỏ tiến qua phần tử vừa thêm; chuỗi add trong ví dụ giữ thứ tự X, Y, Z mà không phải tìm lại C.

Sau khi đã biết toàn bộ lô cần chèn, addAll thường diễn đạt ý định rõ hơn một chuỗi gọi add riêng lẻ. Chi phí lấy dữ liệu từ collection nguồn và yêu cầu dữ liệu không bị thay đổi trong lúc thao tác vẫn phải được xem xét.

## 9. Ví dụ chạy được: đối tượng phần tử không bị sao chép sâu

Lưu vào `MiddleInsertReferenceDemo.java`:

```java
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;

public class MiddleInsertReferenceDemo {
    static final class Document {
        static int constructed;
        final String name;

        Document(String name) {
            this.name = name;
            constructed++;
        }

        @Override
        public String toString() {
            return name;
        }
    }

    public static void main(String[] args) {
        Document a = new Document("A");
        Document b = new Document("B");
        Document c = new Document("C");
        Document d = new Document("D");
        Document inserted = new Document("X");

        List<Document> seed = List.of(a, b, c, d);
        ArrayList<Document> array = new ArrayList<>(16);
        array.addAll(seed);
        LinkedList<Document> linked = new LinkedList<>(seed);

        System.out.println("documents before insertion = " + Document.constructed);
        array.add(2, inserted);
        linked.add(2, inserted);
        System.out.println("documents after insertion = " + Document.constructed);
        System.out.println("ArrayList values = " + array);
        System.out.println("LinkedList values = " + linked);
        System.out.println("ArrayList retained C identity = " + (array.get(3) == c));
        System.out.println("LinkedList retained C identity = " + (linked.get(3) == c));
        System.out.println("both contain the same X = "
                + (array.get(2) == linked.get(2)));
    }
}
```
Biên dịch và chạy:

```shell
javac --release 17 MiddleInsertReferenceDemo.java
java MiddleInsertReferenceDemo
```
Kết quả:

```text
documents before insertion = 5
documents after insertion = 5
ArrayList values = [A, B, X, C, D]
LinkedList values = [A, B, X, C, D]
ArrayList retained C identity = true
LinkedList retained C identity = true
both contain the same X = true
```
Có năm Document được tạo trước khi chèn: A, B, C, D và X. Sau khi chèn X vào cả hai danh sách, số Document đã được constructor tạo vẫn bằng năm.

Kiểm tra bằng == cho thấy C sau khi đổi chỉ số vẫn là chính đối tượng C cũ. X ở hai danh sách cũng là cùng đối tượng được cung cấp.

Điều cần phân biệt:

- Bộ đếm chỉ đếm Document do chương trình tạo, không đếm Node nội bộ của LinkedList hoặc mảng bên trong ArrayList.
- ArrayList có thể di chuyển nhiều tham chiếu mà không tạo Document mới.
- LinkedList có thể tạo Node mới để chứa tham chiếu đến một Document đã có.
- Chương trình không đo tổng số byte cấp phát hoặc thời gian chạy.

Không dựa vào kích thước sâu của một Document để tính số byte phần thân Document bị sao chép trong ArrayList.add. Công việc dịch ở đây liên quan đến các ô tham chiếu.

## 10. Những chi phí ẩn trong cách xác định điểm chèn

### 10.1. Tìm theo giá trị rồi chèn theo chỉ số

Một mẫu dễ viết là:

```java
// Đoạn minh họa; cần xử lý riêng trường hợp target không tồn tại.
int index = items.indexOf(target);
if (index >= 0) {
    items.add(index, inserted);
}
```
indexOf có thể tìm tuyến tính trên cả hai loại danh sách.

Với LinkedList, sau khi indexOf đã đi qua các nút và trả về một số nguyên, add(index, inserted) lại phải định vị nút theo chỉ số. Kết quả tìm về mặt nội bộ không tự được truyền tiếp qua số nguyên index.

Một thuật toán tìm bằng ListIterator rồi chèn ngay tại vị trí phù hợp có thể tránh một lượt định vị lại. Nhưng nếu yêu cầu là “trước lần xuất hiện đầu tiên bằng target”, phải xử lý vị trí con trỏ đúng theo quy tắc next/previous/add. Không thay đổi ngữ nghĩa tìm để tối ưu.

Chặn trên tổng cho một lần tìm và chèn giữa vẫn tuyến tính trong cả hai cách triển khai, nhưng công việc cụ thể và số lượt đi qua dữ liệu có thể khác.

### 10.2. Tìm vị trí bằng nhiều get(i)

Nếu tìm phần tử trên LinkedList bằng một vòng i từ 0 đến n - 1 và gọi get(i) mỗi lượt, có thể tạo ra tổng công việc bậc hai trước khi chèn.

Đây là vấn đề của thuật toán tìm, không phải bằng chứng rằng việc nối một nút tốn bậc hai. Duyệt bằng iterator khi chỉ cần đi tuần tự giúp giữ vị trí thay vì tìm lại từ một đầu danh sách.

### 10.3. Bảng tra cứu chỉ số không tự miễn phí

Một Map từ mã phần tử sang chỉ số có thể giảm một số tìm kiếm, nhưng chèn trước các phần tử khác làm chỉ số của chúng thay đổi. Cập nhật chỉ mục phụ có thể là một công việc đáng kể.

Với LinkedList chuẩn, giữ phần tử trong một Map cũng không cho quyền giữ Node nội bộ. Không thiết kế một phân tích giả định có sẵn thao tác public “chèn trước Node này” nếu API không cung cấp nó.

Nếu tác vụ yêu cầu rất nhiều vị trí ổn định và sửa ở các điểm xa nhau, có thể cần xem lại mô hình dữ liệu hoặc cấu trúc chuyên dụng. Trước hết phải định nghĩa “vị trí” là chỉ số, định danh hay con trỏ duyệt.

## 11. Bảng so sánh theo điều kiện thực tế

Bảng sau nói về công việc cấu trúc thông thường; k là kích thước lô, s là chiều dài đoạn cũ phía sau điểm chèn. Không quy định tỷ lệ thời gian giữa các ô.

| Tình huống | LinkedList | ArrayList |
| --- | --- | --- |
| Một lệnh add(i, x) với i ở giữa, chỉ biết i | Tìm tuyến tính rồi nối nút | Dịch tuyến tính; có thể mở rộng |
| Một lần chèn khi đã có iterator đúng vị trí | Tạo/nối nút với công việc hằng số | Vẫn dịch đoạn phía sau |
| Khởi tạo iterator ở giữa khi chỉ có i | Cần tìm tới vị trí | Có thể giữ vị trí chỉ số trực tiếp |
| Chèn k phần tử bằng một iterator ở giữa | Định vị một lần rồi O(k) thao tác nút | Có thể dịch cùng đoạn đuôi s nhiều lần, tổng O(k * s + k), chưa tính mở rộng |
| Chèn cả lô bằng addAll(i, batch) | Định vị một lần, tạo k nút | Dịch đuôi một lần, ghi k tham chiếu; có thể mở rộng |
| Phải tìm target theo giá trị trước | Cộng chi phí tìm | Cộng chi phí tìm |
| Sau khi chèn có rất nhiều truy cập chỉ số | Cần tính chi phí các lần đi đến nút | Truy cập chỉ số trực tiếp |
| Thêm/xóa liên tục | Tính cấp phát và vòng đời nút | Tính sức chứa, dịch và các lần thay mảng |

Một mẫu đủ thuận lợi cho LinkedList là: thuật toán vốn đã đi tuần tự, giữ iterator hợp lệ và làm nhiều chỉnh sửa tại chỗ trong lượt đó. Lợi thế nằm ở việc tận dụng vị trí đang có và chỉ sửa vùng liên kết nhỏ.

Một mẫu không tạo ra lợi thế rõ từ riêng lý thuyết nối nút là: nhận nhiều chỉ số giữa độc lập, mỗi lần gọi add(index, value), rồi thường xuyên đọc lại bằng get(i).

Cả hai nhận định vẫn cần được đặt trong tổng yêu cầu và kiểm chứng hiệu năng nếu chi phí có ý nghĩa với ứng dụng.

## 12. Đo đúng câu hỏi thay vì đo một phép so sánh lệch

### 12.1. Chọn phạm vi đo

Hai câu hỏi sau đều hợp lệ nhưng khác nhau:

- Mất bao lâu để thực hiện yêu cầu “đây là chỉ số, hãy chèn một phần tử”?
- Mất bao lâu để chèn tại một iterator đã có vì chương trình đang duyệt đến đây?

Câu thứ nhất nên tính việc định vị cần thiết. Câu thứ hai có thể đo riêng phần chèn tại con trỏ, nhưng phải báo trạng thái có sẵn và đánh giá cả giai đoạn duyệt khi nói về toàn tác vụ.

Đừng công bố một nhãn duy nhất “chèn giữa” cho hai điều kiện khác nhau.

### 12.2. Những điều cần giữ nhất quán

1. **Kết quả:** cùng thứ tự dữ liệu, cùng số phần tử mới, cùng quy tắc điểm chèn.
2. **Kích thước:** phép chèn làm size tăng; phải xác định mỗi lần đo bắt đầu từ kích thước nào.
3. **Chuẩn bị:** tạo danh sách, tạo phần tử, tạo iterator và dành sức chứa thuộc hay không thuộc phần đo phải được nêu rõ.
4. **Sức chứa:** ArrayList đã đủ chỗ hay đang đo cả chi phí mở rộng?
5. **Cách định vị:** nhận chỉ số, tìm theo giá trị hay tiếp tục từ một con trỏ đã có?
6. **Công việc khác:** không vô tình đo cả in console, tạo chuỗi hoặc sinh số ngẫu nhiên nếu câu hỏi chỉ là chi phí chèn.

Nếu chèn rồi xóa ngay để phục hồi trạng thái trong cùng đoạn đo, số đo có thể là chi phí **cặp chèn–xóa**, không phải chỉ chèn. Nếu tạo bản sao mới trước mọi lần chèn trong đoạn đo, có thể đang đo chủ yếu việc dựng dữ liệu.

Những công việc đó không mặc nhiên sai; chúng chỉ phải phù hợp câu hỏi và được báo đúng tên.

### 12.3. JVM và phần cứng ảnh hưởng kết quả

Cần khởi động mã đủ để JIT có điều kiện tối ưu, đo nhiều lần, kiểm soát việc kết quả bị loại bỏ và ghi lại môi trường. Một lần nanoTime trên danh sách nhỏ không đủ để kết luận về mọi kích thước.

[JMH của OpenJDK](https://github.com/openjdk/jmh) hỗ trợ xây dựng benchmark JVM. Nếu cần xem vì sao biểu diễn và thứ tự tham chiếu ảnh hưởng phép đo, có thể đọc [mẫu MemoryAccess của JMH](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_39_MemoryAccess.java).

Các ví dụ chạy độc lập trong bài chưa thực hiện một benchmark JMH hoặc đo cache miss. Vì thế, bài không đưa ra tỷ lệ nhanh hơn, điểm kích thước chuyển lợi thế hoặc số nano giây bịa từ mô hình.

### 12.4. Đánh giá cả tải thực tế

Một ứng dụng có thể chèn ít nhưng đọc rất nhiều. Tiết kiệm một phần chi phí chèn không nhất thiết bù được chi phí của hàng triệu lần truy cập theo chỉ số sau đó.

Một ứng dụng khác có thể đi tuần tự và sửa liên tục tại cùng vùng. Giữ con trỏ hợp lệ khi đó làm thay đổi đáng kể phần định vị.

Hãy tính tỷ trọng các thao tác và tuổi thọ dữ liệu, không chọn cấu trúc chỉ từ một ô trong bảng độ phức tạp.

## 13. Những kết luận sai thường gặp

| Nhận định | Điều kiện hoặc phần công việc bị bỏ quên |
| --- | --- |
| “LinkedList chèn giữa luôn O(1)” | Bỏ bước tìm vị trí nếu đầu vào chỉ là chỉ số hoặc giá trị |
| “ArrayList sao chép toàn bộ object phía sau” | Nó dịch tham chiếu, không sao chép sâu phần tử |
| “Cùng O(n) thì hiệu năng bằng nhau” | Số đối tượng, tính phụ thuộc khi đọc liên kết và thao tác sao chép mảng khác nhau |
| “Có iterator rồi thì mọi loại List chèn O(1)” | Iterator không thay cách ArrayList nhường chỗ |
| “Dành trước capacity làm ArrayList chèn giữa O(1)” | Đoạn đuôi vẫn phải dịch |
| “Chèn cả lô và chèn từng phần tử là cùng chi phí” | Số lần dịch hoặc định vị có thể khác lớn |
| “Nối vài tham chiếu là không cấp phát gì” | LinkedList thường tạo một Node mới cho phần tử được chèn |
| “Tìm indexOf xong thì LinkedList đã giữ sẵn nút cho add(index)” | Số nguyên chỉ số không mang theo trạng thái nút của lượt tìm |
| “Benchmark tạo cursor trước luôn chứng minh yêu cầu theo chỉ số nhanh hơn” | Nó có thể đã tách chi phí định vị ra khỏi vùng đo |
| “ArrayList luôn thắng vì sao chép mảng nhanh” | Cần xét mẫu con trỏ, số lần chèn, kích thước và các thao tác khác |
| “Đổi tên lớp là tối ưu đủ” | Thuật toán chèn theo lô, giữ vị trí và cách tìm thường quyết định nhiều công việc |
| “Có một ngưỡng n dùng được cho mọi máy” | Ngưỡng đo phụ thuộc tác vụ và môi trường |

## 14. Tự kiểm tra bằng các tình huống cụ thể

### Bài 1: Một chỉ số ở giữa

Danh sách có một triệu phần tử, chỉ biết chỉ số 500.000 và cần chèn một phần tử.

LinkedList phải tìm nút gần giữa; ArrayList phải dịch khoảng nửa triệu tham chiếu, có thể còn mở rộng. Cả hai có công việc tuyến tính trong mô hình. Không thể kết luận LinkedList là hằng số chỉ từ phần nối nút.

### Bài 2: Đang duyệt và chèn tại con trỏ

Một thuật toán đã duyệt tới vùng cần sửa bằng ListIterator của LinkedList và chèn 100 phần tử ở con trỏ đó.

Có thể tận dụng vị trí đang có: 100 lần tạo/nối nút có tổng O(100) công việc cấu trúc. Khi báo tổng tác vụ, vẫn tính lượt duyệt đã cần để đến vùng đó.

Nếu biết sẵn toàn bộ lô, hãy so cả phương án addAll và cách tổ chức dữ liệu phù hợp, thay vì mặc định phải dùng 100 lời gọi riêng lẻ trên mọi cấu trúc.

### Bài 3: Chèn lô vào ArrayList đã đủ chỗ

Một ArrayList có n = 10.000, chèn k = 200 phần tử trước chỉ số i = 2.000 và giữ thứ tự.

Đoạn cũ phía sau có s = 8.000 phần tử:

- Chèn từng phần tử theo chỉ số tăng dần: riêng tham chiếu cũ trong các đoạn dịch có tổng 200 * 8.000 = 1.600.000 lượt.
- addAll: đoạn cũ được chuyển sang sau lô một lần, dài 8.000 tham chiếu; còn phải ghi 200 phần tử mới và lấy dữ liệu lô.

Đây là số công việc theo mô hình, không phải tỷ lệ thời gian 200 lần.

### Bài 4: Có tham chiếu đến C thì có phải chèn trước C trong O(1) không?

Không thể suy như vậy với Java LinkedList. Tham chiếu đến C là phần tử nghiệp vụ, không phải Node nội bộ. Nếu C xuất hiện nhiều lần, còn phải xác định lần xuất hiện nào cần chọn.

### Bài 5: Document rất lớn có làm dịch ArrayList phải sao chép toàn tài liệu không?

Không. Các ô bị dịch là tham chiếu. Việc xử lý nội dung Document có thể tốn nhiều thời gian nhưng là một phần công việc khác.

### Bài 6: So kết quả trước khi so thời gian

Một chương trình gọi add(2, value) liên tục với X, Y, Z. Chương trình khác dùng addAll(2, List.of("X", "Y", "Z")). Có chắc cùng tác vụ không?

Không. Gọi lại cùng chỉ số có thể đảo thứ tự nhóm mới, còn addAll giữ thứ tự lô. Cần kiểm tra kết quả trước khi diễn giải số đo.

### Bài 7: Đề xuất tối ưu có đúng toàn luồng không?

Một đề xuất đổi ArrayList thành LinkedList vì có vài lệnh chèn giữa, nhưng phần còn lại dùng get(i) trong nhiều vòng lặp. Điều cần làm là kiểm tra tần suất, vị trí và cách duyệt toàn luồng; việc đổi cấu trúc có thể chuyển chi phí sang các lần đọc hoặc thậm chí tạo tìm vị trí lặp lại.

Câu cần trả lời luôn là: **chương trình đã biết gì trước phép chèn, phải làm gì để đến vị trí đó, chèn một phần tử hay cả lô, và sẽ dùng dữ liệu ra sao sau đó?** Khi tách rõ những phần này, lợi thế nối nút của LinkedList được đặt đúng chỗ và việc chọn ArrayList hay LinkedList có cơ sở để kiểm chứng.
