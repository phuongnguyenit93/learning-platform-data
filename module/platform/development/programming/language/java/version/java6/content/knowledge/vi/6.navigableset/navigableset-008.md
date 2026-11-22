# View liên kết với tập hợp gốc và giới hạn phần tử trong khoảng

## 1. Một cửa sổ làm việc trên cùng dữ liệu

Giả sử tập hợp điểm đang có `[10, 20, 30, 40, 50]`. Một chức năng chỉ xử lý các điểm từ 20 đến 40, bao gồm cả hai đầu.

Có hai cách tổ chức dữ liệu khác nhau:

- Tạo một tập hợp riêng chứa các điểm hiện thuộc khoảng đó.
- Tạo một **khung nhìn (view)** chỉ cho thấy phần thuộc khoảng, nhưng vẫn liên kết với tập hợp ban đầu.

Các phương thức lấy khoảng của `NavigableSet` phục vụ cách thứ hai. Với `TreeSet`, khung nhìn được hỗ trợ bởi dữ liệu gốc: thay đổi ở gốc có thể xuất hiện trong khung nhìn, và thay đổi qua khung nhìn có thể sửa chính tập hợp gốc. Xem hợp đồng [TreeSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeSet.html).

Khai báo minh họa trong phương thức:

```java
NavigableSet<Integer> scores =
        new TreeSet<>(List.of(10, 20, 30, 40, 50));
NavigableSet<Integer> window =
        scores.subSet(20, true, 40, true);
```

Đoạn này cần import `NavigableSet`, `TreeSet`, `List` từ `java.util`.

Mô hình cần giữ là: **một tập dữ liệu được lưu → nhiều cách nhìn → mỗi khung nhìn có quy tắc phạm vi → thao tác được áp dụng lên dữ liệu chung**. Đây là hành vi vẫn áp dụng trong Java hiện đại; ví dụ độc lập phía dưới dùng Java 17 trở lên.

## 2. Liên kết hai chiều thể hiện như thế nào?

Với `window` đại diện khoảng đóng `[20, 40]`:

| Thao tác | Ảnh hưởng quan sát được |
| --- | --- |
| `scores.add(25)` | 25 xuất hiện trong cả gốc và window |
| `scores.add(60)` | 60 có ở gốc, không xuất hiện trong window |
| `window.add(35)` | 35 được thêm vào gốc |
| `window.remove(30)` | 30 bị xóa khỏi gốc |
| `window.clear()` | Các phần tử hiện thuộc [20, 40] bị xóa khỏi gốc |

Tạo khung nhìn không tự thêm, xóa hay sao chép các phần tử. Nếu ứng dụng giữ biến `window` qua nhiều bước xử lý, nội dung nhìn thấy không bị cố định ở thời điểm tạo.

Có thể hình dung:

```text
scores: 10 | 20  25  30  35  40 | 50  60
            <---- window ---->
```

Đây là quan hệ dữ liệu, không có nghĩa phải gọi một hàm “đồng bộ khung nhìn” sau mỗi thay đổi. Cũng không phải hai tập hợp riêng đang gửi sự kiện cho nhau.

Liên kết hai chiều cần được xét khi thiết kế hàm. Một hàm nhận `window` rồi gọi `clear()` thực sự có thể xóa một phần dữ liệu mà nơi khác đang giữ qua `scores`.

## 3. Phạm vi của view là một điều kiện cố định

Trong ví dụ, giới hạn luôn là `20 ≤ điểm ≤ 40`, theo thứ tự tự nhiên của số nguyên. Nó không đổi thành “từ phần tử đầu hiện tại đến phần tử cuối hiện tại” sau mỗi thao tác.

Nếu xóa hết nội dung của `window`:

- Khung nhìn trở thành rỗng.
- Điều kiện `[20, 40]` vẫn còn.
- Thêm 28 qua khung nhìn vẫn hợp lệ và làm 28 xuất hiện ở gốc.
- Thêm 45 qua khung nhìn vẫn không hợp lệ, dù khung nhìn đang rỗng.

Các biên cũng không cần đang tồn tại trong dữ liệu. Khung nhìn `[22, 38]` có thể ban đầu chỉ chứa 30; nếu sau đó gốc được thêm 25, khung nhìn thấy thêm 25.

