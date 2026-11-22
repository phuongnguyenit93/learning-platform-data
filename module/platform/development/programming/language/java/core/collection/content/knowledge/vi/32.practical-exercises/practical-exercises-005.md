# Thực hành tổng hợp: Tìm khoảng, phần tử gần nhất và phân trang bằng cấu trúc có thứ tự

## 1. Bài toán và mục tiêu

Giả sử một hệ thống lưu các mã sản phẩm dạng số, cần đồng thời trả lời ba loại yêu cầu:

1. **Tìm khoảng:** lấy mọi mã từ `20` (bao gồm) đến `60` (không bao gồm).
2. **Tìm phần tử gần nhất:** với mã yêu cầu `35`, tìm mã hiện có có khoảng cách số học nhỏ nhất; nếu cách đều hai phía thì chọn mã nhỏ hơn.
3. **Phân trang:** trả các sản phẩm theo mã tăng dần, mỗi trang tối đa ba sản phẩm, và dùng mã cuối trang trước làm con trỏ để lấy trang sau.

Nếu mỗi truy vấn lại sắp xếp cả danh sách rồi quét từ đầu, ta lặp lại công việc không cần thiết. Java Collections cung cấp `NavigableSet` và `NavigableMap` để duy trì thứ tự và tìm mốc trước/sau một khóa.

Sau bài này, bạn có thể:

- Chọn `TreeSet` khi chỉ cần các giá trị duy nhất có thứ tự; chọn `TreeMap` khi mỗi khóa có dữ liệu đi kèm.
- Sử dụng `subSet`/`subMap`, `headSet`/`headMap`, `tailSet`/`tailMap` để lấy các khoảng có biên rõ ràng.
- Phân biệt `lower`, `floor`, `ceiling`, `higher` và xử lý trường hợp không có phần tử ở một phía.
- Xây dựng truy vấn gần nhất và phân trang theo khóa (keyset/cursor pagination), hiểu các giới hạn khi dữ liệu thay đổi.

## 2. Chọn đúng cấu trúc có thứ tự

| Nhu cầu | Giao diện/API | Cài đặt điển hình |
| --- | --- | --- |
| Lưu các mã *duy nhất*, duy trì thứ tự | `NavigableSet<E>` | `TreeSet<E>` |
| Ánh xạ một mã *duy nhất* sang dữ liệu | `NavigableMap<K,V>` | `TreeMap<K,V>` |
| Chỉ cần duyệt theo thứ tự và không tìm mốc điều hướng | `SortedSet` / `SortedMap` | `TreeSet` / `TreeMap` vẫn dùng được |

`TreeSet` và `TreeMap` thường dùng cây đỏ–đen cân bằng. Với `n` phần tử, thao tác tìm kiếm, thêm, xóa theo khóa có độ phức tạp `O(log n)`; sau khi tìm mốc, duyệt `k` phần tử liên tiếp mất thêm khoảng `O(k)`. Điều này phù hợp với câu hỏi “tìm từ khóa X trở đi rồi lấy vài phần tử”.

Thứ tự đến từ `Comparable` (thứ tự tự nhiên) hoặc `Comparator` được truyền vào constructor, **không phải thứ tự thêm phần tử**. Ví dụ `new TreeSet<>(List.of(40, 10, 30))` duyệt thành `[10, 30, 40]`.

**Điều kiện quan trọng:** trong một `TreeSet` hoặc `TreeMap`, hai khóa được coi là trùng khi phép so sánh trả về `0`. Ví dụ dùng `String.CASE_INSENSITIVE_ORDER` thì `"A"` và `"a"` là cùng một khóa theo cấu trúc này. Nên dùng cách so sánh nhất quán với `equals` nếu cần tuân thủ đầy đủ hợp đồng `Set`/`Map`. Nếu nhiều sản phẩm có cùng mức giá, không dùng riêng giá làm khóa duy nhất; có thể dùng khóa tổng hợp `(giá, mã sản phẩm)` hoặc lưu nhóm sản phẩm theo giá.

