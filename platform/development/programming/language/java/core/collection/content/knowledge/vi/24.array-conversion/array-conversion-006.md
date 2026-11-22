# Chuyển List sang Set và hệ quả với trùng lặp hoặc thứ tự

## 1. Từ danh sách các lần xuất hiện sang tập các giá trị

Một `List` trả lời được cả hai câu hỏi: “có những phần tử nào?” và “chúng xuất hiện ở vị trí nào, bao nhiêu lần?”. Một `Set` tập trung vào việc một phần tử có thuộc tập hay không; nó không lưu nhiều phần tử được xem là trùng nhau theo quy tắc của tập đó.

Vì vậy, chuyển `List` sang `Set` là một quyết định về ý nghĩa dữ liệu. Dãy thao tác của người dùng, danh sách mặt hàng đã quét hoặc lịch sử trạng thái có thể chứa những lần lặp hoàn toàn hợp lệ. Nếu mỗi lần xuất hiện có ý nghĩa riêng, loại trùng có thể làm mất thông tin cần thiết.

Ví dụ, danh sách tên trái cây sau có năm lần xuất hiện:

```text
[pear, apple, pear, banana, apple]
```

Nếu yêu cầu là “các tên đã xuất hiện, giữ tên nào gặp trước đứng trước”, kết quả phù hợp là:

```text
[pear, apple, banana]
```

Nếu yêu cầu là “các tên khác nhau theo thứ tự tự nhiên của chuỗi”, kết quả là:

```text
[apple, banana, pear]
```

Hai kết quả cùng có ba tên, nhưng cung cấp hai cách duyệt khác nhau. Cả hai đều không còn cho biết rằng `pear` và `apple` từng xuất hiện hai lần.

Có ba quyết định cần làm rõ trước khi viết lệnh chuyển đổi:

1. **Trùng theo tiêu chí nào?** Hai đối tượng có bằng nhau theo `equals`, hay chỉ có cùng một mã nghiệp vụ?
2. **Duyệt theo thứ tự nào?** Không cần thứ tự, giữ lần xuất hiện đầu tiên hay sắp xếp?
3. **Thông tin nào phải giữ lại?** Chỉ cần giá trị duy nhất, hay còn cần số lần, vị trí và đối tượng đại diện?

Bài này lần lượt trả lời ba câu hỏi đó bằng các chương trình Java độc lập. Mỗi chương trình được lưu vào tệp có tên trùng với `public class`, biên dịch bằng JDK 17 trở lên. Các lệnh dùng `--release 17` để giữ mã trong phạm vi Java 17.

## 2. Chọn kiểu Set theo ý nghĩa thứ tự

`Set` là giao diện. Khai báo biến là `Set<String>` không tự quyết định thứ tự duyệt; lớp thực tế và cách tạo kết quả mới quyết định điều đó.

| Nhu cầu | Cách tạo từ List | Quy tắc trùng | Thứ tự duyệt |
| --- | --- | --- | --- |
| Chỉ cần tập giá trị duy nhất | `new HashSet<>(source)` | `equals` cùng hợp đồng `hashCode` | Không được bảo đảm |
| Giữ thứ tự gặp giá trị lần đầu | `new LinkedHashSet<>(source)` | `equals` cùng hợp đồng `hashCode` | Theo lần thêm đầu tiên |
| Vừa loại trùng vừa sắp xếp tự nhiên | `new TreeSet<>(source)` | So sánh tự nhiên trả về `0` | Theo thứ tự tự nhiên |
| Sắp xếp bằng tiêu chí riêng | Tạo `TreeSet` với `Comparator`, rồi `addAll(source)` | Bộ so sánh trả về `0` | Theo bộ so sánh |
| Tạo tập không cho sửa cấu trúc, không cần thứ tự | `Set.copyOf(source)` | Các phần tử bằng nhau theo `equals` | Không được bảo đảm |

Trong bảng, `source` là một `List` hợp lệ. Cách viết là những biểu thức minh họa; các chương trình đầy đủ ở dưới có đủ khai báo và `import`.

### HashSet không cam kết giữ thứ tự của List

`HashSet` không bảo đảm thứ tự duyệt, kể cả khi một lần chạy tình cờ cho ra đúng thứ tự mong muốn. “Không được bảo đảm” cũng không có nghĩa là mỗi lần chạy chắc chắn đổi thứ tự hoặc được xáo ngẫu nhiên. Chương trình phải đúng với mọi thứ tự mà hợp đồng của tập cho phép. [Javadoc HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html)

Do đó, không dùng chuỗi in trực tiếp từ `HashSet` làm bằng chứng rằng việc chuyển đổi giữ thứ tự. Nếu cần kiểm tra các giá trị trong một ví dụ, có thể sắp xếp riêng để hiển thị, đồng thời nói rõ đó là một bước bổ sung.

### LinkedHashSet giữ lần xuất hiện đầu tiên

Khi duyệt một `List` và đưa các phần tử vào `LinkedHashSet`, phần tử mới được thêm ở cuối thứ tự duyệt. Thêm lại một phần tử đã có không chuyển nó xuống cuối. Vì vậy, dãy `[B, A, B, C, A]` trở thành `[B, A, C]`. [Javadoc LinkedHashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedHashSet.html)

Đây là thứ tự của những giá trị gặp lần đầu, không phải thứ tự của những lần xuất hiện cuối cùng. Nếu cần một chính sách khác, phải mô tả và thực hiện chính sách đó riêng.

### TreeSet áp dụng thứ tự sắp xếp

`TreeSet` không giữ thứ tự gặp trong `List`. Nó tổ chức phần tử theo thứ tự tự nhiên hoặc `Comparator` được cung cấp. Cùng với thứ tự, kết quả so sánh còn quyết định những phần tử nào bị coi là trùng; chi tiết này sẽ được kiểm chứng ở phần 6.