Phạm vi ảnh hưởng đến cả truy vấn. Nếu gốc có 10 nhưng khung nhìn chỉ chứa 22, `window.lower(22)` trả `null`; truy vấn không vượt ra ngoài cửa sổ để lấy 10.

## 4. Thêm ngoài khoảng khác với kiểm tra/xóa ngoài khoảng

Đối với khung nhìn khoảng trên `TreeSet<Integer>`, với các đối số số nguyên hợp lệ:

| Lời gọi trên window=[20, 40] | Kết quả |
| --- | --- |
| `window.contains(10)` | `false`, dù gốc có 10 |
| `window.remove(10)` | `false`, gốc vẫn giữ 10 |
| `window.add(45)` | Ném `IllegalArgumentException` |
| `window.add(20)` khi đã có 20 | `false`, vì phần tử đã tồn tại và vẫn nằm trong khoảng |

Điểm quan trọng là **thêm ngoài phạm vi không phải thao tác bị bỏ qua**. Khung nhìn không mở rộng biên để nhận phần tử đó.

Nếu biên trên là loại trừ, chẳng hạn `subSet(20, true, 40, false)`, thêm 40 cũng là thêm ngoài phạm vi. Điều này vẫn đúng khi 40 đã nằm trong tập hợp gốc.

Các phương thức lấy khoảng và cờ bao gồm biên được quy định trong [NavigableSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/NavigableSet.html). Ở đây cần đọc cả biên lẫn cờ, không chỉ so giá trị nhỏ nhất/lớn nhất đang nhìn thấy.

## 5. Chương trình chạy được: theo dõi gốc, view và bản sao

Chương trình tạo một khung nhìn có thể sửa, một lớp bọc chỉ đọc trên khung nhìn ấy, và một bản sao riêng. Nó cố ý thử thao tác ngoài phạm vi để quan sát ngoại lệ.

Lưu tệp `LinkedSetViewDemo.java`:

```java
import java.util.Collections;
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class LinkedSetViewDemo {
    public static void main(String[] args) {
        NavigableSet<Integer> scores =
                new TreeSet<>(List.of(10, 20, 30, 40, 50));
        NavigableSet<Integer> window =
                scores.subSet(20, true, 40, true);
        NavigableSet<Integer> readOnly =
                Collections.unmodifiableNavigableSet(window);
        NavigableSet<Integer> copy = new TreeSet<>(window);

        System.out.println("initial.view=" + window);
        System.out.println("view.contains.10="
                + window.contains(10));
        System.out.println("view.remove.10="
                + window.remove(10));
        System.out.println("base.still.has.10="
                + scores.contains(10));

        scores.add(25);
        System.out.println("view.after.base.add=" + window);
        System.out.println("readonly.after.base.add=" + readOnly);
        System.out.println("copy.after.base.add=" + copy);

        window.add(35);
        System.out.println("base.after.view.add=" + scores);
        window.remove(30);
        System.out.println("base.after.view.remove=" + scores);

        try {
            window.add(45);
        } catch (IllegalArgumentException ex) {
            System.out.println("outside.add=IllegalArgumentException");
        }

        try {
            readOnly.add(28);
        } catch (UnsupportedOperationException ex) {
            System.out.println("readonly.add=UnsupportedOperationException");
        }

        NavigableSet<Integer> inner =
                window.subSet(25, true, 35, true);
        inner.add(33);
        System.out.println("inner=" + inner);
        System.out.println("view.after.inner.add=" + window);

        window.clear();
        System.out.println("base.after.view.clear=" + scores);
        System.out.println("view.after.clear=" + window);
        System.out.println("copy.after.clear=" + copy);

        scores.add(22);
        scores.add(60);
        System.out.println("base.after.more=" + scores);
        System.out.println("view.after.more=" + window);
        System.out.println("view.lower.22=" + window.lower(22));

        scores.clear();
        window.add(28);
        System.out.println("base.restored.by.view=" + scores);
        System.out.println("view.restored=" + window);
        System.out.println("readonly.restored=" + readOnly);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 LinkedSetViewDemo.java
java LinkedSetViewDemo
```

Stdout:

