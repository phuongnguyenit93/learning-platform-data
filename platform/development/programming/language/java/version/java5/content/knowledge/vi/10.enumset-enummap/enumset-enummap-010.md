# Chi phí và tiêu chí chọn EnumMap so với Map thông thường

## 1. Khái niệm: Map là giao diện, EnumMap là một triển khai

`EnumMap` không đứng ngoài họ `Map`. Nó là một triển khai chuyên dụng khi toàn bộ khóa thuộc cùng một kiểu enum.

```java
// Minh họa; cần import EnumMap và Map, cùng khai báo Mode tương ứng.
Map<Mode, Integer> limits = new EnumMap<>(Mode.class);
```

Kiểu biến là `Map`, nhưng đối tượng thật sự vẫn là `EnumMap`. Khai báo qua giao diện không làm nó đổi sang một cấu trúc băm tổng quát.

Vì vậy, câu hỏi thực tế là: với yêu cầu dữ liệu và tải sử dụng cụ thể, nên chọn `EnumMap`, `HashMap`, `LinkedHashMap`, `TreeMap` hay một cấu trúc khác?

Không có một lựa chọn thắng mọi tiêu chí. Trước hết phải xác định đúng miền khóa và hợp đồng hành vi, sau đó mới so sánh chi phí.

Các API và nguyên tắc trong bài vẫn áp dụng trong Java hiện đại. Ví dụ chạy trên Java 17 trở lên; một số chi tiết chi phí được giải thích theo mã nguồn OpenJDK 21 và được ghi rõ ở phần tương ứng.

## 2. Lợi thế cấu trúc của EnumMap

Khi kiểu khóa là enum, thư viện biết trước toàn bộ miền khóa. Trong triển khai OpenJDK 21, `EnumMap` có một mảng các vị trí giá trị tương ứng với miền enum.

Một khóa enum giúp xác định trực tiếp vị trí liên quan, thay vì cần tìm một entry bằng cơ chế bảng băm tổng quát.

Điều này tạo ra các lợi thế thường gặp:

- Cấu trúc chuyên dụng, nhỏ gọn cho một miền enum phù hợp.
- Các thao tác tra cứu, thêm/thay và xóa một khóa có đường truy cập trực tiếp.
- Không phải quản lý node băm cho từng ánh xạ theo cách của một map băm thông thường.
- Thứ tự duyệt theo thứ tự khai báo hằng enum đã được bảo đảm bởi API.

Đây là lý do `EnumMap` thường là một điểm xuất phát phù hợp khi bài toán thật sự là ánh xạ từ một enum. Nó không phải bằng chứng rằng mọi thao tác trong mọi tải sử dụng đều nhanh hơn một triển khai khác.

## 3. Theo dõi hai kích thước: miền khóa k và số ánh xạ n

Để phân tích chi phí, đặt:

- `k`: tổng số hằng của kiểu enum.
- `n`: số ánh xạ hiện có trong một map.

Luôn có `0 <= n <= k`, nhưng hai đại lượng không nhất thiết gần nhau.

Ví dụ giả định một enum có 1.000 hằng, nhưng mỗi map chỉ dùng 3 khóa. Khi đó `k = 1000`, `n = 3`: map rất thưa so với miền khóa.

Trong triển khai đã nêu, mảng giá trị của mỗi `EnumMap` có số vị trí theo `k`, không chỉ theo `n`:

```text
Miền enum:   K0 K1 K2 K3 K4 K5 K6 K7
Map thưa:     -  V  -  -  -  -  V  -
Map dày:      V  V  V  V  V  V  V  V

Cả hai cùng miền khóa; số ánh xạ thực tế khác nhau.
```

Dấu `-` trong hình chỉ vị trí chưa có ánh xạ, không phải một giá trị mà ứng dụng truy cập trực tiếp.

Nếu có rất nhiều map sống cùng lúc, chi phí các mảng vị trí theo miền enum có thể trở nên đáng kể. Không nên chỉ nhìn `size() = 3` rồi suy ra mỗi map chỉ cần cấu trúc cho ba vị trí.