## 3. Thí nghiệm: cùng một List, ba lựa chọn về thứ tự

Lưu chương trình sau vào `ListToSetOrderDemo.java`.

```java
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class ListToSetOrderDemo {
    public static void main(String[] args) {
        List<String> source = new ArrayList<>(
                List.of("pear", "apple", "pear", "banana", "apple"));
        Set<String> hashed = new HashSet<>(source);
        Set<String> firstOrder = new LinkedHashSet<>(source);
        Set<String> sorted = new TreeSet<>(source);
        Set<String> collected = source.stream()
                .collect(Collectors.toCollection(LinkedHashSet::new));

        System.out.println("source=" + source);
        System.out.println("sourceSize=" + source.size());
        System.out.println("hashSize=" + hashed.size());
        System.out.println("hashSortedForDisplay=" + new TreeSet<>(hashed));
        System.out.println("firstOrder=" + firstOrder);
        System.out.println("sorted=" + sorted);
        System.out.println("collected=" + collected);

        List<String> uniqueList = new ArrayList<>(firstOrder);
        System.out.println("uniqueList=" + uniqueList);
        System.out.println("restoresSource=" + uniqueList.equals(source));
        source.add("kiwi");
        System.out.println("setContainsNewSourceValue="
                + firstOrder.contains("kiwi"));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ListToSetOrderDemo.java
java ListToSetOrderDemo
```

Stdout:

```text
source=[pear, apple, pear, banana, apple]
sourceSize=5
hashSize=3
hashSortedForDisplay=[apple, banana, pear]
firstOrder=[pear, apple, banana]
sorted=[apple, banana, pear]
collected=[pear, apple, banana]
uniqueList=[pear, apple, banana]
restoresSource=false
setContainsNewSourceValue=false
```

Đọc kết quả theo từng thay đổi về dữ liệu:

- `sourceSize=5`, còn `hashSize=3`: các lần xuất hiện lặp đã được gộp.
- `firstOrder=[pear, apple, banana]`: `LinkedHashSet` giữ thứ tự gặp ba tên lần đầu.
- `sorted=[apple, banana, pear]`: `TreeSet` sắp xếp tên theo thứ tự tự nhiên của `String`.
- `collected` trùng với `firstOrder`: chương trình đã yêu cầu rõ `LinkedHashSet` khi thu thập phần tử từ luồng.
- `restoresSource=false`: chuyển tập trở lại `List` tạo được một danh sách mới, nhưng không khôi phục các lần xuất hiện đã bỏ.
- `setContainsNewSourceValue=false`: thêm `kiwi` vào danh sách sau khi tạo tập không tự thêm nó vào tập.

Dòng `hashSortedForDisplay` dùng `new TreeSet<>(hashed)` để có kết quả hiển thị ổn định. Thứ tự `[apple, banana, pear]` trên dòng đó thuộc về `TreeSet` mới tạo, không phải một cam kết về thứ tự của `HashSet`.

Việc in `source` trước bước `source.add("kiwi")` cũng có chủ đích: dòng đầu mô tả đầu vào lúc chuyển đổi. Lệnh thêm ở cuối kiểm tra sự độc lập về cấu trúc sau đó.

### Vì sao Set sang List không phải phép đảo?

Xét ba danh sách:

```text
[B, A]
[B, A, B]
[B, B, A, A]
```

Cả ba đều có thể cho cùng một `LinkedHashSet` với thứ tự `[B, A]`. Từ tập kết quả, không có cách suy ra danh sách ban đầu là danh sách nào.

Các thông tin bị mất gồm:

- Số lần xuất hiện của mỗi giá trị.
- Vị trí của những lần xuất hiện bị gộp.
- Chuỗi đầy đủ ban đầu.
- Những đối tượng bằng nhau đã không được giữ lại.

Nếu chỉ cần một `List` không trùng và giữ thứ tự gặp đầu tiên, cách `new ArrayList<>(new LinkedHashSet<>(source))` đáp ứng được. Danh sách kết quả vẫn có thể thay đổi và có truy cập theo chỉ số, nhưng chỉ chứa các giá trị đã chọn sau loại trùng.

## 4. “Trùng nhau” không đồng nghĩa với “cùng một đối tượng”

Với `HashSet` và `LinkedHashSet`, hai tham chiếu khác nhau vẫn có thể được xem là cùng một phần tử nếu các đối tượng bằng nhau theo `equals`. `hashCode` phải tuân thủ hợp đồng: đối tượng bằng nhau phải có cùng mã băm. Các đối tượng có cùng mã băm chưa chắc bằng nhau; va chạm băm không có nghĩa là tập tự gộp mọi đối tượng trong cùng một nhóm băm.

Điều này ảnh hưởng trực tiếp đến chuyển đổi dữ liệu nghiệp vụ. Giả sử hai đối tượng liên hệ có cùng `id` nhưng khác nhãn hiển thị. Nếu `equals` chỉ dựa trên `id`, tập có thể chỉ giữ một đối tượng. Tập không tự kết hợp các nhãn và không tự quyết định rằng bản ghi sau mới hơn nên phải thay bản ghi trước.

Lớp tự định nghĩa cũng cần có đúng tiêu chí bằng nhau. Nếu lớp dùng `equals` mặc định từ `Object`, hai đối tượng được tạo riêng thường vẫn khác nhau, dù các trường đang chứa cùng dữ liệu. Chuyển sang tập không tự đọc tất cả các trường để suy ra một khóa nghiệp vụ.

### Thí nghiệm về đối tượng đại diện và việc dùng chung tham chiếu