```text
initial.view=[20, 30, 40]
view.contains.10=false
view.remove.10=false
base.still.has.10=true
view.after.base.add=[20, 25, 30, 40]
readonly.after.base.add=[20, 25, 30, 40]
copy.after.base.add=[20, 30, 40]
base.after.view.add=[10, 20, 25, 30, 35, 40, 50]
base.after.view.remove=[10, 20, 25, 35, 40, 50]
outside.add=IllegalArgumentException
readonly.add=UnsupportedOperationException
inner=[25, 33, 35]
view.after.inner.add=[20, 25, 33, 35, 40]
base.after.view.clear=[10, 50]
view.after.clear=[]
copy.after.clear=[20, 30, 40]
base.after.more=[10, 22, 50, 60]
view.after.more=[22]
view.lower.22=null
base.restored.by.view=[28]
view.restored=[28]
readonly.restored=[28]
```

Các quan sát quan trọng:

1. Kiểm tra/xóa 10 qua khung nhìn không đụng đến 10 ở gốc.
2. 25 được thêm ở gốc xuất hiện ngay trong cả `window` và `readOnly`, nhưng không có trong `copy`.
3. Thêm 35 và xóa 30 qua khung nhìn thay đổi tập hợp gốc.
4. `clear()` chỉ xóa cửa sổ đang nhìn; 10 và 50 vẫn ở gốc.
5. Sau khi gốc được xóa hết, chính khung nhìn cũ vẫn dùng được để thêm 28 đúng phạm vi.

Hai khối `catch` phục vụ quan sát hợp đồng trong ví dụ. Trong ứng dụng, nên kiểm soát quyền sửa và điều kiện đầu vào trước khi thực hiện thay đổi.

## 6. View chỉ đọc vẫn có thể thay đổi nội dung nhìn thấy

