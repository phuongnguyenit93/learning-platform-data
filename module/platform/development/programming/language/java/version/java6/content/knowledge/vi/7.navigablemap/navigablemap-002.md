# lowerEntry, floorEntry, ceilingEntry và higherEntry

## 1. Khi cần cả khóa lẫn dữ liệu của phần tử lân cận

Giả sử bảng gói dịch vụ có ba khóa theo mức dung lượng:

```text
10 -> BASIC
20 -> PLUS
30 -> PRO
```

Khách hàng nhập 25. Tra cứu chính xác bằng `get(25)` không tìm thấy gói có đúng khóa 25. Nhưng nghiệp vụ có thể muốn:

- Gói lớn nhất không vượt mức 25: khóa 20, giá trị PLUS.
- Gói nhỏ nhất đáp ứng ít nhất 25: khóa 30, giá trị PRO.

`NavigableMap<K,V>` hỗ trợ các truy vấn lân cận theo thứ tự khóa. Nhóm phương thức kết thúc bằng `Entry` trả về **cặp khóa–giá trị**, giúp biết vừa chọn khóa nào vừa chọn dữ liệu nào.

Ví dụ khai báo minh họa trong phương thức:

```java
NavigableMap<Integer, String> plans = new TreeMap<>();
Map.Entry<Integer, String> candidate = plans.floorEntry(25);
```

Cần import `NavigableMap`, `TreeMap`, `Map` từ `java.util`. Trong đoạn này map còn rỗng nên `candidate` là `null`; chương trình đầy đủ phía dưới sẽ nạp dữ liệu trước khi truy vấn.

Cách học hữu ích là: **định nghĩa phía cần tìm → quyết định có chấp nhận bằng khóa mốc không → nhận Entry hoặc không có kết quả → dùng khóa và giá trị theo nghiệp vụ**. Các API trong bài vẫn áp dụng trong Java hiện đại; ví dụ độc lập dùng Java 17 trở lên.

## 2. Bốn phương thức khác nhau ở hai quyết định

Giả sử map dùng thứ tự tự nhiên tăng dần của khóa số nguyên:

| Phương thức | Điều kiện khóa kết quả k với mốc x | Chọn ứng viên nào trong các khóa thỏa điều kiện |
| --- | --- | --- |
| `lowerEntry(x)` | k < x | Khóa lớn nhất |
| `floorEntry(x)` | k ≤ x | Khóa lớn nhất |
| `ceilingEntry(x)` | k ≥ x | Khóa nhỏ nhất |
| `higherEntry(x)` | k > x | Khóa nhỏ nhất |

Nếu không có khóa phù hợp, phương thức trả `null`. Cả bốn chỉ tìm và đọc, không xóa ánh xạ. Hợp đồng này được quy định trong [NavigableMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/NavigableMap.html).

Với map ở đầu bài:

| Truy vấn | lowerEntry | floorEntry | ceilingEntry | higherEntry |
| --- | --- | --- | --- | --- |
| Mốc 20, đã có trong map | 10→BASIC | 20→PLUS | 20→PLUS | 30→PRO |
| Mốc 25, không có trong map | 20→PLUS | 20→PLUS | 30→PRO | 30→PRO |
| Mốc 5, trước mọi khóa | null | null | 10→BASIC | 10→BASIC |
| Mốc 35, sau mọi khóa | 30→PRO | 30→PRO | null | null |

Hai cặp cần nhớ:

- `lower/higher` bỏ qua khóa bằng mốc.
- `floor/ceiling` cho phép khóa bằng mốc.

Nếu chỉ thử mốc 25, có thể tưởng `lowerEntry` giống `floorEntry`. Mốc 20 mới bộc lộ sự khác biệt. Vì vậy bài kiểm tra đúng phải có cả khóa đã tồn tại và mốc nằm giữa hai khóa.

## 3. Chọn đúng phương thức từ câu hỏi nghiệp vụ

### Không vượt quá một mức

“Chọn gói có khóa cao nhất nhưng không vượt quá ngân sách” tương ứng `floorEntry(limit)`. Nếu khóa bằng ngân sách tồn tại, nó được phép chọn.

Nếu yêu cầu là “phải nhỏ hơn giới hạn”, dùng `lowerEntry(limit)`.

