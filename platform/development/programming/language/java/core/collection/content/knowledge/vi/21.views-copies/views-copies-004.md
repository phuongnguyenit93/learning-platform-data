# View phạm vi của TreeSet, TreeMap và view đảo thứ tự

## 1. Nhìn đúng mô hình: một dữ liệu, nhiều cửa sổ

Giả sử hệ thống giữ các mốc thời gian đã sắp thứ tự. Một chức năng cần xem những mốc từ 20 đến trước 50; chức năng khác cần duyệt chính phạm vi đó từ cuối về đầu. Nếu mỗi lần đều lọc rồi chép sang một tập hợp mới, hai kết quả nhanh chóng trở thành dữ liệu độc lập, phải tự cập nhật khi nguồn đổi.

**View phạm vi** giải quyết nhu cầu làm việc trực tiếp với một khoảng của cấu trúc có thứ tự. **View đảo thứ tự** cho phép đọc cùng dữ liệu theo chiều ngược lại. Với TreeSet và TreeMap, các view này dựa trên cấu trúc nguồn: thay đổi được phép qua view đi vào nguồn; thay đổi ở nguồn hiện ra trong view khi thỏa điều kiện phạm vi.

Hãy tách ba câu hỏi:

- **Dữ liệu ở đâu?** Các view vẫn dùng dữ liệu được quản lý bởi cây nguồn.
- **Nhìn thấy phần nào?** Phạm vi chọn phần tử của set hoặc khóa của map bằng phép so sánh.
- **Nhìn theo chiều nào?** Chiều của bộ so sánh hiện tại quyết định đầu, cuối, trước và sau.

Một view có thể vừa giới hạn phạm vi vừa đảo thứ tự. Đảo chiều không bỏ giới hạn; giới hạn phạm vi không tạo bản sao.

Ví dụ nguồn tăng dần có các phần tử 10, 20, 30, 40, 50:

| Đối tượng đang nhìn | Nội dung theo thứ tự duyệt |
|---|---|
| Nguồn | 10, 20, 30, 40, 50 |
| Phạm vi từ 20, lấy 20, đến 50, không lấy 50 | 20, 30, 40 |
| View đảo của phạm vi trên | 40, 30, 20 |
| Bản sao được tạo từ phạm vi | Các phần tử tại thời điểm sao chép; cấu trúc độc lập với nguồn |

Nếu nguồn có thêm 35, hai view phạm vi lập tức có thêm phần tử đó. Bản sao đã tạo trước đó không tự có 35. Nếu thêm 60 vào nguồn, cả hai view phạm vi vẫn không nhìn thấy 60 vì nó vượt biên.

Bài này đi theo thứ tự: đọc biên → thao tác với phạm vi → đọc thứ tự đảo → kết hợp hai phép biến đổi → quyết định lúc nào nên sao chép. Cần biết cách dùng TreeSet, TreeMap và Comparator cơ bản; không cần biết cách cài đặt cây cân bằng.

Các chương trình đầy đủ dùng JDK 21 trở lên và không cần thư viện ngoài. API phạm vi cùng descendingSet()/descendingMap() đã có trước Java 17; tên reversed() được bổ sung ở Java 21. Những đoạn ngắn được ghi rõ là đoạn minh họa, không phải tệp chạy độc lập.

## 2. API phạm vi: biên được hiểu bằng phép so sánh

### 2.1. Set xét phần tử; map xét khóa

TreeSet triển khai NavigableSet, mở rộng SortedSet. TreeMap triển khai NavigableMap, mở rộng SortedMap. Hai họ API tương ứng nhau:

| Mục đích | NavigableSet | NavigableMap |
|---|---|---|
| Giới hạn hai đầu | subSet(from, fromInclusive, to, toInclusive) | subMap(from, fromInclusive, to, toInclusive) |
| Lấy phần trước một mốc | headSet(to, inclusive) | headMap(to, inclusive) |
| Lấy phần từ một mốc trở đi | tailSet(from, inclusive) | tailMap(from, inclusive) |

Tên gọi “trước”, “từ”, “đầu” đều theo thứ tự của đối tượng nhận lời gọi. Với cây số nguyên tăng dần, thứ tự ấy trùng thứ tự số thông thường. Với bộ so sánh giảm dần, quan hệ đảo lại.

Có thể diễn đạt chính xác bằng c(a,b), kết quả so sánh của bộ so sánh hiện tại:

- Biên dưới đóng chấp nhận x khi c(x,from) >= 0; biên dưới mở yêu cầu > 0.
- Biên trên đóng chấp nhận x khi c(x,to) <= 0; biên trên mở yêu cầu < 0.
- head lấy phía trước mốc theo thứ tự này; tail lấy phía sau mốc theo thứ tự này.

Khi dùng thứ tự tự nhiên, c(a,b) là ý nghĩa của a.compareTo(b), không cần tự tạo Comparator chỉ để gọi các phương thức phạm vi.

### 2.2. Bốn tổ hợp biên

Trong bảng sau, nguồn có thứ tự số tăng dần và chứa mọi số nguyên từ 1 đến 5:

| Lời gọi | Ký hiệu khoảng | Kết quả |
|---|---|---|
| subSet(2, true, 5, true) | [2, 5] | 2, 3, 4, 5 |
| subSet(2, true, 5, false) | [2, 5) | 2, 3, 4 |
| subSet(2, false, 5, true) | (2, 5] | 3, 4, 5 |
| subSet(2, false, 5, false) | (2, 5) | 3, 4 |

Với map, thay subSet bằng subMap và đọc các số ở bảng là khóa. Giá trị đi kèm khóa không tham gia kiểm tra biên.

Hai mốc không phải tồn tại sẵn trong nguồn. Nguồn có 10, 20, 30 nhưng subSet(12, true, 28, false) vẫn hợp lệ và hiện 20. View mô tả một điều kiện theo thứ tự, không lưu “vị trí của phần tử 12” trong cây.

Khoảng hợp lệ cũng có thể chưa chứa phần tử nào. Khi nguồn về sau nhận một phần tử thuộc khoảng đó, view sẽ nhìn thấy nó.

### 2.3. Các dạng cũ có biên mặc định

SortedSet và SortedMap cung cấp các dạng không có boolean:

| Dạng rút gọn | Tương đương về biên |
|---|---|
| subSet(a, b) | subSet(a, true, b, false) |
| headSet(b) | headSet(b, false) |
| tailSet(a) | tailSet(a, true) |
| subMap(a, b) | subMap(a, true, b, false) |
| headMap(b) | headMap(b, false) |
| tailMap(a) | tailMap(a, true) |

Nghĩa là khoảng hai đầu mặc định **lấy đầu, bỏ cuối**; head bỏ mốc, tail lấy mốc. Không dùng trí nhớ “cả hai đều lấy” để suy luận kết quả. Có thể đối chiếu trực tiếp các chữ ký trong [SortedSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedSet.html) và [SortedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedMap.html).

Dạng rút gọn của TreeSet có kiểu trả về khai báo là SortedSet, và của TreeMap là SortedMap. Vì vậy, viết var v = tree.subSet(a,b) không cho biến v các phương thức điều hướng như floor() qua kiểu khai báo. Nếu cần NavigableSet hoặc NavigableMap, dùng dạng có boolean. Không cần ép kiểu để tiếp tục làm việc.