## 3. Tìm các phần tử trong khoảng

Một quy ước thường dùng là khoảng nửa mở `[from, to)`: nhận `from` nhưng bỏ `to`. Quy ước này giúp các khoảng liền kề không bị trùng phần tử ở đường biên.

~~~java
NavigableSet<Integer> ids = new TreeSet<>(
    List.of(10, 20, 30, 40, 50, 60, 70, 80)
);

NavigableSet<Integer> range = ids.subSet(20, true, 60, false);
// [20, 30, 40, 50]

NavigableSet<Integer> before = ids.headSet(40, false);
// [10, 20, 30]

NavigableSet<Integer> fromHere = ids.tailSet(40, true);
// [40, 50, 60, 70, 80]
~~~

Với `subSet(from, fromInclusive, to, toInclusive)`, hai tham số boolean quyết định có lấy các đầu mút hay không. `headSet(bound, inclusive)` lấy phía trước mốc; `tailSet(bound, inclusive)` lấy từ mốc về sau. Phiên bản tương ứng của `NavigableMap` là `subMap`, `headMap` và `tailMap`, áp dụng trên **khóa**:

~~~java
NavigableMap<Integer, String> products = new TreeMap<>();
products.put(10, "P10");
products.put(20, "P20");
products.put(30, "P30");
products.put(40, "P40");
products.put(50, "P50");

NavigableMap<Integer, String> selected =
    products.subMap(20, true, 50, false);
// keys: [20, 30, 40]
~~~

Một số chi tiết dễ bỏ sót:

- `subSet`/`subMap` trả về **view được hỗ trợ bởi cấu trúc gốc**, không phải bản sao độc lập. Thay đổi qua view làm thay đổi cấu trúc gốc, và thay đổi cấu trúc gốc có thể hiện ra trong view. Nếu cần bản chụp độc lập, tạo `new TreeSet<>(range)` hoặc `new TreeMap<>(selected)`.
- Biên phải đứng sau hoặc bằng biên trái **theo comparator đang dùng**. Với thứ tự tăng dần tự nhiên, gọi `subSet(60, true, 20, false)` sẽ ném `IllegalArgumentException`.
- Trên một view đã bị giới hạn, cố tạo view con vượt khỏi giới hạn hiện có cũng có thể ném `IllegalArgumentException`.
- Phạm vi rỗng là kết quả hợp lệ: chẳng hạn `subSet(20, false, 20, false)` không có phần tử. Đừng tự suy ra “không tồn tại dữ liệu” chỉ từ một khoảng rỗng.
- Muốn duyệt theo thứ tự giảm dần, cân nhắc `descendingSet()` hoặc `descendingMap()` và xác định lại cách hiểu điểm bắt đầu/kết thúc theo comparator của view đó.

## 4. Tìm phần tử thấp hơn, cao hơn và gần nhất

Các hàm điều hướng nhận một khóa `x` và tìm phần tử theo thứ tự so sánh:

| Hàm của `NavigableSet` | Điều kiện của phần tử trả về | Ví dụ khi `x = 40` |
| --- | --- | --- |
| `lower(x)` | Lớn nhất nhưng **nhỏ hơn** `x` | `30` |
| `floor(x)` | Lớn nhất và **≤ x** | `40` |
| `ceiling(x)` | Nhỏ nhất và **≥ x** | `40` |
| `higher(x)` | Nhỏ nhất nhưng **lớn hơn** `x` | `50` |

Nếu không tìm thấy phần tử thỏa điều kiện, mỗi hàm trả về `null`. Với `NavigableMap`, dùng `lowerKey`/`floorKey`/`ceilingKey`/`higherKey` nếu cần khóa, hoặc `lowerEntry`/`floorEntry`/`ceilingEntry`/`higherEntry` nếu cần cả cặp khóa–giá trị.

Đối với **khóa số**, một phần tử gần nhất về khoảng cách tuyệt đối phải là ứng viên `floor(target)` hoặc `ceiling(target)`: mọi phần tử còn lại ở xa hơn hoặc bằng một trong hai mốc này. Cần xác định quy tắc khi bằng khoảng cách (ở đây ưu tiên khóa nhỏ hơn).

