# ensureCapacity và trimToSize

## 1. Hai thao tác quản lý chỗ chứa của ArrayList

`ArrayList` dùng một mảng nền để giữ tham chiếu đến các phần tử. Số phần tử đang có gọi là `size`; số ô của mảng nền dành để chứa phần tử gọi là `capacity`. Thường có một phần chỗ dự phòng giữa hai đại lượng này.

Hai phương thức sau tác động đến chỗ chứa:

```java
public void ensureCapacity(int minCapacity)
public void trimToSize()
```

Đây là chữ ký API, không phải một chương trình Java độc lập.

- `ensureCapacity` chuẩn bị đủ chỗ cho một tổng số phần tử dự kiến, khi cần tăng.
- `trimToSize` thu chỗ chứa về bằng số phần tử đang có.

Chúng không phải thao tác thêm hoặc xóa phần tử. Một danh sách có nội dung `[A, B, C]` vẫn có nội dung đó sau khi gọi thành công một trong hai phương thức.

Mục đích của chúng là giúp cân bằng số lần cấp mảng/sao chép với lượng chỗ dự phòng được giữ. Dùng đúng thời điểm có thể hữu ích; gọi thêm thật nhiều không tự làm chương trình hiệu quả hơn.

| Thuộc tính | ensureCapacity(minCapacity) | trimToSize() |
|---|---|---|
| Mục tiêu | Chuẩn bị chỗ cho ít nhất tổng số phần tử cần chứa | Bỏ chỗ dự phòng vượt size hiện tại |
| Có thay size không? | Không | Không |
| Có thay thứ tự hoặc giá trị phần tử không? | Không | Không |
| Có thể thay mảng nền không? | Có, nếu cần tăng | Có, nếu cần thu gọn |
| Có làm giảm capacity đang lớn không? | Không dùng để thu nhỏ | Có, về size |
| Kết quả trả về | `void` | `void` |
| Sau đó danh sách còn thêm/xóa được không? | Có | Có |

