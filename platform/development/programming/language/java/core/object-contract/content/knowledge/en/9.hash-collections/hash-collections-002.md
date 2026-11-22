# Phân biệt băm để định hướng tìm kiếm với xác nhận bằng nhau

## 1. Hai câu hỏi khác nhau trong cấu trúc dữ liệu băm

Khi dùng `HashMap` hoặc `HashSet`, dễ hiểu nhầm rằng “hai đối tượng có cùng `hashCode()` thì bằng nhau”. Điều đó **không đúng**. Cấu trúc băm sử dụng hai cơ chế liên quan nhưng đảm nhiệm hai việc khác nhau:

1. **Băm để định hướng tìm kiếm:** `hashCode()` cung cấp một số nguyên giúp cấu trúc dữ liệu xác định nơi cần tìm trước tiên (bucket, nhóm ứng viên hoặc cấu trúc nội bộ tương ứng).
2. **Xác nhận bằng nhau:** khi gặp một khóa ứng viên thích hợp, phép kiểm tra đồng nhất tham chiếu hoặc `equals(Object)` quyết định đó có đúng là khóa đang tìm không.

**Hash là chỉ dẫn tới nơi tìm, không phải bằng chứng nhận dạng duy nhất.** Hai khóa có thể đụng cùng giá trị băm (hash collision) dù chúng không bằng nhau. Cấu trúc băm phải xử lý va chạm này bằng cách phân biệt các khóa theo hợp đồng `equals`.

Ví dụ:

- Hai chuỗi `"Aa"` và `"BB"` có cùng giá trị `String.hashCode()` là `2112`, nhưng `"Aa".equals("BB")` là `false`.
- Một `HashMap<String, Integer>` có thể chứa **cả hai khóa** và trả đúng giá trị tương ứng.
- Hai đối tượng có cùng ý nghĩa giá trị theo `equals` **bắt buộc** có cùng `hashCode`; điều ngược lại không được bảo đảm.

Bài học tập trung vào cách liên kết **băm để tìm ứng viên** với **so sánh để xác nhận** khi dùng cấu trúc băm Java, và cách thiết kế `equals`/`hashCode` đúng để việc tra cứu đáng tin cậy.

## 2. Luồng tra cứu trong `HashMap`: thu hẹp rồi xác nhận

Hãy hình dung lời gọi `map.get(queryKey)`. Ở mức khái niệm, quá trình diễn ra như sau:

1. Lấy mã băm của khóa truy vấn (với `null`, `HashMap` có cách xử lý riêng).
2. Dùng thông tin băm và dung lượng/cấu trúc bảng hiện tại để định hướng tới nhóm chứa các khóa có thể trùng.
3. Trong nhóm ứng viên, so sánh thông tin hash và kiểm tra khóa. Nếu hai tham chiếu đồng nhất, chúng đại diện cùng khóa; nếu khác tham chiếu, sử dụng `equals` theo quy tắc của `HashMap` để xác nhận.
4. Tìm thấy khóa bằng nhau thì trả giá trị gắn với khóa đó; không tìm thấy thì trả `null`. Lưu ý `get` trả `null` còn có thể do khóa tồn tại nhưng được gắn **giá trị `null`**; dùng `containsKey` để phân biệt khi cần.

Mã giả **chỉ minh họa ý tưởng**, không phải mã nguồn `HashMap` hay thuật toán bucket cụ thể của một bản JDK:

```text
find(queryKey):
    hash = hashOf(queryKey)
    candidates = locateCandidateGroup(hash)

    for each storedEntry in candidates:
        if hashesMayMatch(storedEntry, hash):
            if sameReference(storedEntry.key, queryKey)
               or keysAreEqual(storedEntry.key, queryKey):
                return storedEntry.value

    return NOT_FOUND
```

Phần triển khai thật có tối ưu phân phối hash, kiểm tra hash lưu trong node, và có thể dùng cấu trúc dạng cây cho nhóm va chạm lớn. Thứ tự thực tế của các nhánh kiểm tra phụ thuộc mã nguồn JDK. **Điểm không đổi về ngữ nghĩa** là chỉ dùng hash để khoanh vùng là chưa đủ; các khóa khác nhau cùng hash vẫn phải được phân biệt.

