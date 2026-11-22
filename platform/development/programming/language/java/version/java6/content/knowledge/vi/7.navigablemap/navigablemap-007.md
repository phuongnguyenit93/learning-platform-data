# TreeMap, Comparator và lựa chọn khóa

## 1. Chọn khóa là chọn cách dữ liệu được tìm và phân biệt

Giả sử hệ thống nhận hai sự kiện vào cùng một thời điểm:

```text
10:00:00Z, E1 -> sensor-A
10:00:00Z, E2 -> sensor-B
```

Nếu dùng riêng thời điểm làm khóa của map, một thời điểm chỉ giữ được một ánh xạ. Sự kiện thứ hai có thể thay giá trị của sự kiện thứ nhất. Nếu dùng khóa ghép thời điểm và mã sự kiện, có thể giữ cả hai, nhưng truy vấn cũng sẽ đi theo cả hai thành phần.

Vì vậy, trước khi khởi tạo `TreeMap`, cần trả lời:

1. Khi nào hai bản ghi được xem là cùng một khóa?
2. Cần duyệt và tìm lân cận theo thứ tự nào?
3. Có được giữ nhiều bản ghi cùng giá trị của tiêu chí chính không?
4. Các thuộc tính tham gia khóa có thay đổi sau khi thêm vào map không?

`TreeMap<K,V>` triển khai `NavigableMap<K,V>`, duy trì thứ tự khóa bằng thứ tự tự nhiên hoặc comparator được cung cấp. Phép so sánh quyết định cả thứ tự lẫn sự tương đương của khóa. Xem [TreeMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeMap.html).

Bài dùng API hiện còn áp dụng trong Java hiện đại; chương trình độc lập sử dụng Java 17 trở lên.

## 2. Thứ tự tự nhiên và comparator

### Dùng thứ tự tự nhiên khi kiểu khóa đã có ý nghĩa so sánh phù hợp

Ví dụ minh họa trong phương thức:

```java
NavigableMap<Integer, String> levels = new TreeMap<>();
NavigableMap<Instant, String> latestAtTime = new TreeMap<>();
```

Cần import các kiểu tương ứng. `Integer` có thứ tự số học. `Instant` biểu diễn một thời điểm trên dòng thời gian và hỗ trợ so sánh trước/sau; nó phù hợp khi khóa cần chỉ rõ thời điểm xảy ra sự kiện. Xem [Instant](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Instant.html).

Tên `latestAtTime` cũng gợi ý một quyết định: mỗi thời điểm chỉ có một giá trị hiện được giữ. Nếu thực tế cần lưu mọi sự kiện trùng thời điểm, khai báo ấy chưa đủ mô tả dữ liệu.

### Cung cấp comparator khi cần một thứ tự riêng

```java
NavigableMap<Integer, String> descending =
        new TreeMap<>(Comparator.reverseOrder());
```

Đây là minh họa trong phương thức, cần import từ `java.util`. Map này vẫn dùng khóa số nguyên nhưng duyệt từ lớn xuống nhỏ.

Với kiểu khóa tự định nghĩa không triển khai `Comparable`, cung cấp comparator phù hợp. Nếu không có cách so sánh được hỗ trợ, `TreeMap` không tự đoán cần dùng trường nào của đối tượng để xếp thứ tự.

Thứ tự khóa không được quyết định bởi giá trị V. Đặt tên hoặc ưu tiên vào phần giá trị không khiến cây tự sắp xếp theo các thuộc tính đó.

## 3. compare trả 0 nghĩa là cùng khóa trong TreeMap

Với comparator `c`:

```text
c.compare(k1, k2) < 0  -> k1 đứng trước k2
c.compare(k1, k2) > 0  -> k1 đứng sau k2
c.compare(k1, k2) == 0 -> k1 và k2 tương đương trong TreeMap
```

Khi `put(k2, value2)` gặp một khóa đã có và so sánh bằng 0:

- Map không tăng số ánh xạ vì coi đó là cùng khóa.
- Giá trị cũ bị thay bằng giá trị mới.
- `put` trả giá trị cũ, có thể là null theo hợp đồng map.

Điều này khác kỳ vọng “hai đối tượng khác nhau thì chắc chắn là hai khóa”. Tính khác nhau theo địa chỉ đối tượng, hoặc riêng `equals`, không đủ để làm hai khóa có kết quả so sánh 0 cùng tồn tại trong một `TreeMap`.