### 2.4. Biên trùng nhau và biên ngược chiều

Khi hai mốc so sánh bằng nhau:

- Cả hai phía đóng: view có thể chứa phần tử/khóa tương đương mốc đó, nếu nguồn đang có.
- Có ít nhất một phía mở: view rỗng.
- Dạng rút gọn [a,a) vì thế luôn rỗng.

“Bằng nhau” ở đây theo phép so sánh mà cây sử dụng. Một Comparator không phân biệt chữ hoa và chữ thường có thể xem hai chuỗi khác nhau theo equals là cùng một mốc.

Ngược lại, from đứng sau to theo bộ so sánh hiện tại là yêu cầu sai và gây IllegalArgumentException. Đây không phải cách yêu cầu một khoảng rỗng. Trên cây tăng dần, subSet(40,true,20,true) sai; trên view giảm dần, chính cặp mốc ấy có thể đúng.

## 3. TreeSet: view sống và thao tác đi vào nguồn

Chương trình sau kiểm tra cả hai chiều cập nhật, truy vấn ngoài phạm vi, phạm vi lồng nhau và một view đã bị xóa hết dữ liệu.

Tệp **RangeSetDemo.java**:

```java
import java.util.List;
import java.util.NavigableSet;
import java.util.TreeSet;

public class RangeSetDemo {
    private static void expectIAE(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + ": no exception");
        } catch (IllegalArgumentException expected) {
            System.out.println(label + "=IllegalArgumentException");
        }
    }

    public static void main(String[] args) {
        TreeSet<Integer> source =
                new TreeSet<>(List.of(10, 20, 30, 40, 50));
        NavigableSet<Integer> middle =
                source.subSet(20, true, 50, false);

        System.out.println("initial=" + middle);
        System.out.println("legacy=" + source.subSet(20, 50));
        System.out.println("headClosed=" + source.headSet(20, true));
        System.out.println("tailOpen=" + source.tailSet(40, false));
        System.out.println("contains50=" + middle.contains(50));
        System.out.println("remove50=" + middle.remove(50));
        expectIAE("add50", () -> middle.add(50));

        middle.add(25);
        middle.remove(30);
        source.add(35);
        source.add(60);
        System.out.println("middle=" + middle);
        System.out.println("source=" + source);
        System.out.println("floor100=" + middle.floor(100));
        System.out.println("ceiling0=" + middle.ceiling(0));
        System.out.println("higher40=" + middle.higher(40));

        NavigableSet<Integer> nested = middle.tailSet(25, true);
        System.out.println("nested=" + nested);
        System.out.println("sameExcludedEnd=" + middle.headSet(50, false));
        expectIAE("includeExcludedEnd", () -> middle.headSet(50, true));
        expectIAE("expandNested", () -> middle.headSet(70, false));
        expectIAE("wrongDirection", () -> source.subSet(40, true, 20, true));

        middle.clear();
        System.out.println("afterClear=" + source);
        System.out.println("nestedAfterClear=" + nested);
        source.add(32);
        System.out.println("liveAgain=" + middle);
        System.out.println("nestedLiveAgain=" + nested);
        System.out.println("equalClosed=" + source.subSet(32, true, 32, true));
        System.out.println("equalHalfOpen=" + source.subSet(32, true, 32, false));
    }
}
```

Chạy bằng JDK 21 trở lên:

```shell
javac --release 21 -encoding UTF-8 RangeSetDemo.java
java RangeSetDemo
```

Stdout chính xác:

```text
initial=[20, 30, 40]
legacy=[20, 30, 40]
headClosed=[10, 20]
tailOpen=[50]
contains50=false
remove50=false
add50=IllegalArgumentException
middle=[20, 25, 35, 40]
source=[10, 20, 25, 35, 40, 50, 60]
floor100=40
ceiling0=20
higher40=null
nested=[25, 35, 40]
sameExcludedEnd=[20, 25, 35, 40]
includeExcludedEnd=IllegalArgumentException
expandNested=IllegalArgumentException
wrongDirection=IllegalArgumentException
afterClear=[10, 50, 60]
nestedAfterClear=[]
liveAgain=[32]
nestedLiveAgain=[32]
equalClosed=[32]
equalHalfOpen=[]
```

### 3.1. Đọc những thay đổi chính

middle bắt đầu với 20, 30, 40. Biên 50 bị loại, dù nguồn thực sự có 50.

Lệnh middle.add(25) thêm 25 vào cây nguồn. Lệnh middle.remove(30) xóa 30 khỏi cây nguồn. Sau đó source.add(35) được nhìn thấy trong middle, còn source.add(60) nằm ngoài phạm vi nên chỉ xuất hiện ở source.

Việc cập nhật qua nguồn không bị view giới hạn. Chủ sở hữu source vẫn có quyền thao tác với toàn bộ cây; việc tạo middle không “khóa” nguồn vào [20,50).

Một điểm khác dễ nhầm là: **giới hạn chỗ có thể tìm thấy kết quả khác với giới hạn đối số truy vấn**. middle.floor(100) hợp lệ và trả 40, phần tử lớn nhất đang có trong view không vượt 100. middle.ceiling(0) trả 20. Cả hai đều không được trả phần tử ở ngoài view, mặc dù nguồn còn phần tử khác.

middle.higher(40) trả null vì không có phần tử nào sau 40 trong phạm vi. Nó không vượt ra nguồn để lấy 50.

### 3.2. Hỏi, xóa và chèn ngoài phạm vi không có cùng kết quả

Trong chương trình, đối số là Integer hợp lệ với thứ tự tự nhiên:

| Thao tác với middle = [20,50) | Kết quả | Nguồn bị đổi? |
|---|---|---|
| contains(50) | false | Không |
| remove(50) | false | Không |
| add(50) | IllegalArgumentException | Không thêm 50 qua view |
| floor(100) | Phần tử phù hợp trong view, ở đây 40 | Không |
| clear() | Xóa tất cả phần tử đang thuộc view | Có |

50 đã tồn tại ở source cũng không làm add(50) qua middle hợp lệ. Phép chèn được kiểm tra với phạm vi của đối tượng nhận lời gọi.

Bảng này không nói rằng mọi đối số bất kỳ đều được chấp nhận: kiểu không so sánh được hoặc null không được bộ so sánh hỗ trợ vẫn có thể gây ngoại lệ. Đừng tổng quát kết quả với Integer thành “mọi truy vấn ngoài biên đều an toàn”.