Với `HashSet<E>`, câu hỏi tương tự là “phần tử này đã có trong tập chưa?”. `HashSet` dựa trên `HashMap` bên trong để quản lý sự hiện diện của phần tử: `hashCode` hỗ trợ định vị, còn `equals` quyết định phần tử trùng về mặt ngữ nghĩa.

### Ví dụ sơ đồ luồng

```text
Truy vấn: get(k)
       |
       v
Lấy mã băm / xử lý trường hợp null
       |
       v
Định hướng tới nhóm ứng viên
       |
       v
Xét một khóa ứng viên
       |
       +-- Hash không phù hợp --------> Bỏ qua ứng viên
       |
       +-- Hash phù hợp
                 |
                 v
          Cùng tham chiếu hoặc
          bằng nhau theo equals?
            |             |
           Có            Không
            |             |
            v             v
        Trúng khóa      Xét tiếp
            |
            v
       Trả giá trị
```

Sơ đồ này mô tả **lý do** cần hai lớp kiểm tra; không hứa rằng bảng băm luôn được cài bằng danh sách liên kết, chỉ có một phép gọi `equals`, hoặc thuật toán luôn duyệt từng phần tử theo thứ tự cố định.

## 3. Hash collision: cùng hash vẫn có thể khác nhau

Một `hashCode()` Java chỉ trả về `int` 32 bit. Trong khi đó số lượng đối tượng và trạng thái giá trị có thể lớn hơn rất nhiều số giá trị `int`. Do đó **không thể yêu cầu hash là định danh duy nhất** cho mọi đối tượng.

Với hai đối tượng `a` và `b`:

| Quan hệ | Kết luận đúng | Hệ quả khi dùng cấu trúc băm |
| --- | --- | --- |
| `a.equals(b) == true` | Bắt buộc `a.hashCode() == b.hashCode()` nếu triển khai đúng hợp đồng. | Hai khóa đại diện cho cùng một khóa logic; thêm khóa bằng nhau vào `HashMap` sẽ cập nhật giá trị gắn với khóa đó. |
| `a.hashCode() == b.hashCode()` | **Không suy ra** `a.equals(b)`. | Các khóa khác nhau vẫn có thể cùng tồn tại; cấu trúc cần kiểm tra bằng nhau. |
| `a.hashCode() != b.hashCode()` | Theo hợp đồng đúng, `a.equals(b)` phải là `false`. | Một cấu trúc băm có thể loại trừ cặp này khi tìm kiếm; nếu `equals` lại trả `true`, lớp đã vi phạm hợp đồng. |
| `a.equals(b) == false` | Hash có thể bằng hoặc khác nhau. | Không có yêu cầu khác hash cho hai khóa khác nhau. |

Các cặp khóa có hash trùng nhau tạo thành nhóm cần phân biệt thêm; va chạm là trường hợp bình thường, không phải lỗi của `HashMap`.

Đừng nhầm **hash collision** (hai khóa khác giá trị băm giống nhau) với **bucket collision** (hai hash khác nhau nhưng được ánh xạ vào cùng vùng/bucket do bảng có dung lượng hữu hạn). Cả hai đều có thể khiến nhiều ứng viên được xét trong cùng nhóm. Vì vậy ngay cả hash được phân phối khá tốt vẫn cần bước xác nhận.

### Có cần một hash khác biệt cho mọi đối tượng?

Không. Mã băm tốt cố **phân tán** các khóa khác nhau để giảm số ứng viên cần đối chiếu; nó không được phép phá tính đúng đắn của `equals`. Hai đối tượng bằng nhau phải dùng cùng hash; hai đối tượng không bằng nhau có thể va chạm mà chương trình vẫn đúng chức năng, chỉ có thể chậm hơn.