Ngược lại, nếu enum nhỏ hoặc các map dùng phần lớn miền, biểu diễn trực tiếp thường rất phù hợp.

## 4. Chi phí thời gian: tách thao tác đơn lẻ khỏi vòng đời map

Với kiểu enum cố định, nhiều thao tác cơ bản của `EnumMap` có chi phí hằng số. Nhưng để so sánh các miền enum lớn nhỏ khác nhau, cần nhìn thêm những thao tác xử lý mảng theo `k`.

Theo cấu trúc OpenJDK 21 được đối chiếu:

| Hoạt động | Điểm chi phí cần xét |
| --- | --- |
| `get`, `put`, `remove` một khóa phù hợp | Truy cập vị trí liên quan; không cần quét toàn miền |
| Tạo một map rỗng với kiểu enum | Cần mảng giá trị theo miền khóa |
| Sao chép từ một EnumMap | Sao chép mảng vị trí, kể cả các vị trí chưa có ánh xạ |
| `clear()` | Làm rỗng các vị trí của mảng giá trị |
| Duyệt toàn bộ map | Iterator có thể phải đi qua các vị trí trống trong miền enum |

Nếu coi `k` là một đại lượng thay đổi giữa các kiểu enum đang so sánh, việc cấp phát/khởi tạo mảng, sao chép mảng, làm rỗng hoặc quét miền có thể mang chi phí theo `k`. Nếu xét riêng một kiểu enum cố định, `k` là cố định đối với số ánh xạ `n`; hai cách mô tả không mâu thuẫn.

Bài học thực tế: một map được tạo một lần rồi tra cứu rất nhiều lần có hồ sơ chi phí khác với hàng triệu map thưa được tạo, sao chép và bỏ đi liên tục.

Không chỉ benchmark `get` rồi suy ra kết luận cho cả vòng đời ứng dụng.

## 5. Chi phí bộ nhớ so với HashMap

Một cách so sánh định tính:

| Khía cạnh | EnumMap trong triển khai đang xét | HashMap |
| --- | --- | --- |
| Miền khóa | Một kiểu enum | Kiểu khóa tổng quát phù hợp với khai báo |
| Cấu trúc chính | Mảng vị trí theo miền enum | Bảng bucket và các entry theo triển khai |
| Yếu tố cần theo dõi | `k`, số đối tượng map, dữ liệu giá trị | `n`, capacity, dữ liệu entry và giá trị |
| Trạng thái thưa | Vẫn có các vị trí cho miền enum | Phụ thuộc cách cấp sức chứa và số ánh xạ |
| Dữ liệu ứng dụng V | Vẫn có thể là các đối tượng tốn bộ nhớ | Cũng phải tính cùng dữ liệu V |

Không thể kết luận bằng một con số “mỗi entry tiết kiệm X byte” cho mọi JVM. Kích thước tham chiếu, cấu trúc đối tượng, cấu hình JVM và cách chia sẻ dữ liệu đều ảnh hưởng.

Cũng không cộng toàn bộ bộ nhớ của hằng enum như thể mỗi map tạo lại mọi khóa. Các hằng đã thuộc kiểu enum; chi phí cấu trúc của từng map và chi phí các đối tượng giá trị là những phần cần tách riêng.

Một enum rất lớn với nhiều map rất thưa là tình huống đáng đo thay vì áp dụng máy móc “khóa enum thì luôn tối ưu mọi mặt”. Việc có thể chọn `HashMap` trong trường hợp đó là một giả thuyết kỹ thuật cần đối chiếu với tải thật, không phải một kết luận về số byte đã được đo trong bài.

## 6. So sánh hợp đồng hành vi trước khi so tốc độ

| Yêu cầu | EnumMap | HashMap |
| --- | --- | --- |
| Kiểu khóa | Các hằng của một enum đã xác định | Khóa tổng quát theo kiểu khai báo |
| Khóa null | Không cho thêm | Cho phép |
| Giá trị null | Cho phép | Cho phép |
| Thứ tự duyệt | Thứ tự khai báo hằng enum | Không bảo đảm |
| Thao tác cơ bản | Cấu trúc chuyên biệt cho miền enum | Hiệu quả hằng số với giả định phân bố băm phù hợp |
| Tự đồng bộ nhiều luồng | Không | Không |

