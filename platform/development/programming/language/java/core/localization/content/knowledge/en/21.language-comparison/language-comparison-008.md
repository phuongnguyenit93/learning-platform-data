# Comparator không nhất quán với equals trong TreeSet hoặc TreeMap

## 1. Bài toán: so sánh ngôn ngữ khác với định danh dữ liệu

Một ứng dụng đa ngôn ngữ cần sắp xếp các nhãn theo thứ tự tự nhiên đối với người đọc, chẳng hạn dùng `java.text.Collator` để xếp từ có dấu. Một ứng dụng khác lại cần lưu từng chuỗi như một **khóa định danh riêng**, dù chúng chỉ khác chữ hoa/thường hay dấu.

Hai nhu cầu đó không đồng nghĩa:

- **Tương đương theo ngôn ngữ:** một `Collator` ở mức `PRIMARY` có thể trả `0` khi so sánh `"cafe"` và `"café"`.
- **Bằng nhau theo `String.equals`:** `"cafe".equals("café")` trả `false` vì dãy UTF-16 code unit khác nhau.
- **Bằng nhau theo khóa của `TreeSet`/`TreeMap`:** dựa trên `Comparator.compare(a,b)==0`, **không nhất thiết dựa trên `equals`**.

Điểm cuối cực kỳ quan trọng. Khi dùng `TreeSet` để “vừa sắp xếp vừa loại trùng”, bạn đang cho comparator quyền quyết định **trùng** là gì. Khi dùng `TreeMap`, comparator quyết định một lần `put` là **tạo khóa mới** hay **cập nhật value của khóa cũ**.

### Mục tiêu bài học

Sau khi học, người đọc có thể:

1. Mô tả quy tắc `compare(a,b)==0` và điều kiện *consistent with equals*.
2. Giải thích vì sao `HashSet` và `TreeSet` có thể giữ số phần tử khác nhau từ cùng một dãy chuỗi.
3. Tái hiện việc `TreeSet.add` trả false, `contains` trả true và `remove` xóa một spelling khác.
4. Tái hiện `TreeMap.put` ghi đè value và hiểu lý do key được giữ lại.
5. Phân biệt mục tiêu **collation equivalence** với mục tiêu **Object/String identity**.
6. Dùng tie-breaker đúng, hoặc thiết kế data model tách ID và nhãn hiển thị.
7. Phát hiện comparator sai contract và nguy cơ thay đổi `Collator` khi cây đã chứa dữ liệu.
8. Viết test đủ các trường hợp dấu, case, chuẩn hóa Unicode, locale và tính bắc cầu.

## 2. Comparator.compare và Object.equals: hai quan hệ khác nhau

### 2.1. equals trả lời câu hỏi gì?

Với `String`, `equals(Object)` xác nhận hai chuỗi có cùng nội dung theo các UTF-16 code unit. Ví dụ:

```java
System.out.println("cafe".equals("café")); // false
System.out.println("CAFE".equals("cafe")); // false
```

Các câu lệnh đặt trong một phương thức Java. `HashSet<String>` và `HashMap<String,V>` dùng `hashCode` và `equals` để xác định trùng, nên sẽ giữ ba key `"cafe"`, `"café"` và `"CAFE"` riêng biệt.

### 2.2. compare trả lời câu hỏi gì?

`java.util.Comparator<T>` trả một số nguyên:

| Kết quả | Ý nghĩa |
| --- | --- |
| `compare(a,b)<0` | `a` đứng trước `b` theo thứ tự đã định nghĩa. |
| `compare(a,b)==0` | `a` và `b` tương đương theo thứ tự đã định nghĩa. |
| `compare(a,b)>0` | `a` đứng sau `b` theo thứ tự đã định nghĩa. |

Giá trị trả **không bắt buộc** đúng `-1`, `0` hoặc `1`. So sánh dấu của nó khi viết test, không giả định mọi comparator chỉ trả một trong ba hằng ấy.

Một comparator hợp lệ cần bảo đảm các tính chất:

- **Phản xạ theo quan hệ thứ tự:** `compare(a,a)==0`.
- **Đổi dấu:** `sgn(compare(a,b)) == -sgn(compare(b,a))`.
- **Bắc cầu:** nếu `compare(a,b)>0` và `compare(b,c)>0` thì `compare(a,c)>0`.
- **Lớp tương đương nhất quán:** nếu `compare(a,b)==0`, thứ tự của `a` và `b` so với mọi `z` phải có cùng dấu.