Một triển khai `hashCode() { return 7; }` có thể **hợp lệ về mặt hợp đồng** nếu `equals` hợp lệ, vì mọi cặp bằng nhau đều cùng hash. Tuy nhiên nó rất tệ cho hiệu năng khi số lượng khóa lớn: cấu trúc băm không còn định hướng tìm kiếm tốt.

## 4. Ví dụ Java 17+ độc lập: va chạm vẫn tìm đúng khóa

Chương trình minh họa hai hiện tượng:

- Hai chuỗi khác nhau `"Aa"` và `"BB"` cố ý có cùng `String.hashCode`. `HashMap` vẫn lưu và lấy được hai giá trị.
- Lớp `ConstantHashKey` có mã băm **luôn là 7** nhưng `equals` so theo `id`. Đây là cách chủ động tạo va chạm để nhìn thấy rằng `HashSet` vẫn phân biệt phần tử.

Lưu toàn bộ mã trong tệp `HashAndEqualityDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class HashAndEqualityDemo {
    static final class ConstantHashKey {
        private final String id;

        ConstantHashKey(String id) {
            this.id = Objects.requireNonNull(id, "id");
        }

        @Override
        public boolean equals(Object other) {
            if (this == other) {
                return true;
            }
            if (!(other instanceof ConstantHashKey that)) {
                return false;
            }
            return id.equals(that.id);
        }

        @Override
        public int hashCode() {
            return 7; // Hợp đồng đúng, phân phối kém: chỉ dùng để minh họa.
        }
    }

    public static void main(String[] args) {
        String first = "Aa";
        String second = "BB";

        System.out.println("first hash: " + first.hashCode());
        System.out.println("second hash: " + second.hashCode());
        System.out.println("same hash: "
                + (first.hashCode() == second.hashCode()));
        System.out.println("strings equal: " + first.equals(second));

        Map<String, Integer> map = new HashMap<>();
        map.put(first, 10);
        map.put(second, 20);
        System.out.println("map size: " + map.size());
        System.out.println("get Aa: " + map.get("Aa"));
        System.out.println("get BB: " + map.get("BB"));

        Set<ConstantHashKey> set = new HashSet<>();
        set.add(new ConstantHashKey("alpha"));
        set.add(new ConstantHashKey("beta"));
        set.add(new ConstantHashKey("alpha"));
        System.out.println("set size: " + set.size());
        System.out.println("contains new alpha: "
                + set.contains(new ConstantHashKey("alpha")));
        System.out.println("contains new gamma: "
                + set.contains(new ConstantHashKey("gamma")));

        Map<String, String> nullableValues = new HashMap<>();
        nullableValues.put("exists", null);
        System.out.println("get missing is null: "
                + (nullableValues.get("missing") == null));
        System.out.println("get exists is null: "
                + (nullableValues.get("exists") == null));
        System.out.println("contains missing: "
                + nullableValues.containsKey("missing"));
        System.out.println("contains exists: "
                + nullableValues.containsKey("exists"));
    }
}
```