`HashMap` không có một thứ tự duyệt ổn định được API bảo đảm. Nếu ứng dụng đang dùng thứ tự khai báo enum để hiển thị, thay bằng `HashMap` có thể làm mất một phần hợp đồng dù các cặp khóa–giá trị vẫn bằng nhau.

`HashMap` cũng không có nghĩa mọi thao tác đều có chi phí chỉ theo `n`. Tài liệu API mô tả thời gian duyệt theo capacity cộng với số ánh xạ; một cấu hình sức chứa quá lớn có thể làm việc duyệt kém hơn mong đợi.

Không so một `EnumMap` cung cấp đúng thứ tự yêu cầu với một `HashMap` rồi bỏ qua chi phí sắp xếp bổ sung mà ứng dụng phải làm để có cùng đầu ra.

## 7. Khi cần thứ tự khác hoặc khả năng khác

### Thứ tự chèn

Nếu yêu cầu là giữ thứ tự các khóa được thêm vào, `LinkedHashMap` thường diễn đạt đúng hơn. `EnumMap` không đổi thứ tự duyệt chỉ vì chương trình chèn hằng theo một thứ tự khác.

### Thứ tự tùy biến và truy vấn có thứ tự

Nếu cần một comparator riêng hoặc các khả năng của map có thứ tự như tìm khóa gần nhất, xem xét `TreeMap`. Nó cung cấp các thao tác cây với chi phí logarit cho những thao tác cơ bản được API quy định.

Với khóa enum, thứ tự tự nhiên của `TreeMap` cũng theo thứ tự enum; nếu cần thứ tự chữ cái hoặc quy tắc khác, phải cung cấp comparator phù hợp. Không dùng cấu trúc cây chỉ để tái tạo một thứ tự mà `EnumMap` đã có nếu không cần khả năng bổ sung.

### Truy cập đồng thời

Không thay `EnumMap` bằng `HashMap` rồi cho rằng đã giải quyết truy cập đồng thời; cả hai không tự đồng bộ.

Một lựa chọn như `ConcurrentHashMap` có hợp đồng thao tác đồng thời riêng, nhưng không bảo đảm thứ tự enum và không cho khóa/giá trị `null`. Hoặc ứng dụng có thể giữ `EnumMap` sau một cơ chế phối hợp phù hợp với toàn bộ thao tác cần bảo đảm.

Chọn cấu trúc theo những yêu cầu ấy trước; không lấy một phép đo đơn luồng để quyết định thay thế hợp đồng đồng thời.

### Chỉ đọc sau khi khởi tạo

Nếu muốn công khai một ảnh chụp không cho sửa, có thể sao chép và bọc:

```java
// Minh họa; cần import Collections, EnumMap và Map.
// enumMap ở đây có kiểu EnumMap<Mode, Integer>.
Map<Mode, Integer> snapshot =
        Collections.unmodifiableMap(new EnumMap<>(enumMap));
```

Bản sao tạo chi phí riêng; wrapper và sao chép dữ liệu không phải cùng một thao tác. Các đối tượng giá trị bên trong vẫn là tham chiếu được sao chép, không tự trở thành bản sao sâu.

## 8. Một quy trình lựa chọn thực dụng

1. **Xác định miền khóa.** Nếu khóa không thuộc một enum phù hợp, loại `EnumMap` khỏi lựa chọn.
2. **Ghi các yêu cầu bắt buộc.** Thứ tự, `null`, truy cập đồng thời, khả năng sửa đổi và truy vấn có thứ tự.
3. **Xem hình dạng dữ liệu.** Tổng hằng `k`, số ánh xạ `n`, mật độ dùng khóa và số map cùng sống.
4. **Xem tải thao tác.** Chủ yếu tra cứu hay chủ yếu tạo/copy/clear/duyệt?
5. **Chọn cấu trúc có hợp đồng rõ nhất.** Với enum nhỏ và thứ tự khai báo phù hợp, `EnumMap` thường là lựa chọn tự nhiên.
6. **Đo nếu chi phí có ý nghĩa với yêu cầu.** Tập trung vào phần tải quyết định, không chỉ một thao tác thuận lợi.
7. **Giữ ranh giới giao diện phù hợp.** Có thể trả về `Map<K,V>` khi người gọi không cần API đặc thù, nhưng vẫn phải mô tả những bảo đảm như thứ tự hoặc khả năng sửa đổi nếu chúng quan trọng.

