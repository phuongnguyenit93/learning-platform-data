# Bảng băm, tập hợp và ánh xạ để tra cứu

Trong các bài toán thuật toán, nhiều bước có dạng **“đã gặp giá trị này chưa?”**, **“khóa này ứng với thông tin nào?”** hoặc **“giá trị này xuất hiện bao nhiêu lần?”**. Nếu mỗi truy vấn lại quét tuyến tính qua toàn bộ dữ liệu, chi phí có thể tăng nhanh. **Bảng băm (hash table)** tổ chức các mục theo khóa để việc tra cứu, thêm và xóa thường nhanh. Hai cách sử dụng phổ biến là **tập hợp (set)** và **ánh xạ (map)**.

Điều quan trọng là hiểu đúng giới hạn: bảng băm thường đạt **O(1) trung bình/kỳ vọng** cho thao tác theo khóa khi cơ chế băm hoạt động tốt; điều đó không bảo đảm mọi lần thao tác đều O(1), và bảng băm thông thường không duy trì khóa theo thứ tự tăng dần.

## 1. Phân biệt bảng băm, set và map

| Khái niệm | Lưu dữ liệu theo cách nào? | Truy vấn điển hình |
| --- | --- | --- |
| **Hash table** | Dùng giá trị băm của khóa để xác định nơi có thể chứa mục. | Khóa `k` có trong bảng không? |
| **Set** | Lưu các phần tử **phân biệt** theo quan hệ bằng nhau. | Giá trị `x` đã xuất hiện chưa? |
| **Map** | Lưu các cặp **khóa → giá trị**, mỗi khóa là duy nhất. | Giá trị gắn với khóa `k` là gì? |

Set và map là **mô hình dữ liệu/hành vi thao tác**; bảng băm là một **kỹ thuật triển khai**. Trong Java 17+, `HashSet` triển khai `Set` và `HashMap` triển khai `Map` theo cơ chế băm. Ngược lại, `TreeSet` và `TreeMap` triển khai tập hợp/ánh xạ dựa trên thứ tự so sánh, nên không thể đồng nhất mọi set/map với bảng băm.

Ví dụ: kiểm tra mã giao dịch đã xử lý thích hợp với `Set<String>`; đếm số giao dịch của từng tài khoản thích hợp với `Map<String, Integer>`; tra tên sản phẩm theo mã thích hợp với `Map<ProductId, Product>`.

## 2. Bảng băm chuyển khóa thành vị trí tra cứu như thế nào?

Hãy hình dung một bảng gồm nhiều vùng lưu gọi là **bucket**. Khi thêm một mục có khóa `k`:

1. Tính **giá trị băm (hash)** từ khóa.
2. Dùng giá trị băm để chọn bucket hoặc một vị trí có thể lưu mục.
3. Nếu tại nơi đó có mục khác, xử lý **va chạm (collision)**.
4. Khi tra cứu, tính lại hash rồi kiểm tra khóa ứng viên bằng quan hệ **bằng nhau về logic**, không chỉ bằng hash.

Ví dụ minh họa với khóa số nguyên dương, năm bucket và công thức đơn giản `bucket = key MOD 5`:

| Khóa | Bucket minh họa |
| ---: | ---: |
| 12 | 2 |
| 7 | 2 |
| 18 | 3 |

Khóa 12 và 7 **khác nhau nhưng cùng bucket 2**. Đó là va chạm, không phải lý do để coi hai khóa là một. Công thức trên chỉ giúp hình dung, không khẳng định Java `HashMap` dùng đúng cách tính này với mọi loại khóa.

Hai phương pháp giải quyết va chạm thường được giới thiệu:

- **Separate chaining:** một bucket có thể chứa nhiều mục; tra cứu tiếp tục so sánh các khóa trong bucket.
- **Open addressing:** nếu vị trí đã dùng, thuật toán tìm vị trí khác theo quy tắc dò trong bảng.

Đây là hai họ kỹ thuật băm. API `HashMap` cho người dùng hành vi ánh xạ theo khóa; chi tiết xử lý bucket thuộc về cài đặt và không nên được dùng làm bảo đảm về thứ tự hoặc thời gian của mọi lần thao tác.

### Hệ số tải và việc mở rộng bảng

Với `n` mục và `m` bucket, **hệ số tải** trong mô hình cơ bản là `α = n/m`. Khi nhiều mục dồn vào ít bucket, thao tác tìm có thể phải kiểm tra nhiều khóa hơn. Một cài đặt có thể cấp lại kích thước bảng và phân bố lại mục khi vượt ngưỡng phù hợp.