Đây là các phương thức riêng của `ArrayList`, không thuộc giao diện `List`. [ArrayList.ensureCapacity](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#ensureCapacity(int)), [ArrayList.trimToSize](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html#trimToSize()).

## 2. ensureCapacity nhận tổng sức chứa tối thiểu

### 2.1. Không phải số ô cần thêm vào capacity

Đoạn minh họa bên trong một phương thức, cần import `java.util.ArrayList`:

```java
ArrayList<String> names = new ArrayList<>(2);
names.add("An");
names.add("Binh");

names.ensureCapacity(100);

// names.size() vẫn là 2.
// names vẫn chứa [An, Binh].
```

Số 100 nghĩa là chuẩn bị chỗ để danh sách chứa ít nhất tổng cộng 100 phần tử, không có nghĩa “tăng thêm 100 ô so với capacity hiện tại”.

Phương thức cũng không có nghĩa “đặt capacity chính xác bằng 100”. Nếu chỗ chứa đã đủ lớn, không cần tăng; khi phải tăng, chính sách của triển khai có thể chọn một mảng lớn hơn yêu cầu tối thiểu.

Ví dụ khái niệm:

| Trước lời gọi | Lời gọi | Kết luận phù hợp |
|---|---|---|
| Capacity đang là 20 | `ensureCapacity(100)` | Chuẩn bị đủ cho ít nhất tổng cộng 100 phần tử |
| Capacity đang là 200 | `ensureCapacity(100)` | Không thu nhỏ về 100 |
| Size đang là 50 | `ensureCapacity(10)` | Không xóa 40 phần tử; size vẫn 50 |
| Danh sách rỗng | `ensureCapacity(100)` | Không tạo 100 phần tử `null`; size vẫn 0 |

Các con số capacity trong bảng là giả định để giải thích ý nghĩa tham số, không phải kết quả đọc bằng một phương thức công khai.

### 2.2. Nếu sắp thêm một đợt dữ liệu, tính tổng cần có

Giả sử hiện có `currentSize` phần tử và sắp thêm `incomingCount` phần tử. Mục tiêu là:

```text
requiredTotal = currentSize + incomingCount
```

Đoạn minh họa:

```java
int requiredTotal = Math.addExact(rows.size(), incoming.size());
rows.ensureCapacity(requiredTotal);
```

Ở đây `rows` là một `ArrayList` đã có và `incoming` là nguồn dữ liệu độc lập, ổn định trong lúc nạp. `Math.addExact` kiểm tra tràn số `int`; nếu tổng không biểu diễn được, nó ném `ArithmeticException` thay vì âm thầm biến thành một giá trị sai.

Chẳng hạn, đang có 8.000 mục và sắp thêm 5.000 mục thì yêu cầu là tổng 13.000. Chỉ gọi `ensureCapacity(5_000)` không diễn đạt được nhu cầu chứa tổng số mục sau đợt thêm.

Việc tổng vẫn nằm trong `int` không bảo đảm có đủ bộ nhớ để cấp phát mảng đó. Đây là hai điều kiện khác nhau: tính toán số lượng không tràn và tài nguyên thực tế đáp ứng được yêu cầu. [Math.addExact(int, int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#addExact(int,int)).

Nếu chỉ cần nối trực tiếp một collection, `addAll` của `ArrayList` đã có cơ chế chuẩn bị chỗ theo số phần tử cần thêm. Đừng mặc định rằng gọi thêm `ensureCapacity` trước mọi `addAll` luôn cần thiết hoặc luôn nhanh hơn. Dự phòng rõ ràng thường có ý nghĩa khi biết trước quy mô của một chuỗi thao tác nạp hoặc xử lý nhiều bước.

### 2.3. Dự phòng không làm chỉ số trở nên hợp lệ

Đoạn minh họa:

```java
ArrayList<String> rows = new ArrayList<>();
rows.ensureCapacity(50);

rows.set(0, "first"); // IndexOutOfBoundsException
```

Danh sách vẫn có size bằng 0. `set` chỉ thay một phần tử đã tồn tại, còn capacity chỉ là chỗ chứa. Muốn tạo phần tử đầu tiên, dùng `rows.add("first")`.

Giới hạn chỉ số vẫn dựa vào size:

- `get(i)`, `set(i, value)`: `0 <= i < size()`.
- `add(i, value)`: `0 <= i <= size()`.
- Dự phòng nhiều hơn không tự tạo những phần tử trung gian.

### 2.4. Capacity không phải kiểm tra đầu vào nghiệp vụ

Nếu hệ thống chỉ cho tối đa 100 mục, `ensureCapacity(100)` không thiết lập giới hạn đó. Phần tử thứ 101 vẫn có thể được thêm; cần quy tắc kiểm tra riêng.

Tương tự, nếu số lượng dự kiến đến từ đầu vào, hãy tự kiểm tra tính hợp lệ của nó. Đừng dùng `ensureCapacity` như một hàm xác thực số lượng. Ví dụ, trong OpenJDK 17, một yêu cầu âm không đi vào nhánh tăng mảng; không thể trông chờ nó luôn báo lỗi để phát hiện phép tính sai.

Đối số capacity ban đầu âm của hàm dựng `ArrayList(int)` lại có quy định báo `IllegalArgumentException`. Hai API có mục đích khác nhau; không suy đoán quy tắc kiểm tra của phương thức này từ phương thức kia.

## 3. trimToSize thu phần dự phòng, giữ nguyên phần tử

Giả sử danh sách đang có:

```text
size = 3
capacity = 10
nội dung logic = [A, B, C]
```

Sau `trimToSize()`:

```text
size = 3
capacity = 3
nội dung logic = [A, B, C]
```

Nếu cần thu gọn, triển khai tạo chỗ chứa nhỏ hơn đủ cho các tham chiếu hiện có. Nó không gọi `remove` để bớt phần tử và không làm phần tử cuối biến mất.

Đoạn minh họa:

```java
ArrayList<String> names = new ArrayList<>(1_000);
names.add("An");
names.add("Binh");

names.trimToSize();

// names vẫn là [An, Binh].
// names.size() vẫn là 2.
```

### 3.1. Sau trim vẫn thêm được

`trimToSize` không biến danh sách thành danh sách kích thước cố định hoặc không sửa đổi được.

Nếu capacity đã bằng size và gọi `add`, danh sách lại phải có thêm chỗ chứa cho phần tử mới. Vì vậy, thu gọn sớm rồi tiếp tục nạp nhiều có thể tạo thêm việc cấp phát/sao chép mà trước đó không cần.

Cũng không dùng trim như cách đặt “giới hạn cứng” bằng size hiện tại. Đây là điều chỉnh cách lưu trữ tại thời điểm gọi.

### 3.2. clear và trim giải quyết hai mục tiêu khác nhau

| Thao tác | Phần tử logic | Chỗ chứa nền trong triển khai OpenJDK |
|---|---|---|
| `clear()` | Xóa toàn bộ, size về 0 | Giữ mảng nền để tái sử dụng |
| `trimToSize()` | Giữ nguyên phần tử | Thu về size |
| `clear(); trimToSize();` | Xóa toàn bộ | Đồng thời bỏ phần chỗ chứa dư của danh sách rỗng |

Nếu đang có dữ liệu mà chỉ gọi trim, dữ liệu vẫn được danh sách giữ. Trim không phải cách “giải phóng các đối tượng phần tử”.

Nếu gọi clear rồi trim, các đối tượng cũ có còn sống hay không còn phụ thuộc các tham chiếu khác. Ngay cả khi mảng cũ không còn được giữ, việc bộ gom rác thu hồi hoặc hệ điều hành quan sát lượng bộ nhớ giảm không được bảo đảm xảy ra ngay tại lời gọi.

Một đợt xử lý có quy mô tương tự đợt sau có thể hưởng lợi từ việc giữ mảng sau clear. Một đợt rất lớn rồi chuyển sang giữ lâu danh sách nhỏ lại có thể là lý do cân nhắc trim. Quyết định dựa vào vòng đời dữ liệu, không chỉ nhìn size hiện tại.

## 4. Chi phí của hai phương thức nằm ở cấp mảng và sao chép

Mảng Java có độ dài cố định. Khi cần thay độ dài mảng nền, `ArrayList` không sửa trực tiếp thuộc tính `length` của mảng cũ; nó dùng một mảng khác.

### 4.1. Chi phí khi tăng

Khi `ensureCapacity` phải tăng:

1. Tính độ dài mảng mới đủ đáp ứng yêu cầu.
2. Cấp một mảng tham chiếu mới.
3. Chuyển nội dung mảng cũ sang mảng mới.
4. Cho cùng đối tượng `ArrayList` sử dụng mảng mới.

Trong OpenJDK, thao tác sao chép có thể đi qua cả các ô dự phòng của mảng cũ, không chỉ riêng số phần tử logic. Vì thế, không mô tả mọi lần reserve bằng đúng chi phí `O(size)` nếu capacity cũ có thể lớn hơn size nhiều.

Ngoài chi phí sao chép còn có chi phí cấp và khởi tạo mảng mới, phụ thuộc kích thước được yêu cầu. Tăng capacity là một thao tác quản lý bộ nhớ thật, không phải chỉ cập nhật một con số.

### 4.2. Chi phí khi thu

Khi trim thực sự thu mảng và size khác 0, cần chỗ chứa mới cho size tham chiếu và sao chép các tham chiếu đang dùng. Nếu size bằng 0, triển khai có thể chuyển sang mảng rỗng dùng chung.

Trong thời gian thay mảng, mảng cũ và mảng mới có thể cùng tồn tại tạm thời. Trim nhằm giảm chỗ giữ về sau, nhưng bản thân thao tác có thể cần thêm một lần cấp phát trước khi mảng cũ đủ điều kiện được thu hồi.

### 4.3. Không tạo danh sách mới hoặc sao chép sâu phần tử

Cả hai phương thức đều trả `void` và điều chỉnh cùng đối tượng danh sách. Nếu hai biến cùng tham chiếu một `ArrayList`, chúng vẫn cùng tham chiếu danh sách đó sau lời gọi.

Các đối tượng phần tử không tự được nhân bản. Thay mảng nền chỉ thay chỗ giữ các tham chiếu; một đối tượng phần tử có thể vẫn được nhiều nơi cùng tham chiếu. Không dùng hai phương thức này để tạo bản sao độc lập hoặc làm dữ liệu bất biến.

## 5. Chọn thời điểm dự phòng và thu gọn

Một vòng đời thường dễ quản lý là:

```text
Ước lượng số phần tử sẽ có
        |
        v
Cấp capacity ban đầu hoặc ensureCapacity
        |
        v
Nạp/thêm/xử lý dữ liệu
        |
        v
Hoàn thành đợt sửa đổi lớn
        |
        v
Nếu sẽ giữ lâu và ít thêm tiếp: cân nhắc trimToSize
        |
        v
Tạo iterator/view hoặc bàn giao dữ liệu để đọc
```

Không phải mọi danh sách đều cần bước dự phòng hoặc trim. Flow này đặt các thao tác quản lý chỗ ở ranh giới dễ kiểm soát, khi chúng có lý do rõ.

| Tình huống | Cách cân nhắc |
|---|---|
| Tạo danh sách mới, biết khá chắc tổng số mục | `new ArrayList<>(expectedTotal)` thường diễn đạt trực tiếp |
| Đã có danh sách, sắp nạp thêm nhiều mục | Tính tổng cần có rồi cân nhắc `ensureCapacity` |
| Số lượng nhỏ hoặc không có ước lượng hợp lý | Để cơ chế tự tăng hoạt động thường đủ |
| Vừa xóa nhiều mục, danh sách nhỏ sẽ được giữ lâu | Cân nhắc trim sau khi xóa xong |
| Đang nạp liên tục | Giữ chỗ dự phòng, tránh trim giữa mỗi lần thêm |
| clear rồi sẽ nạp đợt tương tự ngay sau | Giữ mảng nền có thể có lợi |
| Đang có iterator hoặc view được sử dụng | Hoàn tất quản lý capacity ở ranh giới phù hợp trước khi duyệt/tạo lại view |

Ước lượng quá lớn có thể làm giữ nhiều chỗ không dùng. Ước lượng quá nhỏ vẫn không làm sai dữ liệu; danh sách có thể tự tăng, nhưng lợi ích tránh cấp lại có thể giảm.

## 6. Chương trình đầy đủ: dự phòng cho một đợt rồi thu gọn

Các đoạn ngắn phía trên là minh họa trong phương thức và cần import phù hợp. Chương trình sau là tệp độc lập dùng API có trong Java 17.

Lưu thành `CapacityLifecycleDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;

public class CapacityLifecycleDemo {
    private static void appendBatch(
            ArrayList<String> target, List<String> batch) {
        int requiredTotal = Math.addExact(target.size(), batch.size());
        target.ensureCapacity(requiredTotal);
        System.out.println("required total = " + requiredTotal);
        System.out.println("size after reserve = " + target.size());

        for (String value : batch) {
            target.add(value);
        }
    }

    public static void main(String[] args) {
        ArrayList<String> rows = new ArrayList<>(2);
        rows.add("seed");
        ArrayList<String> alias = rows;

        appendBatch(rows, List.of("A", "B", "C"));
        System.out.println("after append = " + rows);
        System.out.println("size after append = " + rows.size());

        rows.remove(1);
        List<String> beforeTrim = new ArrayList<>(rows);
        rows.trimToSize();
        System.out.println("after trim = " + rows);
        System.out.println("trim preserved content = " + rows.equals(beforeTrim));
        System.out.println("same list object = " + (rows == alias));

        rows.add("D");
        System.out.println("after append following trim = " + rows);
        System.out.println("size = " + rows.size());

        rows.clear();
        System.out.println("after clear = " + rows + "; size = " + rows.size());

        rows.ensureCapacity(50);
        System.out.println("after reserve on empty = " + rows
                + "; size = " + rows.size());
        try {
            rows.set(0, "X");
        } catch (IndexOutOfBoundsException ex) {
            System.out.println("set(0) after reserve -> IndexOutOfBoundsException");
        }

        rows.trimToSize();
        rows.add("again");
        System.out.println("after empty trim and reuse = " + rows);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 CapacityLifecycleDemo.java
java CapacityLifecycleDemo
```

Kết quả chuẩn:

```text
required total = 4
size after reserve = 1
after append = [seed, A, B, C]
size after append = 4
after trim = [seed, B, C]
trim preserved content = true
same list object = true
after append following trim = [seed, B, C, D]
size = 4
after clear = []; size = 0
after reserve on empty = []; size = 0
set(0) after reserve -> IndexOutOfBoundsException
after empty trim and reuse = [again]
```

Phương thức `appendBatch` có điều kiện sử dụng trong ví dụ: batch độc lập với target và không bị sửa trong lúc nạp. Nếu nguồn dữ liệu chính là danh sách đích, việc vừa lặp vừa thêm sẽ thành một vấn đề khác; không áp dụng nguyên xi vòng lặp này cho trường hợp đó.

Các bước cần chú ý:

1. Danh sách ban đầu có một phần tử `seed`; batch có ba phần tử. Tổng cần chứa là 4, không phải 3.
2. Sau reserve, size vẫn bằng 1. Chỉ các lệnh `add` trong vòng lặp mới tăng size lên 4.
3. Sau khi xóa `A`, trim giữ nguyên `[seed, B, C]`.
4. So sánh với một bản sao nội dung tạo trước trim cho kết quả `true`; biến `alias` vẫn là cùng đối tượng danh sách.
5. Thêm `D` sau trim vẫn thành công, cho thấy trim không đóng băng danh sách.
6. Dự phòng cho danh sách rỗng không tạo phần tử số 0; `set(0, ...)` vẫn bị từ chối.
7. Sau trim khi rỗng, danh sách vẫn được tái sử dụng bằng `add`.

Ví dụ xác nhận nội dung, size và quan hệ tham chiếu của danh sách. Nó không in capacity bằng suy đoán.

## 7. Không có API công khai đọc capacity để in ra

`ArrayList` có `size()`, `ensureCapacity` và `trimToSize`, nhưng không cung cấp một phương thức công khai `capacity()`.

Vì vậy, một chương trình chỉ dùng API công khai nên kiểm chứng các điều như:

- Reserve và trim không thay size hoặc thứ tự phần tử.
- Dự phòng không làm `set` vào vị trí chưa có trở nên hợp lệ.
- Trim xong vẫn có thể thêm tiếp.
- Hai biến đang cùng tham chiếu danh sách vẫn giữ quan hệ đó.

`toArray().length` là độ dài mảng kết quả chứa phần tử logic, không phải capacity của mảng nền. Dùng nó như phép đo capacity vừa sai ý nghĩa vừa có thể tạo thêm mảng không cần thiết.

Các con số về hệ số tăng, mảng rỗng dùng chung hoặc trường theo dõi sửa đổi có thể được tìm hiểu qua mã nguồn của phiên bản JDK đang xét. Cần ghi rõ đó là phân tích triển khai, không biến thành giả định bắt buộc trong mã nghiệp vụ.

## 8. Một số chi tiết triển khai OpenJDK 17 cần phân biệt với hợp đồng

### 8.1. Reserve nhỏ trên danh sách rỗng mặc định có thể chưa cấp mảng riêng

OpenJDK 17 dùng cơ chế trì hoãn cấp mảng cho danh sách rỗng tạo bằng `new ArrayList<>()`. Một yêu cầu capacity nhỏ trong phạm vi mặc định có thể chưa làm cấp ngay một mảng riêng; chính sách cấp ban đầu sẽ được áp dụng khi thật sự thêm.

Vì vậy, không dùng lời gọi `ensureCapacity(5)` trên một danh sách rỗng mặc định làm bằng chứng rằng “đã cấp ngay mảng vật lý đúng năm ô”. Hãy hiểu ý nghĩa chuẩn bị sức chứa và tách nó khỏi cách cấp phát cụ thể.

### 8.2. Mức tăng có thể vượt yêu cầu

Chính sách tăng trong OpenJDK 17 kết hợp mức tăng ưu tiên với sức chứa tối thiểu đang cần. Con số truyền vào `ensureCapacity` không phải yêu cầu chọn đúng độ dài đó.

Không dựa vào hệ số cố định như “luôn gấp đôi” hoặc “luôn đúng 1,5 lần” để xác nhận chương trình. Mức tăng nhỏ, yêu cầu theo lô và giới hạn mảng có thể làm diễn tiến khác với một công thức đơn giản.

### 8.3. Những phương thức trông như không đổi nội dung vẫn có thể ảnh hưởng lượt duyệt

OpenJDK 17 có một bộ đếm sửa đổi để kiểm tra iterator và các view liên quan:

- `ensureCapacity` khi thật sự đi vào nhánh tăng cập nhật trạng thái theo dõi sửa đổi.
- `trimToSize` cập nhật bộ đếm ngay cả khi capacity đã bằng size và không cần thay mảng.

Điểm thứ hai rất dễ bỏ sót nếu chỉ suy luận “nội dung không đổi thì iterator chắc chắn dùng tiếp được”. Đây là chi tiết triển khai được nêu để giải thích hiện tượng; không cần hoặc không nên tự truy cập bộ đếm đó từ ứng dụng. [ensureCapacity, trimToSize và grow trong OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/ArrayList.java).

## 9. Ảnh hưởng đến iterator và subList

### 9.1. Cùng một size không có nghĩa cùng trạng thái cấu trúc

Tài liệu `ArrayList` tính việc thay đổi kích thước mảng nền một cách tường minh vào các thay đổi cấu trúc. Vì vậy, tăng hoặc thu mảng có thể làm iterator đã tạo trước đó không còn phù hợp, dù size và nội dung phần tử vẫn giống trước.

Một lời gọi tiếp theo như `iterator.next()` có thể ném `ConcurrentModificationException`. Tên ngoại lệ không đòi hỏi phải có hai luồng; một luồng cũng có thể tạo iterator, đổi capacity rồi dùng lại iterator cũ.

Cách tổ chức tốt hơn là hoàn tất dự phòng/thu gọn trước khi bắt đầu một lượt duyệt cần iterator ổn định, rồi tạo iterator sau các thao tác đó.

Không xây dựng tính đúng đắn của chương trình dựa trên việc luôn thấy ngoại lệ ở cùng một vị trí. Cơ chế phát hiện sửa đổi chủ yếu hỗ trợ tìm lỗi; cần tôn trọng vòng đời iterator và quy tắc sửa đổi thay vì bắt lỗi rồi dùng tiếp.

### 9.2. View subList cũng còn liên hệ với danh sách nền

Một `subList` là view của nguồn. Nếu nguồn bị sửa cấu trúc bên ngoài đường thao tác của view, hợp đồng không bảo đảm ngữ nghĩa của view cũ.

Do đó, đừng tạo `part = list.subList(...)`, gọi `list.ensureCapacity(...)` làm tăng mảng hoặc thu mảng nguồn, rồi cho rằng view cũ chắc chắn an toàn vì “chỉ đổi bộ nhớ”.

Đặt quản lý capacity trước khi tạo view cần dùng, hoặc hoàn tất việc dùng view trước khi thay đổi cấu trúc nguồn. Nếu tạo lại view, tính biên theo trạng thái hiện tại và ý định cần chọn dữ liệu. [Quy tắc sửa đổi của ArrayList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayList.html), [giới hạn sử dụng List.subList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#subList(int,int)).

### 9.3. Chương trình quan sát cơ chế phát hiện của OpenJDK

Chương trình sau dùng API có trong Java 17 và minh họa các nhánh được đối chiếu với triển khai OpenJDK 17. Kết quả ngoại lệ dưới đây là minh chứng cho cơ chế đó, không phải yêu cầu rằng mọi JVM phải phát hiện mọi thay đổi ở đúng các lời gọi này.

Lưu thành `CapacityTraversalDemo.java`:

```java
import java.util.ArrayList;
import java.util.ConcurrentModificationException;
import java.util.Iterator;
import java.util.List;

public class CapacityTraversalDemo {
    private static void readNext(String label, Iterator<String> iterator) {
        try {
            System.out.println(label + " -> " + iterator.next());
        } catch (ConcurrentModificationException ex) {
            System.out.println(label + " -> ConcurrentModificationException");
        }
    }

    public static void main(String[] args) {
        ArrayList<String> growing = new ArrayList<>(2);
        growing.add("A");
        Iterator<String> beforeGrowth = growing.iterator();
        growing.ensureCapacity(100);
        readNext("reserve that grows", beforeGrowth);
        readNext("new iterator after reserve", growing.iterator());

        ArrayList<String> shrinking = new ArrayList<>(10);
        shrinking.add("B");
        Iterator<String> beforeShrink = shrinking.iterator();
        shrinking.trimToSize();
        readNext("trim that shrinks", beforeShrink);

        ArrayList<String> alreadyTight = new ArrayList<>(1);
        alreadyTight.add("C");
        Iterator<String> beforeNoOpTrim = alreadyTight.iterator();
        alreadyTight.trimToSize();
        readNext("trim when capacity equals size", beforeNoOpTrim);

        ArrayList<String> sufficient = new ArrayList<>(4);
        sufficient.add("D");
        Iterator<String> beforeNoOpReserve = sufficient.iterator();
        sufficient.ensureCapacity(2);
        readNext("reserve with sufficient capacity", beforeNoOpReserve);

        ArrayList<String> root = new ArrayList<>(2);
        root.add("X");
        root.add("Y");
        List<String> part = root.subList(0, 1);
        root.ensureCapacity(100);
        try {
            System.out.println("old subList size -> " + part.size());
        } catch (ConcurrentModificationException ex) {
            System.out.println("old subList -> ConcurrentModificationException");
        }
        System.out.println("root content = " + root);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 CapacityTraversalDemo.java
java CapacityTraversalDemo
```

Kết quả quan sát với cơ chế OpenJDK được mô tả:

```text
reserve that grows -> ConcurrentModificationException
new iterator after reserve -> A
trim that shrinks -> ConcurrentModificationException
trim when capacity equals size -> ConcurrentModificationException
reserve with sufficient capacity -> D
old subList -> ConcurrentModificationException
root content = [X, Y]
```

Giải thích các trường hợp:

- `growing` có capacity ban đầu 2 và một phần tử. Yêu cầu 100 buộc chuẩn bị mảng lớn hơn; iterator cũ bị từ chối, còn iterator tạo mới sau reserve đọc được `A`.
- `shrinking` có nhiều chỗ dự phòng. Trim thu mảng và iterator tạo trước đó bị từ chối.
- `alreadyTight` đã có capacity bằng size. Dù không cần thu mảng, trim vẫn thay bộ đếm trong triển khai đang xét, nên iterator cũ cũng bị từ chối.
- `sufficient` đã có capacity 4 và chỉ yêu cầu 2. Nhánh reserve không cần tăng, nên iterator trong ví dụ vẫn đọc được `D`.
- `part` là view tạo trước khi mảng của `root` tăng. Việc dùng lại view cũ bị phát hiện, trong khi nguồn vẫn chứa `[X, Y]`.

Không suy từ trường hợp reserve không tăng rằng nên chen các lệnh quản lý capacity vào giữa mọi lượt duyệt. Khi cần bảo đảm mã dễ hiểu và ít phụ thuộc chi tiết triển khai, hãy quản lý chỗ chứa ở ranh giới trước hoặc sau lượt duyệt.

## 10. Các cách dùng làm mất lợi ích của mảng động

### 10.1. Trim sau mỗi lần thêm

Đoạn minh họa cách dùng nên tránh trong một đợt nạp lớn:

```java
for (String value : incoming) {
    rows.add(value);
    rows.trimToSize();
}
```

Sau mỗi vòng, capacity bị ép sát size. Ở vòng tiếp theo, thêm phần tử lại cần thêm chỗ; sau đó trim tiếp tục bỏ phần dự phòng vừa có.

Nếu lặp đủ dài, việc sao chép có thể tích lũy theo kiểu `1 + 2 + ... + n`, dẫn đến chi phí bậc hai thay vì tận dụng tăng trưởng khấu hao của một chuỗi thêm cuối thông thường. Nó còn tạo nhiều mảng trung gian.

Nếu thực sự cần trim, làm sau khi đợt thêm/xóa lớn đã kết thúc và có lý do giữ cấu trúc gọn về sau.

### 10.2. Reserve và trim kéo ngược nhau

Đoạn minh họa:

```java
rows.ensureCapacity(10_000);
rows.trimToSize();
```

Nếu rows đang nhỏ, lệnh đầu chuẩn bị nhiều chỗ còn lệnh sau bỏ chỗ dự phòng. Không có đợt nạp nằm giữa, hai mục tiêu này xung đột và có thể tạo việc cấp phát/sao chép thừa.

Các lời gọi nên gắn với một giai đoạn dữ liệu cụ thể: chuẩn bị trước khi nạp, thu sau khi ổn định nếu cần.

### 10.3. Reserve quá lớn hoặc tối ưu bằng phỏng đoán

Dự phòng rất lớn có thể tăng lượng bộ nhớ được giữ, áp lực cấp phát và cả bộ nhớ tạm trong lúc thay mảng. Nó không làm nhanh hơn các phép tạo đối tượng phần tử, tìm kiếm tuyến tính hoặc dịch phần tử khi chèn giữa.

Khi đánh giá lợi ích, đo mẫu sử dụng thực: kích thước dữ liệu, số đợt nạp lại, số lần xóa, thời gian giữ danh sách và lượng cấp phát. Không kết luận bằng một lần chạy rất ngắn rằng mọi danh sách đều cần reserve hoặc trim.

## 11. Kiểu biến và ranh giới thiết kế

Đoạn sau cố ý không biên dịch:

```java
List<String> rows = new ArrayList<>();
rows.ensureCapacity(100);
```

Biến có kiểu khai báo `List`, nên chỉ thấy các phương thức thuộc giao diện đó. Nếu đang xây dựng dữ liệu bằng `ArrayList` và thật sự cần quản lý capacity, có thể giữ biến cục bộ cụ thể:

```java
ArrayList<String> building = new ArrayList<>(100);
building.add("A");
building.trimToSize();

List<String> result = building;
```

Đây là đoạn minh họa, cần import `java.util.List` và `java.util.ArrayList`. Việc gán sang `List` không sao chép hoặc làm danh sách bất biến; `result` vẫn tham chiếu cùng đối tượng.

Không ép kiểu một `List` tùy ý sang `ArrayList` chỉ để gọi trim. Danh sách nhận từ bên ngoài có thể là một triển khai khác hoặc có chính sách sở hữu dữ liệu riêng. Quản lý capacity nên nằm ở nơi thật sự sở hữu quá trình xây dựng và sử dụng cấu trúc đó.

Hai phương thức cũng không cung cấp đồng bộ hóa cho nhiều luồng. Dự phòng đủ chỗ không biến các thao tác thêm hoặc lượt duyệt thành an toàn khi có sửa đổi đồng thời.

## 12. Tự kiểm tra và sửa các cách hiểu sai

| Cách hiểu sai | Cách hiểu đúng |
|---|---|
| `ensureCapacity(100)` thêm 100 phần tử | Nó quản lý chỗ chứa, size không đổi |
| Tham số là số ô cần cộng thêm | Nó là tổng sức chứa tối thiểu cần đáp ứng |
| Reserve đặt capacity đúng bằng tham số | Nó không thu nhỏ và có thể chọn mức lớn hơn yêu cầu |
| `trimToSize` xóa bớt phần tử | Nó bỏ phần chỗ dự phòng, giữ nội dung logic |
| Sau trim không thêm được nữa | Danh sách vẫn tăng chỗ chứa nếu thêm tiếp |
| Reserve đủ rồi thì dùng `set` ở chỉ số bất kỳ | `set` vẫn yêu cầu phần tử đã có theo size |
| Nội dung không đổi nên iterator chắc chắn còn hợp lệ | Các phương thức capacity có thể ảnh hưởng trạng thái theo dõi cấu trúc |
| `clear` và trim là cùng thao tác | Một bên xóa phần tử, một bên thu chỗ chứa |
| Trim trả ngay toàn bộ bộ nhớ về hệ điều hành | Nó điều chỉnh cấu trúc lưu trữ; thu hồi thực tế có vòng đời riêng |
| Cứ gọi hai phương thức sau mỗi vòng lặp là tốt | Gọi sai thời điểm có thể tạo nhiều lần sao chép và cấp mảng |

Dự đoán các tình huống sau trước khi chạy:

1. Danh sách có size 20 và capacity giả định 100; gọi `ensureCapacity(50)`. Có bị xóa 50 ô để capacity thành 50 không?
2. Đang có 200 mục, sắp thêm 80 mục. Tổng cần yêu cầu là 80, 200 hay 280?
3. Sau `trimToSize` trên danh sách ba phần tử, gọi `add` có bị từ chối chỉ vì đã trim không?
4. Trên danh sách rỗng đã reserve 100, `set(99, value)` có hợp lệ không?
5. Cần nạp lại nhiều đợt 10.000 mục. Việc clear rồi trim sau mọi đợt có chắc tốt hơn clear và tái sử dụng mảng không?
6. Trong OpenJDK 17, trim khi capacity đã bằng size có chắc không ảnh hưởng iterator cũ không?

Đáp án:

1. Không; `ensureCapacity` không có nhiệm vụ thu nhỏ.
2. 280, với phép tính được kiểm tra phù hợp; tham số là tổng số cần chứa.
3. Không; việc thêm có thể làm mảng tăng trở lại.
4. Không; size vẫn là 0.
5. Không chắc; trim có thể khiến đợt kế tiếp phải cấp lại nhiều chỗ đã có.
6. Không; triển khai đó vẫn cập nhật bộ đếm khi gọi trim.

Chọn hai phương thức theo giai đoạn sử dụng dữ liệu: dự phòng khi có căn cứ về tổng số phần tử sắp cần, thu gọn khi cấu trúc đã ổn định và lợi ích giữ ít chỗ dư đáng với chi phí sao chép. Giữ riêng các câu hỏi về nội dung, chỗ chứa và vòng đời iterator/view để không đánh đổi tính đúng đắn lấy một tối ưu chưa được kiểm chứng.