Biên dịch, chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 HashAndEqualityDemo.java
java HashAndEqualityDemo
```

Kết quả chuẩn:

```text
first hash: 2112
second hash: 2112
same hash: true
strings equal: false
map size: 2
get Aa: 10
get BB: 20
set size: 2
contains new alpha: true
contains new gamma: false
get missing is null: true
get exists is null: true
contains missing: false
contains exists: true
```

**Giải thích theo cơ chế:**

1. Cả `"Aa"` và `"BB"` cho hash `2112`. Nếu `HashMap` dùng duy nhất mã băm để xác nhận khóa, hai phần tử này sẽ bị gộp sai; nhưng `String.equals` phân biệt chúng, nên `map.size()` là `2`.
2. `map.get("Aa")` lấy `10` và `map.get("BB")` lấy `20` vì truy vấn khớp đúng khóa thông qua cả hash và so sánh bằng nhau, không phải vì mỗi khóa bắt buộc có một hash khác nhau.
3. `ConstantHashKey("alpha")` và `ConstantHashKey("beta")` đều có hash `7` nhưng không bằng nhau, nên `HashSet` giữ hai phần tử. Hai đối tượng `ConstantHashKey("alpha")` mới tạo ở lần thêm thứ nhất và thứ ba **bằng nhau**, nên lần thêm thứ ba không tăng kích thước tập.
4. Khi gọi `contains(new ConstantHashKey("alpha"))`, có thể dùng một đối tượng truy vấn mới mà vẫn tìm thấy phần tử tương đương. Ngược lại `"gamma"` không có phần tử bằng nhau trong tập dù cùng hash.
5. Hai biểu thức `get(...) == null` có kết quả `true` nhưng mang ý nghĩa khác nhau: khóa `"missing"` không tồn tại, còn khóa `"exists"` có tồn tại với giá trị `null`. `containsKey` giải quyết sự mơ hồ này.

Ví dụ dùng mã băm hằng số có chủ đích để chứng minh tính đúng đắn trước va chạm; **không nên chọn cách này cho các khóa thực tế có nhiều giá trị**.

## 5. Vì sao `equals` và `hashCode` phải được thiết kế thành một cặp?

Hợp đồng cơ bản của Java là:

> Nếu `a.equals(b)` là `true` thì `a.hashCode() == b.hashCode()` phải là `true`, miễn trạng thái dùng cho so sánh chưa thay đổi.

Hợp đồng một chiều này cho phép bảng băm dùng hash để thu hẹp tìm kiếm **mà không bỏ lỡ khóa bằng nhau**. Nếu hai khóa được `equals` coi là bằng nhau nhưng có hash khác nhau, quá trình truy vấn có thể đi tới nhóm khác và không đối chiếu đúng khóa đã lưu. Khi đó thao tác `get`, `containsKey`, `contains`, phát hiện khóa trùng hoặc loại bỏ phần tử có thể trả kết quả không phù hợp.

Ví dụ **thiết kế sai** (đoạn rút gọn, không phải chương trình độc lập):

```java
@Override
public boolean equals(Object other) {
    return other instanceof BadKey that
            && id.equalsIgnoreCase(that.id);
}

@Override
public int hashCode() {
    return id.hashCode(); // SAI: hash phân biệt hoa/thường.
}
```

Giả sử `BadKey("java").equals(BadKey("JAVA"))` là `true`, nhưng hash của chuỗi gốc khác nhau. Hai cách tính không tương thích. Cách sửa phụ thuộc quy tắc nghiệp vụ: hoặc dùng một **khóa chuẩn hóa duy nhất** cho cả hai phương thức (và bảo đảm miền/thuật toán chuẩn hóa đúng policy), hoặc để cả hai phương thức cùng so sánh/phân biệt hoa-thường.

Với một lớp giá trị như `ProductCode`, ví dụ hợp đồng hợp lệ là:

```java
// Minh họa trong lớp ProductCode có trường final String code.
@Override
public boolean equals(Object other) {
    return this == other
            || (other instanceof ProductCode that
                && code.equals(that.code));
}