Không cần viết một lớp chọn map động cho mọi enum chỉ để chuẩn bị cho một tối ưu chưa được chứng minh. Một lựa chọn trực tiếp, đúng hợp đồng và dễ đọc thường là điểm xuất phát tốt.

## 9. Chương trình so sánh hành vi, không phải benchmark

Lưu vào `EnumMapChoiceDemo.java`:

```java
import java.util.Comparator;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;

public class EnumMapChoiceDemo {
    enum Mode {
        BATCH,
        INTERACTIVE,
        BACKGROUND
    }

    static void populate(Map<Mode, Integer> map) {
        map.put(Mode.INTERACTIVE, 20);
        map.put(Mode.BACKGROUND, 30);
        map.put(Mode.BATCH, 10);
    }

    public static void main(String[] args) {
        EnumMap<Mode, Integer> enumMap = new EnumMap<>(Mode.class);
        HashMap<Mode, Integer> hashMap = new HashMap<>();
        LinkedHashMap<Mode, Integer> linkedMap = new LinkedHashMap<>();
        TreeMap<Mode, Integer> sortedMap =
                new TreeMap<>(Comparator.comparing(Mode::name));

        populate(enumMap);
        populate(hashMap);
        populate(linkedMap);
        populate(sortedMap);

        System.out.println("enumKeys=" + enumMap.keySet());
        System.out.println("linkedKeys=" + linkedMap.keySet());
        System.out.println("sortedKeys=" + sortedMap.keySet());
        System.out.println("sameMappings=" + enumMap.equals(hashMap));
        System.out.println("lookup=" + enumMap.get(Mode.BATCH));

        hashMap.put(null, 99);
        System.out.println("hashAllowsNull=" + hashMap.containsKey(null));

        try {
            enumMap.put(null, 99);
        } catch (NullPointerException ex) {
            System.out.println("enumRejectsNull");
        }

        Map<Mode, Integer> throughInterface = enumMap;
        System.out.println("implementation="
                + throughInterface.getClass().getSimpleName());

        EnumMap<Mode, Integer> sparse = new EnumMap<>(Mode.class);
        sparse.put(Mode.BATCH, 10);
        System.out.println("domain=" + Mode.values().length
                + ", mappings=" + sparse.size());

        EnumMap<Mode, Integer> copy = new EnumMap<>(enumMap);
        copy.remove(Mode.INTERACTIVE);
        System.out.println("originalSize=" + enumMap.size()
                + ", copySize=" + copy.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 EnumMapChoiceDemo.java
java EnumMapChoiceDemo
```

Stdout chính xác:

```text
enumKeys=[BATCH, INTERACTIVE, BACKGROUND]
linkedKeys=[INTERACTIVE, BACKGROUND, BATCH]
sortedKeys=[BACKGROUND, BATCH, INTERACTIVE]
sameMappings=true
lookup=10
hashAllowsNull=true
enumRejectsNull
implementation=EnumMap
domain=3, mappings=1
originalSize=3, copySize=2
```

Điều chương trình chứng minh:

- Cùng dữ liệu ánh xạ không có nghĩa cùng thứ tự duyệt.
- `EnumMap` dùng thứ tự khai báo, `LinkedHashMap` dùng thứ tự chèn trong cấu hình mặc định ở đây, `TreeMap` dùng comparator đã cung cấp.
- Kiểu giao diện `Map` không đổi đối tượng thực tế.
- Kích thước miền khóa khác với số ánh xạ đang có.
- Sao chép tạo cấu trúc map riêng.
- Hợp đồng khóa `null` của hai triển khai khác nhau.

Chương trình cố ý không in thứ tự khóa của `HashMap` như một kết quả kỳ vọng được bảo đảm. Nó cũng không đo thời gian hoặc bộ nhớ, nên không chứng minh một hệ số nhanh/chậm hay một số byte tiết kiệm.