Một lần **resize/rehash** có thể tốn O(n), vì nhiều mục cần được xử lý lại. Nhận định “thêm mục trung bình O(1)” thường xét chi phí **khấu hao** của một chuỗi nhiều lần thêm, với giả định phân phối hash tốt và bảng được quản lý hợp lý.

## 3. Tập hợp (Set): dữ liệu duy nhất và kiểm tra thành viên

Các thao tác chính của `Set<T>` trong Java:

| Thao tác | Hành vi |
| --- | --- |
| `add(x)` | Thêm phần tử tương đương `x` nếu chưa có; trả `true` nếu tập thay đổi. |
| `contains(x)` | Kiểm tra sự tồn tại của phần tử tương đương `x`. |
| `remove(x)` | Loại bỏ phần tử tương đương `x` nếu có. |
| `size()` | Trả số phần tử phân biệt đang lưu. |

Giả sử nhận lần lượt các mã `[A, B, A, C, B]`. Sau khi thêm tất cả vào set, số phần tử phân biệt bằng **3**; set không lưu thông tin rằng `A` và `B` xuất hiện hai lần. Nếu cần số lần xuất hiện, cần bộ đếm hoặc map.

Giả mã đếm số giá trị phân biệt:

```text
ALGORITHM DISTINCT_COUNT(A)
    seen <- empty hash set
    FOR EACH x IN A DO
        INSERT x INTO seen
    END FOR
    RETURN SIZE(seen)
END ALGORITHM
```

**Bất biến:** sau khi duyệt `i` phần tử đầu của `A`, set chứa đúng các giá trị phân biệt trong phần đã duyệt. Do đó, sau phần tử cuối, `SIZE(seen)` chính là đáp án. Vòng lặp hữu hạn nên dừng; mảng rỗng trả `0`.

Với hash phân phối tốt, mỗi lần thêm/kiểm tra thường O(1), nên thời gian kỳ vọng của thuật toán là **O(n)**, bộ nhớ phụ **O(u)** với `u` là số giá trị phân biệt (`u ≤ n`).

**Không dựa vào thứ tự duyệt `HashSet`**. Nếu cần các phần tử theo thứ tự được chèn, sử dụng `LinkedHashSet`; nếu cần thứ tự sắp xếp, xem xét `TreeSet`.

## 4. Ánh xạ (Map): khóa gắn với dữ liệu

Một `Map<K,V>` lưu mỗi khóa tối đa một lần nhưng nhiều khóa có thể có cùng giá trị. Các thao tác thường gặp:

| Phương thức | Tác dụng | Lưu ý quan trọng |
| --- | --- | --- |
| `put(k,v)` | Đặt hoặc thay giá trị tại khóa `k`. | Nếu có khóa, giá trị cũ bị thay; map không giữ hai bản sao của cùng khóa. |
| `get(k)` | Lấy giá trị tại `k`. | Giá trị trả về `null` có thể nghĩa là khóa vắng hoặc khóa có giá trị `null`. |
| `containsKey(k)` | Kiểm tra có ánh xạ tại khóa `k` hay không. | Dùng khi cần phân biệt hai trường hợp có/không. |
| `getOrDefault(k,d)` | Giá trị hiện tại, hoặc `d` nếu khóa vắng. | Khóa tồn tại với giá trị `null` vẫn có thể trả `null`. |
| `remove(k)` | Xóa khóa và giá trị gắn với khóa đó nếu có. | Không ảnh hưởng khóa khác. |
| `merge(k,1,Integer::sum)` | Thêm hoặc tăng bộ đếm nguyên. | Thích hợp map tần suất với các giá trị không `null`. |

Ví dụ với các từ `[java, db, java, api, db, java]`, map đếm số lần xuất hiện nhận kết quả `java → 3`, `db → 2`, `api → 1`. Set chỉ có thể giữ ba từ phân biệt.

Cần nhớ rằng `HashMap` **không cam kết thứ tự khi duyệt các khóa hoặc các cặp key–value**. Nếu bài toán cần duyệt theo thứ tự chèn, cân nhắc `LinkedHashMap`; nếu cần thứ tự khóa, cân nhắc `TreeMap`.

## 5. Ví dụ Java 17+ hoàn chỉnh: phát hiện giá trị mới và đếm tần suất

