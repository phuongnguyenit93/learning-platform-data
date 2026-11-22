# Duyệt liên tiếp, tính cục bộ bộ nhớ và RandomAccess của ArrayList

## 1. Ba ý tưởng liên quan nhưng không đồng nghĩa

Khi đọc ArrayList, ta thường gặp ba nhận xét: nó duyệt tốt theo thứ tự, có lợi về tính cục bộ bộ nhớ và triển khai RandomAccess. Ba nhận xét này liên quan đến nhau, nhưng nói về ba vấn đề khác nhau.

| Ý tưởng | Câu hỏi mà nó trả lời |
| --- | --- |
| Duyệt liên tiếp | Chương trình đi qua các phần tử theo thứ tự nào và bằng cách nào? |
| Tính cục bộ bộ nhớ (memory locality) | Các lần truy cập có tái sử dụng dữ liệu gần nhau trong không gian hoặc thời gian không? |
| RandomAccess | Một thuật toán nhận List có thể nhận biết danh sách hỗ trợ truy cập theo chỉ số nhanh hay không? |

Ví dụ, vòng lặp đọc lần lượt `get(0), get(1), get(2)` là duyệt liên tiếp, dù ArrayList có tên giao diện RandomAccess. Chữ “random” ở đây nói đến khả năng lấy một vị trí bất kỳ mà không phải đi qua toàn bộ phần tử trước đó; nó không yêu cầu chương trình đọc các vị trí ngẫu nhiên.

Mặt khác, phần tử của ArrayList là tham chiếu đến đối tượng. Đọc các ô tham chiếu liên tiếp không bảo đảm các đối tượng được trỏ tới cũng nằm cạnh nhau trong bộ nhớ.

Muốn phân tích đúng, hãy đi theo thứ tự:

1. Biết ArrayList lưu dữ liệu như thế nào.
2. Xác định cách vòng lặp lấy phần tử.
3. Xác định công việc thực hiện sau khi đã lấy được tham chiếu.
4. Tách chi phí thuật toán khỏi các yếu tố bố trí bộ nhớ và tối ưu của JVM.
5. Dùng phép đo phù hợp nếu cần kết luận về tốc độ thực tế.

Bài dùng Java 17 trở lên, với ví dụ đọc dữ liệu ổn định trong một luồng. Không thay đổi cấu trúc danh sách trong khi các vòng lặp minh họa đang chạy. Các ví dụ số nguyên đều không chứa null.

## 2. Cấu trúc mảng bên trong: liền nhau là cái gì?

### 2.1. ArrayList giữ một dãy tham chiếu

ArrayList là một triển khai List dựa trên mảng có thể tăng sức chứa. Trong triển khai thông thường của OpenJDK, các phần tử được giữ trong một mảng tham chiếu bên trong.

Mô hình khái niệm:

```text
ArrayList
   |
   v
mảng tham chiếu bên trong
index:   0       1       2       3
       [ref A] [ref B] [ref C] [ref D]
          |       |       |       |
          v       v       v       v
       object A  object B object C object D

Các ô ref thuộc cùng một mảng.
Hình không thể hiện địa chỉ thật hoặc khoảng cách giữa các object.
```

Với cách bố trí mảng thông thường trên HotSpot, các ô tham chiếu là các ô kề nhau trong vùng dữ liệu của mảng. Lấy phần tử ở chỉ số i có thể xác định ô tương ứng trực tiếp; không cần đi qua i phần tử đầu tiên.

Điều này không có nghĩa “mọi dữ liệu bên trong các đối tượng đều nằm trong mảng”. Nếu mỗi phần tử là một đơn hàng chứa khách hàng, danh sách sản phẩm và các chuỗi, đọc sâu vào đơn hàng có thể kéo theo nhiều lần đi đến những đối tượng khác.

Cũng không suy từ hình rằng vùng nhớ ảo của tiến trình tương ứng với một dải RAM vật lý liên tục. Các chi tiết ánh xạ bộ nhớ thuộc hệ điều hành và JVM, nằm ngoài hợp đồng của List.

### 2.2. Đối chiếu với danh sách liên kết để thấy cơ chế duyệt

Một danh sách liên kết thường có các nút giữ phần tử và liên kết đến nút kế tiếp. Ví dụ khái niệm:

```text
node A --next--> node B --next--> node C
  |                |                |
item A           item B           item C
```
Để đi tiếp, iterator đọc liên kết của nút hiện tại rồi sang nút kế. Khi nút kế ở vị trí xa trong bộ nhớ, có thể phải chờ dữ liệu tương ứng được đưa đến bộ xử lý. Đường đi còn phụ thuộc vào kết quả đọc liên kết trước đó.

ArrayList không cần một nút liên kết riêng cho mỗi phần tử để xác định vị trí kế tiếp trong dãy tham chiếu. Đây là một lý do nó thường thuận lợi cho các lượt quét lớn, nhưng chưa đủ để khẳng định nó nhanh hơn trong mọi chương trình hoặc trên mọi loại phần tử.

Các đối tượng được tạo gần nhau có thể tình cờ được đặt gần nhau; bộ thu gom rác có thể di chuyển chúng. Không biến các khả năng đó thành quy tắc rằng nút của LinkedList luôn xa nhau hoặc phần tử của ArrayList luôn gần nhau.