Thứ tự cần nhất quán với `equals` để tuân thủ đầy đủ hợp đồng của `Map`: so sánh bằng 0 đúng khi hai khóa bằng nhau theo `equals`. Hợp đồng comparator được mô tả tại [Comparator](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Comparator.html).

Một comparator không nhất quán với `equals` vẫn có thể cho hành vi cây xác định, nhưng cấu trúc không còn đáp ứng đầy đủ kỳ vọng chung của map dựa trên sự bằng nhau. Đây là lỗi thiết kế cần hiểu rõ, không phải mẹo gộp dữ liệu mặc định.

## 4. Thiết kế khóa ghép theo đúng danh tính và thứ tự

Với sự kiện, giả sử khóa được định nghĩa bởi cặp:

```text
(thời điểm, mã sự kiện)
```

Có thể dùng record bất biến gồm cả hai thành phần, rồi so sánh theo thời điểm trước, mã sau.

- Khác thời điểm: thời điểm quyết định thứ tự.
- Cùng thời điểm nhưng khác mã: mã phân biệt hai khóa.
- Cùng thời điểm và cùng mã: cùng khóa, giá trị mới thay giá trị cũ.

Tiêu chí phụ không chỉ “làm thứ tự đẹp hơn”: nó thay đổi trường hợp nào comparator trả 0. Phải chọn tiêu chí phụ theo mô hình dữ liệu.

Nếu danh tính nghiệp vụ thực sự chỉ là mã sự kiện và thời điểm có thể sửa, không được mặc định khóa ghép này là mô hình thích hợp. Có thể cần một map chính theo mã và một chỉ mục thời gian riêng được duy trì có chủ đích.

Trường hợp chỉ cần nhóm sự kiện theo thời gian thường có thể dùng `NavigableMap<Instant, List<Event>>`: thời điểm là khóa, danh sách là các sự kiện cùng thời điểm. Mô hình ấy giữ các sự kiện trùng mốc mà không buộc truy vấn thời gian phải mang thêm mã.

## 5. Chương trình Java: comparator thiếu tiêu chí và khóa ghép đầy đủ

Chương trình cố ý tạo comparator chỉ theo thời điểm để quan sát việc hai khóa khác nhau bị coi là trùng. Sau đó dùng comparator theo đủ hai thành phần.

Lưu tệp `TreeMapKeyDemo.java`:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.Comparator;
import java.util.NavigableMap;
import java.util.Objects;
import java.util.TreeMap;

public class TreeMapKeyDemo {
    record EventKey(Instant at, String id) {
        EventKey {
            Objects.requireNonNull(at);
            Objects.requireNonNull(id);
        }
    }