Những điều kiện này khác với việc comparator có nhất quán với `equals` không. Một `Collator` có thể là comparator hợp lệ nhưng vẫn gọi hai String không `equals` là tương đương theo ngôn ngữ.

### 2.3. “Consistent with equals” chính xác là gì?

Một thứ tự được xem là **nhất quán với equals** nếu với mọi cặp phần tử trong miền:

```text
compare(a, b) == 0  ⇔  a.equals(b)
```

Tức đồng thời:

1. Nếu hai phần tử `equals` thì comparator phải trả 0.
2. Nếu comparator trả 0 thì hai phần tử phải `equals`.

Với `String`, `String.compareTo` nhất quán với `String.equals`. Với `Collator` ở mức làm lỏng phân biệt dấu và case, điều này **không được đảm bảo**.

Không nhất quán với equals không nhất thiết làm comparator **không hợp lệ**; nó thay đổi ý nghĩa của việc lưu và tìm phần tử trong những sorted collections dùng comparator.

## 3. TreeSet: phần tử khác nhau có thể bị coi là trùng

`TreeSet` lưu phần tử theo **natural ordering** hoặc comparator đưa vào constructor. Khi comparator trả 0 giữa phần tử mới và phần tử đã có, `TreeSet` xem chúng là trùng.

Ví dụ:

```java
Collator collator = Collator.getInstance(Locale.FRENCH);
collator.setStrength(Collator.PRIMARY);

TreeSet<String> set = new TreeSet<>(collator);
System.out.println(set.add("cafe")); // true
System.out.println(set.add("café")); // false
System.out.println(set.add("CAFE")); // false
System.out.println(set.size());      // 1
```

Đây là đoạn minh họa trong một phương thức Java với import `Collator`, `Locale` và `TreeSet`.

`PRIMARY` trong môi trường minh họa cho ba spelling bằng nhau theo thứ tự Collator. Nhưng `String.equals` phân biệt cả ba. Do đó, chỉ phần tử được thêm lần đầu được lưu; hai lần `add` tiếp theo **trả false**.

### contains và remove cũng theo comparator

```java
System.out.println(set.contains("CAFE")); // true
System.out.println(set.remove("café"));   // true
System.out.println(set.size());           // 0
```

`set.contains("CAFE")` trả true ngay cả khi trong tập chỉ có string `"cafe"`. Tương tự, `remove("café")` có thể xóa phần tử `"cafe"` đang lưu.

Điều này làm API **trông như mâu thuẫn** với việc so sánh bằng `equals` thông thường. Tuy nhiên, `TreeSet` thực hiện đúng quan hệ trùng do comparator cung cấp. Tài liệu Java khuyến nghị thứ tự phải nhất quán với equals nếu muốn sorted set đáp ứng đầy đủ hợp đồng `Set` thông thường.

### Lỗi logic có thể xảy ra

Giả sử ứng dụng cần lưu mọi cách viết của tên sản phẩm để tìm kiếm lại, nhưng lại:

```java
Set<String> names = new TreeSet<>(collator);
names.addAll(List.of("cafe", "café", "CAFE"));
```

Hai spelling biến mất khỏi tập. Nếu ứng dụng không còn nơi lưu dữ liệu gốc, đó là **mất thông tin**. Nếu nghiệp vụ cố ý gộp một nhóm từ tương đương theo collation, hành vi ấy có thể chấp nhận được, nhưng phải ghi rõ chính sách chọn spelling đại diện.

## 4. TreeMap: put có thể ghi đè value của key khác spelling

`TreeMap` cũng dùng comparator để quyết định **hai key có tương đương hay không**. Xét:

```java
TreeMap<String, Integer> map = new TreeMap<>(collator);

System.out.println(map.put("cafe", 10)); // null
System.out.println(map.put("café", 20)); // 10
System.out.println(map.put("CAFE", 30)); // 20
System.out.println(map.size());         // 1
```

Lần thứ nhất tạo entry; hai lần sau tương đương theo comparator nên **cập nhật value** của entry hiện có. Kết quả trên mô tả môi trường dùng Collator PRIMARY trong ví dụ.

Sau ba lần `put`:

- `map.get("Café")` có thể trả `30`.
- `map.containsKey("CAFE")` có thể trả true.
- `map.firstKey()` có thể vẫn là `"cafe"`, spelling đầu tiên được chèn.
- `map.size()` vẫn bằng `1`.
- `map.keySet()` chỉ hiển thị key đã được lưu cho lớp tương đương ấy.

**Comparator không trả về một chuỗi đã chuẩn hóa**. Nó chỉ so sánh hai phần tử; TreeMap không tự “chuẩn hóa” `"CAFE"` thành `"cafe"`. Value có thể đổi, còn key object ban đầu thường được giữ trong entry khi `put` vào key tương đương.

### Giá trị trả về của Map.put

`put(k,v)` trả value trước đó hoặc `null` nếu không có mapping trước đó. Nhưng nếu map cho phép value `null`, kết quả `null` riêng lẻ không đủ chứng minh key chưa có. Khi chính sách cần chống ghi đè, xác định rõ quan hệ trùng và kiểm tra có key/va chạm phù hợp.

### Vì sao bug nghiêm trọng?

Một hệ thống coi spelling tên sản phẩm như ID có thể:

- Ghi nhầm giá trị tồn kho của sản phẩm B lên sản phẩm A.
- Mất metadata của một bản dịch khác.
- Xóa entry bằng một spelling khác, dù người dùng nghĩ mình chọn một khóa độc lập.
- Không thể phục hồi các spelling vốn chưa bao giờ được lưu vào map.

Đừng dùng collation-equivalent key làm ID nghiệp vụ duy nhất khi domain cần phân biệt các bản ghi.

## 5. Đối chiếu với HashSet/HashMap

| Collection | Quy tắc trùng | Với `"cafe"`, `"café"`, `"CAFE"` |
| --- | --- | --- |
| `HashSet<String>` | `hashCode/equals` | Ba phần tử. |
| `HashMap<String,V>` | `hashCode/equals` | Ba key độc lập. |
| `TreeSet<String>`, comparator Collator PRIMARY | `compare==0` | Có thể chỉ một phần tử. |
| `TreeMap<String,V>`, comparator Collator PRIMARY | `compare==0` | Có thể chỉ một entry, value bị cập nhật. |
| `TreeSet<String>` theo natural order | `String.compareTo==0` | Ba phần tử vì phân biệt theo UTF-16. |
| `TreeSet<String>` theo Collator + natural-order tie-breaker | Ưu tiên theo ngôn ngữ nhưng compare==0 chỉ khi String.equals | Ba phần tử. |

Nếu yêu cầu **giữ đầy đủ dữ liệu nhưng sắp xếp để hiển thị**, không nhất thiết phải đưa dữ liệu vào TreeSet. Một cách làm rõ ràng:

```java
Set<String> keys = new HashSet<>(incoming);
List<String> sorted = new ArrayList<>(keys);
sorted.sort(collator);
```

Đây là đoạn minh họa trong phương thức Java có `incoming` và `collator` được khai báo. `List.sort` không loại phần tử có comparator bằng 0. Nếu muốn kết quả hiển thị ổn định giữa các phần tử ngang nhau theo collation, nên dùng tie-breaker.

## 6. Collator và cấp độ phân biệt theo locale

`Collator` là API của `java.text` dành cho thứ tự ngôn ngữ. Nó phụ thuộc `Locale` và nguồn dữ liệu locale của JVM. Có các mức `strength`:

| Mức | Ý nghĩa tổng quát | Chú ý khi dùng cho key |
| --- | --- | --- |
| `PRIMARY` | Khác biệt cơ bản của chữ cái; thường bỏ qua dấu/case ở một số locale. | Có thể gộp nhiều String khác nhau. |
| `SECONDARY` | Xét thêm khác biệt thứ cấp, thường liên quan dấu. | Có thể vẫn gộp các khác biệt case. |
| `TERTIARY` | Xét thêm khác biệt cấp ba, thường gồm case. | Không được suy ra rằng compare==0 luôn tương đương `String.equals`. |
| `IDENTICAL` | Mức mạnh nhất trong API, xét các khác biệt rất tinh tế. | Không tự chứng minh nhất quán với `String.equals` cho mọi Unicode string/cấu hình. |

Đây chỉ là định hướng. **Các ký tự nào được xem tương đương tùy vào locale**, dữ liệu collation và implementation. Không được áp giả định “PRIMARY bỏ mọi dấu ở mọi ngôn ngữ” như một luật toàn cầu.