~~~java
static Integer nearest(NavigableSet<Integer> sorted, int target) {
    Integer left = sorted.floor(target);
    Integer right = sorted.ceiling(target);

    if (left == null) return right;  // không có khóa phía dưới
    if (right == null) return left;  // không có khóa phía trên

    long leftDistance = (long) target - left;
    long rightDistance = (long) right - target;
    return leftDistance <= rightDistance ? left : right;
}
~~~

Ví dụ, `nearest([10,20,30,40,50], 35)` là `30` vì `30` và `40` đều cách `35` năm đơn vị, và quy tắc chọn phía nhỏ hơn. `nearest(..., 47)` là `50`; tập rỗng trả về `null`. Ép sang `long` trước khi trừ tránh tràn `int` khi hai khóa cách nhau rất xa.

**Phân biệt thứ tự và khoảng cách:** `Comparator` chỉ nói khóa nào đứng trước; nó **không tự định nghĩa “gần nhất” về mặt nghiệp vụ**. Với chuỗi, ngày giờ, tọa độ hay khóa tổng hợp, cần xác định thước đo khoảng cách rõ ràng trước khi áp dụng thuật toán gần nhất. Nếu muốn phần tử liền trước/liền sau theo thứ tự, `lower`/`higher` mới là phép toán phù hợp.

## 5. Phân trang theo con trỏ trên khóa có thứ tự

Giả sử khóa đang tăng dần: `10, 20, 30, 40, 50, 60, 70, 80` và mỗi trang tối đa ba khóa.

- Trang 1: bắt đầu từ đầu; lấy `10, 20, 30`; gửi `nextCursor = 30` nếu còn dữ liệu.
- Trang 2: chỉ lấy khóa **> 30** bằng `tailMap(30, false)`; nhận `40, 50, 60`; `nextCursor = 60`.
- Trang 3: chỉ lấy khóa **> 60**; nhận `70, 80`; hết dữ liệu nên `nextCursor = null`.

Cursor là khóa **cuối cùng đã trả về**, không phải chỉ số phần tử hoặc vị trí trang. Biến thể này còn gọi là *keyset pagination*. Nó tìm điểm bắt đầu theo khóa khoảng `O(log n)` rồi duyệt tối đa `pageSize + 1` phần tử để vừa lấy trang vừa biết còn trang sau, thay vì bỏ qua liên tiếp hàng nghìn phần tử bằng chỉ số offset. Với `NavigableMap`, dùng `tailMap(cursor, false)`; với `NavigableSet`, dùng `tailSet(cursor, false)`.

Hợp đồng API nên làm rõ:

- `cursor = null` ở **đầu vào** nghĩa là bắt đầu từ đầu danh sách; `nextCursor = null` ở **đầu ra** nghĩa là không còn trang tiếp theo.
- `pageSize > 0` và nên có giới hạn tối đa để tránh yêu cầu quá lớn.
- Thứ tự khóa phải ổn định; nếu sắp xếp bằng nhiều trường, cursor phải chứa đủ các trường đó cộng khóa phân biệt bản ghi. Ví dụ sắp xếp theo giá tăng dần rồi ID tăng dần, cursor phải là `(lastPrice, lastId)`.
- Cursor phải cùng thứ tự lọc/sắp xếp giữa các request. Khi đổi bộ lọc hoặc comparator, phải bắt đầu phân trang lại.
- Khi đang lọc trong một khoảng `[min, max)`, cursor phải được kiểm tra thuộc phạm vi hợp lệ trước khi gọi `tailMap` trên một bounded view, vì cursor ngoài giới hạn có thể làm phát sinh `IllegalArgumentException`.