Lưu vào `SetEqualityAndSharingDemo.java`.

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class SetEqualityAndSharingDemo {
    static final class Contact {
        private final int id;
        private String label;

        Contact(int id, String label) {
            this.id = id;
            this.label = label;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Contact contact && id == contact.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    public static void main(String[] args) {
        Contact earlier = new Contact(1, "earlier");
        Contact later = new Contact(1, "later");
        Contact other = new Contact(2, "other");
        List<Contact> source =
                new ArrayList<>(List.of(earlier, later, other));
        Set<Contact> result = new LinkedHashSet<>(source);
        Contact retained = result.iterator().next();

        System.out.println("sourceSize=" + source.size());
        System.out.println("setSize=" + result.size());
        System.out.println("equalById=" + earlier.equals(later));
        System.out.println("retainedIsEarlier=" + (retained == earlier));
        System.out.println("retainedLabel=" + retained.label);

        earlier.label = "edited";
        source.clear();
        System.out.println("labelAfterEdit=" + retained.label);
        System.out.println("setSizeAfterSourceClear=" + result.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SetEqualityAndSharingDemo.java
java SetEqualityAndSharingDemo
```

Stdout:

```text
sourceSize=3
setSize=2
equalById=true
retainedIsEarlier=true
retainedLabel=earlier
labelAfterEdit=edited
setSizeAfterSourceClear=2
```

Hai đối tượng `earlier` và `later` có cùng `id=1`, nên `equals` trả về `true`. `LinkedHashSet` nhận `earlier` trước. Lần thêm `later` không làm tập có phần tử thứ ba và không thay thế đối tượng đang giữ.

Vì thế:

- `retainedIsEarlier=true` kiểm tra trực tiếp danh tính đối tượng bằng `==`.
- `retainedLabel=earlier` cho thấy dữ liệu từ đối tượng bằng nhau xuất hiện sau không tự ghi đè.
- `labelAfterEdit=edited` cho thấy phần tử trong tập vẫn là chính đối tượng được tham chiếu từ danh sách trước đó.
- `setSizeAfterSourceClear=2` cho thấy xóa cấu trúc danh sách không xóa cấu trúc tập đã tạo.

Ví dụ cố ý giữ `id` là `final`; trường `label` không tham gia `equals` hoặc `hashCode`. Đổi `label` vì thế không làm thay đổi tiêu chí nhận diện phần tử trong tập.

Nếu một trường tham gia `equals` hoặc `hashCode` thay đổi trong khi đối tượng còn nằm trong tập băm, các thao tác tìm kiếm hoặc loại bỏ có thể không còn hoạt động như mong đợi. Không dùng việc chuyển sang `HashSet` hay `LinkedHashSet` để “đóng băng” những trường này; tập không bảo vệ đối tượng phần tử khỏi thay đổi.

## 5. Container mới và bản sao sâu là hai việc khác nhau

Các constructor `new HashSet<>(source)`, `new LinkedHashSet<>(source)` và `new TreeSet<>(source)` tạo cấu trúc chứa mới. Tập kết quả không phải một khung nhìn cập nhật trực tiếp theo mọi lần thêm hoặc xóa ở danh sách nguồn.

Tuy nhiên, chúng không tạo bản sao mới của từng đối tượng phần tử:

```text
List nguồn ──tham chiếu──> đối tượng Contact
                              ↑
Set mới   ──tham chiếu─────────┘
```

Sơ đồ chỉ minh họa quan hệ tham chiếu. Một số phần tử trùng có thể không đi vào tập, nhưng phần tử được giữ lại vẫn là đối tượng đã có.

Từ đó cần tách hai yêu cầu:

1. **Độc lập về cấu trúc:** thêm hoặc xóa phần tử ở danh sách không tự thêm hoặc xóa phần tử ở tập mới.
2. **Độc lập về trạng thái phần tử:** sửa một đối tượng ở phía này không ảnh hưởng đối tượng được nhìn thấy ở phía kia.

Constructor chuyển đổi đáp ứng yêu cầu đầu. Muốn đáp ứng yêu cầu sau, phải dùng phần tử bất biến hoặc sao chép phần tử theo quy tắc của mô hình dữ liệu. Việc tạo một tập không cho sửa cấu trúc cũng không tự đáp ứng yêu cầu sau.

Nếu hai đối tượng bằng nhau nhưng mang các trường còn lại khác nhau, hãy xác định rõ cần giữ bản đầu, giữ bản cuối, từ chối trùng hay hợp nhất thông tin. Với yêu cầu hợp nhất theo khóa, một `Map` cùng chính sách xử lý xung đột thường diễn đạt ý định rõ hơn việc chỉ đưa các đối tượng vào `Set`.

## 6. TreeSet có thể loại phần tử theo một tiêu chí khác equals

Với tập được sắp xếp, phép so sánh làm hai việc: xác định vị trí theo thứ tự và xác định hai phần tử có chiếm cùng một vị trí hay không. Nếu kết quả so sánh là `0`, `TreeSet` xem chúng là trùng.

Điều đó tạo ra một bẫy khi dùng `Comparator` chỉ để “đổi cách hiển thị”. Chẳng hạn, so sánh chuỗi không phân biệt hoa thường khiến `"Java"`, `"java"` và `"JAVA"` rơi vào cùng một nhóm, dù `String.equals` xem chúng là ba chuỗi khác nhau.

Một `TreeSet` cần có thứ tự nhất quán với `equals` để tuân thủ đầy đủ hợp đồng chung của `Set`. Chương trình dưới đây cố ý dùng bộ so sánh không nhất quán với `String.equals` để quan sát hệ quả, không phải mẫu mặc định cho mọi tập chuỗi. [Javadoc TreeSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeSet.html)

Lưu vào `TreeSetDuplicateRuleDemo.java`.

```java
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.TreeSet;

public class TreeSetDuplicateRuleDemo {
    public static void main(String[] args) {
        List<String> source = List.of("Java", "java", "JAVA", "SQL", "Java");
        Set<String> byEquals = new HashSet<>(source);
        Set<String> natural = new TreeSet<>(source);
        Set<String> caseInsensitive = new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        caseInsensitive.addAll(source);

        Set<String> normalized = new LinkedHashSet<>();
        for (String value : source) {
            normalized.add(value.toLowerCase(Locale.ROOT));
        }

        System.out.println("equalsSize=" + byEquals.size());
        System.out.println("naturalSize=" + natural.size());
        System.out.println("natural=" + natural);
        System.out.println("ignoreCaseSize=" + caseInsensitive.size());
        System.out.println("ignoreCase=" + caseInsensitive);
        System.out.println("stringEquals=" + "Java".equals("java"));
        System.out.println("compareAsSame="
                + (String.CASE_INSENSITIVE_ORDER.compare("Java", "java") == 0));
        System.out.println("normalized=" + normalized);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 TreeSetDuplicateRuleDemo.java
java TreeSetDuplicateRuleDemo
```

Stdout:

```text
equalsSize=4
naturalSize=4
natural=[JAVA, Java, SQL, java]
ignoreCaseSize=2
ignoreCase=[Java, SQL]
stringEquals=false
compareAsSame=true
normalized=[java, sql]
```

Trong đầu vào có năm lần xuất hiện. Chuỗi `"Java"` xuất hiện hai lần, còn ba cách viết `"Java"`, `"java"`, `"JAVA"` không bằng nhau theo `String.equals`.

Kết quả cần đọc như sau:

- `equalsSize=4`: `HashSet` chỉ gộp hai lần xuất hiện của đúng chuỗi `"Java"`.
- `naturalSize=4`: thứ tự tự nhiên của `String` cũng phân biệt những cách viết hoa thường đó.
- `natural=[JAVA, Java, SQL, java]`: đây là thứ tự tự nhiên của các chuỗi trong ví dụ, không phải quy tắc sắp xếp ngôn ngữ dành cho mọi giao diện người dùng.
- `ignoreCaseSize=2`: bộ so sánh không phân biệt hoa thường gộp ba cách viết của Java thành một phần tử.
- `stringEquals=false` nhưng `compareAsSame=true`: cùng một cặp chuỗi được hai cơ chế nhận diện khác nhau.
- `normalized=[java, sql]`: chương trình chủ động chuyển chuỗi sang chữ thường trước khi đưa vào `LinkedHashSet`.

### Chuẩn hóa khóa là một lựa chọn có chủ đích

Đoạn chuẩn hóa dùng `Locale.ROOT` để việc chuyển chữ thường không phụ thuộc ngôn ngữ mặc định của máy. Sau chuẩn hóa, tập chứa chính những chuỗi đã chuyển đổi, nên `equals` làm việc trên dạng đã chọn.

Đổi lại, kết quả không giữ nguyên cách viết ban đầu. Nếu cần giữ `"Java"` để hiển thị nhưng nhận diện trùng bằng khóa `"java"`, phải lưu cả khóa chuẩn hóa và giá trị đại diện, đồng thời quy định giữ cách viết đầu hay cách viết cuối.

Cũng không nên xem “chuyển chữ thường” là quy tắc chuẩn hóa phù hợp cho mọi loại dữ liệu. Mã định danh, tên người, địa chỉ và chuỗi hiển thị có thể có hợp đồng riêng. Điều cần rút ra là phải chọn quy tắc bằng nhau trước, rồi chọn cấu trúc thể hiện đúng quy tắc đó.

Một lỗi tương tự xảy ra khi dùng bộ so sánh chỉ xét độ dài chuỗi: hai tên khác nhau nhưng có cùng độ dài sẽ có kết quả so sánh `0`. Nếu mục tiêu chỉ là sắp các phần tử mà vẫn giữ mọi phần tử khác nhau, tiêu chí so sánh phải có cách phân biệt những trường hợp bằng nhau ở tiêu chí đầu, hoặc nên dùng `List` rồi sắp xếp thay vì biến thành `TreeSet`.

## 7. null và quyền sửa kết quả cũng thay đổi theo cách chuyển

Không có một quy tắc chung rằng mọi cách chuyển `List` sang `Set` đều chấp nhận `null`, hoặc mọi tập kết quả đều cho thêm phần tử.

| Cách tạo | Khi nguồn có nhiều null | Thêm hoặc xóa ở tập kết quả |
| --- | --- | --- |
| `new HashSet<>(source)` | Giữ tối đa một `null` | Được |
| `new LinkedHashSet<>(source)` | Giữ tối đa một `null`, ở vị trí gặp đầu tiên | Được |
| `new TreeSet<>(source)` theo thứ tự tự nhiên | Ném `NullPointerException` | Được nếu đã tạo thành công |
| `Set.copyOf(source)` | Ném `NullPointerException` | Không được |
| `Collections.unmodifiableSet(new LinkedHashSet<>(source))` | Tập nền giữ tối đa một `null` | Không được qua lớp bao |

Hàng về `TreeSet` nói riêng trường hợp thứ tự tự nhiên. Có thể cung cấp bộ so sánh xử lý `null` một cách tường minh; không suy ra rằng mọi cấu hình `TreeSet` đều có cùng cách xử lý.

`Set.copyOf` nhận một `Collection`, nên có thể nhận trực tiếp `List`. Nó chấp nhận phần tử trùng và giữ một phần tử đại diện tùy ý trong nhóm bằng nhau; nó không cam kết giữ đối tượng gặp trước. Kết quả không cho sửa cấu trúc, không chấp nhận phần tử `null` và không bảo đảm thứ tự duyệt. [Javadoc Set.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection))

Điểm “đại diện tùy ý” quan trọng khi phần tử là đối tượng như `Contact` trong phần trước: hai đối tượng có thể bằng nhau theo mã nhưng mang nhãn khác nhau. Không thay `new LinkedHashSet<>(source)` bằng `Set.copyOf(source)` rồi vẫn dựa vào việc giữ đúng đối tượng đầu.

### Thí nghiệm về null, loại trùng và tập chỉ đọc

Lưu vào `SetNullAndReadOnlyDemo.java`.

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class SetNullAndReadOnlyDemo {
    public static void main(String[] args) {
        List<String> withNull = Arrays.asList("A", null, "A", null, "B");
        Set<String> firstOrder = new LinkedHashSet<>(withNull);
        Set<String> hashed = new HashSet<>(withNull);
        System.out.println("firstOrder=" + firstOrder);
        System.out.println("hashSize=" + hashed.size());
        System.out.println("hashContainsNull=" + hashed.contains(null));

        try {
            new TreeSet<>(withNull);
        } catch (NullPointerException e) {
            System.out.println("naturalTree=NullPointerException");
        }
        try {
            Set.copyOf(withNull);
        } catch (NullPointerException e) {
            System.out.println("copyWithNull=NullPointerException");
        }

        Set<String> readOnly = Set.copyOf(List.of("B", "A", "B"));
        System.out.println("copySize=" + readOnly.size());
        System.out.println("copySortedForDisplay=" + new TreeSet<>(readOnly));
        try {
            readOnly.add("C");
        } catch (UnsupportedOperationException e) {
            System.out.println("copyAdd=UnsupportedOperationException");
        }

        Set<String> orderedReadOnly = Collections.unmodifiableSet(
                new LinkedHashSet<>(List.of("B", "A", "B")));
        System.out.println("orderedReadOnly=" + orderedReadOnly);
        try {
            Set.of("A", "A");
        } catch (IllegalArgumentException e) {
            System.out.println("ofDuplicate=IllegalArgumentException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 SetNullAndReadOnlyDemo.java
java SetNullAndReadOnlyDemo
```

Stdout:

```text
firstOrder=[A, null, B]
hashSize=3
hashContainsNull=true
naturalTree=NullPointerException
copyWithNull=NullPointerException
copySize=2
copySortedForDisplay=[A, B]
copyAdd=UnsupportedOperationException
orderedReadOnly=[B, A]
ofDuplicate=IllegalArgumentException
```

Trong phần đầu, danh sách nguồn được tạo bằng `Arrays.asList` để có thể chứa `null`. Dùng `List.of` tại vị trí này sẽ khiến chương trình gặp lỗi ngay khi tạo nguồn, trước khi kiểm chứng cách chuyển sang tập.

Kết quả xác nhận:

1. `LinkedHashSet` giữ `[A, null, B]`: hai `A` được gộp và hai `null` cũng được gộp.
2. `HashSet` có ba phần tử và chứa `null`. Chương trình kiểm tra kích thước và khả năng chứa thay vì dự đoán thứ tự in.
3. `TreeSet` theo thứ tự tự nhiên và `Set.copyOf` từ chối đầu vào có `null`.
4. `Set.copyOf(List.of("B", "A", "B"))` tạo được tập hai phần tử. Dòng `copySortedForDisplay` chỉ sắp xếp một bản phục vụ hiển thị.
5. Gọi `add` trên tập do `Set.copyOf` tạo ra ném `UnsupportedOperationException`.
6. Tập được bao bằng `Collections.unmodifiableSet` vẫn duyệt theo `LinkedHashSet` nền, nên cho `[B, A]`.
7. `Set.of("A", "A")` ném `IllegalArgumentException`; cách gọi này không có cùng chính sách với `Set.copyOf` khi gặp dữ liệu trùng.

Các khối `catch` trong chương trình in nhãn cố định của trường hợp đã bắt, thay vì in toàn bộ thông điệp ngoại lệ. Vì thế stdout không phụ thuộc đường dẫn máy hoặc chi tiết thông báo của bản JDK.

### “Không cho sửa cấu trúc” không có nghĩa là giữ thứ tự

Hai yêu cầu cần chọn riêng:

- `Set.copyOf` phù hợp khi cần một kết quả không cho sửa cấu trúc và không dựa vào thứ tự.
- Nếu cần giữ thứ tự gặp đầu tiên đồng thời không cho phía nhận thêm hoặc xóa, có thể tạo `LinkedHashSet` rồi bao bằng `Collections.unmodifiableSet`.

`Collections.unmodifiableSet` tạo một khung nhìn chỉ đọc của tập nền. Nếu một phần khác của chương trình vẫn giữ tập nền và sửa nó, khung nhìn phản ánh thay đổi đó. Vì vậy, để bảo vệ một ảnh chụp về cấu trúc, tạo bản sao nền riêng và không để lộ đường sửa bản sao đó. [Javadoc Collections.unmodifiableSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set))

Ví dụ trong chương trình tạo `LinkedHashSet` mới ngay bên trong lời gọi bao. Danh sách nguồn không phải tập nền của lớp bao. Tuy nhiên, phần tử có thể vẫn được dùng chung; cả lớp bao lẫn `Set.copyOf` đều không tự sao chép sâu đối tượng.

## 8. Dùng Stream vẫn phải chọn hợp đồng về thứ tự

Nếu đang có sẵn `List` và chỉ cần chuyển đổi trực tiếp, constructor thường đủ rõ:

```java
// Đoạn minh họa; source là List<String> đã có.
Set<String> unique = new LinkedHashSet<>(source);
```

Nếu còn cần lọc hoặc biến đổi phần tử trong một luồng, phải chọn cách thu thập phù hợp:

```java
// Đoạn minh họa; đặt trong phương thức có source và các import cần thiết.
Set<String> uniqueInFirstOrder = source.stream()
        .collect(Collectors.toCollection(LinkedHashSet::new));
```

Với luồng có thứ tự từ `List` trong ví dụ, kết quả giữ thứ tự gặp các giá trị lần đầu. Chương trình `ListToSetOrderDemo` đã kiểm chứng đúng biểu thức này.

Không thay biểu thức đó bằng `Collectors.toSet()` khi thứ tự là một phần của yêu cầu. `toSet()` không cam kết kiểu tập cụ thể, quyền sửa hoặc thứ tự gặp. Muốn chỉ định lớp chứa, dùng `toCollection` với hàm tạo tương ứng. [Javadoc Collectors.toSet và toCollection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html)

Ví dụ, một bước lọc có thể thay đổi những phần tử được gặp; một bước sắp xếp có thể thay đổi thứ tự được gặp. `LinkedHashSet` chỉ giữ thứ tự thực tế được đưa vào nó, không tự tìm lại thứ tự của danh sách ở một giai đoạn trước trong chuỗi xử lý.

Việc chọn Stream hay constructor vì thế là lựa chọn cách biểu diễn luồng công việc. Nó không làm mất đi yêu cầu phải xác định tiêu chí trùng, thứ tự và quyền sửa kết quả.

## 9. Khi số lần xuất hiện vẫn quan trọng, giữ thêm dữ liệu

Chuyển sang `Set` không phải cách đếm. Nếu đầu vào là `[B, A, B, C, A, B]`, tập các giá trị duy nhất chỉ còn `[B, A, C]`. Từ tập đó không biết `B` xuất hiện ba lần, `A` hai lần và `C` một lần.

Cũng cần phân biệt hai con số:

- **Số lần xuất hiện bị bỏ:** kích thước danh sách trừ kích thước tập duy nhất.
- **Số giá trị bị lặp:** có bao nhiêu giá trị khác nhau xuất hiện từ hai lần trở lên.

Với đầu vào trên, có ba lần xuất hiện bị bỏ nhưng chỉ có hai giá trị bị lặp là `B` và `A`.

Phương thức `add` của tập băm trả về `false` khi phần tử đã có và tập không thay đổi. Có thể dùng kết quả đó ngay trong lúc duyệt để phát hiện trùng, thay vì loại trùng xong mới cố suy ngược dữ liệu nguồn.

Lưu chương trình sau vào `DuplicatesAndCountsDemo.java`.

```java
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class DuplicatesAndCountsDemo {
    public static void main(String[] args) {
        List<String> source = List.of("B", "A", "B", "C", "A", "B");
        Set<String> seen = new LinkedHashSet<>();
        Set<String> repeated = new LinkedHashSet<>();
        Map<String, Integer> counts = new LinkedHashMap<>();

        for (String value : source) {
            if (!seen.add(value)) {
                repeated.add(value);
            }
            counts.put(value, counts.getOrDefault(value, 0) + 1);
        }

        System.out.println("sourceSize=" + source.size());
        System.out.println("uniqueFirstOrder=" + seen);
        System.out.println("repeatedValues=" + repeated);
        System.out.println("counts=" + counts);
        System.out.println("droppedOccurrences=" + (source.size() - seen.size()));
        System.out.println("repeatedValueCount=" + repeated.size());
        System.out.println("hasDuplicates=" + !repeated.isEmpty());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 DuplicatesAndCountsDemo.java
java DuplicatesAndCountsDemo
```

Stdout:

```text
sourceSize=6
uniqueFirstOrder=[B, A, C]
repeatedValues=[B, A]
counts={B=3, A=2, C=1}
droppedOccurrences=3
repeatedValueCount=2
hasDuplicates=true
```

Chương trình duy trì ba cấu trúc với ba mục đích riêng:

| Biến | Thông tin được giữ | Với đầu vào trong chương trình |
| --- | --- | --- |
| `seen` | Những giá trị đã gặp, theo lần gặp đầu tiên | `[B, A, C]` |
| `repeated` | Những giá trị đã gặp lại ít nhất một lần | `[B, A]` |
| `counts` | Số lần xuất hiện của từng giá trị | `{B=3, A=2, C=1}` |

Ở vòng lặp:

1. `seen.add(value)` thử ghi nhận một giá trị mới.
2. Nếu kết quả là `false`, giá trị đó đã từng được gặp, nên thêm vào `repeated`.
3. `counts` tăng bộ đếm ở mọi lần xuất hiện, kể cả lần lặp.

`LinkedHashMap` được dùng để bảng đếm in theo thứ tự các khóa xuất hiện lần đầu. Việc cập nhật bộ đếm cho khóa đã có không biến thứ tự đó thành thứ tự xuất hiện cuối.

Trong ví dụ này, thứ tự của `repeated` là thứ tự phát hiện các giá trị bị lặp: gặp lại `B` trước, rồi gặp lại `A`. Không suy rộng rằng thứ tự này luôn giống thứ tự gặp giá trị lần đầu. Chẳng hạn, ở dãy `[A, B, B, A]`, giá trị được phát hiện lặp trước là `B`, dù `A` xuất hiện đầu tiên trong nguồn.

### Phát hiện đầu vào không hợp lệ khác với tự động loại trùng

Nếu hợp đồng nói “mỗi mã chỉ được gửi một lần”, chuyển thẳng sang tập rồi tiếp tục xử lý sẽ che mất vi phạm. Lúc này nên kiểm tra và báo lỗi rõ ràng.

Với cùng tiêu chí bằng nhau của `HashSet` hoặc `LinkedHashSet`, so sánh kích thước nguồn với kích thước tập có thể cho biết có ít nhất một lần lặp. Nếu cần báo mã nào lặp, cách duyệt với `add` như chương trình trên cho phép giữ bằng chứng cần thiết.

Nếu dùng `TreeSet` với bộ so sánh khác `equals`, kích thước giảm có thể do hai phần tử khác nhau theo `equals` nhưng được bộ so sánh xem là một. Vì vậy, không lấy một `TreeSet` bất kỳ để kiểm tra “trùng theo equals”.

Nếu cần báo đầy đủ vị trí lỗi, phải ghi thêm chỉ số trong lúc duyệt danh sách. Tập chỉ lưu giá trị duy nhất không chứa đủ thông tin vị trí cho việc báo lỗi này.

## 10. Chọn cách chuyển trong tình huống thực tế

### Danh sách nhãn để hiển thị theo thứ tự người dùng nhập

Yêu cầu: bỏ nhãn trùng nhưng giữ nhãn gặp trước, thứ tự hiển thị ổn định theo đầu vào.

Chọn `LinkedHashSet`. Nếu giao diện sau đó vẫn cần một `List`, tạo `ArrayList` từ tập như chương trình đầu. Thống nhất trước việc khoảng trắng hoặc chữ hoa thường có làm hai nhãn được xem là khác nhau hay không; constructor không tự chuẩn hóa những chi tiết này.

### Tập mã để kiểm tra thành viên

Yêu cầu: cần trả lời “mã này có xuất hiện không?”, không dùng thứ tự duyệt làm dữ liệu đầu ra.

`HashSet` thường là lựa chọn trực tiếp khi `equals` và `hashCode` phù hợp. Các thao tác cơ bản có chi phí kỳ vọng hằng số khi hàm băm phân bố tốt; việc chuyển n phần tử thường có chi phí kỳ vọng tuyến tính trong điều kiện đó. Đây không phải cam kết mọi đầu vào đều có cùng thời gian thực thi.

Nếu còn cần danh sách gốc để thể hiện từng lần thao tác, giữ cả danh sách và tập tra cứu với vai trò riêng. Việc có thêm tập hỗ trợ không buộc phải xóa danh sách.

### Các giá trị duy nhất cần sắp xếp

Yêu cầu: chỉ một phần tử cho mỗi giá trị theo quy tắc đã chọn, đồng thời duyệt có thứ tự.

Chọn `TreeSet` với thứ tự tự nhiên hoặc bộ so sánh phù hợp. Với cách thêm từng phần tử, các thao tác thêm có chi phí logarit theo kích thước tập; chuyển n phần tử thường được xét ở mức O(n log n), ngoài chi phí so sánh thực tế.

Nếu mọi lần xuất hiện đều phải còn, giữ `List` và sắp xếp danh sách. Sắp xếp không tự yêu cầu loại trùng.

### Dữ liệu thống kê hoặc giao dịch

Yêu cầu: cùng một mã có thể xuất hiện nhiều lần và mỗi lần ảnh hưởng kết quả.

Giữ `List`, hoặc tạo `Map` đếm số lần, hoặc giữ từng bản ghi với số lượng tương ứng. Chỉ giữ `Set` khi câu hỏi thực sự chỉ cần sự có mặt.

Ví dụ, một giỏ hàng biểu diễn mỗi lần quét là một phần tử không thể chuyển sang tập rồi dùng kích thước tập làm tổng số sản phẩm. Hai lần quét cùng mã có thể là hai đơn vị hàng, không phải dữ liệu lỗi.

### Danh sách đối tượng cần chọn bản ghi đại diện

Yêu cầu: cùng mã nghiệp vụ chỉ giữ một bản ghi nhưng các bản ghi có thể mang dữ liệu khác nhau.

Trước hết chọn chính sách: bản đầu, bản cuối, bản có thời gian mới nhất hay báo xung đột. `LinkedHashSet` phù hợp với việc giữ đối tượng bằng nhau gặp trước khi `equals` đúng tiêu chí. Những chính sách khác cần được biểu diễn rõ, thường bằng việc xử lý theo khóa trong `Map`.

Không để tình cờ của thứ tự nguồn hoặc cách triển khai tập trở thành chính sách nghiệp vụ mà người đọc mã không thấy.

## 11. Những lỗi cần nhận ra khi đọc hoặc sửa mã

| Cách nghĩ hoặc cách viết dễ sai | Hệ quả | Cách sửa theo yêu cầu |
| --- | --- | --- |
| “Set nào cũng giữ thứ tự List” | Thứ tự đầu ra phụ thuộc kiểu tập, có thể không được bảo đảm | Chọn `LinkedHashSet` khi cần lần xuất hiện đầu |
| “HashSet in đúng thứ tự ở máy tôi là đủ” | Đặt yêu cầu lên hành vi không có cam kết | Kiểm tra hợp đồng API; sắp xếp riêng nếu cần hiển thị có thứ tự |
| “Chuyển Set về List sẽ có lại nguồn” | Không thể khôi phục số lần hoặc vị trí đã bỏ | Giữ nguồn hoặc lưu thông tin cần thiết trước khi chuyển |
| “Cùng dữ liệu nhìn thấy thì Set tự gộp” | Lớp có thể chưa có `equals` và `hashCode` theo tiêu chí cần dùng | Định nghĩa tiêu chí bằng nhau hoặc chuyển sang khóa phù hợp |
| “Trùng mã nghĩa là giữ bản ghi cuối” | `LinkedHashSet` không tự thay đối tượng đầu bằng đối tượng sau | Dùng chính sách lựa chọn đại diện tường minh |
| “Comparator chỉ ảnh hưởng cách sắp xếp” | `compare(a, b) == 0` cũng quyết định loại trùng trong `TreeSet` | Kiểm tra tiêu chí so sánh và tính nhất quán với `equals` |
| “Set.copyOf nhận dữ liệu trùng thì phải ném lỗi” | Nhầm với `Set.of`; không hiểu phần tử đại diện | Phân biệt hai API và kiểm tra yêu cầu về trùng |
| “Có Set mới là phần tử đã được sao chép” | Sửa đối tượng có thể nhìn thấy từ cả hai cấu trúc | Dùng phần tử bất biến hoặc quy tắc sao chép riêng |
| “Tập chỉ đọc sẽ giữ thứ tự hiện có” | Quyền sửa và thứ tự là hai hợp đồng khác nhau | Chọn cả kiểu tập và cách bảo vệ kết quả |
| “Loại trùng xong vẫn đếm được số lần” | Chỉ còn sự có mặt, mất tần suất | Đếm khi còn dữ liệu gốc hoặc giữ bảng đếm |

Khi nguồn rỗng, các cách chuyển hợp lệ cho ra tập rỗng. Khi chính tham chiếu nguồn là `null`, đó là trường hợp khác với danh sách có một phần tử `null`; cần xử lý đầu vào theo hợp đồng của phương thức nhận dữ liệu. Không dùng quy tắc “HashSet chứa được null” để kết luận rằng constructor có thể nhận một `Collection` nguồn là `null`.

## 12. Thực hành: dự đoán đúng dữ liệu còn lại

### Bài 1: một nguồn, hai quy tắc thứ tự

Cho danh sách `[C, A, C, B, A]`. Dự đoán kết quả khi chuyển sang `LinkedHashSet` và `TreeSet` theo thứ tự tự nhiên. Có thể dự đoán chính xác thứ tự in trực tiếp của `HashSet` từ hợp đồng API hay không?

**Đối chiếu:**

- `LinkedHashSet`: `[C, A, B]`.
- `TreeSet`: `[A, B, C]`.
- `HashSet`: có ba phần tử `A`, `B`, `C`, nhưng không dự đoán thứ tự in dựa vào hợp đồng.
- Cả ba không còn cho biết số lần và vị trí xuất hiện của từng chữ trong nguồn.

### Bài 2: số lần bị bỏ và số giá trị bị lặp

Cho danh sách `[A, A, A, B, B, C]`. Nếu loại trùng theo `String.equals`, có bao nhiêu lần xuất hiện bị bỏ? Có bao nhiêu giá trị bị lặp?

**Đối chiếu:**

Nguồn có sáu phần tử và ba giá trị duy nhất, nên có ba lần xuất hiện bị bỏ. Hai giá trị bị lặp là `A` và `B`. Muốn biết riêng số lần của từng giá trị, cần nguồn hoặc bảng đếm; tập `[A, B, C]` không đủ.

### Bài 3: thứ tự phát hiện trùng

Thay đầu vào của `DuplicatesAndCountsDemo` bằng `List.of("A", "B", "B", "A")`. Trước khi chạy, viết kết quả của `seen`, `repeated` và `counts`.

**Đối chiếu:**

- `seen` có thứ tự `[A, B]`.
- `repeated` có thứ tự `[B, A]`, vì lần lặp của `B` được phát hiện trước.
- `counts` có nội dung và thứ tự `{A=2, B=2}`.
- Có hai lần xuất hiện bị bỏ và hai giá trị bị lặp.

Bài này kiểm tra việc không đánh đồng thứ tự gặp đầu tiên với thứ tự phát hiện lặp.

### Bài 4: chọn một đối tượng theo mã

Hai đối tượng liên hệ cùng `id=1` có nhãn `old` và `new`; nguồn đưa `old` trước. `equals` và `hashCode` chỉ dựa trên `id`. Sau khi chuyển sang `LinkedHashSet`, nhãn nào được giữ? Nếu muốn giữ `new`, đổi sang `Set.copyOf` có giải quyết được yêu cầu không?

**Đối chiếu:**

`LinkedHashSet` giữ đối tượng mang nhãn `old`. `Set.copyOf` không cam kết giữ đối tượng sau cùng nên không diễn đạt yêu cầu “giữ new”. Cần viết chính sách chọn bản ghi cuối hoặc bản ghi mới nhất một cách rõ ràng, chẳng hạn khi đưa dữ liệu vào `Map` theo `id`.

### Bài 5: dữ liệu không được phép mất lần xuất hiện

Danh sách `[P1, P1, P2]` biểu diễn ba lần quét hàng. Phần xử lý chỉ nhận tập `{P1, P2}`. Có thể tính đúng tổng ba đơn vị hàng từ tập đó mà không có dữ liệu khác không?

**Đối chiếu:**

Không. Tập này cũng có thể đến từ `[P1, P2]` hoặc rất nhiều danh sách dài hơn. Cần giữ các lần quét hoặc truyền kèm số lượng, ví dụ `P1 → 2`, `P2 → 1`.

### Bài 6: điều kiện nghiệm thu một phép chuyển

Tự chọn một đầu vào có phần tử lặp và viết chương trình kiểm chứng:

1. Kích thước trước và sau chuyển.
2. Quy tắc nhận diện trùng.
3. Thứ tự duyệt có phải yêu cầu bắt buộc hay không.
4. Đối tượng nào được giữ khi các đối tượng bằng nhau.
5. Kết quả có cho sửa cấu trúc không.
6. Thêm hoặc xóa ở nguồn có tác động đến tập không.
7. Sửa trạng thái đối tượng được dùng chung có tác động gì.

Một lời giải đạt yêu cầu phải giải thích được vì sao chọn kiểu tập đó. Chỉ in một tập có vẻ đúng trên một lần chạy chưa chứng minh được rằng chương trình giữ đúng hợp đồng về trùng lặp và thứ tự.