### Decomposition

`Collator.setDecomposition(Collator.CANONICAL_DECOMPOSITION)` giúp áp dụng xử lý phân rã chuẩn tắc cho một số ký tự tổ hợp/dựng sẵn. Hai biểu diễn như `"\u00E9"` và `"e\u0301"` có thể trở nên tương đương theo collation, nhưng điều này không đổi hành vi của `String.equals` hoặc bắt buộc phải gộp các ID Unicode trong database.

`NO_DECOMPOSITION`, `CANONICAL_DECOMPOSITION` và các hành vi liên quan phải được lựa chọn theo mục đích. **Normalization, collation equivalence và String.equals là ba khái niệm khác nhau.**

### Collator không phải thuật toán định danh vĩnh viễn

Dữ liệu locale và thuật toán collation có thể phát triển theo JDK/provider. Nếu một hệ thống cần khóa ổn định nhiều năm, không lấy “`Collator.PRIMARY` của bản JDK hiện tại” làm hợp đồng lưu trữ ID mà không kiểm soát phiên bản và kế hoạch migration.

## 7. Khắc phục bằng tie-breaker nhất quán với equals

Khi yêu cầu là:

1. Ưu tiên thứ tự theo ngôn ngữ cho người dùng; **và**
2. Không loại bất kỳ `String` nào khác nhau theo `String.equals`,

hãy tạo comparator hai tầng:

```java
Comparator<String> primary = collator::compare;

Comparator<String> safeOrder =
        primary.thenComparing(Comparator.naturalOrder());
```

Đây là đoạn minh họa trong phương thức Java với `collator` đã tạo, cần import `Comparator`.

`String.compareTo` nhất quán với `String.equals`. Khi Collator trả 0, bộ so sánh phụ quyết định thứ tự theo UTF-16. Nếu Collator không trả 0, thứ tự ngôn ngữ được ưu tiên.

Với cùng ba chuỗi, chương trình mẫu cho:

```text
distinct=[CAFE, cafe, café] size=3
```

### Vì sao điều này đúng?

Với hai String `a` và `b`:

- Nếu `collator.compare(a,b) != 0`, comparator tổng hợp trả kết quả khác 0. Hai chuỗi không thể được xem là cùng khóa.
- Nếu Collator trả 0, comparator dùng `a.compareTo(b)`.
- `String.compareTo` trả 0 **khi và chỉ khi** `String.equals` true.
- Vậy `safeOrder.compare(a,b)==0` iff `a.equals(b)`.

Miễn là comparator thành phần tuân thủ hợp đồng và không đổi trong suốt vòng đời cây, thứ tự kết hợp vẫn có ý nghĩa nhất quán. Đây là một cách vừa ưu tiên collation vừa bảo toàn từng spelling String.

### Mặt trái của tie-breaker

Thứ tự phụ là **thứ tự code unit**, không phải “tự nhiên đối với người đọc” giữa các từ mà Collator cho ngang nhau. Nhưng khi cần một **thứ tự quyết định** cho dữ liệu đồng hạng, đây là điều hợp lý. Có thể chọn tie-breaker khác, miễn là nó phù hợp định nghĩa `equals` của kiểu T và không vi phạm hợp đồng comparator.

### Sai lầm: ép trả 1 cho mọi cặp bằng nhau

```java
Comparator<String> broken = (a, b) -> {
    int result = collator.compare(a, b);
    return result == 0 ? 1 : result;
};
```

Đây là **ví dụ sai có chủ ý**. Nó khiến `compare(a,a)==1` và vi phạm đổi dấu. TreeSet/TreeMap có thể vận hành không đúng giả định sorted collection. **Không sửa lỗi trùng bằng cách làm comparator luôn trả khác 0.**

## 8. Khắc phục bằng cách tách ID khỏi nhãn hiển thị

Trong ứng dụng thực tế, **tên người/tên sản phẩm** không phải lúc nào cũng là ID.

Ví dụ cấu trúc:

```java
record Product(long id, String displayName) {}
```

Một sản phẩm có ID riêng và tên có thể trùng với sản phẩm khác. Cách thiết kế hợp lý:

- `Map<Long, Product>` bảo toàn danh tính theo ID.
- Khi cần hiển thị, tạo `List<Product>` từ các giá trị map và sort theo `displayName` bằng Collator.
- Nếu hai tên tương đương theo Collator, tie-break bằng ID để có thứ tự quyết định.
- Không dùng chỉ `displayName` làm comparator duy nhất của `TreeSet<Product>` rồi kỳ vọng giữ tất cả ID.

Ví dụ minh họa trong phương thức Java:

```java
Comparator<Product> displayOrder =
        Comparator.comparing(
                Product::displayName, collator::compare)
                .thenComparingLong(Product::id);
```

Tuy nhiên, cần chú ý: `record Product(long id, String displayName)` mặc định `equals` dựa trên **cả ID lẫn displayName**. Comparator trên tên và ID ở ví dụ **có thể không nhất quán với equals của record** nếu hai Product có cùng ID, displayName khác nhau nhưng Collator lại cho chúng bằng nhau.

Nếu muốn dùng `TreeSet<Product>` và đòi **consistent with equals**, có thể:

- Thiết kế class `Product` có `equals/hashCode` dựa trên ID nếu đó là identity nghiệp vụ, rồi comparator tie-break theo ID; hoặc
- Với record mặc định, tie-break thêm phép so sánh chính xác `String.compareTo(displayName)` bên cạnh ID; hoặc
- Không dùng TreeSet làm nơi lưu truth; sử dụng Map theo ID và List cho hiển thị.

**Nguyên tắc:** không có một “tie-break field” thần kỳ. Phải biết chính xác `equals` của đối tượng biểu diễn điều gì.

## 9. Khi hành vi không nhất quán với equals là chủ đích

Không phải mọi TreeSet dùng Collator PRIMARY đều là bug. Ví dụ một màn hình chỉ cần một đại diện cho mỗi nhóm từ được xem tương đương ở mức tìm kiếm. Khi đó comparator-based uniqueness có thể là **đặc tả nghiệp vụ**.

Nhưng phải trả lời rõ:

1. Locale và strength cố định nào định nghĩa lớp tương đương?
2. Giữ spelling nào khi hai chuỗi compare==0?
3. Có cần giữ lại mọi spelling gốc để audit/tìm kiếm không?
4. Khi `remove("café")`, có chủ đích xóa đại diện `"cafe"` không?
5. Khi `put` một spelling khác, được phép thay value của entry cũ không?
6. Nếu JDK/provider thay đổi collation, có cần rebuild index và giải quyết trùng không?

Nếu cần giữ mọi bản ghi nhưng vẫn gom nhóm theo collation, có thể có một `Map<ID, Item>` lưu bản gốc và một **index nhóm** hỗ trợ truy vấn, thay vì dùng một TreeSet mất những spelling khác làm nguồn dữ liệu duy nhất.

Không nên gọi một TreeMap có comparator PRIMARY là “Map ánh xạ mọi key gốc” nếu thực tế nó chỉ lưu một entry cho một lớp tương đương.

## 10. Ví dụ Java 17+ hoàn chỉnh, chạy độc lập

Tạo tệp **`ComparatorEqualsDemo.java`**:

```java
import java.text.Collator;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.TreeMap;
import java.util.TreeSet;

public class ComparatorEqualsDemo {

    public static void main(String[] args) {
        Collator collator = Collator.getInstance(Locale.FRENCH);
        collator.setStrength(Collator.PRIMARY);
        collator.setDecomposition(
                Collator.CANONICAL_DECOMPOSITION);

        String plain = "cafe";
        String accent = "caf\u00E9";
        String upper = "CAFE";

        System.out.println("compareCafe="
                + collator.compare(plain, accent));
        System.out.println("stringEquals="
                + plain.equals(accent));

        TreeSet<String> words = new TreeSet<>(collator);
        System.out.println("addCafe=" + words.add(plain));
        System.out.println("addAccent=" + words.add(accent));
        System.out.println("addUpper=" + words.add(upper));
        System.out.println("set=" + words
                + " size=" + words.size()
                + " containsUpper=" + words.contains(upper));

        TreeMap<String, Integer> scores =
                new TreeMap<>(collator);
        System.out.println("putFirst=" + scores.put(plain, 10));
        System.out.println("putSecond=" + scores.put(accent, 20));
        System.out.println("putThird=" + scores.put(upper, 30));
        System.out.println("map=" + scores
                + " size=" + scores.size()
                + " lookup=" + scores.get("Caf\u00E9"));

        Comparator<String> primary = collator::compare;
        Comparator<String> stableOrder =
                primary.thenComparing(Comparator.naturalOrder());

        TreeSet<String> distinct = new TreeSet<>(stableOrder);
        distinct.addAll(List.of(plain, accent, upper));
        System.out.println("distinct=" + distinct
                + " size=" + distinct.size());

        System.out.println("hashSetSize="
                + new HashSet<>(
                        List.of(plain, accent, upper)).size());

        System.out.println("removed=" + words.remove(accent)
                + " remaining=" + words.size());
    }
}
```