Tạo tệp `HashLookupDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class HashLookupDemo {
    public static void main(String[] args) {
        String[] topics = {"java", "db", "java", "api", "db", "java"};

        Set<String> seen = new HashSet<>();
        Map<String, Integer> counts = new HashMap<>();

        for (String topic : topics) {
            boolean firstTime = seen.add(topic);
            counts.merge(topic, 1, Integer::sum);

            if (firstTime) {
                System.out.println("new=" + topic);
            }
        }

        System.out.println("unique=" + seen.size());
        System.out.println("hasJava=" + seen.contains("java"));
        System.out.println("java=" + counts.get("java"));
        System.out.println("api=" + counts.getOrDefault("api", 0));
        System.out.println("kotlin=" + counts.getOrDefault("kotlin", 0));

        System.out.println("replaced=" + counts.put("db", 10));
        System.out.println("dbNow=" + counts.get("db"));
    }
}
```

Biên dịch và chạy:

```bash
javac HashLookupDemo.java
java HashLookupDemo
```

Đầu ra chính xác:

```text
new=java
new=db
new=api
unique=3
hasJava=true
java=3
api=1
kotlin=0
replaced=2
dbNow=10
```

Lý do kết quả có thể xác định dù dùng `HashSet`: chương trình in `new=...` **ngay khi đang duyệt mảng đầu vào**, không duyệt qua set. `seen.add(topic)` trả `true` đúng ở lần gặp đầu. `counts.merge(topic,1,Integer::sum)` thêm bộ đếm bằng 1 nếu chưa có, hoặc tăng thêm 1 nếu đã có. `put("db",10)` trả giá trị cũ `2` và đổi giá trị hiện tại thành `10`, không tạo khóa thứ tư.

Biến được khai báo bằng `Set` và `Map` để phản ánh giao diện thao tác; đối tượng thực tế là `HashSet` và `HashMap`. `System.out.println` chỉ phục vụ quan sát, còn dữ liệu được tổ chức bên trong các cấu trúc.

## 6. Khóa đúng phải có quan hệ bằng nhau ổn định

Đối với đối tượng Java dùng làm khóa:

1. Nếu `a.equals(b)` là `true`, bắt buộc `a.hashCode() == b.hashCode()`.
2. Chiều ngược lại không bắt buộc: hai đối tượng khác nhau có thể có cùng `hashCode`.
3. Trong thời gian một đối tượng nằm trong bảng dưới vai trò khóa, không nên đổi các thuộc tính ảnh hưởng đến `equals` hoặc `hashCode`.
4. Toán tử `==` so sánh hai tham chiếu đối tượng có trỏ đến cùng một đối tượng không; `equals` có thể định nghĩa sự bằng nhau theo nội dung.

Java `record` là công cụ thuận tiện để tạo khóa từ nhiều thành phần khi các thành phần phù hợp. Tạo tệp `RecordKeyDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class RecordKeyDemo {
    record LessonKey(String subject, int number) {}

    public static void main(String[] args) {
        Map<LessonKey, String> titles = new HashMap<>();
        titles.put(new LessonKey("CS", 7), "Hash Table");

        System.out.println(titles.get(new LessonKey("CS", 7)));
        System.out.println(titles.containsKey(new LessonKey("CS", 8)));
    }
}
```

Chạy:

```bash
javac RecordKeyDemo.java
java RecordKeyDemo
```

Đầu ra:

```text
Hash Table
false
```

Hai biểu thức `new LessonKey("CS", 7)` tạo ra hai đối tượng khác nhau, nhưng `record` tự sinh `equals`/`hashCode` dựa trên các thành phần nên `HashMap` nhận ra chúng tương đương. Ví dụ dùng `String` và `int` có nội dung ổn định. Cẩn thận: `record` **không bảo đảm bất biến sâu** cho thành phần kiểu mảng hoặc đối tượng có thể thay đổi.

Một lớp tự tạo có thể bị lỗi khi định nghĩa `equals` theo `id` nhưng tính `hashCode` theo trường khác, hoặc khi sửa `id` sau lúc chèn khóa. Đây là lỗi **hợp đồng khóa**, không phải lỗi ngẫu nhiên của bảng băm.

## 7. Bài toán điển hình: tìm cặp hai số có tổng cho trước (Two Sum)