Phân trang trên cấu trúc đang bị thay đổi **không bảo đảm cùng một ảnh chụp dữ liệu giữa các lần gọi**: bản ghi thêm sau cursor có thể xuất hiện, bản ghi thêm trước hoặc bằng cursor có thể không được nhìn thấy, bản ghi bị xóa sẽ biến mất. Nếu nghiệp vụ cần kết quả nhất quán tuyệt đối giữa nhiều trang, phải có snapshot/version hoặc cơ chế transaction phù hợp ở tầng lưu trữ. `TreeMap`/`TreeSet` không tự đồng bộ hóa; không nên đồng thời sửa cấu trúc trong lúc duyệt iterator mà thiếu cơ chế đồng bộ phù hợp.

## 6. Chương trình Java 17 hoàn chỉnh

Lưu đoạn sau thành **`OrderedQueriesDemo.java`**. Chương trình dùng một tập khóa có thứ tự cho truy vấn khoảng và gần nhất, đồng thời tạo map có thứ tự từ cùng dữ liệu để thực hiện phân trang. Hàm `pageAfter` chụp lại các `Map.Entry` được trả về bằng `SimpleImmutableEntry`; danh sách kết quả không bị ràng buộc trực tiếp với `TreeMap` sau khi hàm trả về.

~~~java
import java.util.ArrayList;
import java.util.AbstractMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.NavigableSet;
import java.util.TreeMap;
import java.util.TreeSet;

public class OrderedQueriesDemo {
    record Page(List<Map.Entry<Integer, String>> items, Integer nextCursor) {}

    static Integer nearest(NavigableSet<Integer> sorted, int target) {
        Integer left = sorted.floor(target);
        Integer right = sorted.ceiling(target);

        if (left == null) return right;
        if (right == null) return left;

        long leftDistance = (long) target - left;
        long rightDistance = (long) right - target;
        return leftDistance <= rightDistance ? left : right;
    }

    static Page pageAfter(
            NavigableMap<Integer, String> rows,
            Integer afterExclusive,
            int pageSize) {

        if (pageSize <= 0) {
            throw new IllegalArgumentException("pageSize must be positive");
        }

        NavigableMap<Integer, String> window =
            afterExclusive == null
                ? rows
                : rows.tailMap(afterExclusive, false);

        Iterator<Map.Entry<Integer, String>> it =
            window.entrySet().iterator();

        List<Map.Entry<Integer, String>> items = new ArrayList<>();
        while (items.size() < pageSize && it.hasNext()) {
            Map.Entry<Integer, String> entry = it.next();
            items.add(new AbstractMap.SimpleImmutableEntry<>(entry));
        }

        Integer nextCursor =
            it.hasNext() && !items.isEmpty()
                ? items.get(items.size() - 1).getKey()
                : null;

        return new Page(List.copyOf(items), nextCursor);
    }

