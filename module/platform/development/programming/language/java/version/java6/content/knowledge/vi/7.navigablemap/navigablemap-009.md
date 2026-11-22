# View theo khoảng và cập nhật dữ liệu qua view của NavigableMap

## 1. Khung nhìn khoảng giải quyết vấn đề gì?

Giả sử một `NavigableMap<Integer, String>` lưu dữ liệu theo mã số. Một tác vụ chỉ cần xử lý các mã từ 20 đến trước 50. Có thể sao chép các ánh xạ phù hợp sang map mới, nhưng khi mục tiêu là thao tác trực tiếp trên dữ liệu nguồn trong phạm vi đó, một **khung nhìn theo khoảng** (range view) diễn đạt yêu cầu rõ hơn.

`subMap`, `headMap` và `tailMap` trả về các khung nhìn dựa trên thứ tự khóa. Chúng duy trì liên hệ với map gốc:

- Thêm hoặc cập nhật qua khung nhìn làm thay đổi map gốc.
- Thêm hoặc cập nhật qua map gốc được phản ánh trong khung nhìn nếu khóa thuộc phạm vi.
- Xóa qua khung nhìn xóa ánh xạ tương ứng khỏi map gốc.
- Giới hạn phạm vi tiếp tục tồn tại dù hiện tại không có phần tử nào trong khoảng.

Vì vậy, “khung nhìn chỉ có một phần dữ liệu” không có nghĩa “sửa nó không ảnh hưởng dữ liệu nguồn”. Hợp đồng dùng chung dữ liệu vẫn áp dụng trong Java hiện hành; xem [NavigableMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableMap.html).

## 2. Chọn phạm vi và quyền bao gồm biên

Với khóa số nguyên theo thứ tự tự nhiên:

| Lời gọi | Khóa được nhìn thấy |
| --- | --- |
| `map.subMap(a, true, b, false)` | `a <= key && key < b` |
| `map.subMap(a, true, b, true)` | `a <= key && key <= b` |
| `map.headMap(b, false)` | `key < b` |
| `map.headMap(b, true)` | `key <= b` |
| `map.tailMap(a, true)` | `key >= a` |
| `map.tailMap(a, false)` | `key > a` |

Cờ `true` cho phép điểm bằng mốc tham gia; `false` loại điểm ấy. Các mốc là **giá trị khóa**, không phải vị trí chỉ số. Mốc cũng không cần có sẵn trong map.

Ví dụ:

```java
// base la NavigableMap<Integer, String>.
NavigableMap<Integer, String> range =
        base.subMap(20, true, 50, false);
```

Khoảng `[20, 50)` cho phép các khóa như 20, 25, 49; không cho phép 19 hoặc 50. Nếu map gốc dùng comparator riêng, mọi quan hệ phải xét theo comparator đó. Xem [TreeMap: các phương thức tạo khung nhìn khoảng](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html).

Các overload ngắn dùng quy ước cố định: `subMap(a,b)` là `[a,b)`, `headMap(b)` loại b, `tailMap(a)` gồm a. Dùng overload có cờ khi cần diễn đạt rõ biên và giữ kiểu kết quả `NavigableMap` trong mã gọi.

## 3. Cập nhật qua khung nhìn hoạt động ra sao?

Giả sử map gốc là:

```text
{10=A, 20=B, 30=C, 40=D, 50=E}
```

Khung nhìn `[20, 50)` thấy `{20=B, 30=C, 40=D}`.

| Thao tác qua range | Hành vi trong ví dụ TreeMap |
| --- | --- |
| `put(25, "X")` | Thêm `25=X` vào map gốc |
| `put(30, "C2")` | Thay giá trị của khóa 30 trong map gốc |
| `remove(30)` | Xóa ánh xạ khóa 30 khỏi map gốc |
| `clear()` | Xóa các ánh xạ thuộc khoảng; giữ dữ liệu ngoài khoảng |
| `get(10)` | Trả null vì khóa 10 nằm ngoài phần đang nhìn thấy |
| `remove(10)` | Không xóa khóa 10 ở map gốc |
| `put(50, "BAD")` | Ném `IllegalArgumentException` vì 50 bị loại khỏi khoảng |

Cần phân biệt **khóa không nhìn thấy** với **khóa không tồn tại ở map gốc**. Một kết quả null từ khung nhìn không đủ để kết luận dữ liệu nguồn không có khóa đó.

Với map cho phép giá trị null, `get` hoặc `remove` trả null còn cần được diễn giải theo hợp đồng map và ngữ cảnh. Ví dụ trong bài chỉ dùng giá trị String khác null để quan hệ phạm vi dễ theo dõi.