**Đầu vào:** mảng số nguyên `A`, số nguyên `target`. **Đầu ra:** một cặp chỉ số khác nhau `i < j` sao cho `A[i] + A[j] = target`, hoặc `NOT_FOUND` nếu không có. Giả mã dùng số nguyên toán học; khi chuyển sang Java với `int`, phải phòng tràn số ở `target - A[i]` nếu dữ liệu có thể chạm giới hạn kiểu, chẳng hạn bằng cách dùng `long` cho phép tính trung gian và khóa phù hợp.

Cách duyệt mọi cặp chỉ số mất O(n²) thời gian. Dùng map `giá trị → chỉ số trước đó` cho phép kiểm tra phần bù ngay khi duyệt:

```text
ALGORITHM TWO_SUM(A, target)
    seenAt <- empty hash map

    FOR i FROM 0 TO LENGTH(A) - 1 DO
        needed <- target - A[i]

        IF CONTAINS_KEY(seenAt, needed) THEN
            RETURN (seenAt[needed], i)
        END IF

        IF NOT CONTAINS_KEY(seenAt, A[i]) THEN
            seenAt[A[i]] <- i
        END IF
    END FOR

    RETURN NOT_FOUND
END ALGORITHM
```

**Bất biến:** trước lượt có chỉ số `i`, mọi chỉ số lưu trong map đều nhỏ hơn `i`; giá trị tại các khóa đã xuất hiện ở phần đầu mảng. Vì vậy, tìm thấy `needed` luôn tạo cặp `(p,i)` với `p<i`, không dùng một phần tử hai lần. Để duy trì bất biến, phải **kiểm tra trước khi chèn phần tử hiện tại**.

Với `A = [3, 2, 4]`, `target = 6`: lượt 0 lưu `3→0`, lượt 1 lưu `2→1`, lượt 2 cần `2` và trả `(1,2)`. Với `A = [3,3]`, `target = 6`, trả `(0,1)`; hai giá trị bằng nhau vẫn có hai chỉ số khác nhau. Với `A = [5]`, trả `NOT_FOUND`.

Nếu duyệt hết mà không tìm thấy, không có cặp nào vì mỗi phần tử đã được đối chiếu với tất cả giá trị trước đó qua map. Vòng lặp hữu hạn nên kết thúc. Thời gian **O(n) kỳ vọng** nhờ tra cứu hash trung bình O(1); bộ nhớ phụ **O(n)** khi có nhiều giá trị khác nhau. Va chạm quá bất lợi có thể làm thời gian lớn hơn.

## 8. Độ phức tạp và cách chọn cấu trúc

| Cấu trúc | Chi phí tra cứu điển hình | Đặc điểm quan trọng |
| --- | --- | --- |
| Mảng chưa sắp xếp | O(n) trong trường hợp xấu | Ít cấu trúc phụ trợ, hợp dữ liệu nhỏ. |
| Mảng đã sắp xếp + tìm kiếm nhị phân | O(log n) | Không cần bảng băm; việc chèn giữ thứ tự có thể O(n). |
| `HashSet`/`HashMap` | O(1) trung bình/kỳ vọng | Tra cứu theo khóa; không bảo đảm thứ tự. |
| `LinkedHashSet`/`LinkedHashMap` | Tra cứu băm tương tự trong điều kiện thông thường | Có thể giữ thứ tự chèn khi duyệt. |
| `TreeSet`/`TreeMap` | O(log n) cho các thao tác chính | Hỗ trợ thứ tự khóa và truy vấn theo khoảng. |

Bảng băm đánh đổi **bộ nhớ cho tốc độ tra cứu**. Trong mô hình số bucket giữ tương ứng với số mục, không gian dùng thường O(n), gồm mục và cấu trúc quản lý. Phép tính hash, so sánh khóa, va chạm và những lần mở rộng đều ảnh hưởng đến chi phí thật; không nên coi hiệu năng trung bình là cam kết từng thao tác.

Chọn `HashMap` khi ưu tiên truy vấn theo khóa và không cần thứ tự; chọn `TreeMap` khi phải duyệt từ khóa nhỏ đến lớn, tìm cận trước/sau hoặc truy vấn phạm vi; chọn mảng/list khi tập dữ liệu rất nhỏ, ít truy vấn và chi phí cấu trúc phụ có thể không đáng.

`HashMap` thông thường không phù hợp cho nhiều luồng cập nhật đồng thời mà thiếu đồng bộ. Nếu chương trình có yêu cầu này, cần cơ chế đồng bộ hoặc cấu trúc như `ConcurrentHashMap`, đồng thời hiểu ngữ nghĩa của các thao tác đồng thời.