    public static void main(String[] args) {
        NavigableSet<Integer> ids = new TreeSet<>(
            List.of(10, 20, 30, 40, 50, 60, 70, 80)
        );

        System.out.println(
            "Khoang [20, 60): " + ids.subSet(20, true, 60, false)
        );
        System.out.println(
            "floor(35): " + ids.floor(35)
                + ", ceiling(35): " + ids.ceiling(35)
        );
        System.out.println(
            "lower(40): " + ids.lower(40)
                + ", higher(40): " + ids.higher(40)
        );
        System.out.println("Gan 35: " + nearest(ids, 35));
        System.out.println("Gan 68: " + nearest(ids, 68));

        NavigableMap<Integer, String> products = new TreeMap<>();
        for (Integer id : ids) {
            products.put(id, "P" + id);
        }

        Integer cursor = null;
        int pageNumber = 1;
        while (true) {
            Page page = pageAfter(products, cursor, 3);
            System.out.println(
                "Trang " + pageNumber + ": "
                    + page.items().stream().map(Map.Entry::getKey).toList()
                    + ", next=" + page.nextCursor()
            );
            if (page.nextCursor() == null) {
                break;
            }
            cursor = page.nextCursor();
            pageNumber++;
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac OrderedQueriesDemo.java
java OrderedQueriesDemo
~~~

Kết quả chuẩn:

~~~text
Khoang [20, 60): [20, 30, 40, 50]
floor(35): 30, ceiling(35): 40
lower(40): 30, higher(40): 50
Gan 35: 30
Gan 68: 70
Trang 1: [10, 20, 30], next=30
Trang 2: [40, 50, 60], next=60
Trang 3: [70, 80], next=null
~~~

**Giải thích:** truy vấn khoảng bỏ `60` do biên trên không bao gồm. Với `35`, `floor = 30` và `ceiling = 40` cách đều nhau nên chọn `30`; với `68`, `70` gần hơn `60`. Ở trang 1, sau khi lấy ba bản ghi iterator vẫn còn dữ liệu, vì vậy `nextCursor = 30`. Trang cuối đã duyệt hết dữ liệu nên `nextCursor = null`. Vòng lặp không truy cập lại các bản ghi trước con trỏ.

Trong hàm phân trang, `items` là các cặp khóa–giá trị sao chép vào `SimpleImmutableEntry` bất biến và được đưa vào `List.copyOf`. Đây là ảnh chụp của *riêng trang hiện tại*, không phải snapshot của toàn bộ map qua nhiều lượt phân trang.

## 7. Độ phức tạp và lựa chọn cách làm

| Thao tác | Với `TreeSet` / `TreeMap` | Ghi chú |
| --- | --- | --- |
| `floor`, `ceiling`, `lower`, `higher` | `O(log n)` | Mỗi truy vấn định vị một mốc |
| Tìm phần tử gần nhất kiểu số | `O(log n)` | Hai lần tìm mốc và so sánh `O(1)` |
| Tìm mốc rồi duyệt `k` phần tử của khoảng | Khoảng `O(log n + k)` | Không cần sao chép toàn bộ tập |
| Lấy một trang kích thước `p` theo cursor | Khoảng `O(log n + p)` | Duyệt thêm tối đa một phần tử để biết còn trang sau |
| Bộ nhớ phụ của `pageAfter` | `O(p)` | Lưu bản sao các entry của một trang |

Các độ phức tạp trên mô tả thao tác trên cấu trúc cây đang có sẵn; nếu đầu vào là danh sách chưa được sắp xếp thì việc dựng `TreeSet`/`TreeMap` cũng có chi phí. Nếu chỉ chạy một truy vấn trên một danh sách nhỏ, quét tuyến tính có thể đơn giản hơn. Nếu hệ thống phải truy vấn liên tục trong lúc thêm/xóa dữ liệu, lưu dữ liệu theo cấu trúc cây có thứ tự đem lại lợi ích rõ ràng hơn.

Khi số lượng dữ liệu vượt bộ nhớ hoặc cần phân trang giữa nhiều máy, hãy dùng **chỉ mục có thứ tự của cơ sở dữ liệu** với điều kiện tương đương `WHERE id > :cursor ORDER BY id LIMIT :pageSize`. Ý tưởng cursor vẫn giống nhau, nhưng `TreeMap` không phải giải pháp lưu trữ bền vững hay chỉ mục phân tán.

## 8. Các lỗi thường gặp và cách tránh

1. **Nhầm biên inclusive/exclusive.** `tailMap(cursor, true)` khiến bản ghi cuối trang trước có thể lặp lại ở trang sau. Dùng `false` khi cursor có nghĩa “đã xuất bản ghi này”.
2. **Dùng `floor`/`ceiling` thay cho “liền trước/liền sau”.** Khi khóa trùng đúng `x`, cả `floor(x)` và `ceiling(x)` có thể trả về `x`. Muốn *khác x*, dùng `lower(x)`/`higher(x)`.
3. **Quên kiểm tra `null`.** Với tập rỗng hoặc không có dữ liệu một phía, các hàm điều hướng trả về `null`. Không unbox sang `int` trước khi xử lý.
4. **Tính khoảng cách bằng `int`.** Phép trừ hai số nguyên cực trị có thể tràn; chuyển sang `long` trước khi trừ, đồng thời định nghĩa quy tắc xử lý trường hợp cách đều.
5. **Dùng khóa không duy nhất.** `TreeMap` chỉ giữ một giá trị ứng với mỗi khóa theo comparator; `put` vào khóa trùng có thể thay dữ liệu cũ. Nếu sắp theo giá, dùng giá cộng ID hoặc map giá đến một nhóm nhiều sản phẩm.
6. **Hiểu view là danh sách bất biến.** `subSet`, `subMap` và `tailMap` là view sống; sửa cấu trúc nền có thể ảnh hưởng nội dung khi duyệt. Khi cần bản sao độc lập, sao chép rõ ràng.
7. **Phân trang bằng số thứ tự trên tập có thứ tự.** `TreeMap` không cung cấp truy xuất “phần tử thứ i” trong `O(log n)`. `pageIndex * pageSize` không biến `TreeMap` thành danh sách truy cập ngẫu nhiên; dùng khóa cuối trang trước khi phù hợp.
8. **Thay đổi thứ tự hoặc bộ lọc giữa các trang.** Cursor của thứ tự tăng không thể tái sử dụng bừa cho thứ tự giảm hoặc bộ lọc khác. Với nhiều cột sắp xếp, phải dùng khóa cursor tổng hợp.
9. **Quên giới hạn của concurrent access.** `TreeSet` và `TreeMap` không tự thread-safe; iterator thường phát hiện một số chỉnh sửa đồng thời bằng `ConcurrentModificationException` theo cơ chế best effort, không được dựa vào ngoại lệ đó để bảo đảm tính đúng đắn.

## 9. Bài tập tự kiểm tra

**Bài A — truy vấn theo khoảng.** Với `ids = [10,20,30,40,50,60,70,80]`, hãy dự đoán kết quả của:

~~~java
ids.subSet(20, false, 60, true);
ids.headSet(40, true);
ids.tailSet(40, false);
~~~

Đáp án lần lượt là `[30, 40, 50, 60]`, `[10, 20, 30, 40]` và `[50, 60, 70, 80]`. Mỗi câu kiểm tra một cách chọn biên khác nhau.

**Bài B — gần nhất ở biên.** Dùng hàm `nearest` trong chương trình, thử `target = 5`, `target = 80`, `target = 85` và một `TreeSet<Integer>` rỗng. Kết quả lần lượt là `10`, `80`, `80` và `null`. Giải thích vì sao phải xử lý ứng viên `null` trước khi trừ khoảng cách.

**Bài C — phân trang thực tế.** Đổi `pageSize` thành `2`. Dự đoán các trang `[10,20]`, `[30,40]`, `[50,60]`, `[70,80]`. Cursor đầu ra lần lượt là `20`, `40`, `60` và `null`. Sau đó thử gọi trực tiếp `pageAfter(products, 35, 3)`; kết quả phải bắt đầu bằng `40`, không yêu cầu khóa `35` tồn tại trong map.

**Bài D — mở rộng.** Một kho hàng phải lọc giá trong khoảng `[100, 500)`, sắp tăng dần theo giá và phân trang 20 sản phẩm. Hãy thiết kế `Comparator`/khóa dạng `(price, productId)` để hai sản phẩm cùng giá không đè lên nhau. Con trỏ cần chứa cả `price` và `productId`; truy vấn trang sau dùng so sánh lớn hơn **toàn bộ khóa tổng hợp**, không chỉ lớn hơn giá. Khi áp dụng trên database, giữ cùng điều kiện lọc và thứ tự cho mọi trang.

## 10. Ghi nhớ khi triển khai

`NavigableSet` và `NavigableMap` phù hợp khi dữ liệu có thứ tự và cần truy vấn theo mốc: dùng `subSet`/`subMap` để tìm khoảng, `floor`/`ceiling` để chọn hai ứng viên gần nhất, `tailSet`/`tailMap` với biên **exclusive** để phân trang theo cursor. Chọn comparator rõ ràng, xử lý biên và `null`, bảo đảm khóa phân biệt bản ghi, và xác định mức nhất quán dữ liệu khi phân trang qua nhiều lần gọi.