Biên dịch và chạy với JDK 17+ trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 ComparatorEqualsDemo.java
java ComparatorEqualsDemo
```

**Stdout đối chiếu với Java 17 và `Locale.FRENCH` ở PRIMARY:**

```text
compareCafe=0
stringEquals=false
addCafe=true
addAccent=false
addUpper=false
set=[cafe] size=1 containsUpper=true
putFirst=null
putSecond=10
putThird=20
map={cafe=30} size=1 lookup=30
distinct=[CAFE, cafe, café] size=3
hashSetSize=3
removed=true remaining=0
```

Chú ý: collation theo locale có thể khác khi JDK/provider hoặc dữ liệu CLDR thay đổi. Ví dụ được kiểm thử với môi trường Java 17 tương ứng; nếu dự án kiểm tra **chính xác từng ký tự** của stdout, cố định JDK và các locale provider được hỗ trợ hoặc kiểm thử bằng những invariant quan trọng thay vì snapshot toàn bộ kết quả.

### Đọc stdout từng phần

- `compareCafe=0` nhưng `stringEquals=false`: comparator và equals định nghĩa tương đương khác nhau.
- `addAccent=false` / `addUpper=false`: TreeSet không thêm hai spelling vì comparator cho bằng nhau.
- `containsUpper=true`: tra cứu theo comparator thay vì đòi đúng String gốc.
- `putSecond=10` / `putThird=20`: value cũ bị thay, không thêm key mới.
- `map={cafe=30}`: một entry được giữ, với spelling đầu tiên làm key.
- `distinct=[CAFE, cafe, café] size=3`: tie-breaker giữ ba String khác nhau.
- `hashSetSize=3`: HashSet dùng equals nên giữ cả ba.
- `removed=true remaining=0`: dùng spelling khác nhưng cùng nhóm comparator có thể xóa phần tử đã lưu.

## 11. Không sửa comparator khi cây đã có dữ liệu

`Collator` là **mutable**. Có thể gọi:

```java
collator.setStrength(Collator.TERTIARY);
collator.setStrength(Collator.PRIMARY);
```

Nếu một `TreeSet`/`TreeMap` đã được xây dựng và chứa key theo một thứ tự, thay strength/decomposition hoặc thay đổi dữ liệu mà comparator phụ thuộc vào **không khiến cây tự được xây dựng lại**. Sau thay đổi, các phép `contains/get/remove` và việc duyệt có thể không còn khớp giả định về thứ tự đang được lưu.

Các trường hợp nguy hiểm:

- Có nhiều spelling ở `TERTIARY`, sau đó hạ xuống `PRIMARY` khiến chúng trở nên tương đương nhưng cây vẫn giữ nhiều node.
- Comparator dựa trên một thuộc tính mutable của key, như tên hiển thị; sửa tên sau `add` làm key “di chuyển về mặt logic” nhưng node không di chuyển.
- Comparator phụ thuộc locale mặc định rồi ứng dụng đổi `Locale.setDefault(...)`; cách so sánh có thể đổi giữa hai lần thao tác.
- Một `Collator` duy nhất được chia sẻ và thay `setStrength` cho các request khác nhau.

**Biện pháp:** chọn cấu hình comparator trước khi tạo collection; không sửa trong suốt vòng đời của collection. Khi cần đổi luật thứ tự, tạo collection mới từ **dữ liệu gốc** và xử lý những lớp tương đương mới theo chính sách đã định nghĩa.

`Collator` không được bảo đảm thread-safe khi truy cập/chỉnh sửa tùy tiện. Không chia sẻ một Collator mutable và thay thông số theo user request. Có thể tạo hoặc clone cấu hình theo phạm vi cần thiết và quản lý đồng bộ khi thích hợp.

## 12. Các lỗi phổ biến

| Sai lầm | Hệ quả | Cách làm |
| --- | --- | --- |
| Dùng `TreeSet<>(collator)` thay `HashSet` chỉ để sort | Đổi luôn quy tắc uniqueness. | Giữ HashSet, sort List; hoặc thêm tie-breaker. |
| Nghĩ TreeSet phải dựa vào `equals` | `contains/add/remove` có thể xử lý spelling khác như cùng phần tử. | Hiểu compare==0 là quan hệ trùng. |
| Dùng `TreeMap` theo tên hiển thị làm ID | Có thể ghi đè value của bản ghi khác tên nhưng collation bằng nhau. | Dùng ID ổn định làm key. |
| Tin Collator PRIMARY của mọi ngôn ngữ giống nhau | Quy tắc collation phụ thuộc locale/provider. | Test locale cụ thể. |
| Chọn `TERTIARY` rồi cho rằng luôn nhất quán với equals | Unicode decomposition/locale vẫn có thể tạo equivalence khác String.equals. | Dùng tie-breaker dựa vào equals. |
| Comparator trả 1 khi gặp bằng nhau | Vi phạm contract comparator, kể cả compare(a,a). | Dùng comparator phụ hợp lệ. |
| Chỉ tie-break bằng priority không duy nhất | Những object khác nhau cùng priority vẫn có thể bị gộp. | Tie-break bằng thuộc tính bảo toàn identity theo equals. |
| Dùng comparator tên cho record có equals dựa nhiều field | Comparator chưa chắc nhất quán với equals record. | Thiết kế identity rõ; kiểm tra từng field. |
| Đổi `Collator.setStrength` sau khi insert | Cây không tự rebuild, lookup khó dự đoán. | Dựng collection mới. |
| Dùng Collator để tạo khóa canonical xuyên các phiên bản JDK | Thuật toán/dữ liệu locale có thể thay đổi. | Quy định canonicalization riêng có version. |
| Dùng String natural order như thứ tự UI theo ngôn ngữ | Thứ tự UTF-16 không phải ngôn ngữ tự nhiên. | Collator cho display; natural order chỉ tie-break. |
| Nhầm Unicode normalization với collation và equals | Gộp hoặc tách dữ liệu không đúng chính sách. | Định nghĩa rõ các lớp tương đương. |

## 13. Kiểm thử đúng cả hợp đồng và hành vi Collection

Một bộ test tốt cần kiểm tra riêng:

| Trường hợp | Dữ liệu | Mục tiêu |
| --- | --- | --- |
| Collator tương đương | `"cafe"` / `"café"` | compare==0, equals false tại strength/locale được chọn. |
| Khác chữ hoa | `"CAFE"` / `"cafe"` | Xác nhận cách Collator xử lý case. |
| Unicode canonical equivalence | `"\u00E9"` / `"e\u0301"` | Kiểm tra normalization/decomposition. |
| TreeSet insert | Ba spelling | `add`, `size`, phần tử được giữ. |
| TreeSet lookup/remove | Spelling khác nhưng compare==0 | Đảm bảo hiểu đúng kết quả `contains/remove`. |
| TreeMap overwrite | Ba lần `put` cùng lớp collation | Value cũ được trả và size không tăng. |
| Comparator tie-breaker | Collator + String natural | compare==0 iff equals trên tập thử. |
| Comparator bất biến | Insert rồi không thay cấu hình | Cây giữ một thứ tự ổn định. |
| Locale/JDK | Locale được sản phẩm hỗ trợ | Chú ý khác biệt dữ liệu collation. |
| Null/bad input | Nếu API cho phép | Quyết định `nullsFirst/nullsLast` hoặc từ chối null. |

### Test các tiên đề comparator

Cần kiểm thử:

```text
compare(a, a) == 0
sign(compare(a, b)) == -sign(compare(b, a))
if compare(a,b) > 0 and compare(b,c) > 0:
    compare(a,c) > 0