## 4. Chương trình đầy đủ chạy trên Java 17+

Tệp `NavigableMapRangeUpdates.java`:

```java
import java.util.Collections;
import java.util.Map;
import java.util.NavigableMap;
import java.util.TreeMap;

public class NavigableMapRangeUpdates {
    private static void expectRangeError(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + ": missing exception");
        } catch (IllegalArgumentException expected) {
            System.out.println(label + "=IllegalArgumentException");
        }
    }

    private static void expectReadOnlyError(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError(label + ": missing exception");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        NavigableMap<Integer, String> base = new TreeMap<>();
        base.put(10, "A");
        base.put(20, "B");
        base.put(30, "C");
        base.put(40, "D");
        base.put(50, "E");

        NavigableMap<Integer, String> range =
                base.subMap(20, true, 50, false);
        System.out.println("initial range=" + range);

        range.put(25, "X");
        System.out.println("base after range insert=" + base);
        base.put(35, "Y");
        System.out.println("range after base insert=" + range);
        System.out.println("previous value=" + range.put(30, "C2"));

        for (Map.Entry<Integer, String> entry : range.entrySet()) {
            if (entry.getKey() == 20) {
                entry.setValue("B2");
                break;
            }
        }
        System.out.println("base after value updates=" + base);
        System.out.println("range get(10)=" + range.get(10));
        System.out.println("range remove(10)=" + range.remove(10));
        System.out.println("base still contains 10=" + base.containsKey(10));

        expectRangeError("put excluded upper", () -> range.put(50, "BAD"));
        expectRangeError("nested outside bounds",
                () -> range.subMap(10, true, 30, true));

        Map.Entry<Integer, String> snapshotEntry = range.firstEntry();
        expectReadOnlyError("firstEntry setValue",
                () -> snapshotEntry.setValue("BAD"));

        NavigableMap<Integer, String> readOnly =
                Collections.unmodifiableNavigableMap(range);
        expectReadOnlyError("readOnly put", () -> readOnly.put(25, "BAD"));
        base.put(45, "Z");
        System.out.println("readOnly after base insert=" + readOnly);

        NavigableMap<Integer, String> copy = new TreeMap<>(range);
        range.headMap(30, false).clear();
        System.out.println("base after head clear=" + base);
        range.tailMap(40, true).clear();
        System.out.println("base after tail clear=" + base);
        range.clear();
        System.out.println("base after range clear=" + base);
        System.out.println("readOnly after range clear=" + readOnly);
        System.out.println("copy after range clear=" + copy);

        range.put(20, "NEW");
        System.out.println("base after range reuse=" + base);
    }
}
```

Biên dịch và chạy với JDK 17 hoặc mới hơn:

```shell
javac -encoding UTF-8 NavigableMapRangeUpdates.java
java NavigableMapRangeUpdates
```

Kết quả:

```text
initial range={20=B, 30=C, 40=D}
base after range insert={10=A, 20=B, 25=X, 30=C, 40=D, 50=E}
range after base insert={20=B, 25=X, 30=C, 35=Y, 40=D}
previous value=C
base after value updates={10=A, 20=B2, 25=X, 30=C2, 35=Y, 40=D, 50=E}
range get(10)=null
range remove(10)=null
base still contains 10=true
put excluded upper=IllegalArgumentException
nested outside bounds=IllegalArgumentException
firstEntry setValue=UnsupportedOperationException
readOnly put=UnsupportedOperationException
readOnly after base insert={20=B2, 25=X, 30=C2, 35=Y, 40=D, 45=Z}
base after head clear={10=A, 30=C2, 35=Y, 40=D, 45=Z, 50=E}
base after tail clear={10=A, 30=C2, 35=Y, 50=E}
base after range clear={10=A, 50=E}
readOnly after range clear={}
copy after range clear={20=B2, 25=X, 30=C2, 35=Y, 40=D, 45=Z}
base after range reuse={10=A, 20=NEW, 50=E}
```

## 5. Theo dõi từng đường cập nhật trong chương trình

### Thêm qua view, rồi thêm qua nguồn

`range.put(25, "X")` làm map gốc có thêm 25. Tiếp đó `base.put(35, "Y")` làm khung nhìn thấy 35 vì khóa này nằm trong `[20, 50)`.

Không có bước làm mới hay đồng bộ thủ công giữa hai biến. Chúng là hai cách truy cập cùng dữ liệu nền.

Nếu thêm `base.put(60, "...")`, map gốc có thể nhận giá trị ấy nhưng `range` không thấy 60. Khung nhìn chỉ phản ánh phần dữ liệu đáp ứng giới hạn của nó.

### Cập nhật một khóa đã có