### Đáp ứng ít nhất một mức

“Chọn gói nhỏ nhất có dung lượng đủ yêu cầu” tương ứng `ceilingEntry(required)`. Nếu một gói có đúng dung lượng cần, không phải nhảy sang gói lớn hơn.

Nếu yêu cầu là “phải cao hơn phiên bản này”, dùng `higherEntry(version)`.

### Phiên bản có hiệu lực theo mốc

Nếu khóa là thời điểm bắt đầu áp dụng và giá trị là cấu hình, `floorEntry(time)` tìm cấu hình có mốc bắt đầu mới nhất không nằm sau thời điểm cần hỏi.

Cách suy luận đó chỉ đủ khi mô hình nghiệp vụ quy định cấu hình có hiệu lực đến mốc kế tiếp hoặc vô thời hạn. Nếu còn ngày hết hạn, thời gian gián đoạn hoặc trạng thái thu hồi, phải kiểm tra thêm dữ liệu của Entry; tìm đúng khóa gần phía trước chưa tự chứng minh cấu hình còn hợp lệ.

### “Gần nhất” phải có nghĩa rõ ràng

Bốn phương thức tìm lân cận theo phía và điều kiện bằng, không tự chọn giá trị có khoảng cách số học nhỏ nhất giữa hai phía. Muốn “gần nhất tuyệt đối” phải định nghĩa thêm khoảng cách cùng quy tắc xử lý hòa rồi so các ứng viên phù hợp.

## 4. Đọc Entry an toàn

`Map.Entry<K,V>` biểu diễn cặp khóa và giá trị. Dùng `getKey()` để đọc khóa, `getValue()` để đọc giá trị. Không nhầm hai trường này chỉ vì chúng có thể cùng kiểu dữ liệu.

Có hai trạng thái khác nhau:

1. `entry == null`: không tìm thấy khóa thỏa yêu cầu.
2. `entry != null` nhưng `entry.getValue() == null`: tìm thấy khóa, ánh xạ đó đang giữ giá trị null trong một lớp map cho phép null.

`TreeMap` cho phép giá trị null. Vì thế không dùng riêng giá trị để kết luận có tìm thấy ánh xạ hay không. Xem các quy định của [TreeMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeMap.html).

Ví dụ minh họa:

```java
Map.Entry<Integer, String> result = plans.ceilingEntry(25);
if (result == null) {
    System.out.println("Khong co goi phu hop");
} else {
    System.out.println("Khoa=" + result.getKey());
    System.out.println("Gia tri=" + result.getValue());
}
```

Đoạn này cần biến `plans` đã khởi tạo; không gọi `getKey/getValue` trước kiểm tra null. Nếu khóa hoặc giá trị dùng kiểu bao như `Integer`, cũng cần chú ý việc tự mở hộp có thể gây lỗi nếu chính giá trị được đọc là null.

## 5. Chương trình Java đầy đủ

Ví dụ dùng chuỗi để kết quả xuất ra ổn định. Hàm `show` cố ý hiển thị riêng `none` và một Entry có giá trị null.

Lưu tệp `EntryNavigationDemo.java`:

```java
import java.util.Comparator;
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;

public class EntryNavigationDemo {
    static String show(Map.Entry<Integer, String> entry) {
        return entry == null
                ? "none"
                : entry.getKey() + ":" + entry.getValue();
    }

    public static void main(String[] args) {
        NavigableMap<Integer, String> plans = new TreeMap<>();
        plans.put(10, "BASIC");
        plans.put(20, "PLUS");
        plans.put(30, "PRO");

        System.out.println("get.25=" + plans.get(25));
        System.out.println("lower.20="
                + show(plans.lowerEntry(20)));
        System.out.println("floor.20="
                + show(plans.floorEntry(20)));
        System.out.println("ceiling.20="
                + show(plans.ceilingEntry(20)));
        System.out.println("higher.20="
                + show(plans.higherEntry(20)));
        System.out.println("floor.25="
                + show(plans.floorEntry(25)));
        System.out.println("ceiling.25="
                + show(plans.ceilingEntry(25)));
        System.out.println("floor.5="
                + show(plans.floorEntry(5)));
        System.out.println("ceiling.35="
                + show(plans.ceilingEntry(35)));
        System.out.println("size.after.lookups=" + plans.size());

        Map.Entry<Integer, String> saved = plans.floorEntry(25);
        plans.put(20, "PLUS_V2");
        System.out.println("saved=" + show(saved));
        System.out.println("fresh="
                + show(plans.floorEntry(25)));

        try {
            saved.setValue("EDITED");
        } catch (UnsupportedOperationException ex) {
            System.out.println("entry.setValue=UnsupportedOperationException");
        }

        plans.put(saved.getKey(), "EDITED");
        System.out.println("after.put="
                + show(plans.floorEntry(25)));

        plans.put(40, null);
        Map.Entry<Integer, String> withNull =
                plans.ceilingEntry(35);
        System.out.println("null.value.entry=" + show(withNull));
        System.out.println("null.value.is.absent="
                + (withNull == null));

        NavigableMap<Integer, String> descending =
                new TreeMap<>(Comparator.reverseOrder());
        descending.putAll(plans);
        System.out.println("descending.lower.20="
                + show(descending.lowerEntry(20)));
        System.out.println("descending.higher.20="
                + show(descending.higherEntry(20)));

        NavigableMap<Integer, String> empty = new TreeMap<>();
        System.out.println("empty.floor="
                + show(empty.floorEntry(20)));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 EntryNavigationDemo.java
java EntryNavigationDemo
```

Stdout:

```text
get.25=null
lower.20=10:BASIC
floor.20=20:PLUS
ceiling.20=20:PLUS
higher.20=30:PRO
floor.25=20:PLUS
ceiling.25=30:PRO
floor.5=none
ceiling.35=none
size.after.lookups=3
saved=20:PLUS
fresh=20:PLUS_V2
entry.setValue=UnsupportedOperationException
after.put=20:EDITED
null.value.entry=40:null
null.value.is.absent=false
descending.lower.20=30:PRO
descending.higher.20=10:BASIC
empty.floor=none
```

Kiểm tra từng nhóm:

- Dòng `get.25` cho thấy tra cứu chính xác khác truy vấn lân cận.
- Với mốc 20, các phương thức có chấp nhận bằng mốc trả chính gói PLUS.
- `size.after.lookups=3` chứng minh các truy vấn không lấy phần tử khỏi map.
- `saved` và `fresh` thể hiện khác biệt giữa Entry đã nhận trước đó và một truy vấn mới sau cập nhật.
- Entry có khóa 40 tồn tại dù giá trị của nó là null.
- Trong map giảm dần, `lower/higher` phải đọc theo comparator.

## 6. Entry trả về là ảnh chụp của ánh xạ

Các Entry do bốn phương thức này trả về là ảnh chụp ánh xạ tại thời điểm gọi. Chúng không hỗ trợ sửa map qua `setValue`. Đây là quy định của [NavigableMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/NavigableMap.html), không phải một cách sử dụng tùy chọn của ví dụ.

Trong chương trình:

1. `saved` nhận cặp `20 -> PLUS`.
2. Map được cập nhật thành `20 -> PLUS_V2`.
3. `saved` vẫn giữ cặp đã nhận; truy vấn mới trả giá trị mới.
4. `saved.setValue(...)` không phải đường cập nhật map.
5. Muốn thay ánh xạ ở khóa được chọn, thao tác trên map bằng `put`.

Không nên suy luận hành vi chỉ từ kiểu `Map.Entry`. Entry lấy khi duyệt `entrySet()` của một số map có thể có khả năng cập nhật khác; phải xem cách Entry được tạo và hợp đồng tương ứng. Xem [Map.Entry](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.Entry.html).

“Ảnh chụp ánh xạ” cũng không có nghĩa sao chép sâu đối tượng giá trị. Nếu V là một đối tượng có thể thay đổi, Entry và map vẫn có thể tham chiếu cùng đối tượng ấy. Ví dụ dùng `String` giúp tách bạch việc thay ánh xạ khỏi việc sửa trạng thái bên trong một đối tượng.

## 7. Mọi quan hệ đều đi theo thứ tự khóa

Với map tự nhiên tăng dần, “nhỏ hơn” của khóa số nguyên trùng cách hiểu số học. Nhưng nếu dùng `Comparator.reverseOrder()`, thứ tự là:

```text
40 -> 30 -> 20 -> 10
```

Lúc đó:

- `lowerEntry(20)` trả khóa 30: nó là phần tử đứng ngay trước 20 theo thứ tự giảm dần.
- `higherEntry(20)` trả khóa 10: nó đứng ngay sau 20 theo thứ tự ấy.

Comparator xác định quan hệ thứ tự, không phải một phép tính khoảng cách. Với khóa là đối tượng, comparator còn quyết định khi nào hai khóa được coi là tương đương trong map đã sắp xếp. Cần thiết kế nhất quán với ý nghĩa khóa và sự bằng nhau. Xem [Comparator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Comparator.html).

Không viết hàm trợ giúp với tên “gói nhỏ hơn” rồi âm thầm giả định mọi map truyền vào đều tăng dần. Hoặc ghi rõ tiền điều kiện thứ tự, hoặc thiết kế hàm theo comparator thực tế.

## 8. Entry hay Key, tra cứu đơn hay duyệt nhiều?

Nếu chỉ cần khóa, dùng `lowerKey/floorKey/ceilingKey/higherKey`. Nếu cần cả khóa và giá trị, dùng nhóm `Entry` để nhận cặp kết quả trong cùng truy vấn.

Tránh một bước tìm khóa rồi lập tức quên khóa đã chọn và gọi `get` bằng chính mốc ban đầu: `floorKey(25)` tìm ra 20 nhưng `get(25)` vẫn không có kết quả.

Các phương thức điều hướng thích hợp cho việc định vị một ánh xạ. Nếu cần xử lý cả một dải nhiều phần tử, nên xem các khung nhìn khoảng và cơ chế duyệt thay vì lặp tìm lại từng phần tử bằng một truy vấn mới cho mỗi bước.

Một Entry đã nhận không phải khóa bảo vệ dữ liệu. Nếu dùng map chia sẻ giữa nhiều luồng, việc tìm Entry rồi cập nhật sau đó không tự trở thành một thao tác nguyên tử. `TreeMap` không tự đồng bộ; thiết kế đồng thời cần được xử lý ở mức phù hợp với yêu cầu cập nhật.

## 9. Lỗi thường gặp

- **Dùng higherEntry khi cho phép bằng:** khóa đúng mốc bị bỏ qua; `ceilingEntry` mới diễn đạt điều kiện đó.
- **Dùng lowerEntry để lấy cấu hình bắt đầu đúng thời điểm hỏi:** kết quả lùi về cấu hình trước; cần `floorEntry` nếu cho phép bằng.
- **Đọc getValue trước khi kiểm tra Entry:** không có ứng viên gây `NullPointerException`.
- **Coi giá trị null là không có Entry:** có thể bỏ sót một khóa thật trong lớp map cho phép giá trị null.
- **Gọi setValue trên Entry điều hướng:** không phải cách sửa ánh xạ; cập nhật qua map theo đúng hợp đồng.
- **Cho rằng truy vấn tự loại bỏ kết quả:** bốn phương thức đang học không xóa phần tử.
- **Mặc định nhỏ hơn là nhỏ hơn số học:** kiểm tra comparator, nhất là với map đảo chiều.

## 10. Thực hành

Với map tự nhiên tăng dần `{100=A, 200=B, 350=C}`:

1. `lowerEntry(200)` và `floorEntry(200)` khác nhau thế nào?
2. `ceilingEntry(250)` và `higherEntry(250)` có cùng kết quả không?
3. Truy vấn nào tìm mức cao nhất không vượt quá 250?
4. `floorEntry(50)` trả gì?
5. Nếu lấy Entry ở khóa 200 rồi map đổi giá trị thành B2, Entry đã lấy có tự trở thành B2 không?

Định hướng: (1) lần lượt 100→A và 200→B; (2) cùng 350→C vì không có đúng khóa 250; (3) `floorEntry(250)`; (4) null; (5) không, cần truy vấn mới để nhận ánh xạ hiện tại.

Khi chọn phương thức, hãy viết điều kiện khóa trước bằng <, ≤, ≥ hoặc >, rồi kiểm tra phía cần tìm và trường hợp không có kết quả.