if compare(a,b) == 0:
    sign(compare(a,z)) == sign(compare(b,z))
```

Đây là **pseudocode** chứ không phải Java nguyên xi. Khi nghiệp vụ yêu cầu nhất quán với equals, bổ sung:

```text
for every tested pair (a,b):
    (compare(a,b) == 0) == a.equals(b)
```

Dùng dữ liệu chứa chữ có dấu, case, khoảng trắng, ký tự tổ hợp, emoji và tên trùng để tìm lỗi. Một tập test hữu hạn không chứng minh toàn bộ Unicode, nhưng giúp phát hiện những thiết kế comparator rõ ràng sai.

### Null và phạm vi hỗ trợ

`TreeSet` hoặc `TreeMap` không bắt buộc chấp nhận `null` với mọi comparator. Với natural String comparison, thường không hỗ trợ null. Nếu bạn chủ động dùng `Comparator.nullsFirst(...)`, hãy xác định `equals`/identity của dữ liệu và test. Không tự chấp nhận null chỉ để “tránh lỗi”, bởi null key có thể là trạng thái thiếu dữ liệu phải được xử lý trước khi insert.

## 14. Bài tập tự luyện

**Bài 1 — Tái hiện lỗi:** tạo `Collator` với `Locale.FRENCH`, `PRIMARY`; thêm `"cafe"`, `"café"`, `"CAFE"` vào TreeSet. In `add`, `size`, `contains`, `remove`. So sánh với HashSet, giải thích tất cả khác biệt.

**Bài 2 — TreeMap ghi đè:** `put` ba spelling với value 10, 20, 30; in `size`, `firstKey`, `get("Café")`, kết quả trả về của từng `put`. Giải thích tại sao không thể dựa vào map ấy để lưu ba spelling độc lập.

**Bài 3 — Tie-breaker đúng:** tạo comparator Collator trước, `String.compareTo` sau. Viết unit test cho các cặp khác nhau theo equals nhưng Collator xem ngang nhau. Chứng minh TreeSet mới giữ đủ ba spelling.

**Bài 4 — Comparator sai:** tạo comparator luôn trả 1 khi Collator trả 0. Test `compare(a,a)` và đổi chỗ `a/b` để thấy vi phạm hợp đồng. Sửa bằng natural-order tie-breaker, không cố “ép” cây nhận phần tử.

**Bài 5 — Model theo ID:** tạo hai sản phẩm khác ID nhưng cùng displayName. Lưu vào Map theo ID, sắp xếp List theo Collator + ID. Nếu dùng record mặc định, phân tích vì sao comparator theo ID có thể khác định nghĩa equals của record.

**Bài 6 — Mức strength:** thử `PRIMARY`, `SECONDARY`, `TERTIARY`, `IDENTICAL` với các cặp dấu, case và ký tự tổ hợp. Ghi locale/JDK provider để giải thích sự khác biệt, không suy luận chung cho mọi ngôn ngữ.

**Bài 7 — Thay luật so sánh:** trên một collection thử nghiệm nhỏ, chèn dữ liệu bằng Collator TERTIARY rồi thay sang PRIMARY. Quan sát sự lệch thứ tự/trùng; sau đó xây TreeSet mới theo comparator mới từ nguồn dữ liệu ban đầu.

### Checklist

- [ ] Nêu được định nghĩa “consistent with equals”.
- [ ] Biết TreeSet/TreeMap dùng `compare==0` cho uniqueness, khác HashSet/HashMap.
- [ ] Giải thích được `add=false`, `contains=true` và `remove=true` với spelling khác.
- [ ] Biết `TreeMap.put` thay value khi key tương đương theo comparator.
- [ ] Phân biệt `Collator` theo locale với `String.equals` và Unicode normalization.
- [ ] Dùng tie-breaker hợp lệ nếu muốn vừa sort theo locale vừa phân biệt từng String.
- [ ] Tách ID nghiệp vụ khỏi tên hiển thị khi data model cần.
- [ ] Không mutate comparator/Collator sau khi chèn vào sorted collection.
- [ ] Kiểm thử tiên đề comparator, các mức strength và hành vi collection thực tế.

**Kết luận:** `TreeSet` và `TreeMap` xem `compare(a,b)==0` là một quan hệ đồng nhất trong cây. Nếu `Collator` ở mức ngôn ngữ gộp những spelling khác nhau, collection cũng có thể gộp chúng. Cần chọn rõ **equivalence theo ngôn ngữ** hay **identity theo equals/ID**; khi vừa muốn sắp xếp tự nhiên vừa giữ mọi String riêng biệt, dùng tie-breaker nhất quán với equals hoặc tách tập dữ liệu nguồn khỏi lớp sắp xếp hiển thị.