Đặc tả các phương thức phạm vi của [TreeSet](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html#subSet(E,boolean,E,boolean)) xác nhận view dùng chung nguồn và từ chối chèn phần tử ngoài khoảng.

### 3.3. clear() xóa phần nào?

middle.clear() không chỉ làm một đối tượng trung gian trống. Nó xóa các phần tử 20, 25, 35, 40 khỏi cấu trúc nguồn. Những phần tử ngoài khoảng là 10, 50, 60 vẫn còn.

nested cũng dựa vào dữ liệu này nên lập tức rỗng. Sau đó source.add(32) làm cả middle và nested hiện 32 trở lại. Biên của hai view vẫn tồn tại dù dữ liệu hiện có bằng không.

Đó là lý do không nên mô tả clear() là “bỏ bộ lọc” hoặc “ngắt kết nối view”. Khi muốn ngắt kết nối, phải sao chép sang cấu trúc khác.

## 4. Phạm vi lồng nhau: thu hẹp có kiểm tra, không tự cắt biên

Xét middle đã giới hạn [20,50), rồi gọi middle.tailSet(25,true). nested nhận khoảng [25,50). Nó không có cấu trúc dữ liệu riêng; cập nhật nguồn và các view liên quan vẫn dùng chung dữ liệu.

Tuy nhiên, không thể yêu cầu một view con với mốc ngoài giới hạn của view cha rồi mong Java tự lấy phần giao:

- middle.headSet(70,false) gây IllegalArgumentException.
- middle.tailSet(10,true) cũng yêu cầu mốc ngoài phạm vi cha và không hợp lệ.
- middle.headSet(50,false) hợp lệ: nó giữ mốc 50 ở trạng thái không được lấy.
- middle.headSet(50,true) không hợp lệ: nó yêu cầu nhận thêm chính mốc cha đã loại.

Hai lời gọi cuối rất hữu ích để hiểu biên. Mốc nằm đúng tại giới hạn mở của cha có thể được dùng làm giới hạn mở của con; yêu cầu lấy mốc đó sẽ vượt quyền của khoảng cha.

Ngay cả khi nguồn hiện chưa có 50, lỗi includeExcludedEnd vẫn là lỗi. Ràng buộc dựa trên biên đã khai báo, không phụ thuộc việc có tìm thấy khóa/phần tử vi phạm ở thời điểm tạo view hay không.

Để kết hợp hai khoảng nghiệp vụ tùy ý, hãy tự tính biên giao bằng đúng Comparator và xử lý trường hợp giao rỗng trước, hoặc tạo view từ nguồn đủ rộng với biên cuối đã hợp lệ. Đừng coi chuỗi headSet()/tailSet() là phép giao tự động cho mọi mốc.

Quy tắc tương ứng áp dụng với subMap/headMap/tailMap trên phạm vi TreeMap. Hướng dẫn về giới hạn của [NavigableMap.subMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableMap.html#subMap(K,boolean,K,boolean)) là căn cứ để xử lý lỗi biên ngay tại nơi tạo view.

## 5. TreeMap: chọn theo khóa, cập nhật cả ánh xạ

Với TreeMap, phạm vi áp dụng lên **khóa**. Ví dụ bảng tra cứu theo mã đơn hàng có thể dùng [100,300) để xem các đơn có mã từ 100 đến 299. Giá trị có tên “ngoài khoảng”, “ưu tiên”, số tiền lớn hay nhỏ không ảnh hưởng đến việc ánh xạ được chọn.

Chương trình này còn minh họa một view đảo của phạm vi, view tập khóa và một lớp bọc không cho sửa.

Tệp **RangeMapDemo.java**:

```java
import java.util.Collections;
import java.util.NavigableMap;
import java.util.NavigableSet;
import java.util.TreeMap;

public class RangeMapDemo {
    private static void expectIAE(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + ": no exception");
        } catch (IllegalArgumentException expected) {
            System.out.println(label + "=IllegalArgumentException");
        }
    }

    public static void main(String[] args) {
        TreeMap<Integer, String> source = new TreeMap<>();
        source.put(50, "outside-low");
        source.put(100, "A");
        source.put(200, "B");
        source.put(300, "outside-high");

        NavigableMap<Integer, String> window =
                source.subMap(100, true, 300, false);
        System.out.println("initial=" + window);
        System.out.println("get300=" + window.get(300));
        System.out.println("remove300=" + window.remove(300));
        System.out.println("sourceKeeps300=" + source.containsKey(300));
        expectIAE("put300", () -> window.put(300, "blocked"));

        window.put(150, "C");
        window.put(100, "A2");
        source.put(250, "D");
        source.put(375, "outside-later");
        System.out.println("updated=" + window);

        NavigableMap<Integer, String> reverse = window.descendingMap();
        System.out.println("reverse=" + reverse);
        System.out.println("reverseKeys=" + reverse.navigableKeySet());
        System.out.println("reverseValues=" + reverse.values());
        System.out.println("reverseHead200=" + reverse.headMap(200, false));
        System.out.println("reverseFloor175=" + reverse.floorKey(175));
        System.out.println("reverseCeiling175=" + reverse.ceilingKey(175));

        System.out.println("pollReverseFirst=" + reverse.pollFirstEntry());
        System.out.println("afterPoll=" + window);
        NavigableSet<Integer> keys = window.navigableKeySet();
        keys.remove(150);
        System.out.println("afterKeyRemoval=" + window);

        NavigableMap<Integer, String> readOnly =
                Collections.unmodifiableNavigableMap(window);
        source.put(175, "E");
        System.out.println("readOnlyLive=" + readOnly);
        System.out.println("firstOutside=" + source.firstEntry());
        window.clear();
        System.out.println("afterWindowClear=" + source);
        System.out.println("readOnlyAfterClear=" + readOnly);
    }
}
```

Lệnh biên dịch và chạy:

```shell
javac --release 21 -encoding UTF-8 RangeMapDemo.java
java RangeMapDemo
```

Stdout chính xác:

```text
initial={100=A, 200=B}
get300=null
remove300=null
sourceKeeps300=true
put300=IllegalArgumentException
updated={100=A2, 150=C, 200=B, 250=D}
reverse={250=D, 200=B, 150=C, 100=A2}
reverseKeys=[250, 200, 150, 100]
reverseValues=[D, B, C, A2]
reverseHead200={250=D}
reverseFloor175=200
reverseCeiling175=150
pollReverseFirst=250=D
afterPoll={100=A2, 150=C, 200=B}
afterKeyRemoval={100=A2, 200=B}
readOnlyLive={100=A2, 175=E, 200=B}
firstOutside=50=outside-low
afterWindowClear={50=outside-low, 300=outside-high, 375=outside-later}
readOnlyAfterClear={}
```

### 5.1. Chèn mới và thay giá trị đều đi qua cùng cửa sổ

window bao gồm khóa 100 và 200, loại khóa 300. window.put(150,"C") thêm một ánh xạ vào source; window.put(100,"A2") thay giá trị đang có ở source. source.put(250,"D") xuất hiện trong window, còn khóa 375 không xuất hiện.

window.get(300) trả null và window.remove(300) trả null trong ví dụ này, dù source thật sự có ánh xạ cho 300. Khóa ấy nằm ngoài góc nhìn của window. Ngược lại, window.put(300,...) bị từ chối vì nó cố ghi ở ngoài khoảng.

Đối với TreeMap cho phép giá trị null, get() trả null không đủ phân biệt “không có ánh xạ” với “có ánh xạ mang giá trị null”. Khi cần phân biệt trong view, dùng containsKey() trên chính view đó. Phạm vi không làm thay đổi quy tắc cơ bản này của Map.

Đừng dựa vào kết quả truy vấn source để kết luận một khóa có thể ghi qua window. Điều kiện là khóa nằm trong khoảng của window, kể cả khi source đã có khóa ấy.

### 5.2. View của view vẫn thay đổi nguồn

reverse = window.descendingMap() chỉ đổi thứ tự của cửa sổ [100,300). Khi gọi reverse.pollFirstEntry(), phần tử “đầu” theo chiều giảm dần là khóa 250. Ánh xạ 250 bị xóa khỏi source và window.

keys = window.navigableKeySet() là view các khóa trong cùng phạm vi. keys.remove(150) xóa toàn bộ ánh xạ 150 khỏi source. Nó không để lại một khóa với giá trị null.

Tập khóa này hỗ trợ xóa nhưng không hỗ trợ add()/addAll(): chỉ một khóa không cung cấp giá trị cần thiết để thêm ánh xạ. Vì cùng mang kiểu NavigableSet không có nghĩa mọi đối tượng hỗ trợ các phép thêm giống TreeSet.

reverse.values() duyệt giá trị theo thứ tự khóa giảm dần; nó không tự sắp xếp giá trị theo chữ cái hay theo một Comparator dành cho giá trị. Vì vậy kết quả D, B, C, A2 là hệ quả thứ tự khóa 250, 200, 150, 100.

### 5.3. Lớp bọc không cho sửa không ngăn nguồn thay đổi

readOnly được tạo bằng Collections.unmodifiableNavigableMap(window). Nó chặn các thao tác cập nhật thông qua giao diện được trả về, nhưng không giữ một bản chụp của window.

source.put(175,"E") vẫn hiện trong readOnly. Sau window.clear(), readOnly rỗng. Chương trình cho thấy rõ hai thuộc tính khác nhau:

- **Không sửa được qua tham chiếu này**: thuộc tính của lớp bọc.
- **Không thay đổi khi nguồn thay đổi**: thuộc tính cần có bản sao hoặc cơ chế lưu phiên bản riêng.

Các lớp bọc của [Collections](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#unmodifiableNavigableMap(java.util.NavigableMap)) giữ việc đọc qua cấu trúc được bọc. Bọc một view không tự tách dữ liệu.

## 6. Đảo thứ tự: đảo cả ý nghĩa điều hướng

### 6.1. descending và reversed

| Đối tượng | API đã có ở Java 17 | API từ Java 21 | Kiểu kết quả |
|---|---|---|---|
| TreeSet/NavigableSet | descendingSet() | reversed() | NavigableSet |
| TreeMap/NavigableMap | descendingMap() | reversed() | NavigableMap |

Trong hai họ Navigable này, reversed() tương đương descendingSet()/descendingMap(). Với TreeSet và TreeMap, view đảo dùng chung nguồn, nên các cập nhật được phép tiếp tục phản ánh qua lại. Không cần duyệt rồi chèn lại toàn bộ dữ liệu chỉ để đọc từ cuối về đầu. Đặc tả tương đương nằm ở [NavigableSet.reversed](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableSet.html#reversed()) và [NavigableMap.reversed](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableMap.html#reversed()).

Đừng suy từ tính chất cụ thể này rằng mọi phương thức reversed() trên mọi cấu trúc Java đều có cùng bảo đảm cập nhật. Bài này đang xét cây và các view của chúng.

Đảo thứ tự hai lần khôi phục thứ tự ban đầu về mặt hành vi. Không dùng so sánh tham chiếu == làm điều kiện đúng của thuật toán; đặc tả không yêu cầu mọi triển khai phải trả đúng cùng một đối tượng sau hai lần đảo.

### 6.2. “Đầu” là đầu theo Comparator của view

Nguồn tăng dần có 10, 20, 30, 40, 50. Trong view giảm dần:

| Lời gọi trên view giảm dần | Kết quả |
|---|---|
| first() | 50 |
| last() | 10 |
| headSet(30,false) | 50, 40 |
| tailSet(30,true) | 30, 20, 10 |
| lower(30) | 40 |
| higher(30) | 20 |
| floor(35) | 40 |
| ceiling(35) | 30 |

lower(30) trả 40 không phải một ngoại lệ của số học. Theo thứ tự giảm dần, 40 đứng trước 30. lower tìm phần tử lớn nhất còn nhỏ hơn đối số **theo thứ tự đang dùng**; trong chiều giảm dần, kết quả nhìn bằng số thông thường nằm ở phía lớn hơn.

Tương tự, floor(35) đi về phía không vượt 35 theo thứ tự giảm dần, nên chọn 40; ceiling(35) chọn 30. Để tự tính, hãy viết dãy đang duyệt ra giấy trước khi đọc tên hàm theo cảm giác “sàn là số nhỏ”.

Đối với một view v và view đảo d của chính v, các quan hệ sau giúp kiểm tra suy luận, miễn là dùng cùng phạm vi dữ liệu hiện tại:

| Trên d | Tương ứng trên v |
|---|---|
| first | last |
| last | first |
| lower(x) | higher(x) |
| floor(x) | ceiling(x) |
| ceiling(x) | floor(x) |
| higher(x) | lower(x) |

Với map, thay bằng firstKey/lastKey, lowerKey/higherKey và floorKey/ceilingKey; các phương thức trả entry cũng đổi chiều tương ứng. Kết quả vẫn bị giới hạn trong phạm vi của v. Không so một view giảm dần của khoảng nhỏ với toàn bộ nguồn tăng dần rồi áp bảng một cách máy móc.

### 6.3. Đảo cây vốn đã có Comparator giảm dần

descendingSet() không có nghĩa tuyệt đối là “sắp số giảm dần”. Nó đảo **thứ tự hiện có**. Nếu TreeSet ban đầu dùng Comparator.reverseOrder() cho số nguyên, thứ tự nguồn đã là 50, 40, 30, 20, 10; view descending của nó sẽ duyệt 10, 20, 30, 40, 50.

Điều tương tự đúng với Comparator sắp mã, chuỗi theo độ dài hay đối tượng theo thời gian. Hãy xác định bộ so sánh của nguồn trước; đừng gắn cố định tên descending với cách in giá trị.

## 7. Ghép phạm vi với chiều đảo: phải đổi mốc và giữ cờ tương ứng

Có hai cách tạo view cho cùng khoảng dữ liệu:

1. Chọn phạm vi trên nguồn, sau đó đảo chiều.
2. Đảo chiều nguồn, sau đó chọn phạm vi trong chiều mới.

Cách thứ hai phải đổi vị trí hai mốc. Với nguồn tăng dần s, hai đoạn minh họa sau cùng chọn 20, 30, 40 và cùng duyệt 40, 30, 20:

```java
// Doan minh hoa; s la NavigableSet<Integer> theo thu tu tang dan.
NavigableSet<Integer> a = s.subSet(20, true, 50, false).descendingSet();
NavigableSet<Integer> b = s.descendingSet().subSet(50, false, 20, true);
```

Cờ “lấy 20” phải đi cùng mốc 20; cờ “bỏ 50” phải đi cùng mốc 50. Đổi vị trí mốc nhưng không đổi cờ sẽ chọn nhầm biên.

Biểu thức s.descendingSet().subSet(20,true,50,false) không còn hợp lệ vì 20 đứng sau 50 trong chiều giảm dần. Java không tự hiểu hai số ấy là “cận số học nhỏ/lớn”.

Quy tắc tổng quát đối với view và biên hợp lệ:

| Tạo từ view đảo của s | Cách nhìn tương đương từ s |
|---|---|
| descendingSet().subSet(b, bi, a, ai) | subSet(a, ai, b, bi).descendingSet() |
| descendingSet().headSet(k, inclusive) | tailSet(k, inclusive).descendingSet() |
| descendingSet().tailSet(k, inclusive) | headSet(k, inclusive).descendingSet() |

Map dùng cùng phép biến đổi với descendingMap, subMap, headMap và tailMap. Chẳng hạn window.descendingMap().headMap(200,false) ở chương trình trước chỉ còn khóa 250: “trước 200” theo chiều giảm dần chính là các khóa lớn hơn 200 trong window.

Các quan hệ này nói về nội dung, thứ tự và việc dùng chung dữ liệu, không khẳng định hai biểu thức trả cùng tham chiếu. Chúng cũng không cho phép nới biên ra ngoài một view cha đã bị giới hạn.

Một mẹo thực tế: nếu điều kiện nghiệp vụ được mô tả bằng khoảng số tăng dần hoặc khoảng thời gian từ sớm đến muộn, thường nên tạo khoảng theo chiều đó trước, rồi đảo để hiển thị. Cách viết này giữ mốc nghiệp vụ dễ đọc hơn.

## 8. Chương trình kết hợp: đảo phạm vi và sao chép đúng thứ tự

Ví dụ đầy đủ sau kiểm tra:

- Hai cách tạo cùng một view phạm vi đảo.
- Các phép head/tail và điều hướng theo chiều đảo.
- Bản sao giữ Comparator so với bản sao dùng thứ tự tự nhiên.
- Nguồn đổi nhưng bản sao không đổi.
- Bản sao không tiếp tục mang giới hạn của view ban đầu.
- API định vị đầu/cuối bị từ chối trên cấu trúc có thứ tự do phép so sánh quyết định.

Tệp **ReverseRangeDemo.java**, yêu cầu JDK 21 trở lên:

```java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.NavigableSet;
import java.util.TreeMap;
import java.util.TreeSet;

public class ReverseRangeDemo {
    private static void expectUOE(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + ": no exception");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        TreeSet<Integer> source =
                new TreeSet<>(List.of(10, 20, 30, 40, 50));
        NavigableSet<Integer> descending = source.reversed();
        NavigableSet<Integer> rangeThenReverse =
                source.subSet(20, true, 50, false).reversed();
        NavigableSet<Integer> reverseThenRange =
                descending.subSet(50, false, 20, true);

        System.out.println("descending=" + descending);
        System.out.println("rangeThenReverse=" + rangeThenReverse);
        System.out.println("reverseThenRange=" + reverseThenRange);
        System.out.println("sameMembers=" +
                rangeThenReverse.equals(reverseThenRange));
        System.out.println("head30=" + descending.headSet(30, false));
        System.out.println("tail30=" + descending.tailSet(30, true));
        System.out.println("lower30=" + descending.lower(30));
        System.out.println("higher30=" + descending.higher(30));
        System.out.println("floor35=" + descending.floor(35));
        System.out.println("ceiling35=" + descending.ceiling(35));

        TreeSet<Integer> sortedCopy = new TreeSet<>(rangeThenReverse);
        Collection<Integer> widened = rangeThenReverse;
        TreeSet<Integer> naturalCopy = new TreeSet<>(widened);
        List<Integer> listCopy = new ArrayList<>(rangeThenReverse);
        System.out.println("sortedCopy=" + sortedCopy);
        System.out.println("naturalCopy=" + naturalCopy);
        System.out.println("listCopy=" + listCopy);

        source.add(45);
        System.out.println("viewAfterAdd45=" + rangeThenReverse);
        System.out.println("copyAfterAdd45=" + sortedCopy);
        sortedCopy.add(100);
        System.out.println("copyOutsideFormerRange=" + sortedCopy);
        System.out.println("sourceHas100=" + source.contains(100));
        expectUOE("addFirst", () -> descending.addFirst(99));
        System.out.println("doubleReverseEquals=" +
                descending.reversed().equals(source));

        TreeMap<Integer, String> map = new TreeMap<>();
        map.put(10, "A");
        map.put(20, "B");
        map.put(30, "C");
        NavigableMap<Integer, String> mapView =
                map.subMap(10, true, 30, false).reversed();
        TreeMap<Integer, String> sortedMapCopy = new TreeMap<>(mapView);
        Map<Integer, String> widenedMap = mapView;
        TreeMap<Integer, String> naturalMapCopy = new TreeMap<>(widenedMap);
        System.out.println("mapView=" + mapView);
        System.out.println("sortedMapCopy=" + sortedMapCopy);
        System.out.println("naturalMapCopy=" + naturalMapCopy);
        map.put(15, "D");
        System.out.println("mapViewAfterPut15=" + mapView);
        System.out.println("mapCopyAfterPut15=" + sortedMapCopy);
        expectUOE("putFirst", () -> mapView.putFirst(12, "X"));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 21 -encoding UTF-8 ReverseRangeDemo.java
java ReverseRangeDemo
```

Stdout chính xác:

```text
descending=[50, 40, 30, 20, 10]
rangeThenReverse=[40, 30, 20]
reverseThenRange=[40, 30, 20]
sameMembers=true
head30=[50, 40]
tail30=[30, 20, 10]
lower30=40
higher30=20
floor35=40
ceiling35=30
sortedCopy=[40, 30, 20]
naturalCopy=[20, 30, 40]
listCopy=[40, 30, 20]
viewAfterAdd45=[45, 40, 30, 20]
copyAfterAdd45=[40, 30, 20]
copyOutsideFormerRange=[100, 40, 30, 20]
sourceHas100=false
addFirst=UnsupportedOperationException
doubleReverseEquals=true
mapView={20=B, 10=A}
sortedMapCopy={20=B, 10=A}
naturalMapCopy={10=A, 20=B}
mapViewAfterPut15={20=B, 15=D, 10=A}
mapCopyAfterPut15={20=B, 10=A}
putFirst=UnsupportedOperationException
```

Các kết quả cùng thứ tự giữa rangeThenReverse và reverseThenRange được thấy trực tiếp ở hai dòng in danh sách. Riêng equals() của Set chỉ kiểm tra tập phần tử, không kiểm tra thứ tự duyệt; dòng sameMembers=true một mình chưa chứng minh thứ tự trùng nhau.

source.add(45) hiện trong view thành 45, 40, 30, 20. sortedCopy vẫn là 40, 30, 20. Khi sortedCopy.add(100), phần tử 100 được chấp nhận: đó đã là một TreeSet độc lập với Comparator giảm dần, không còn ràng buộc [20,50) của view gốc.

Ở nửa map, map.put(15,"D") thay đổi mapView nhưng không thay sortedMapCopy. Thứ tự của bản sao và liên kết với nguồn là hai thuộc tính cần kiểm tra riêng.

Nếu đang dùng Java 17, dùng descendingSet()/descendingMap() để tạo các view đảo. Không gọi reversed(), addFirst() hay putFirst() của ví dụ Java 21 trên nền API 17. Những API mới không cần thiết để hiểu hoặc sử dụng phạm vi TreeSet/TreeMap.

## 9. Sao chép view: giữ nội dung, thứ tự hay ràng buộc?

### 9.1. Constructor nhận SortedSet/SortedMap giữ bộ so sánh

Trong ReverseRangeDemo:

- rangeThenReverse có kiểu NavigableSet, là một SortedSet, nên new TreeSet<>(rangeThenReverse) chọn constructor nhận SortedSet và giữ thứ tự của view.
- widened có kiểu Collection, nên new TreeSet<>(widened) chọn constructor nhận Collection và sử dụng thứ tự tự nhiên.
- mapView có kiểu NavigableMap, là SortedMap, nên new TreeMap<>(mapView) chọn constructor nhận SortedMap và giữ Comparator.
- widenedMap có kiểu Map, nên new TreeMap<>(widenedMap) chọn constructor nhận Map và sử dụng thứ tự tự nhiên của khóa.

Cùng một đối tượng lúc chạy nhưng **kiểu khai báo của đối số** dẫn tới chọn constructor khác khi biên dịch. Kết quả in [40,30,20] và [20,30,40] làm khác biệt này nhìn thấy rõ.

Với phần tử/khóa tùy chỉnh không triển khai Comparable, chọn nhầm constructor dùng thứ tự tự nhiên còn có thể gây ClassCastException, dù nguồn hoạt động tốt với Comparator riêng.

Nếu API đầu vào chỉ lộ Collection hoặc Map, muốn giữ một thứ tự tùy chỉnh thì phải truyền Comparator đã biết một cách tường minh vào cấu trúc đích rồi mới thêm dữ liệu. Không đoán Comparator từ vài phần tử được in ra.

### 9.2. Sao chép không sao chép luôn “hàng rào”

TreeSet mới được dựng từ view không lưu lại giới hạn cũ. TreeMap mới cũng vậy. Bản sao giữ các phần tử/ánh xạ được chọn lúc sao chép, và có thể giữ bộ so sánh tùy constructor, nhưng không tự có lại điều kiện chỉ được chèn trong khoảng ban đầu.

Nếu muốn bản sao riêng vẫn chỉ cho phép sửa trong một khoảng, đó là yêu cầu mới: tạo cấu trúc riêng rồi tạo view phạm vi trên chính cấu trúc riêng ấy, hoặc đóng gói các phương thức cập nhật với kiểm tra nghiệp vụ phù hợp.

Phân biệt ba mục tiêu:

| Mục tiêu | Lựa chọn |
|---|---|
| Cập nhật trực tiếp phần dữ liệu trong nguồn | View phạm vi |
| Cùng nguồn, chỉ đọc theo chiều ngược | View đảo |
| Dữ liệu riêng, còn khả năng tìm kiếm có thứ tự | TreeSet/TreeMap mới với Comparator đúng |
| Giữ thứ tự duyệt hiện tại thành dãy độc lập | ArrayList mới từ set/view |
| Chặn sửa qua tham chiếu trả ra nhưng vẫn theo dõi nguồn | Lớp bọc unmodifiable trên view |
| Không theo dõi nguồn và chặn sửa cấu trúc qua tham chiếu trả ra | Tạo bản sao riêng rồi bọc bản sao |

ArrayList từ view giữ thứ tự gặp phần tử lúc sao chép, nhưng không trở thành một tập có điều hướng; nó cho phép trùng và không tự duy trì thứ tự sau các lần thêm. Bản sao bằng Set.copyOf()/Map.copyOf() cũng không phải cam kết giữ Comparator hay khả năng điều hướng của cây.

### 9.3. Bản sao thường chỉ tách cấu trúc

Sao chép một TreeMap<Integer,MutableValue> sang TreeMap khác không tự nhân bản các MutableValue. Hai map có các cấu trúc ánh xạ riêng nhưng vẫn có thể giữ tham chiếu tới cùng đối tượng giá trị.

Tương tự, sao chép set không tự nhân bản từng phần tử. Nếu cần ảnh chụp độc lập cả trạng thái bên trong, phải chọn dữ liệu bất biến hoặc thiết kế phép sao chép đối tượng phù hợp. Không gọi một bản sao cấu trúc là “bất biến sâu”.

Tạo bản sao rồi bọc unmodifiable chỉ đủ để chặn cập nhật cấu trúc qua lớp bọc. Nó không tự làm các đối tượng được chứa trở nên bất biến và không bảo đảm ảnh chụp nhất quán nếu có luồng khác đang sửa nguồn mà thiếu phối hợp.

## 10. Cập nhật qua view: phạm vi là một điều kiện, không phải giao dịch

### 10.1. Đảo thứ tự không cho quyền tự đặt vị trí

Cây duy trì thứ tự theo phép so sánh. Thêm qua view đảo vẫn dùng add()/put() và vị trí do Comparator quyết định, đồng thời phải thỏa phạm vi nếu view đã bị giới hạn.

Java 21 có addFirst/addLast ở họ sequenced collection và putFirst/putLast ở họ sequenced map. TreeSet và TreeMap không hỗ trợ định vị tường minh như vậy: các phép này gây UnsupportedOperationException. Đảo chiều không thay đổi quy tắc ấy.

Trong chương trình, descending.addFirst(99) và mapView.putFirst(12,"X") đều bị từ chối. Để thêm 12 vào mapView, thao tác phù hợp là put(12,"X"), vì 12 thuộc khoảng [10,30); nó tự xuất hiện sau 15 và trước 10 theo thứ tự giảm dần hiện tại.

### 10.2. Các phép xóa có thể ảnh hưởng nhiều dữ liệu nguồn

Không chỉ remove() mới thay đổi nguồn. Các phép sau, khi được cấu trúc/view hỗ trợ, cũng tác động vào phần nguồn đang nhìn thấy:

- clear() xóa toàn bộ phạm vi hiện tại.
- pollFirst()/pollLast() trên set và pollFirstEntry()/pollLastEntry() trên map lấy rồi xóa đầu/cuối của view.
- removeIf(), retainAll(), removeAll() hoặc xóa qua iterator của set có thể loại nhiều phần tử trong khoảng.
- Xóa qua tập khóa hoặc tập entry của một subMap có thể xóa ánh xạ trong nguồn.

Do đó trả một view có thể sửa cho nơi gọi tương đương trao quyền sửa một phần dữ liệu của mình. Nếu chức năng chỉ nên đọc, hãy thể hiện điều đó bằng API/lớp bọc phù hợp.

Các entry lấy bằng phương thức điều hướng như TreeMap.firstEntry()/floorEntry() là ảnh chụp ánh xạ, không phải một lối tùy ý gọi setValue() để cập nhật cây. Muốn thay giá trị, dùng put() trên map/view với khóa hợp lệ. Đừng suy mọi Map.Entry đều có hành vi cập nhật giống nhau.

### 10.3. Không giả định thao tác nhiều phần tử sẽ hoàn tác khi lỗi

Một lệnh addAll()/putAll() lên view có thể gặp phần tử hoặc khóa ngoài khoảng. Không có bảo đảm giao dịch rằng mọi cập nhật hợp lệ trước đó sẽ được hoàn tác nếu phần sau gây lỗi.

Với yêu cầu “tất cả hợp lệ mới cập nhật”, kiểm tra toàn bộ dữ liệu trước bằng cùng quy tắc biên/Comparator rồi mới ghi trong cơ chế đồng bộ hoặc giao dịch do ứng dụng sở hữu. Việc kiểm tra rồi ghi riêng lẻ cũng không tự chống được thay đổi đồng thời.

Không bắt IllegalArgumentException rồi tiếp tục coi nguồn như chưa bị động tới sau một thao tác hàng loạt. Tùy thuật toán đang dùng, nguồn có thể đã nhận một phần cập nhật.

Phạm vi là điều kiện chọn dữ liệu và kiểm tra chỗ ghi; nó không thay thế ràng buộc nghiệp vụ tổng thể, xử lý lỗi hay cơ chế nguyên tử.

## 11. Các giới hạn thực tế khi giữ và duyệt view

### 11.1. Không sửa dữ liệu so sánh khi phần tử/khóa còn trong cây

Khoảng được quyết định bởi thứ tự của cây. Nếu đối tượng phần tử của TreeSet hoặc khóa của TreeMap có trường tham gia Comparator, đổi trực tiếp trường ấy khi đối tượng còn trong cây có thể làm thứ tự cấu trúc sai với trạng thái hiện tại.

Không thể dùng view để sửa chữa tình huống này. Chọn phần tử/khóa bất biến; nếu cần thay thuộc tính sắp xếp, xóa bằng cách hợp lệ trước, thay đổi đối tượng rồi thêm lại. Comparator cũng phải ổn định trong quá trình cây được sử dụng.

Đổi trường của một giá trị trong map không tự đổi phạm vi theo khóa. Nếu nghiệp vụ muốn lọc theo thuộc tính của giá trị, subMap không phải công cụ trực tiếp đáp ứng yêu cầu ấy; cần chỉ mục theo khóa phù hợp hoặc phép lọc khác.

### 11.2. View sống không đồng nghĩa với iterator chịu mọi sửa đổi

Một view vẫn có thể dùng để quan sát dữ liệu sau khi nguồn được cập nhật tuần tự. Nhưng iterator đang đi dở trên nguồn/view là đối tượng khác với bản thân view.

TreeSet và TreeMap không tự đồng bộ giữa các luồng. Sửa cấu trúc khi đang duyệt qua tham chiếu khác có thể khiến iterator báo ConcurrentModificationException. Cơ chế phát hiện này là cố gắng phát hiện lỗi, không phải bảo đảm đồng bộ và không nên là điều kiện đúng của chương trình.

Nếu cần xóa đúng phần tử đang duyệt và iterator hỗ trợ, dùng iterator.remove(). Khi cần cập nhật theo đợt, thường dễ kiểm soát hơn nếu xác định dữ liệu cần xử lý rồi thực hiện cập nhật trong một bước có quyền sở hữu/đồng bộ rõ ràng.

Tạo view đảo, view phạm vi hoặc lớp bọc unmodifiable không biến TreeMap thành ConcurrentNavigableMap. Bản sao cũng chỉ là ảnh chụp đáng tin khi việc đọc nguồn lúc sao chép được phối hợp đúng với các bên ghi.

### 11.3. Đừng đánh đồng chi phí tạo view với chi phí xử lý dữ liệu

Tạo view không chủ động sao chép mọi phần tử của khoảng sang một cây mới. Vì vậy nó phù hợp khi cần làm việc với cửa sổ dữ liệu hiện tại.

Tuy nhiên, duyệt k phần tử vẫn phải đọc k phần tử; xóa một khoảng có thể phải xóa nhiều ánh xạ; sao chép phạm vi vẫn phải tạo cấu trúc mới chứa dữ liệu được chọn. Không suy ra rằng size(), clear() hay mọi thao tác trên view đều O(1).

Cũng không coi một view nhỏ là một bản lưu nhỏ độc lập: vì view liên kết với nguồn, giữ nó lâu có thể giữ cả cấu trúc nguồn trong vòng đời bộ nhớ. Nếu chỉ cần vài dữ liệu lịch sử và muốn giải phóng nguồn lớn, một bản sao thích hợp có thể thể hiện mục đích tốt hơn.

## 12. Áp dụng: cửa sổ thời gian và xử lý theo đợt

Giả sử TreeMap lưu sự kiện theo Instant, mỗi khóa đại diện một thời điểm. Nhu cầu “các sự kiện từ đầu ngày, không lấy đầu ngày kế tiếp, hiển thị mới nhất trước” có ba bước rõ ràng:

1. Xác định hai mốc Instant bằng quy tắc múi giờ của nghiệp vụ.
2. Tạo subMap(start,true,nextStart,false) theo thứ tự thời gian tăng dần.
3. Lấy descendingMap() của phạm vi để hiển thị ngược.

Khoảng đóng/mở [start,nextStart) cho phép hai ngày liền nhau ghép nối mà không cùng nhận một sự kiện tại ranh giới. Không cần tự tính “giây cuối cùng” hoặc “nano giây cuối cùng” của ngày. Mốc thời gian cụ thể vẫn phải được tạo đúng múi giờ; API phạm vi không giải quyết chuyển đổi lịch và múi giờ thay ứng dụng.

Sau khi có phạm vi, hãy quyết định quyền cập nhật:

- Một màn hình phải theo dữ liệu đang thay đổi có thể dùng view được bảo vệ khỏi sửa qua phía đọc, với cơ chế đồng bộ phù hợp.
- Một báo cáo cố định cần tạo bản sao vào thời điểm được kiểm soát.
- Một tác vụ dọn dữ liệu cũ có thể dùng headMap(cutoff,false).clear(), nhưng đó là xóa dữ liệu nguồn trước cutoff, cần đúng quyền sở hữu nghiệp vụ.
- Một tác vụ lấy sự kiện mới nhất trong khoảng có thể dùng pollFirstEntry() trên view giảm dần; sau lời gọi, sự kiện đó không còn trong nguồn.

Nếu nhiều sự kiện có cùng thời điểm, TreeMap<Instant,Event> chỉ giữ một giá trị cho một khóa theo phép so sánh. Muốn giữ tất cả, chọn giá trị là danh sách sự kiện hoặc khóa ghép có thứ tự phân biệt thêm mã sự kiện. View không thay đổi tính duy nhất của khóa.

Biên của view cố định theo các mốc đã truyền. Nó không tự “trượt theo đồng hồ” qua ngày mới. Muốn một cửa sổ “24 giờ gần nhất”, phải tính lại mốc theo yêu cầu và tạo view tương ứng; tính sống chỉ nói dữ liệu trong khoảng hiện tại còn dùng chung nguồn.

## 13. Những lỗi cần nhận ra trong lúc đọc code

| Cách hiểu/lựa chọn sai | Hậu quả | Cách xử lý |
|---|---|---|
| Xem subSet/subMap là bản sao | Sửa view làm nguồn đổi ngoài dự tính | Xác định có cần cấu trúc độc lập ngay khi nhận dữ liệu |
| Nghĩ subMap lọc theo giá trị | Chọn nhầm tập ánh xạ | Xây khóa/chỉ mục theo điều kiện cần tìm |
| Nhớ sai biên của dạng rút gọn | Thừa hoặc thiếu dữ liệu tại ranh giới | Dùng dạng boolean khi cần đọc rõ biên |
| Đảo chiều nhưng giữ nguyên thứ tự hai mốc | IllegalArgumentException | Đổi vị trí mốc và mang cờ lấy/bỏ theo mốc |
| Hiểu head là các số nhỏ hơn trong mọi view | Kết quả phía đối diện dự tính | Đọc head theo Comparator hiện tại |
| Dùng view con để tự động cắt một khoảng vượt cha | Lỗi khi tạo phạm vi con | Tính giao biên hoặc tạo từ nguồn đủ rộng |
| Nghĩ view rỗng đã tách khỏi nguồn | Dữ liệu mới xuất hiện bất ngờ | Phân biệt rỗng hiện tại với bản sao |
| Nghĩ clear chỉ xóa đối tượng trung gian | Xóa dữ liệu thật trong nguồn | Kiểm tra phạm vi và quyền ghi trước khi xóa |
| Mở rộng kiểu đầu vào thành Collection/Map khi sao chép | Mất Comparator tùy chỉnh | Chọn constructor nhận SortedSet/SortedMap hoặc truyền Comparator |
| Nghĩ bản sao tiếp tục chặn phần tử ngoài khoảng cũ | Thêm được dữ liệu ngoài phạm vi ban đầu | Tạo lại ràng buộc trên cấu trúc riêng nếu cần |
| Bọc unmodifiable rồi gọi là bản chụp | Nguồn đổi, dữ liệu đọc vẫn đổi | Sao chép trước nếu cần tách liên kết |
| Dùng equals để kiểm tra thứ tự của Set/Map | Hai thứ tự khác nhau vẫn bằng nhau | So dãy duyệt khi yêu cầu là thứ tự |
| Dựa vào ConcurrentModificationException để điều phối | Hành vi đồng thời thiếu bảo đảm | Dùng quyền sở hữu và cơ chế đồng bộ đúng |

## 14. Bài tập tự kiểm tra và lời giải

### Bài 1 — Bốn biên, không đổi dữ liệu

Nguồn tăng dần chứa 1, 2, 3, 4, 5, 6. Viết kết quả theo thứ tự duyệt cho:

1. subSet(2,false,5,true).
2. headSet(3).
3. tailSet(3).
4. subSet(4,true,4,true).
5. subSet(4,false,4,true).

**Lời giải:** lần lượt là [3,4,5], [1,2], [3,4,5,6], [4], []. Hai trường hợp cuối có cùng mốc nhưng khác việc lấy mốc.

### Bài 2 — Nguồn và phạm vi rỗng

Nguồn có 10, 50. Tạo v = subSet(20,true,40,false), sau đó thêm 30 và 45 qua nguồn. v là gì? Nếu gọi v.clear(), nguồn còn gì?

**Lời giải:** v ban đầu rỗng nhưng sau khi thêm hiện [30]. 45 nằm ngoài khoảng. v.clear() xóa 30 khỏi nguồn, để lại [10,45,50]. View vẫn giữ khoảng [20,40), không mất kết nối.

### Bài 3 — Biên cha đang mở

p là view [10,40) trên nguồn tăng dần. So sánh p.headSet(40,false), p.headSet(40,true) và p.headSet(50,false).

**Lời giải:** trường hợp đầu hợp lệ và không mở rộng phạm vi; trường hợp thứ hai cố nhận 40 đã bị cha loại, trường hợp thứ ba dùng mốc 50 vượt biên cha. Hai trường hợp sau gây IllegalArgumentException, không phải tự cắt về [10,40).

### Bài 4 — Phạm vi đảo tương đương

Nguồn tăng dần có 10, 20, 30, 40, 50. Muốn cùng dữ liệu và thứ tự với s.subSet(20,false,50,true).descendingSet(), hãy viết từ s.descendingSet().

**Lời giải:** s.descendingSet().subSet(50,true,20,false), kết quả [50,40,30]. Cờ true vẫn đi cùng 50; cờ false vẫn đi cùng 20. Nếu chỉ đổi thứ tự mốc mà giữ vị trí hai cờ, kết quả sẽ sai ở ranh giới.

### Bài 5 — Điều hướng trên chiều giảm dần

d là view giảm dần của nguồn tăng dần [10,20,30,40,50]. Tính d.headSet(30,true), d.floor(25), d.ceiling(25) và phần tử bị d.pollLast() xóa.

**Lời giải:** headSet là [50,40,30]; floor(25) là 30; ceiling(25) là 20; pollLast() xóa 10 khỏi nguồn. “Cuối” của d là phần tử nhỏ nhất theo số thông thường trong ví dụ này.

### Bài 6 — TreeMap chọn khóa

Nguồn chứa 1→"Z", 2→"A", 3→"M". Tạo w = subMap(1,true,3,false), rồi đọc w.descendingMap().values(). Nếu gọi w.navigableKeySet().remove(2), nguồn đổi thế nào?

**Lời giải:** dãy giá trị là A, Z vì khóa duyệt theo 2, 1. Xóa khóa 2 qua tập khóa xóa cả ánh xạ 2→"A" khỏi nguồn; còn 1→"Z" và 3→"M". Khóa 3 chưa từng nằm trong w, dù giá trị của nó có thể giống một giá trị trong khoảng.

### Bài 7 — Cùng view, constructor khác

rev có kiểu NavigableSet<Integer> và hiện [9,7,5]. So sánh new TreeSet<>(rev) với việc gán rev vào Collection<Integer> rồi truyền biến đó vào new TreeSet<>(...).

**Lời giải:** cách đầu chọn constructor SortedSet và giữ thứ tự giảm dần; cách sau chọn constructor Collection và dùng thứ tự tự nhiên, nên duyệt [5,7,9]. Cả hai đều tách cấu trúc khỏi nguồn; không bản nào tự giữ giới hạn chèn của rev. Kết luận giữ Comparator phụ thuộc constructor được chọn, không chỉ phụ thuộc tên TreeSet.

### Bài 8 — Chọn API cho nơi gọi

Một dịch vụ lưu TreeMap theo mã. Nơi gọi chỉ được xem khoảng [100,200), cần dữ liệu không tự thay đổi sau khi trả về và không được sửa cấu trúc nhận được. Nên trả unmodifiableNavigableMap(source.subMap(...)) hay tạo bản sao rồi bọc?

**Lời giải:** cần tạo bản sao của phạm vi trong điều kiện đọc nguồn nhất quán rồi bọc bản sao. Chỉ bọc view sẽ chặn thao tác ghi qua tham chiếu đó nhưng vẫn thấy cập nhật nguồn. Nếu giá trị là đối tượng có thể sửa, còn phải quyết định có cần sao chép giá trị hoặc chuyển sang dữ liệu bất biến hay không.

### Bài 9 — Comparator nguồn vốn đã đảo

Nguồn dùng Comparator.reverseOrder() cho Integer và có 1, 2, 3, 4. source.headSet(3,false) hiện gì? source.descendingSet().headSet(3,false) hiện gì?

**Lời giải:** nguồn duyệt [4,3,2,1], nên head trước 3 là [4]. View đảo duyệt [1,2,3,4], nên head trước 3 là [1,2]. Không thể tính kết quả đúng chỉ từ chữ head hoặc descending mà bỏ qua Comparator của đối tượng nhận lời gọi.

## 15. Tài liệu để đối chiếu tiếp

Các giải thích và chương trình trong bài có thể kiểm tra với những hợp đồng API chính thức sau:

- [TreeSet — constructor, phạm vi, descendingSet và giới hạn thao tác](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeSet.html).
- [TreeMap — constructor, subMap, descendingMap và các phương thức điều hướng](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html).
- [NavigableSet — biên tường minh và reversed từ Java 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableSet.html).
- [NavigableMap — phạm vi theo khóa và view đảo](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableMap.html).
- [Collections — các lớp bọc không cho sửa](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html).