`range.put(30, "C2")` thay giá trị C bằng C2 và trả về giá trị cũ C. Nó không tạo một khóa 30 thứ hai.

Trong `TreeMap`, tính trùng khóa được quyết định qua thứ tự so sánh. Comparator phải được thiết kế phù hợp với `equals` để giữ đúng đầy đủ hợp đồng map. Không coi việc khung nhìn giới hạn phạm vi là cơ chế kiểm tra mọi quy tắc nghiệp vụ khác.

### Xóa theo các khoảng con

Sau khi tạo đủ dữ liệu, `range.headMap(30, false).clear()` xóa các khóa nhỏ hơn 30 **trong phạm vi range**: 20 và 25. Khóa 10 vẫn còn vì không thuộc range cha.

`range.tailMap(40, true).clear()` tiếp tục xóa 40 và 45. Khóa 50 vẫn còn vì bị loại từ đầu ở biên trên của range.

Cuối cùng `range.clear()` xóa phần còn lại trong khoảng: 30 và 35. Kết quả map gốc còn `{10=A, 50=E}`.

### Khung nhìn rỗng vẫn dùng lại được

Sau khi đã clear, `range.put(20, "NEW")` hợp lệ vì 20 vẫn thuộc giới hạn `[20, 50)`. Map gốc nhận ánh xạ mới.

Phạm vi gắn với **mốc đã khai báo**, không bị thu nhỏ thành khoảng của những khóa hiện đang có. Xóa hết dữ liệu cũng không hủy khung nhìn.

## 6. Vì sao có loại entry sửa được và có loại không?

Trong vòng lặp trên `range.entrySet()`, ví dụ dùng `entry.setValue("B2")` để thay giá trị của khóa 20. Với `TreeMap` có thể sửa, entry lấy trực tiếp trong quá trình duyệt có liên hệ với map; cập nhật giá trị qua cơ chế này được phản ánh về nguồn.

Không được giữ entry ấy rồi dùng tùy ý sau khi map đã bị thay đổi cấu trúc. Hợp đồng entry gắn với quá trình duyệt và khả năng hỗ trợ của map cụ thể; xem [Map.Entry](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.Entry.html).

Ngược lại:

```java
Map.Entry<Integer, String> snapshotEntry = range.firstEntry();
```

Entry của truy vấn điều hướng `firstEntry()` là ảnh chụp ánh xạ tại thời điểm gọi và không hỗ trợ sửa map qua `setValue`. Vì vậy chương trình nhận `UnsupportedOperationException` khi thử làm điều đó. Các entry từ `floorEntry/ceilingEntry/lowerEntry/higherEntry` cũng thuộc nhóm truy vấn ảnh chụp được mô tả trong [NavigableMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableMap.html).

Khi muốn thay giá trị đã tìm được bằng truy vấn điều hướng, thường có thể lấy khóa rồi gọi `put` hoặc một API cập nhật thích hợp trên map, đồng thời bảo đảm trạng thái không bị thay đổi ngoài kiểm soát giữa các bước.

## 7. Phạm vi con không được vượt phạm vi cha

Lời gọi:

```java
range.subMap(10, true, 30, true);
```

không có nghĩa “tự lấy giao với khoảng cha rồi trả phần còn lại”. Nó yêu cầu mốc 10 nằm ngoài giới hạn dưới 20 của range, nên ví dụ ném `IllegalArgumentException`.

Tương tự, `range.put(50, "BAD")` không được bỏ qua âm thầm dù 50 đang có sẵn trong map gốc. Phép cập nhật vẫn phải đi qua quyền truy cập theo khoảng của đối tượng nhận lời gọi.

Khi mốc con bằng một biên bị loại của khoảng cha, phải kiểm tra cả cờ bao gồm biên. Khi dùng comparator đảo, còn phải kiểm tra thứ tự của hai mốc theo comparator. Ví dụ với thứ tự giảm, mốc “đầu” của một `subMap` thường có số lớn hơn mốc “cuối”.

Các yêu cầu về mốc, phạm vi hạn chế và khóa ngoài khoảng được quy định tại [TreeMap.subMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html).

## 8. View có thể sửa, view chỉ đọc và bản sao

Ba lựa chọn này phục vụ ba ý định khác nhau:

| Cách tạo | Có dùng chung dữ liệu nguồn? | Có sửa qua đối tượng trả về? |
| --- | --- | --- |
| `base.subMap(...)` trên TreeMap có thể sửa | Có | Có, trong phạm vi |
| `Collections.unmodifiableNavigableMap(range)` | Có | Không |
| `new TreeMap<>(range)` | Không về cấu trúc map | Có trên bản sao |

### Chỉ đọc không đồng nghĩa cố định dữ liệu