    public static void main(String[] args) {
        Instant at = Instant.parse("2026-01-01T10:00:00Z");
        EventKey first = new EventKey(at, "E1");
        EventKey second = new EventKey(at, "E2");
        EventKey later = new EventKey(at.plusSeconds(60), "E3");

        Comparator<EventKey> byTime =
                Comparator.comparing(EventKey::at);
        System.out.println("different.keys.equals="
                + first.equals(second));
        System.out.println("time.only.compare="
                + byTime.compare(first, second));

        NavigableMap<EventKey, String> coarse =
                new TreeMap<>(byTime);
        coarse.put(first, "sensor-A");
        String replaced = coarse.put(second, "sensor-B");
        System.out.println("time.only.previous=" + replaced);
        System.out.println("time.only.size=" + coarse.size());
        System.out.println("time.only.get.E1=" + coarse.get(first));

        Comparator<EventKey> byTimeAndId =
                byTime.thenComparing(EventKey::id);
        NavigableMap<EventKey, String> events =
                new TreeMap<>(byTimeAndId);
        events.put(later, "sensor-C");
        events.put(second, "sensor-B");
        events.put(first, "sensor-A");

        System.out.println("complete.size=" + events.size());
        System.out.println("complete.ids="
                + events.navigableKeySet().stream()
                        .map(EventKey::id).toList());
        System.out.println("complete.higher.E1="
                + events.higherKey(first).id());
        System.out.println("complete.floor.E1="
                + events.floorKey(new EventKey(at, "E1")).id());
        System.out.println("complete.replace="
                + events.put(new EventKey(at, "E1"), "sensor-A2"));
        System.out.println("complete.size.after.replace="
                + events.size());

        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");
        System.out.println("decimal.equals=" + a.equals(b));
        System.out.println("decimal.compare=" + a.compareTo(b));

        NavigableMap<BigDecimal, String> decimals = new TreeMap<>();
        decimals.put(a, "A");
        System.out.println("decimal.previous=" + decimals.put(b, "B"));
        System.out.println("decimal.size=" + decimals.size());
        System.out.println("decimal.get=" + decimals.get(a));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 TreeMapKeyDemo.java
java TreeMapKeyDemo
```

Stdout:

```text
different.keys.equals=false
time.only.compare=0
time.only.previous=sensor-A
time.only.size=1
time.only.get.E1=sensor-B
complete.size=3
complete.ids=[E1, E2, E3]
complete.higher.E1=E2
complete.floor.E1=E1
complete.replace=sensor-A
complete.size.after.replace=3
decimal.equals=false
decimal.compare=0
decimal.previous=A
decimal.size=1
decimal.get=B
```

Các điểm cần đối chiếu:

1. `first` và `second` không bằng nhau theo quy tắc của record vì khác mã, nhưng comparator chỉ theo thời điểm trả 0.
2. Map `coarse` chỉ còn một ánh xạ; tra bằng `first` nhận giá trị sensor-B vì khóa được nhận diện theo comparator.
3. Comparator đủ thời điểm và mã giữ cả ba sự kiện; dữ liệu được duyệt E1, E2, E3 dù thứ tự chèn khác.
4. Thêm một khóa mới có cùng hai thành phần với E1 cập nhật giá trị mà không tăng kích thước.
5. Trong map khóa ghép, `higherKey(first)` có thể trả E2 ở cùng thời điểm, vì thứ tự còn có thành phần mã.

## 6. BigDecimal: thứ tự tự nhiên cũng cần được kiểm tra

Không chỉ comparator tự viết mới có thể khác `equals`. `BigDecimal("1.0")` và `BigDecimal("1.00")` có cùng giá trị số nhưng khác số chữ số thập phân được biểu diễn (scale).

- `compareTo` coi hai giá trị số này bằng nhau.
- `equals` đòi hỏi cả giá trị số và biểu diễn phù hợp, nên trả false.
- `TreeMap` dùng thứ tự tự nhiên sẽ coi chúng là cùng một khóa.

Đây là hành vi được mô tả rõ trong [BigDecimal](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/math/BigDecimal.html).

Cần quyết định ứng dụng muốn phân biệt điều gì:

- Nếu hai cách biểu diễn thực sự là cùng một khóa nghiệp vụ, chuẩn hóa dữ liệu khóa theo một quy ước thống nhất.
- Nếu scale là thông tin phân biệt có ý nghĩa, thiết kế khóa và comparator có tính đến điều đó.
- Không suy luận từ kết quả của một cấu trúc dựa trên `equals/hashCode` rằng `TreeMap` sẽ nhận diện khóa y hệt.

Ví dụ trong chương trình chỉ minh họa hợp đồng so sánh của kiểu số, không đề xuất mặc định lấy một đại lượng bất kỳ làm khóa.

## 7. Khóa ghép làm thay đổi cách truy vấn

`floorEntry(new EventKey(time, id))` tìm theo toàn bộ cặp có thứ tự, không phải “bất kỳ sự kiện nào gần thời điểm time”.

Trong ví dụ, khi thời điểm bằng nhau, mã vẫn tham gia quyết định phần tử đứng trước/sau. Vì vậy một truy vấn chỉ biết thời gian nhưng không có mã chưa tự nhiên trở thành một truy vấn khóa ghép hoàn chỉnh.

Trước khi chọn khóa, hãy liệt kê các truy vấn chính:

| Yêu cầu chính | Hướng mô hình |
| --- | --- |
| Mỗi mốc chỉ giữ một giá trị cấu hình hiện hành | Map theo thời điểm |
| Giữ nhiều bản ghi trong một mốc và tra cứu theo mốc | Map theo thời điểm, giá trị là nhóm bản ghi |
| Duyệt và tra cứu theo cặp thời điểm/mã | Map dùng khóa ghép đúng định nghĩa |
| Tra cứu duy nhất theo mã, thời điểm chỉ là thuộc tính | Map theo mã; chỉ mục thời gian nếu thực sự cần |
| Chỉ cần trình bày dữ liệu theo một thứ tự khác | Xem xét sắp xếp một bản kết quả thay vì đổi danh tính khóa |

Không tự chọn một chuỗi “cực nhỏ” hoặc “cực lớn” làm mã giả rồi coi đó là biên tổng quát cho mọi dữ liệu. Nếu cần truy vấn theo từng thành phần, hãy thiết kế hợp đồng biên hoặc cấu trúc dữ liệu biểu đạt điều kiện ấy rõ ràng.

## 8. Giữ phép so sánh ổn định và đúng

### Không sửa thuộc tính khóa khi khóa đang nằm trong cây

Nếu khóa có thể thay đổi và trường tham gia comparator bị sửa, cây không tự di chuyển ánh xạ đến vị trí mới. Tra cứu và duyệt có thể không còn phù hợp với quy tắc thứ tự.

Ví dụ dùng `Instant` và `String` trong record: các thành phần này bất biến, phù hợp để giữ khóa ổn định. Record chỉ bảo vệ việc gán lại thành phần; nếu thành phần là đối tượng có thể thay đổi thì vẫn phải xem xét trạng thái của đối tượng đó.

Khi nghiệp vụ cần đổi khóa, loại ánh xạ theo khóa cũ trước rồi thêm bằng khóa mới, đồng thời xử lý việc khóa mới có thể đã tồn tại.

### Không để comparator phụ thuộc vào trạng thái thay đổi ngoài map

Một comparator đọc ưu tiên từ một bảng bên ngoài rồi bảng ấy thay đổi có thể làm cùng hai khóa đổi quan hệ thứ tự mà cây không được tổ chức lại.

Tương tự, không cố sắp khóa bằng cách đọc giá trị đang thay đổi trong chính map. Cần tách danh tính khóa, tiêu chí chỉ mục và dữ liệu cập nhật.

### Không dùng phép trừ thay cho so sánh số nguyên

Với hai khóa hoặc trường kiểu `int`, biểu thức `a - b` có thể tràn và trả dấu sai. Dùng `Integer.compare(a,b)` hoặc `Comparator.comparingInt(...)`.

Với nhiều tiêu chí, dùng `thenComparing` sau tiêu chí chính. Không trả số ngẫu nhiên hoặc kết quả tùy thời điểm chỉ để “phân biệt hai khóa”; comparator phải tuân thủ tính nhất quán và bắc cầu.

### Quy định rõ null

`TreeMap` dùng thứ tự tự nhiên không chấp nhận khóa null. Comparator có thể được thiết kế để xử lý null, nhưng nên chọn hợp đồng dữ liệu có chủ đích.

Trong ví dụ, constructor của `EventKey` từ chối thành phần null. Nhờ vậy comparator có thể so sánh trực tiếp mà không phải đoán cách xếp một thời điểm hoặc mã bị thiếu.

## 9. Tự kiểm tra

1. Comparator chỉ theo độ dài chuỗi có giữ được cả "AB" và "CD" làm hai khóa khác nhau trong TreeMap không?
2. Vì sao thay `hashCode` không giải quyết việc hai khóa có compare bằng 0?
3. Nếu ứng dụng cần tất cả sự kiện cùng thời điểm, vì sao chỉ dùng `Map<Instant,Event>` có thể mất dữ liệu?
4. Comparator theo thời điểm rồi mã có phù hợp nếu ứng dụng xem mã là danh tính duy nhất và thời điểm thay đổi được không?
5. Nêu hai điều phải kiểm tra trước khi chọn một kiểu khóa có sẵn.

Định hướng: (1) không, độ dài bằng nhau làm comparator trả 0; (2) cây nhận diện khóa bằng phép so sánh; (3) mỗi khóa chỉ giữ một ánh xạ; (4) cần xem lại mô hình và các chỉ mục; (5) ý nghĩa thứ tự và sự nhất quán giữa so sánh với sự bằng nhau, kèm tính ổn định của khóa.

Một khóa phù hợp phải vừa phân biệt đúng bản ghi, vừa phục vụ thứ tự truy vấn, vừa giữ quy tắc so sánh ổn định trong suốt thời gian nằm trong map.