`Collections.unmodifiableNavigableSet(window)` ngăn thao tác sửa qua lớp bọc đó. Nó không đóng băng tập hợp nguồn: khi nguồn thay đổi, bên đọc vẫn thấy dữ liệu mới. Xem [Collections.unmodifiableNavigableSet](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#unmodifiableNavigableSet(java.util.NavigableSet)).

Phân biệt ba ý định:

| Ý định | Cách tổ chức |
| --- | --- |
| Cho phép sửa trực tiếp một phần dữ liệu gốc | Dùng khung nhìn khoảng |
| Chỉ cho đọc nhưng tiếp tục thấy thay đổi ở gốc | Bọc khung nhìn bằng `unmodifiableNavigableSet` |
| Giữ tập phần tử riêng tại thời điểm lấy | Tạo `new TreeSet<>(window)` |

Nếu cần bản sao riêng và không cho sửa cấu trúc qua kết quả, có thể bọc bản sao:

```java
NavigableSet<Integer> snapshot =
        Collections.unmodifiableNavigableSet(new TreeSet<>(window));
```

Đây là đoạn minh họa trong phương thức với các import đã có. `window` có kiểu `NavigableSet<Integer>`, nên constructor nhận nguồn đã sắp xếp giữ quy tắc thứ tự của nguồn.

Bản sao cấu trúc không phải bản sao sâu. Nếu phần tử là đối tượng có thể thay đổi, hai tập hợp vẫn có thể tham chiếu cùng đối tượng. Lớp bọc chỉ đọc cũng không tự làm cho các trường bên trong phần tử trở thành bất biến.

## 7. Khung nhìn con chỉ thu hẹp trong giới hạn được cấp

Ví dụ chương trình tạo `inner=[25,35]` từ `window=[20,40]`. Thêm 33 qua `inner` xuất hiện trong cả `window` lẫn `scores`: các lớp khung nhìn cùng dựa trên dữ liệu chung.

Nhưng không được dùng khung nhìn cha để yêu cầu một khoảng vượt biên của nó. Nếu cần `[10,45]`, phải bắt đầu từ tập hợp nguồn phù hợp; yêu cầu khoảng ấy trên `window` bị từ chối bằng `IllegalArgumentException`.

Quy tắc này xét phạm vi được định nghĩa, không chỉ các phần tử hiện có. Cho dù gốc không có phần tử nào từ 41 đến 45, yêu cầu mở rộng biên trên từ 40 lên 45 vẫn không hợp lệ.

Nếu khung nhìn cha loại biên 40, khung nhìn con không được biến 40 thành biên được bao gồm. Vì thế khi thao tác qua nhiều tầng, cần giữ cả giá trị biên và cờ bao gồm/loại trừ.

Một `descendingSet()` lấy từ khung nhìn cũng vẫn liên kết với dữ liệu chung; nó đổi hướng quan sát, không tạo tập hợp riêng và không loại bỏ giới hạn khoảng hiện có.

## 8. Sửa dữ liệu khi đang duyệt

Việc khung nhìn liên kết với gốc không có nghĩa một iterator đang chạy có thể tùy ý chịu mọi thay đổi ở gốc.

Với `TreeSet`, sửa cấu trúc trong lúc duyệt bằng một đường truy cập khác có thể làm iterator báo `ConcurrentModificationException`. Cơ chế phát hiện này không phải bảo đảm an toàn giữa các luồng và không nên được dùng làm điều kiện đúng đắn của chương trình.

Nếu cần xóa phần tử hiện đang duyệt, dùng chính iterator của tập hợp có hỗ trợ xóa:

```java
// Minh họa: window là view trên TreeSet có thể sửa.
for (Iterator<Integer> it = window.iterator(); it.hasNext();) {
    int score = it.next();
    if (score < 30) {
        it.remove();
    }
}
```

Đoạn này cần thêm import `java.util.Iterator`. Nó xóa các phần tử dưới 30 đang thuộc khung nhìn, đồng thời xóa chúng ở gốc. Theo hợp đồng [Iterator.remove](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Iterator.html#remove()), thao tác xóa áp dụng cho phần tử vừa được `next()` trả về và không được gọi hai lần cho cùng một lần `next()`.

Không suy luận rằng thay đổi ở gốc “nằm ngoài khoảng đang duyệt” luôn vô hại đối với iterator của lớp cài đặt cụ thể. Nếu cần thay đổi dữ liệu theo nhiều bước, tổ chức thời điểm duyệt và thời điểm sửa rõ ràng.

## 9. Những giả định dễ làm sai nghiệp vụ

- **Xóa trên kết quả lọc tưởng chỉ xóa bản tạm:** với view, dữ liệu gốc bị tác động. Đặt tên biến như `activeRangeView` hoặc tạo bản sao khi cần độc lập.
- **Kiểm tra rỗng rồi coi view hết tác dụng:** rỗng chỉ là trạng thái dữ liệu hiện tại; giới hạn và liên kết vẫn tồn tại.
- **Dùng add ngoài phạm vi như phép thử trả false:** vi phạm giới hạn ném ngoại lệ; `false` của add thường diễn đạt phần tử đã có.
- **Cho rằng lớp bọc chỉ đọc là ảnh chụp dữ liệu:** lớp bọc vẫn nhìn qua nguồn đang sống.
- **Giả định addAll là giao dịch:** việc thêm nhiều phần tử không mặc nhiên có nghĩa tất cả thành công hoặc không thay đổi gì. Nếu có phần tử ngoài phạm vi, không dựa vào giả định tự hoàn tác các thay đổi trước đó.
- **Cho rằng view có cơ chế đồng bộ riêng:** dữ liệu dùng chung vẫn chịu các điều kiện truy cập đồng thời của cấu trúc nguồn. Chia sẻ view không tự giải quyết việc nhiều luồng sửa cùng tập hợp.

## 10. Thực hành

Tạo gốc `[5, 10, 15, 20, 25]` và khung nhìn `[10,20)`:

1. Thêm 12 qua gốc rồi dự đoán view.
2. Xóa 15 qua view rồi dự đoán gốc.
3. Gọi `view.remove(25)`: giá trị trả về là gì, gốc còn 25 không?
4. Thêm 20 qua view có hợp lệ không?
5. Tạo bản sao view, rồi gọi `view.clear()`: phần nào còn tồn tại ở mỗi nơi?

Định hướng theo đúng thứ tự thao tác: (1) view thành `[10,12,15]`; (2) gốc thành `[5,10,12,20,25]`; (3) trả `false`, gốc còn 25; (4) không, biên 20 bị loại; (5) bản sao giữ `[10,12]`, gốc còn `[5,20,25]`, view rỗng.

Trước khi truyền một kết quả lấy khoảng sang hàm khác, hãy xác định đó là view hay bản sao, hàm nhận có được sửa không, và các biên cho phép những phần tử nào.