`readOnly` trong ví dụ từ chối `put`, nhưng vẫn thấy 45 khi `base` thêm 45. Sau `range.clear()`, nó cũng trở thành rỗng.

Bộ bao chỉ đọc chặn sửa qua đường truy cập đó; nó không ngăn chủ sở hữu map sửa qua các tham chiếu khác. Xem [Collections.unmodifiableNavigableMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#unmodifiableNavigableMap(java.util.NavigableMap)).

### Bản sao không giữ liên hệ cập nhật

`copy` được tạo trước các lần xóa nên vẫn giữ sáu ánh xạ khi nguồn đã bị clear trong khoảng. Constructor nhận `SortedMap` giữ thứ tự của nguồn.

Bản sao là một map mới; nó không tự giữ giới hạn khoảng của range. Thêm một khóa ngoài khoảng cũ có thể hợp lệ trên copy nếu đáp ứng comparator của nó.

Nếu cần cả bản sao độc lập và không cho nơi nhận sửa, có thể bao một `TreeMap` mới trong `unmodifiableNavigableMap`. Bản sao cấu trúc vẫn không phải bản sao sâu của các đối tượng khóa/giá trị có thể thay đổi.

## 9. Các điểm cần kiểm soát trong mã thực tế

### Truyền view là truyền một đường truy cập tới dữ liệu nguồn

Nếu một hàm nhận `range` rồi gọi `clear()`, nguồn của nơi gọi cũng bị xóa trong khoảng. Hợp đồng hàm nên nói rõ có sửa dữ liệu không; người gọi cần chọn đúng view hoặc bản sao.

Không dùng phạm vi collection như một ranh giới phân quyền an toàn giữa các thành phần không đáng tin cậy. Nó là công cụ mô hình hóa và giới hạn thao tác collection, không thay thế kiểm tra quyền của ứng dụng.

### Thao tác nhiều bước không tự thành giao dịch

Tạo view không làm một chuỗi đọc–kiểm tra–cập nhật trở nên nguyên tử. Tương tự, không coi thao tác cập nhật hàng loạt như `putAll` là một giao dịch có tự động hoàn tác nếu gặp khóa không hợp lệ.

Nếu yêu cầu là “tất cả cập nhật thành công hoặc không thay đổi gì”, cần thiết kế xác thực, cập nhật và phối hợp đồng thời ở cấp phù hợp. Giới hạn biên chỉ là một phần của điều kiện hợp lệ.

### Duyệt và sửa cấu trúc phải theo đúng hợp đồng

Không thêm hoặc xóa tùy ý qua map gốc trong khi đang for-each trên `range.entrySet()`. Với `TreeMap`, iterator có cơ chế phát hiện sửa cấu trúc nhưng không nên dựa vào nó để đồng bộ.

Khi cần xóa trong quá trình duyệt, dùng chính iterator nếu nó hỗ trợ xóa; khi cần xóa cả khoảng, `clear` trên khoảng diễn đạt ý định rõ hơn. Khung nhìn không bổ sung an toàn luồng cho `TreeMap`; xem [quy tắc iterator và đồng bộ TreeMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html).

## 10. Kiểm thử và thực hành

Một bộ kiểm thử có ý nghĩa cần đối chiếu **cả view lẫn nguồn**, thay vì chỉ in view:

1. Thêm khóa trong khoảng qua view; xác nhận nguồn nhận cùng ánh xạ.
2. Cập nhật khóa qua nguồn; xác nhận view thấy giá trị mới nếu khóa nằm trong khoảng.
3. Thử thêm đúng biên bị loại và ngoài biên; xác nhận đúng loại ngoại lệ và dữ liệu nguồn không bị thay đổi bởi lời gọi thất bại đó.
4. Xóa một khoảng con; xác nhận các khóa ngoài khoảng còn nguyên.
5. Clear toàn bộ view, sau đó thêm lại một khóa hợp lệ; xác nhận view vẫn giữ giới hạn ban đầu.
6. So sánh bộ bao chỉ đọc với bản sao: thay đổi nguồn phải xuất hiện trong bộ bao, nhưng không thay đổi cấu trúc của bản sao.
7. Thử entry từ vòng duyệt và entry từ `firstEntry`; không mặc định mọi `Map.Entry` có cùng quyền sửa.

Bài tập: đổi biên trên từ `false` sang `true` trong ví dụ, dự đoán ảnh hưởng tới khóa 50 và ca `put excluded upper` trước khi chạy. Sau đó viết một phiên bản chỉ cập nhật các giá trị trong khoảng, không thêm hoặc xóa khóa, và xác nhận toàn bộ khóa ngoài khoảng giữ nguyên giá trị.