### 2.3. Hợp đồng Java khác với mô hình bố trí cụ thể

Tài liệu [ArrayList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html) mô tả triển khai dựa trên mảng và truy cập get theo thời gian hằng số. Nó không cung cấp API để hỏi địa chỉ thật của phần tử hoặc số lần trượt bộ nhớ đệm.

[Đặc tả JVM, phần biểu diễn đối tượng](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-2.html#jvms-2.7) để cách biểu diễn nội bộ cho triển khai JVM quyết định. Vì vậy, sơ đồ bộ nhớ trong bài là mô hình giải thích cho cách triển khai thông thường, không phải một công thức địa chỉ có thể sử dụng trong mã Java độc lập nền tảng.

## 3. Tính cục bộ bộ nhớ giúp duyệt liên tiếp như thế nào?

### 3.1. Bộ nhớ đệm CPU là một lớp khác với collection

CPU thường làm việc với nhiều tầng bộ nhớ đệm để giảm thời gian chờ dữ liệu từ các tầng bộ nhớ chậm hơn. Dữ liệu thường được chuyển theo từng khối, gọi là dòng bộ nhớ đệm (cache line), chứ không chỉ đúng một biến Java đang được đọc.

Kích thước dòng bộ nhớ đệm, số tầng đệm, độ trễ và cách dự đoán truy cập phụ thuộc phần cứng. Không mặc định mọi máy đều có cùng một con số rồi dùng nó như thuộc tính của ArrayList.

Đây là bộ nhớ đệm của phần cứng. Nó khác với một Map dùng làm cache trong ứng dụng, khác với giá trị đã lưu trong biến và khác với Integer cache của thư viện Java.

### 3.2. Cục bộ theo không gian

Tính cục bộ theo không gian (spatial locality) xuất hiện khi chương trình truy cập các vùng ở gần nhau.

Khi đọc liên tiếp các ô tham chiếu trong cùng mảng, một khối dữ liệu đã được đưa vào bộ nhớ đệm có thể phục vụ nhiều lần đọc ở các chỉ số lân cận. Phần cứng cũng có thể nhận ra một mẫu truy cập đều đặn và nạp trước dữ liệu (prefetch).

Mô hình giản lược:

```text
Đọc: ref[0], ref[1], ref[2], ref[3], ...

Một khối chứa nhiều ô tham chiếu lân cận có thể được dùng
cho nhiều bước liên tiếp của vòng lặp.
```
Từ khóa là “có thể”. Kết quả còn phụ thuộc căn chỉnh, kích thước dữ liệu, dữ liệu khác tranh chấp bộ nhớ đệm, phần cứng và mã máy mà JVM tạo ra.

### 3.3. Cục bộ theo thời gian

Tính cục bộ theo thời gian (temporal locality) xuất hiện khi một vùng dữ liệu vừa dùng được dùng lại sớm.

Ví dụ, nhiều phép xử lý nhỏ trên cùng một nhóm phần tử có thể tái sử dụng dữ liệu đã được nạp. Nhưng nếu tập dữ liệu quá lớn hoặc giữa hai lượt có nhiều công việc khác, dữ liệu có thể không còn ở tầng đệm mong muốn.

Vì vậy, “chạy lượt thứ hai nhanh hơn” không tự chứng minh ArrayList có một bảo đảm cache nào. Có thể có đồng thời tác động của bộ nhớ đệm, JIT, cấp phát, thu gom rác và lịch chạy hệ điều hành.

### 3.4. Khi nào lợi thế có thể bị che khuất?

Nếu mỗi bước chỉ đọc một trường số và cộng vào tổng, chi phí truy cập bộ nhớ có thể chiếm tỷ trọng lớn. Nếu mỗi bước gọi mạng, ghi log lớn hoặc giải mã một tài liệu phức tạp, chi phí nghiệp vụ có thể lấn át khác biệt ở cách lấy tham chiếu.

Một mô hình hữu ích là:

```text
Tổng thời gian một lượt
= thời gian điều khiển vòng lặp
+ thời gian lấy các tham chiếu
+ thời gian đọc dữ liệu của từng đối tượng
+ thời gian xử lý nghiệp vụ
+ các tác động của môi trường chạy.
```
Không được chỉ nhìn số lần gọi get hoặc sự có mặt của iterator rồi bỏ qua các phần còn lại.

## 4. Hai tầng truy cập: tham chiếu và nội dung đối tượng

Xét biểu thức:

```java
// Đoạn minh họa, readings là ArrayList<Reading>.
total += readings.get(i).value;
```
Ở mức mô hình, có hai công việc khác nhau:

1. Lấy tham chiếu ở ô i của mảng bên trong.
2. Dùng tham chiếu đó để đọc trường value của đối tượng Reading.

Tầng thứ nhất có lợi từ dãy ô tham chiếu kề nhau. Tầng thứ hai phụ thuộc vị trí và cấu trúc của những đối tượng Reading.

Nếu các tham chiếu trỏ đến cùng một đối tượng, có thể tái sử dụng cùng dữ liệu nhiều lần. Nếu mỗi tham chiếu trỏ đến một đối tượng lớn khác nhau, công việc đọc sâu có đặc điểm khác. Chỉ biết số phần tử n chưa mô tả đầy đủ lượng bộ nhớ thực sự bị chạm đến.

### 4.1. ArrayList<Integer> khác int[]

Trong Java 17, generic như ArrayList dùng kiểu tham chiếu; `ArrayList<int>` không hợp lệ. `ArrayList<Integer>` giữ tham chiếu đến các đối tượng Integer, còn `int[]` có các thành phần giá trị nguyên thủy.

| Biểu diễn | Cái được giữ trong các ô | Công việc điển hình để cộng giá trị |
| --- | --- | --- |
| `int[]` | Các giá trị int | Đọc giá trị tại ô rồi cộng |
| `ArrayList<Integer>` | Tham chiếu Integer | Lấy tham chiếu, bỏ hộp Integer để lấy int rồi cộng |
| `ArrayList<Reading>` | Tham chiếu Reading | Lấy tham chiếu, đọc trường hoặc gọi phương thức rồi xử lý |

Đây là khác biệt về biểu diễn, không phải kết luận rằng mọi chương trình dùng int[] đều nhanh hơn với một tỷ lệ cố định.

Autoboxing có thể tái sử dụng một số Integer; không được mặc định “mỗi lần thêm một số luôn tạo một đối tượng mới”. Ngược lại, việc có Integer được tái sử dụng cũng không làm ArrayList<Integer> trở thành int[].

Nếu có null trong ArrayList<Integer>, biểu thức cộng có thể ném NullPointerException khi bỏ hộp. Đây là khác biệt về hành vi cần giải quyết trước khi nói đến tốc độ.

### 4.2. Đổi thứ tự tham chiếu không sắp xếp lại các đối tượng trên heap

Sắp xếp ArrayList thay đổi thứ tự các tham chiếu trong danh sách theo quy tắc so sánh. Nó không phải lệnh “di chuyển tất cả đối tượng phần tử đến cạnh nhau trong bộ nhớ”.

Tương tự, sao chép sang một ArrayList mới tạo một container khác chứa các tham chiếu đến các phần tử. Việc đó không tự nhân bản sâu hoặc gom các đối tượng được tham chiếu thành một khối mới.

Duyệt một ArrayList đã xáo thứ tự vẫn đọc các ô tham chiếu theo chỉ số liên tiếp nếu vòng lặp đi 0, 1, 2, ...; tuy nhiên thứ tự các đối tượng được truy cập qua những tham chiếu ấy đã thay đổi. Hai tầng cục bộ phải được phân biệt.

## 5. Ba cách duyệt ArrayList và điều kiện để phân tích đúng

### 5.1. Vòng lặp theo chỉ số

```java
// Đoạn minh họa: danh sách không bị thay đổi trong vòng lặp.
for (int i = 0, n = values.size(); i < n; i++) {
    Integer value = values.get(i);
    use(value);
}
```
ArrayList lấy phần tử theo chỉ số trong thời gian hằng số, nên một lượt đọc n phần tử có chi phí O(n), chưa tính use.

Lưu size vào biến n thể hiện rõ rằng ta đang đọc một dãy có kích thước ổn định trong lượt này. Nó không tạo snapshot. Nếu nơi khác thêm/xóa dữ liệu, biến n có thể không còn phù hợp với danh sách hiện tại.

Không suy từ cú pháp rằng JVM chắc chắn sinh ra đúng một hình dạng mã máy. JVM có thể tối ưu kiểm tra chỉ số và các lời gọi khi có đủ điều kiện, nhưng việc tối ưu cụ thể phải được kiểm tra hoặc đo trên môi trường liên quan.

### 5.2. Foreach

```java
// Đoạn minh họa.
for (Integer value : values) {
    use(value);
}
```
Với đối tượng Iterable, vòng lặp foreach có ngữ nghĩa dựa trên iterator. Với mảng, foreach có cách dịch theo mảng riêng. Xem [JLS 17, enhanced for statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.14.2).

Dùng foreach trên ArrayList không biến cấu trúc bên dưới thành danh sách liên kết. Iterator vẫn đọc dãy phần tử của ArrayList theo thứ tự.

Một cách viết gọn không nhất thiết nhanh hơn hoặc chậm hơn một cách viết dài. Khi iterator không cần tồn tại độc lập ra ngoài, JVM có thể có cơ hội tối ưu việc sử dụng nó. Không khẳng định luôn có cấp phát iterator thật ở mỗi lượt chạy chỉ từ mã nguồn.

### 5.3. Iterator viết tường minh

```java
// Đoạn minh họa.
for (Iterator<Integer> it = values.iterator(); it.hasNext();) {
    Integer value = it.next();
    use(value);
}
```
Iterator phù hợp khi cần thể hiện rõ thao tác duyệt hoặc làm việc theo giao thức iterator. Với ArrayList ổn định, duyệt một lượt cũng tuyến tính.

Nếu cần sửa cấu trúc trong khi duyệt, phải tuân theo quy tắc của thao tác được chọn. Iterator của ArrayList có cơ chế fail-fast ở mức best effort; nó không tạo ra bảo đảm an toàn luồng. Vòng lặp get(i) cũng không trở nên an toàn chỉ vì không dùng iterator.

Trong bài này, hãy giữ dữ liệu ổn định để tập trung vào mẫu truy cập. Việc đồng bộ và quản lý thay đổi cần một thiết kế riêng theo yêu cầu chương trình.

### 5.4. Khi chỉ cần đọc từng phần tử, ưu tiên diễn đạt rõ mục tiêu

- Cần cả vị trí và phần tử: vòng lặp chỉ số có thể phù hợp nếu biết đặc điểm truy cập của danh sách.
- Chỉ cần đọc tuần tự: foreach thường diễn đạt mục tiêu ngắn gọn.
- Cần giao thức duyệt tường minh: dùng Iterator hoặc ListIterator theo đúng nhu cầu.

Đừng thay toàn bộ foreach bằng get(i) chỉ vì một nhận xét chung về cache. Cả hai cách vẫn đọc cùng dữ liệu của ArrayList; khác biệt tốc độ cần được đặt vào ngữ cảnh.

## 6. Ví dụ chạy được: cùng thứ tự, cùng tổng, ba cách viết

Lưu chương trình sau vào `ArrayListTraversalStylesDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public class ArrayListTraversalStylesDemo {
    static long sumByIndex(List<Integer> values) {
        long sum = 0;
        for (int i = 0, n = values.size(); i < n; i++) {
            sum += values.get(i);
        }
        return sum;
    }

    static long sumByForEach(List<Integer> values) {
        long sum = 0;
        for (int value : values) {
            sum += value;
        }
        return sum;
    }

    static long sumByIterator(List<Integer> values) {
        long sum = 0;
        for (Iterator<Integer> it = values.iterator(); it.hasNext();) {
            sum += it.next();
        }
        return sum;
    }

    public static void main(String[] args) {
        List<Integer> values = new ArrayList<>(List.of(3, 1, 4, 1, 5));
        System.out.println("values = " + values);
        System.out.println("index sum = " + sumByIndex(values));
        System.out.println("foreach sum = " + sumByForEach(values));
        System.out.println("iterator sum = " + sumByIterator(values));
    }
}
```
Biên dịch và chạy:

```shell
javac --release 17 ArrayListTraversalStylesDemo.java
java ArrayListTraversalStylesDemo
```
Kết quả:

```text
values = [3, 1, 4, 1, 5]
index sum = 14
foreach sum = 14
iterator sum = 14
```
Chương trình chứng minh ba cách duyệt đọc cùng dãy và cho cùng kết quả với dữ liệu này. Nó không đo cache miss và không chứng minh cách nào nhanh nhất.

Kiểu tích lũy long tránh việc tổng bị giới hạn ở miền int như khi dùng biến tổng int. Việc lựa chọn kiểu tổng vẫn phải dựa trên miền dữ liệu thực tế; ví dụ nhỏ này không kiểm tra giới hạn của long.

Dù tham số các hàm là List<Integer>, đối tượng trong main là ArrayList. Điều đó quan trọng với hàm dùng get(i): khai báo kiểu giao diện không xóa đặc điểm của đối tượng thực tế.

## 7. RandomAccess là dấu hiệu cho thuật toán, không phải một thao tác

### 7.1. Đây là marker interface

`java.util.RandomAccess` là giao diện đánh dấu (marker interface). Nó không khai báo phương thức để tự lấy phần tử.

Hình dung hình dạng giao diện, lược bỏ phần tài liệu:

```java
// Đoạn minh họa hình dạng giao diện, không phải lớp cần tạo trong dự án.
public interface RandomAccess {
}
```
Một đối tượng có thể vừa là List vừa triển khai RandomAccess. Thuật toán kiểm tra:

```java
// Đoạn minh họa: values có kiểu List<?>.
if (values instanceof RandomAccess) {
    // Có thể cân nhắc thuật toán dùng truy cập theo chỉ số.
} else {
    // Có thể ưu tiên cách đi tuần tự bằng iterator.
}
```

Theo [hợp đồng RandomAccess của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/RandomAccess.html), dấu hiệu này mô tả hỗ trợ truy cập bất kỳ theo chỉ số nhanh, nhìn chung là thời gian hằng số, để thuật toán tổng quát có thể chọn cách xử lý phù hợp.

Không có cơ chế trong interface tự kiểm tra độ phức tạp của get. Nếu một lớp tự khai báo implements RandomAccess nhưng triển khai get rất chậm, việc thêm marker không làm thuật toán của lớp đó nhanh hơn. Người viết lớp phải chọn marker phù hợp với hành vi thực tế.

### 7.2. “Random access” không có nghĩa là “random order”

ArrayList có thể đọc trực tiếp phần tử ở chỉ số 900 mà không cần đi qua 900 phần tử trước nó. Đó là ý nghĩa khả năng truy cập bất kỳ.

Cùng một ArrayList có thể được đọc theo:

```text
Liên tiếp:      0, 1, 2, 3, 4, ...
Ngược:          n - 1, n - 2, ..., 0
Theo một lịch:  7, 2, 9, 1, 5, ...
```
Cả ba đều dùng một đối tượng triển khai RandomAccess. Nhưng mẫu địa chỉ bộ nhớ được chạm đến và cơ hội tái sử dụng bộ nhớ đệm có thể khác nhau.

Vì vậy, không viết “ArrayList có RandomAccess nên locality luôn tốt”, cũng không viết “random access nghĩa là cache luôn kém”. Marker nói về năng lực truy cập của cấu trúc; locality còn phụ thuộc mẫu sử dụng cụ thể.

### 7.3. Marker không nói các thuộc tính khác

RandomAccess không khẳng định rằng danh sách:

- Đã được sắp xếp theo giá trị.
- Không có phần tử trùng hoặc null.
- Cho phép sửa đổi.
- Có snapshot khi duyệt.
- An toàn khi nhiều luồng cùng sửa.
- Tìm contains hoặc indexOf trong thời gian hằng số.
- Giữ toàn bộ đối tượng phần tử cạnh nhau trong bộ nhớ.

Thuật toán phải kiểm tra hoặc quy định các điều kiện liên quan riêng, thay vì suy ra chúng từ một marker.

## 8. Vì sao một thuật toán dùng get(i) có thể trở thành bậc hai?

Trên ArrayList, mỗi get(i) có chi phí hằng số. Duyệt n chỉ số có tổng tuyến tính:

```text
n lần lấy phần tử * O(1) = O(n)
```
Với LinkedList, lấy một chỉ số có thể phải đi qua các nút từ đầu hoặc cuối danh sách đến vị trí cần lấy. Khi gọi get(0), get(1), ..., get(n - 1), ta bắt đầu nhiều cuộc tìm vị trí riêng.

Chi phí của những lần đi qua nút cộng lại có thể là Θ(n²), dù vòng lặp bên ngoài chỉ có n lượt. LinkedList chọn đầu gần vị trí hơn không làm tổng cả chuỗi get liên tiếp trở thành tuyến tính.

Nếu thay bằng một iterator đi từ đầu đến cuối, iterator giữ vị trí hiện tại và tiến sang nút kế tiếp; không phải bắt đầu lại việc tìm chỉ số cho mỗi phần tử. Một lượt duyệt khi đó tuyến tính.

Tài liệu [LinkedList Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html) mô tả việc truy cập bằng chỉ số phải đi qua các liên kết từ đầu hoặc cuối phù hợp.

| Cấu trúc thực tế | Duyệt bằng get(i) từ 0 đến n - 1 | Duyệt bằng iterator một lượt |
| --- | --- | --- |
| ArrayList | O(n) | O(n) |
| LinkedList | Có thể Θ(n²) | O(n) |

Bảng nói về số công việc theo kích thước dữ liệu, với công việc trên từng phần tử là hằng số. Nó không đưa ra thời gian tính bằng mili giây.

Hai cách duyệt ArrayList cùng O(n) vẫn có thể có hằng số khác nhau do JVM và phần cứng. Nhưng tránh một thuật toán bậc hai trên danh sách liên kết thường quan trọng hơn việc suy đoán một khác biệt nhỏ giữa hai vòng lặp tuyến tính.

Đây là lý do RandomAccess hữu ích trong thư viện nhận List tổng quát: không cần buộc mọi đầu vào là ArrayList nhưng vẫn có dấu hiệu để tránh cách truy cập không phù hợp.

## 9. Ví dụ chạy được: chọn cách duyệt theo RandomAccess

Lưu vào `RandomAccessChoiceDemo.java`:

```java
import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedList;
import java.util.List;
import java.util.Objects;
import java.util.RandomAccess;

public class RandomAccessChoiceDemo {
    record Result(String path, long sum) {}

    static Result sumAdaptively(List<Integer> values) {
        Objects.requireNonNull(values, "values");

        long sum = 0;
        if (values instanceof RandomAccess) {
            for (int i = 0, n = values.size(); i < n; i++) {
                sum += values.get(i);
            }
            return new Result("index", sum);
        }

        for (Iterator<Integer> it = values.iterator(); it.hasNext();) {
            sum += it.next();
        }
        return new Result("iterator", sum);
    }

    static void show(String label, List<Integer> values) {
        Result result = sumAdaptively(values);
        System.out.println(label + " RandomAccess = "
                + (values instanceof RandomAccess));
        System.out.println(label + " path = " + result.path()
                + ", sum = " + result.sum());
    }

    public static void main(String[] args) {
        List<Integer> array = new ArrayList<>(List.of(10, 20, 30, 40));
        List<Integer> linked = new LinkedList<>(List.of(10, 20, 30, 40));

        show("ArrayList", array);
        show("LinkedList", linked);
    }
}
```
Biên dịch và chạy:

```shell
javac --release 17 RandomAccessChoiceDemo.java
java RandomAccessChoiceDemo
```
Kết quả:

```text
ArrayList RandomAccess = true
ArrayList path = index, sum = 100
LinkedList RandomAccess = false
LinkedList path = iterator, sum = 100
```
Giải thích:

1. Hai biến đều có kiểu List<Integer> nhưng giữ hai cách triển khai khác nhau.
2. ArrayList mang marker RandomAccess nên hàm chọn nhánh index.
3. LinkedList không mang marker này nên hàm giữ một iterator để đi tuần tự.
4. Cả hai nhánh vẫn phải đáp ứng cùng yêu cầu chức năng: tổng bằng 100.

Hàm minh họa cách dùng marker để chọn chiến lược. Nó không phải bằng chứng rằng phải rẽ hai nhánh cho mọi phép cộng. Trong mã ứng dụng chỉ cần cộng từng phần tử, một vòng foreach duy nhất thường đã đơn giản và phù hợp cho cả hai loại danh sách.

Không thay kiểm tra marker bằng `values.getClass() == ArrayList.class` nếu mục tiêu là nhận biết năng lực truy cập. Kiểm tra tên lớp cụ thể có thể bỏ qua các cách triển khai khác hoặc các lớp bọc vẫn có đặc điểm truy cập nhanh.

Ngược lại, việc một đối tượng không mang marker không chứng minh rằng nó luôn chậm. Thuật toán tổng quát chỉ đang dùng một dấu hiệu được quy ước để chọn chiến lược an toàn hơn về đặc điểm truy cập.

Nếu thư viện có yêu cầu mạnh hơn, chẳng hạn không cho null hoặc không được sửa cấu trúc trong khi hàm chạy, hãy ghi các tiền điều kiện đó trong hợp đồng. RandomAccess không thay thế chúng.

## 10. Ví dụ chạy được: sao chép danh sách không gom các object thành một khối

Lưu vào `ArrayListReferencesDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class ArrayListReferencesDemo {
    static final class Reading {
        int value;

        Reading(int value) {
            this.value = value;
        }
    }

    static List<Integer> valuesOf(List<Reading> readings) {
        ArrayList<Integer> values = new ArrayList<>();
        for (Reading reading : readings) {
            values.add(reading.value);
        }
        return values;
    }

    static long sum(List<Reading> readings) {
        long total = 0;
        for (Reading reading : readings) {
            total += reading.value;
        }
        return total;
    }

    public static void main(String[] args) {
        Reading shared = new Reading(10);
        ArrayList<Reading> original = new ArrayList<>(
                List.of(shared, new Reading(20), shared));
        ArrayList<Reading> copy = new ArrayList<>(original);

        System.out.println("initial values = " + valuesOf(original));
        System.out.println("initial sum = " + sum(original));
        System.out.println("same object at 0 and 2 = "
                + (original.get(0) == original.get(2)));
        System.out.println("different list containers = " + (original != copy));
        System.out.println("shared first element across lists = "
                + (original.get(0) == copy.get(0)));

        shared.value = 99;
        System.out.println("original after object change = " + valuesOf(original));
        System.out.println("copy after object change = " + valuesOf(copy));
        System.out.println("sum after object change = " + sum(original));

        copy.set(1, new Reading(7));
        System.out.println("original after copy.set = " + valuesOf(original));
        System.out.println("copy after copy.set = " + valuesOf(copy));
    }
}
```
Biên dịch và chạy:

```shell
javac --release 17 ArrayListReferencesDemo.java
java ArrayListReferencesDemo
```
Kết quả:

```text
initial values = [10, 20, 10]
initial sum = 40
same object at 0 and 2 = true
different list containers = true
shared first element across lists = true
original after object change = [99, 20, 99]
copy after object change = [99, 20, 99]
sum after object change = 218
original after copy.set = [99, 20, 99]
copy after copy.set = [99, 7, 99]
```
Những điều có thể kết luận từ chương trình:

- Hai vị trí 0 và 2 của original giữ cùng một đối tượng Reading.
- copy là một container khác, nhưng ban đầu dùng chung các đối tượng phần tử với original.
- Thay trường của shared làm giá trị đọc qua cả hai vị trí và cả hai danh sách thay đổi.
- `copy.set(1, ...)` thay tham chiếu ở một vị trí của copy, không thay tham chiếu ở vị trí tương ứng của original.

Những điều **không** thể kết luận từ output:

- Địa chỉ thật của các đối tượng.
- Khoảng cách giữa các Reading trên heap.
- Số dòng bộ nhớ đệm đã dùng.
- Tốc độ duyệt của copy so với original.

Toán tử == trên tham chiếu cho biết có cùng đối tượng hay không, không cho địa chỉ bộ nhớ. `System.identityHashCode` cũng không phải API để suy ra địa chỉ hoặc khoảng cách vật lý giữa các đối tượng.

Ví dụ này giúp sửa một mô hình tinh thần sai: “new ArrayList<>(original) làm mọi dữ liệu phần tử trở nên liền nhau”. Thao tác sao chép container không tự sao chép sâu các phần tử hoặc kiểm soát cách JVM bố trí chúng.

## 11. Bố trí dữ liệu và mẫu truy cập cần được xem cùng nhau

### 11.1. Liên tiếp trong danh sách khác với liên tiếp trong dữ liệu sâu

Giả sử ArrayList chứa các tài liệu. Vòng lặp đọc các tham chiếu theo thứ tự tốt, nhưng mỗi tài liệu lại có một cây các nút, chuỗi và danh sách con. Nếu công việc đi sâu khắp cây, toàn bộ vùng dữ liệu được chạm đến lớn hơn nhiều so với mảng tham chiếu.

Nếu mục tiêu chỉ cần cộng một trường số nhỏ trên hàng triệu đối tượng, cấu trúc biểu diễn có thể ảnh hưởng rõ đến lượng dữ liệu phải đọc. Nếu mục tiêu là xử lý từng tài liệu một cách phức tạp, tối ưu vòng lặp ngoài có thể không phải ưu tiên đầu tiên.

Đừng tự đổi mô hình đối tượng hoặc API chỉ vì một suy đoán về cache. Trước hết cần xác định công việc nào thật sự chiếm thời gian và yêu cầu nghiệp vụ nào phải được giữ.

### 11.2. Sắp xếp và xáo trộn ảnh hưởng các tầng khác nhau

Khi đổi thứ tự phần tử ArrayList:

- Dãy ô tham chiếu vẫn thuộc mảng bên trong.
- Giá trị tham chiếu được đặt ở mỗi ô có thể đổi.
- Thứ tự truy cập các đối tượng được trỏ tới có thể đổi.
- JVM không được yêu cầu di chuyển các đối tượng phần tử theo thứ tự mới.

Vì thế, hai ArrayList chứa cùng tập đối tượng nhưng có thứ tự khác nhau có thể có thời gian xử lý khác nhau. Đây là một giả thuyết hiệu năng có cơ sở để đo, không phải tỷ lệ tốc độ được bảo đảm.

Với dữ liệu số, thay đổi thứ tự còn có thể ảnh hưởng hành vi nghiệp vụ hoặc kết quả nếu phép toán không độc lập thứ tự. Ví dụ, không tùy ý đổi thứ tự cộng số thực rồi mặc định kết quả phải giống từng bit. Tối ưu locality phải giữ đúng yêu cầu kết quả.

### 11.3. Đọc nhiều lần không miễn phí

Nếu phải quét n phần tử qua r lượt, số lượt đọc về mặt thuật toán vẫn là O(r * n). Bộ nhớ đệm có thể giảm hằng số trong điều kiện phù hợp, nhưng không biến việc xử lý r lượt thành một lượt.

Có thể cân nhắc kết hợp các phép xử lý độc lập trong một lượt để giảm số lần duyệt. Tuy nhiên, việc kết hợp phải giữ đúng thứ tự tác dụng, điều kiện dừng và độ rõ ràng của thuật toán. Không gộp các bước có phụ thuộc khác nhau chỉ vì muốn ít vòng lặp hơn.

## 12. Kiểm chứng hiệu năng mà không biến giả thuyết thành sự thật

### 12.1. Một kết quả đúng không phải số đo locality

Ba chương trình trong bài kiểm chứng:

| Ví dụ | Điều đã kiểm chứng |
| --- | --- |
| TraversalStyles | Các cách duyệt trả cùng tổng trên dữ liệu đã cho |
| RandomAccessChoice | Kiểm tra marker chọn đúng nhánh với ArrayList và LinkedList |
| References | Danh sách có thể dùng chung đối tượng và bản sao container không phải bản sao sâu |

Không chương trình nào đo số lần trượt bộ nhớ đệm hoặc địa chỉ heap. In một dòng “ArrayList nhanh” sau khi chạy không tạo thêm bằng chứng.

### 12.2. Vì sao không dùng một phép bấm giờ nhỏ?

Một lần đo quanh vòng lặp có thể chịu ảnh hưởng của:

- JIT chưa hoặc đã tối ưu phần mã đó.
- Bộ nhớ đang nóng hoặc lạnh theo lịch chạy trước đó.
- Thu gom rác và cấp phát dữ liệu kiểm thử.
- Trình biên dịch loại bỏ kết quả không được dùng.
- Boxing/unboxing, kiểu dữ liệu và kích thước đối tượng.
- In console, tạo chuỗi hoặc công việc khác nằm trong vùng đo.
- CPU, tần số, tải nền và cấu hình JVM.

Vì vậy, không rút ra một quy luật “for nhanh hơn foreach X lần” từ một đoạn nanoTime chạy một lần trên vài chục phần tử.

### 12.3. Nếu cần đo, đặt một câu hỏi cụ thể

Một câu hỏi đủ rõ có thể là:

> Trên JVM và dữ liệu của ứng dụng này, tổng hợp một trường số qua ArrayList ổn định bằng chỉ số và bằng iterator có khác biệt đáng kể không?

Sau đó:

1. Tách chuẩn bị dữ liệu khỏi phần đo nếu mục tiêu là đo một lượt đọc.
2. Giữ cùng công việc nghiệp vụ và cùng dữ liệu giữa các phương án.
3. Dùng nhiều kích thước dữ liệu, không chỉ một danh sách nhỏ.
4. Đảm bảo kết quả được sử dụng để tránh tối ưu loại bỏ công việc.
5. Có giai đoạn khởi động, nhiều lần đo và tiến trình chạy độc lập phù hợp.
6. Ghi JVM, phần cứng, tham số chạy và mức sai số cùng kết quả.

JMH là công cụ của OpenJDK dành cho benchmark JVM. [Mẫu JMHSample_39_MemoryAccess](https://github.com/openjdk/jmh/blob/master/jmh-samples/src/main/java/org/openjdk/jmh/samples/JMHSample_39_MemoryAccess.java) minh họa việc biểu diễn số nguyên bằng mảng nguyên thủy, danh sách số được boxing và thứ tự tham chiếu có thể làm phép đo chịu ảnh hưởng lớn của truy cập bộ nhớ.

Mẫu đó là tài liệu học cách đặt phép đo, không phải bảng tốc độ có thể áp nguyên vào mọi máy. Muốn kết luận về cache miss cụ thể, cần công cụ phân tích hoặc bộ đếm phần cứng phù hợp và phải kiểm tra giới hạn của công cụ trên môi trường đó.

## 13. Các nhầm lẫn cần tránh

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “ArrayList giữ các object liên tiếp” | Nó giữ các tham chiếu trong mảng; vị trí object được tham chiếu là vấn đề riêng |
| “foreach làm mất locality của ArrayList” | Iterator vẫn duyệt các phần tử của cùng cấu trúc ArrayList |
| “RandomAccess nghĩa là phải đọc ngẫu nhiên” | Nó chỉ báo khả năng truy cập vị trí bất kỳ nhanh |
| “Có RandomAccess thì contains O(1)” | Marker không tạo chỉ mục tìm theo giá trị |
| “Cùng O(n) nên mọi vòng lặp nhanh như nhau” | Big O không mô tả hết hằng số, bố trí bộ nhớ hoặc tối ưu JVM |
| “ArrayList luôn nhanh hơn LinkedList trong mọi bài toán” | Phải xét mẫu thao tác, dữ liệu, vị trí sửa và môi trường |
| “get(i) trong vòng for luôn là duyệt tuyến tính” | Tổng phụ thuộc chi phí get của cách triển khai thực tế |
| “Sao chép hoặc sort làm các object nằm sát nhau” | Các thao tác đó không cho chương trình kiểm soát vị trí heap của phần tử |
| “Cache locality tốt nghĩa là an toàn luồng” | Locality nói về truy cập bộ nhớ; đồng bộ và khả năng nhìn thấy thay đổi là vấn đề khác |
| “Cứ thêm implements RandomAccess là danh sách nhanh lên” | Marker mô tả đặc điểm; không thay thuật toán của get |
| “identityHashCode cho biết object ở địa chỉ nào” | Nó không phải địa chỉ bộ nhớ và không đo khoảng cách giữa các object |
| “Kết quả một lần nanoTime chứng minh cache miss ít hơn” | Đo thời gian tổng không tự phân tách được nguyên nhân phần cứng |

## 14. Thực hành suy luận trước khi tối ưu

### Bài 1: Duyệt liên tiếp trên một RandomAccess list có mâu thuẫn không?

Không. “Liên tiếp” mô tả lịch truy cập mà vòng lặp đang dùng; RandomAccess mô tả khả năng của cấu trúc. Một ArrayList vừa hỗ trợ lấy chỉ số bất kỳ nhanh, vừa có thể được quét từ đầu đến cuối.

### Bài 2: Hai ArrayList có cùng n có chắc cùng tốc độ duyệt không?

Không. Nếu một danh sách chứa các đối tượng nhỏ được dùng lại nhiều lần, còn danh sách kia trỏ đến nhiều đối tượng lớn và đọc sâu, lượng dữ liệu phải chạm đến khác nhau. Mẫu công việc và trạng thái JVM cũng có thể khác.

### Bài 3: Hàm nhận List và dùng get(i) để cộng toàn bộ có vấn đề gì?

Nó có thể tuyến tính với ArrayList nhưng bậc hai với LinkedList. Nếu chỉ cần đọc tuần tự, dùng foreach/iterator là một cách tự nhiên. Nếu thuật toán thật sự có hai chiến lược khác nhau, có thể dùng RandomAccess để chọn như ví dụ trong bài.

### Bài 4: Vì sao ArrayList<Integer> không có cùng biểu diễn với int[]?

ArrayList<Integer> giữ tham chiếu Integer; khi cộng thường phải lấy giá trị int qua unboxing. int[] có thành phần int nguyên thủy. Việc một số Integer được tái sử dụng không xóa khác biệt giữa hai biểu diễn.

### Bài 5: Có thể dùng output của ReferencesDemo để biết locality không?

Không. Output chứng minh quan hệ dùng chung tham chiếu và khác biệt giữa sửa đối tượng với thay một ô trong container. Nó không cung cấp địa chỉ hay bộ đếm bộ nhớ đệm. Quan hệ đối tượng đúng là nền tảng để đặt giả thuyết, nhưng không thay thế phép đo.

### Bài 6: Nên sửa gì trước trong đoạn duyệt chậm?

Giả sử mỗi lượt gọi `items.get(i)`, rồi lại tìm cùng đối tượng bằng `items.indexOf(value)` để lấy vị trí hiện tại. Trước khi so for với foreach, hãy xem có đang tạo tìm kiếm tuyến tính lồng nhau không, và có thực sự cần tìm lại vị trí đã biết không.

Cũng phải nhớ rằng indexOf trả lần xuất hiện đầu tiên theo quan hệ bằng nhau. Nếu có phần tử trùng, kết quả không nhất thiết là chỉ số của lượt duyệt hiện tại. Đây có thể đồng thời là lỗi hiệu năng và lỗi tính đúng.

### Bài 7: Tự thiết kế một phép đo có thể trả lời được

Chọn một tác vụ đọc ổn định thực tế, xác định dữ liệu, kết quả cần giữ, các cách duyệt muốn so sánh và những công việc nào thuộc vùng đo. Viết trước điều có thể kết luận và điều không thể kết luận từ số đo.

Nếu chỉ đo thời gian tổng, hãy báo thời gian tổng trên môi trường đã ghi. Không tự đặt nhãn “ít cache miss hơn” khi chưa có bằng chứng phù hợp.

Khi đọc một nhận xét về ArrayList, hãy hỏi: **nhận xét đó nói về hợp đồng truy cập, số bước thuật toán, dãy tham chiếu hay bố trí đối tượng và phần cứng?** Phân biệt đúng tầng giúp chọn cách duyệt rõ ràng, tránh bậc hai ngoài ý muốn và đánh giá hiệu năng bằng bằng chứng phù hợp.