## 9. Những sai lầm thường gặp

- **Cho rằng hash là mã định danh duy nhất:** hai khóa khác nhau vẫn có thể có cùng hash; phải so sánh bằng quy tắc `equals`.
- **Chỉ cài đặt `equals` mà bỏ `hashCode` phù hợp:** bảng băm có thể không tìm đúng khóa tương đương.
- **Thay đổi nội dung khóa sau khi thêm:** nếu hash hoặc quan hệ bằng nhau thay đổi, mục có thể trở nên khó truy xuất theo cách thông thường.
- **Duyệt `HashSet`/`HashMap` rồi giả định có thứ tự:** không có bảo đảm thứ tự; cần cấu trúc phù hợp khi thứ tự quan trọng.
- **Nhầm `get(k) == null` với khóa vắng:** `HashMap` có thể lưu giá trị `null`; dùng `containsKey` khi phải phân biệt.
- **Dùng `Set` để đếm số lần xuất hiện:** set chỉ lưu phần tử phân biệt; map mới gắn được bộ đếm với khóa.
- **Tưởng `put` luôn làm tăng kích thước map:** khi khóa đã có, thao tác chỉ thay giá trị.
- **Tuyên bố mọi lệnh băm luôn O(1):** va chạm, resize và công tính hash/so sánh có thể làm thao tác chậm đi.
- **Trong Two Sum, chèn trước khi kiểm tra phần bù:** có nguy cơ tìm lại chính phần tử ở chỉ số hiện tại.
- **Bỏ qua đầu vào rỗng hoặc khóa không tồn tại:** bài toán phải định nghĩa đáp án rõ ràng cho các trường hợp này.

## 10. Bài tập tự kiểm tra

**Bài 1.** Thêm `["a","b","a","c"]` vào `HashSet<String>`. Kích thước cuối là gì? **Đáp án:** `3`, vì `"a"` chỉ được giữ một lần.

**Bài 2.** Map có `"x"→2`. Sau `put("x",5)`, map có bao nhiêu khóa? **Đáp án:** vẫn một khóa; giá trị mới là `5`, giá trị trả về từ `put` là `2`.

**Bài 3.** Hai đối tượng khác nhau có cùng `hashCode` có bắt buộc được coi là bằng nhau không? **Đáp án:** không. Cần kiểm tra `equals`; đây là va chạm hợp lệ.

**Bài 4.** Với `A=[4,4]`, `target=8`, thuật toán Two Sum trả gì? **Đáp án:** `(0,1)`, vì phần tử ở chỉ số 0 đã được lưu trước khi duyệt chỉ số 1.

**Bài 5.** Tại sao một lệnh `put` đôi khi tốn O(n)? **Đáp án:** bảng có thể phải mở rộng và phân phối lại nhiều mục; độ phức tạp O(1) thường là nhận định trung bình/khấu hao.

**Bài 6.** `get("k")` trả `null` nhưng `containsKey("k")` trả `true` có mâu thuẫn không? **Đáp án:** không; với `HashMap`, khóa `"k"` có thể tồn tại và được gắn với giá trị `null`.

**Bài 7.** Cần in mọi khóa theo thứ tự tăng dần. Chọn `HashMap` hay `TreeMap`? **Đáp án:** `TreeMap` nếu thứ tự khóa là yêu cầu trực tiếp; `HashMap` không cam kết thứ tự duyệt.

## 11. Quy trình áp dụng trong bài toán mới

Trước hết xác định **loại tra cứu**: chỉ cần biết có/không, hay cần giá trị gắn với khóa hoặc tần suất. Tiếp theo kiểm tra **hợp đồng bằng nhau và tính ổn định của khóa**, yêu cầu về thứ tự, hành vi khi thiếu khóa và giới hạn bộ nhớ. Sau đó mới chọn set/map và cài đặt băm/có thứ tự phù hợp. Cuối cùng, kiểm chứng trên dữ liệu rỗng, trùng lặp, không tìm thấy, khóa va chạm về mặt khái niệm, dữ liệu lớn và các biên số học trong thuật toán.

**Ghi nhớ:** bảng băm là công cụ hỗ trợ tra cứu, không tự bảo đảm thuật toán đúng. Muốn dùng hiệu quả, phải nắm rõ đặc tả kết quả, quan hệ bằng nhau của khóa, thứ tự cập nhật, chi phí trung bình và những trường hợp ngoại lệ.