## 10. Nếu cần đo hiệu năng, đo đúng câu hỏi

Một phép đo đơn lẻ bằng `System.nanoTime()` quanh một vòng lặp rất ngắn dễ bị ảnh hưởng bởi khởi động JVM, biên dịch JIT, tối ưu loại bỏ công việc, cấp phát và thu gom rác.

Khi cần bằng chứng hiệu năng, có thể dùng một công cụ tổ chức phép đo như JMH và thiết kế các trường hợp tách biệt:

| Trường hợp đo | Câu hỏi |
| --- | --- |
| Map đã tạo, liên tục get khóa có/không có | Chi phí tra cứu trong tải ổn định |
| Tạo nhiều map rồi bỏ đi | Chi phí cấp phát và vòng đời |
| Sao chép hoặc clear thường xuyên | Chi phí xử lý cấu trúc theo miền |
| Duyệt map thưa và dày | Ảnh hưởng của `k`, `n` và capacity |
| Nhiều map sống đồng thời | Dấu chân bộ nhớ của toàn bộ tải |
| Yêu cầu đầu ra có thứ tự | Chi phí bao gồm những bước cần để đáp ứng cùng hợp đồng |

Giữ dữ liệu, giá trị `V`, số thao tác và yêu cầu đầu ra tương đương giữa các lựa chọn. Nếu một phương án cần sắp xếp bổ sung, đừng loại bước đó khỏi phép đo rồi kết luận nó rẻ hơn cho cùng chức năng.

Ghi rõ JDK, cấu hình chạy, cách khởi động nóng, số lần lặp và cách sử dụng kết quả để tránh tối ưu xóa mất công việc. Phân biệt số đo thu được với suy luận từ cấu trúc dữ liệu.

Bài này cung cấp mô hình phân tích và ví dụ hợp đồng; không đưa ra một kết quả benchmark thực nghiệm.

## 11. Tự kiểm tra

1. Vì sao `Map<Mode, Integer> m = new EnumMap<>(Mode.class)` vẫn có chi phí cấu trúc của `EnumMap`?
2. Với enum có rất nhiều hằng nhưng mỗi map dùng vài khóa, cần theo dõi thêm đại lượng nào ngoài `size()`?
3. Vì sao chỉ đo `get` không đủ để quyết định cho một tải tạo và sao chép rất nhiều map?
4. Nếu cần thứ tự chèn, vì sao `EnumMap` không thay thế trực tiếp `LinkedHashMap`?
5. Nếu dùng `HashMap` thay `EnumMap`, tại sao không được giữ một stdout thứ tự khóa cố định làm hợp đồng?
6. Nếu phải chia sẻ có ghi giữa nhiều luồng, vì sao cả `EnumMap` và `HashMap` thông thường đều chưa giải quyết xong yêu cầu?
7. Đề xuất bộ trường hợp đo cho một bảng cấu hình enum nhỏ tạo một lần, rồi so sánh với một hệ thống tạo nhiều bảng thưa trong thời gian ngắn.
8. Một nhận định “EnumMap luôn dùng ít bộ nhớ hơn” thiếu những dữ liệu nào để đánh giá?

## Tài liệu đối chiếu

- [Java API — EnumMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumMap.html): cấu trúc chuyên dụng, thứ tự và hợp đồng.
- [OpenJDK 21 — EnumMap implementation](https://github.com/openjdk/jdk21u/blob/master/src/java.base/share/classes/java/util/EnumMap.java): mảng giá trị theo miền, sao chép, clear và iterator.
- [Java API — HashMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/HashMap.html): giả định hiệu năng, capacity và chi phí duyệt.
- [Java API — LinkedHashMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/LinkedHashMap.html): thứ tự chèn trong cấu hình thông thường.
- [Java API — TreeMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeMap.html): thứ tự/comparator và chi phí logarit.
- [Java API — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): hợp đồng truy cập đồng thời và giới hạn null.
- [OpenJDK — JMH](https://github.com/openjdk/jmh): bộ công cụ đo hiệu năng trên JVM.