@Override
public int hashCode() {
    return code.hashCode();
}
```

Đoạn này chỉ minh họa cặp phương thức trong lớp có `code` khác `null`; không tự chạy độc lập. Điểm chính: **cùng tiêu chí bằng nhau dẫn đến cùng tiêu chí băm**.

### Một hash tốt có thay thế được `equals` không?

Không. Ngay cả hash được phối hợp từ nhiều trường và có độ phân tán tốt vẫn chỉ là giá trị `int`; hai giá trị khác nhau có thể trùng hash. Đoạn mã sau là **sai nếu dùng để kết luận bình đẳng đối tượng**:

```java
// SAI: hash trùng không chứng minh hai đối tượng bằng nhau.
boolean same = left.hashCode() == right.hashCode();
```

Nếu cần so sánh giá trị, hãy dùng quy tắc bằng nhau thật sự (`equals` hoặc API so sánh nghiệp vụ đã công bố). Nếu cần khóa cho cấu trúc băm, cài đặt cả `equals` lẫn `hashCode`.

## 6. Khi nào hash không còn định hướng tới đúng khóa?

### Khóa thay đổi sau khi lưu

Giả sử một đối tượng khóa có trường `id` mutable và `hashCode` phụ thuộc vào `id`. Các bước:

1. `map.put(key, value)` đặt node vào vùng được chọn theo **hash lúc chèn**.
2. Chương trình sửa `key.id`, khiến `hashCode()` thay đổi.
3. `map.get(key)` dùng **hash mới** để định hướng tìm kiếm; node cũ vẫn ở vị trí theo hash cũ, nên `get` có thể không tìm thấy ngay cả khi truyền lại chính tham chiếu `key`.

Vấn đề ở đây không phải “đã sửa hash trong bảng” mà là **bảng không tự biết đối tượng khóa ngoài bảng bị thay đổi và không tự di chuyển node**. Ngay cả khi hash không thay đổi, việc thay đổi các trường trong `equals` sau khi làm khóa cũng có thể tạo kết quả bất ngờ như trùng khóa logic.

Cách an toàn nhất là chọn **khóa bất biến**: các trường tham gia `equals` và `hashCode` không đổi trong vòng đời sử dụng làm khóa. Nếu buộc phải đổi khóa logic, thường cần loại bỏ mục nhập theo khóa cũ trước khi thay đổi và chèn lại bằng khóa mới; với tập hợp, cân nhắc tạo đối tượng khóa mới thay vì sửa đối tượng đang nằm trong tập.

### `hashCode` phụ thuộc môi trường hoặc kết quả ngẫu nhiên

`hashCode` phải ổn định giữa các lần gọi trên cùng một đối tượng khi các trường dùng cho `equals` không đổi. Hash sinh ngẫu nhiên mỗi lần gọi, phụ thuộc giờ hiện tại, hoặc dựa vào trạng thái bên ngoài thay đổi bất thường sẽ làm định hướng tìm kiếm không nhất quán.

Mã băm Java **không được bảo đảm ổn định giữa các tiến trình hoặc phiên bản ứng dụng**, ngoại trừ khi API/triển khai cụ thể công bố điều đó. Không lưu tùy tiện `Object.hashCode()` như định danh bền vững của bản ghi hay giao thức.

## 7. Chi phí hiệu năng: hash giúp giảm số ứng viên, equals làm công việc chính xác

Đối với bảng băm có phân phối tốt và tải hợp lý, thao tác thêm/tìm/xóa thường có chi phí kỳ vọng gần **O(1)**. Nhưng đây là độ phức tạp trung bình/kỳ vọng trong những điều kiện phù hợp, không phải cam kết mọi thao tác luôn chỉ thực hiện một phép băm và một phép so sánh.

Khi quá nhiều khóa va chạm:

- Nhiều ứng viên phải được phân biệt; số phép kiểm tra bằng nhau có thể tăng.
- `equals` tốn kém (so sánh chuỗi dài, đồ thị dữ liệu sâu, truy vấn ngoại vi) có thể làm thời gian tăng rõ rệt. Không thực hiện I/O, gọi database hoặc các tác vụ có tác dụng phụ trong `equals`.
- `HashMap` ở các bản Java hiện đại có tối ưu bucket với cấu trúc cây trong những tình huống nhất định; không nên suy ra chính xác độ phức tạp của mọi tình huống chỉ bằng mô hình “bucket là danh sách”. Với hash và kiểu khóa khác nhau, hiệu năng phụ thuộc dữ liệu, số phần tử và chi tiết JDK.
- Thiết kế `hashCode` đơn giản, nhất quán và có phân phối tốt trên các trường có ý nghĩa giúp giảm ứng viên; **không cố tính hash đắt hơn phép so sánh đầy đủ chỉ để tránh mọi va chạm**.

Có thể hình dung hai tiêu chí chất lượng tách biệt:

| Thuộc tính | Cơ chế liên quan | Hậu quả khi kém |
| --- | --- | --- |
| **Tính đúng đắn** | `equals` đúng quan hệ bằng nhau; `hashCode` tương thích với `equals` | Có thể tìm sai/mất khóa, trùng phần tử logic hoặc hành vi collection bất thường. |
| **Hiệu năng** | Hash phân phối tốt, khóa bất biến, `equals` đủ rẻ | Nhiều va chạm khiến cần so sánh nhiều ứng viên; tăng thời gian thao tác. |

Một hash hằng số với `equals` đúng: **đúng chức năng nhưng thường chậm**. Một hash phân phối rất tốt với `equals` sai hợp đồng: **có thể nhanh nhưng trả kết quả sai**. Phải ưu tiên đúng ngữ nghĩa rồi tối ưu.

## 8. Những ranh giới và nhầm lẫn thường gặp

### 8.1. Dùng `==` ở đâu và dùng `equals` ở đâu?

- Với tham chiếu đối tượng, `a == b` chỉ xác định hai biến cùng trỏ đến một đối tượng (hoặc cùng `null`); nó không tự hiểu hai đối tượng được tạo riêng nhưng có cùng giá trị.
- Một triển khai cấu trúc băm có thể tối ưu trường hợp hai khóa là **cùng tham chiếu**, vì một đối tượng không thể khác chính nó theo hợp đồng `equals`. Điều đó không có nghĩa bảng băm chỉ dùng `==`.
- `equals` định nghĩa quan hệ bằng nhau theo giá trị/miền của loại khóa. Nếu lớp không ghi đè `Object.equals` thì mặc định vẫn là đồng nhất tham chiếu.

### 8.2. `HashMap` xử lý khóa `null` như thế nào?

`HashMap` cho phép một khóa `null`, và `HashSet` cho phép phần tử `null`. Trong trường hợp này không thể gọi `null.hashCode()` hay `null.equals(...)`; triển khai collection xử lý đặc biệt. Đừng diễn giải sơ đồ hai bước thành “luôn gọi `key.hashCode()` trực tiếp” đối với mọi khóa, kể cả `null`.

Chính sách khóa `null` khác giữa các collection: ví dụ `ConcurrentHashMap` không cho phép khóa hoặc giá trị `null`. Chọn collection phù hợp thay vì giả định mọi Map đều xử lý `null` như `HashMap`.

### 8.3. Tại sao `TreeMap` / `TreeSet` khác?

`TreeMap` và `TreeSet` dùng **thứ tự so sánh** thông qua `Comparable` hoặc `Comparator` để định vị và xác định trùng khóa, không dùng `hashCode` để định hướng như bảng băm. Với cây sắp xếp, kết quả `compare(a, b) == 0` có vai trò quan trọng đối với trùng khóa. Do đó hai đối tượng có thể được xử lý khác nhau giữa `HashSet` và `TreeSet` nếu comparator không nhất quán với `equals`.

Đây là lý do phải biết cơ chế của collection đang dùng: “tra cứu khóa” không luôn đồng nghĩa “băm mã hash”.

### 8.4. Có phải `hashCode` là mã hóa hoặc định danh an toàn?

Không. `Object.hashCode()` / `String.hashCode()` và các hàm hash dành cho collection không phải hàm băm mật mã. Chúng không được thiết kế để chống giả mạo, lưu mật khẩu, làm chữ ký hay xác minh dữ liệu tải về. Những yêu cầu đó phải dùng thuật toán/API mật mã phù hợp; trong bài này, “hash” có ý nghĩa **định hướng truy vấn** trong cấu trúc dữ liệu.

### 8.5. Khi ghi đè `equals` mà không ghi đè `hashCode`

Hai đối tượng khác tham chiếu có thể được `equals` xem là bằng nhau nhưng vẫn nhận mã băm mặc định khác nhau. Khi đó `HashSet.contains`, `HashMap.get` hoặc phát hiện khóa trùng có thể trả kết quả sai. Java không tự động sửa `hashCode` khi bạn ghi đè `equals` trên một class thông thường.

Với `record`, Java tự tạo triển khai giá trị cho `equals` và `hashCode` dựa trên các thành phần record; tuy vậy nếu thành phần là tham chiếu tới dữ liệu mutable, vấn đề khóa thay đổi vẫn cần được cân nhắc.

## 9. Quy trình thiết kế và kiểm thử

Khi cần tạo kiểu khóa mới cho `HashMap`/`HashSet`:

1. **Xác định quan hệ bằng nhau:** trường nào làm nên danh tính logic? So sánh có phân biệt hoa/thường không? `null` và lớp con được xử lý thế nào?
2. **Cài đặt `equals(Object)`:** bảo đảm phản xạ, đối xứng, bắc cầu, nhất quán và không bằng `null`; bảo đảm hai đối tượng khác tham chiếu nhưng tương đương vẫn được xác nhận.
3. **Cài đặt `hashCode()` trên cùng dữ liệu:** mọi cặp bằng nhau có mã băm giống nhau. Không dùng dữ liệu ngoại lai hoặc nguồn không xác định.
4. **Chọn khóa bất biến:** nhất là khi dùng trong collection nhiều thao tác hoặc chia sẻ qua các tầng ứng dụng.
5. **Thử va chạm có chủ đích:** tạo ít nhất hai khóa khác nhau nhưng cùng hash. Cả hai phải cùng tồn tại nếu `equals` khác nhau; tìm đúng từng khóa.
6. **Thử nhiều đối tượng bằng nhau:** tạo nhiều instance độc lập đại diện một giá trị; kiểm tra `contains`/`get` có trả đúng, thêm lại không tạo khóa logic trùng và cập nhật giá trị đúng.
7. **Thử khóa không tồn tại:** hash có thể trùng nhưng tìm kiếm phải vẫn báo không có phần tử; tách trường hợp khóa vắng mặt với giá trị `null` qua `containsKey`.
8. **Đánh giá phân phối hash và chi phí `equals`:** chỉ tối ưu khi các test ngữ nghĩa đã đúng; đo với dữ liệu đại diện.

Một bảng kiểm thử tham khảo:

| Thao tác | Dữ liệu kiểm tra | Điều mong đợi |
| --- | --- | --- |
| `map.put(a, value1)` rồi `map.get(b)` | `a.equals(b) == true`, `a` và `b` là instance riêng | Tìm được `value1`, hash của hai khóa bằng nhau. |
| `map.put(a, value1)` và `map.put(c, value2)` | `a.equals(c) == false` nhưng hash trùng nhau | Map có hai khóa; mỗi `get` trả đúng giá trị. |
| `set.add(a)` rồi `set.add(b)` | `a.equals(b) == true` | Lần thêm thứ hai trả `false`, kích thước không tăng. |
| `set.contains(c)` | `c` không bằng bất kỳ phần tử nào dù hash trùng | Trả `false`. |
| `map.get(k)` / `map.containsKey(k)` | Kết quả `get` là `null` | Phân biệt được absent key với present-null value. |
| Tra cứu sau khi khóa bị sửa trường dùng cho `hashCode` | Khóa mutable (thử nghiệm có kiểm soát) | Phơi bày rủi ro tra cứu không nhất quán, từ đó đổi thiết kế sang khóa bất biến. |

Không có một bài test duy nhất chứng minh mọi cặp giá trị thỏa hợp đồng; nên kiểm tra cả thuộc tính toán học của `equals` và các hành vi collection với cặp bằng nhau, khác nhau và va chạm.

## 10. Kết luận

Trong cấu trúc băm Java, `hashCode` hỗ trợ **định hướng tới những khóa có khả năng trùng**, còn `equals` **xác nhận hai khóa có thật sự bằng nhau**. Cùng hash không chứng minh cùng khóa; cùng khóa theo `equals` thì bắt buộc cùng hash. Va chạm không phải lỗi, và Java collection được thiết kế để xử lý nó đúng khi khóa tuân thủ hợp đồng. Hãy thiết kế `equals`/`hashCode` nhất quán, ưu tiên khóa bất biến, kiểm thử trường hợp va chạm có chủ đích và tách yêu cầu đúng ngữ nghĩa khỏi mục tiêu tối ưu hiệu năng.