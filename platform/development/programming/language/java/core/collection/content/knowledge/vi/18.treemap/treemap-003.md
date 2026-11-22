# TreeMap: Comparator, compareTo và khóa được xem là trùng

## 1. Một quy tắc so sánh quyết định cả thứ tự lẫn danh tính khóa

`TreeMap` lưu các cặp khóa–giá trị và duyệt khóa theo thứ tự đã chọn. Ví dụ, ta có thể muốn tra dữ liệu của một phiên bản phần mềm và đồng thời duyệt các phiên bản từ thấp đến cao. Một map có thứ tự như vậy cần biết khóa nào đứng trước khóa nào.

Điểm dễ bỏ sót là: trong `TreeMap`, quy tắc so sánh còn quyết định **hai khóa có được xem là cùng một khóa hay không**. Nó không chỉ được dùng lúc in hoặc sắp xếp kết quả cuối cùng.

Giả sử một comparator chỉ so sánh độ dài chuỗi. Hai chuỗi `"cat"` và `"dog"` có nội dung khác nhau, nhưng comparator trả về 0 vì cùng dài ba ký tự. Đưa lần lượt chúng vào cùng `TreeMap` sẽ tác động đến cùng một mapping theo cách nhìn của map. Nếu muốn giữ cả hai như hai khóa riêng, quy tắc so sánh cần phân biệt chúng.

Bài học sẽ đi theo ba câu hỏi:

1. `TreeMap` lấy quy tắc so sánh từ `Comparable.compareTo` hay từ `Comparator.compare`?
2. Kết quả âm, 0, dương có ý nghĩa gì khi tìm và cập nhật khóa?
3. Làm thế nào thiết kế quy tắc so sánh để không vô tình gộp các khóa cần giữ riêng?

Ở đây, “khóa trùng” có nghĩa **trùng theo thứ tự của chính map**, không phải cùng tham chiếu đối tượng. Việc nó có đồng thời trùng theo `equals` hay không là một yêu cầu thiết kế cần kiểm tra.

## 2. Hai nguồn cung cấp thứ tự

### 2.1. Comparable và thứ tự tự nhiên của kiểu

Một kiểu triển khai `Comparable<T>` cung cấp phương thức `compareTo(T other)`. Đây là thứ tự tự nhiên mà kiểu đó công bố. Ví dụ, một kiểu `Version` có thể quy định so số phiên bản lớn trước, rồi số phiên bản nhỏ nếu phần lớn bằng nhau.

Trong ví dụ `Version` phía dưới, `compareTo` so phần phiên bản lớn trước, rồi so phần nhỏ. Khả năng so sánh này được khai báo trực tiếp trên kiểu khóa.

Khi tạo `new TreeMap<K, V>()`, map dùng thứ tự tự nhiên của khóa. Các khóa phải có khả năng so sánh với nhau theo thứ tự đó. Generics không tự kiểm tra tất cả điều kiện này ngay ở nơi khai báo `TreeMap`: một lớp không triển khai `Comparable` vẫn có thể xuất hiện trong khai báo kiểu, rồi gây lỗi khi map phải so sánh khóa.

### 2.2. Comparator là quy tắc được truyền từ bên ngoài

`Comparator<T>` cung cấp `compare(T left, T right)`. Nó phù hợp khi muốn chọn thứ tự riêng cho một map, khi kiểu khóa không thể sửa, hoặc khi cùng một kiểu cần nhiều cách sắp thứ tự.

Đoạn minh họa bên trong một phương thức:

```java
Comparator<String> byLength = Comparator.comparingInt(String::length);
TreeMap<String, Integer> map = new TreeMap<>(byLength);
```

Map này dùng `byLength` để so khóa. Nó không tự gọi thêm `String.compareTo` khi độ dài bằng nhau. Nếu muốn có tiêu chí phụ theo nội dung chuỗi, phải ghi rõ tiêu chí đó trong comparator.

Một comparator có thể sử dụng `compareTo` ở bên trong, chẳng hạn `Comparator.naturalOrder()`. Nhưng đó là lựa chọn trong cài đặt comparator; không có hai vòng độc lập kiểu “comparator cho thứ tự, equals cho trùng khóa” ở `TreeMap`.

### 2.3. Constructor chọn một quy tắc có hiệu lực

| Cách tạo map | Nguồn thứ tự | `map.comparator()` |
|---|---|---|
| `new TreeMap<>()` | Thứ tự tự nhiên của khóa | `null` |
| `new TreeMap<>(comparator)` với comparator khác `null` | Comparator được cung cấp | Comparator đó |
| Constructor nhận comparator `null` | Thứ tự tự nhiên | `null` |

`comparator() == null` không có nghĩa map không được sắp thứ tự. Nó cho biết map dùng thứ tự tự nhiên. Nếu đã có comparator khác `null`, kiểu khóa không bắt buộc tự triển khai `Comparable`, miễn comparator so sánh hợp lệ mọi khóa được đưa vào.

Ví dụ, một record có hai trường không tự sinh `compareTo` chỉ vì nó là record. Record có thể tự sinh `equals` theo các thành phần, nhưng khả năng so thứ tự vẫn phải được khai báo hoặc được cung cấp qua comparator.

## 3. Đọc kết quả so sánh theo dấu

Cả `compareTo` lẫn `compare` trả một số nguyên:

| Kết quả | Ý nghĩa trong thứ tự được chọn |
|---|---|
| `< 0` | Khóa bên trái đứng trước khóa bên phải |
| `== 0` | Hai khóa tương đương theo thứ tự |
| `> 0` | Khóa bên trái đứng sau khóa bên phải |

API chỉ yêu cầu **dấu** của kết quả. Không được kiểm tra chung mọi comparator bằng `result == -1` hoặc `result == 1`. Một cài đặt hợp lệ có thể trả một số âm hoặc dương khác. Cách kiểm tra đúng cho quan hệ trước–sau là so với 0.

“Đứng trước” cũng không luôn đồng nghĩa “giá trị số nhỏ hơn”. Với comparator đảo thứ tự số, số 10 có thể đứng trước số 2. Ý nghĩa đầu/cuối và trước/sau của map đều theo quy tắc đang dùng.

### 3.1. Cách tìm kiếm được hình dung qua cây

Không cần tự cài cây để hiểu ảnh hưởng của comparator. Có thể hình dung ở mỗi khóa đang xét, map lấy kết quả so sánh để quyết định:

```text
So khóa cần tìm với khóa đang xét
    ├─ âm   → tiếp tục theo phía khóa đứng trước
    ├─ dương → tiếp tục theo phía khóa đứng sau
    └─ bằng 0 → đã gặp khóa được xem là tương đương
```

`TreeMap` thực tế dùng cây đỏ–đen để duy trì cấu trúc cân bằng. Chi tiết xoay cây không làm thay đổi quy tắc nhận diện khóa: kết quả so sánh bằng 0 là trường hợp gặp cùng khóa theo thứ tự. Đây không phải việc sắp lại một danh sách sau khi đã lưu tất cả đối tượng riêng biệt.

### 3.2. Kết quả bằng 0 chi phối các thao tác theo khóa

Giả sử `compare(a, b) == 0` theo quy tắc của map:

| Thao tác | Điều cần dự đoán |
|---|---|
| `put(a, v1)` rồi `put(b, v2)` | Lần sau cập nhật mapping tương đương; không tăng số mapping chỉ vì b là đối tượng khác |
| `get(b)` khi đã có a | Có thể tìm mapping của a theo so sánh bằng 0 |
| `containsKey(b)` khi đã có a | Nhận diện cùng nhóm khóa tương đương |
| `remove(b)` khi đã có a | Có thể loại mapping mà a đã tạo |

Các từ “tương đương” trong bảng không nói đến giá trị `V`. TreeMap sắp và nhận diện **khóa K**. Hai giá trị bằng nhau không làm hai khóa khác nhau bị gộp; hai giá trị khác nhau cũng không cứu được hai khóa mà comparator đã xem là tương đương.

### 3.3. Không nhầm với hash collision

Khóa có cùng mã băm trong `HashMap` chưa có nghĩa là cùng khóa; cấu trúc băm còn xét phép bằng nhau theo hợp đồng của nó. `TreeMap` dùng phép so sánh thứ tự cho việc nhận diện khóa, không dùng `hashCode` để quyết định các khóa đi về đâu.

Vì vậy, sửa `hashCode` không giải quyết việc comparator trả 0 cho hai khóa cần giữ riêng. Ngược lại, cài `equals` rất đầy đủ nhưng comparator bỏ sót một thành phần quan trọng vẫn có thể làm `TreeMap` cập nhật nhầm nhóm khóa theo ý định ứng dụng.

## 4. Chương trình 1: compareTo xác định thứ tự tự nhiên và khóa trùng

Lưu chương trình đầy đủ vào `TreeMapComparableDemo.java`. Ví dụ tương thích Java 17 trở lên. `Version` là record có hai thành phần số; `equals` do record cung cấp xét cả hai thành phần, và `compareTo` cũng xét cả hai.

```java
import java.util.Comparator;
import java.util.TreeMap;

public class TreeMapComparableDemo {
    record Version(int major, int minor) implements Comparable<Version> {
        @Override
        public int compareTo(Version other) {
            int result = Integer.compare(major, other.major);
            return result != 0 ? result : Integer.compare(minor, other.minor);
        }

        @Override
        public String toString() {
            return major + "." + minor;
        }
    }

    public static void main(String[] args) {
        Version first = new Version(1, 2);
        Version later = new Version(1, 10);
        Version same = new Version(1, 2);
        System.out.println("sameReference=" + (first == same));
        System.out.println("sameEquals=" + first.equals(same));
        System.out.println("sameCompare=" + first.compareTo(same));
        System.out.println("firstBeforeLater=" + (first.compareTo(later) < 0));

        TreeMap<Version, String> natural = new TreeMap<>();
        natural.put(later, "later");
        natural.put(first, "initial");
        natural.put(new Version(2, 0), "major-two");
        System.out.println("oldValue=" + natural.put(same, "updated"));
        System.out.println("natural=" + natural);
        System.out.println("naturalSize=" + natural.size());
        System.out.println("lookup=" + natural.get(new Version(1, 2)));
        System.out.println("usesNaturalOrder=" + (natural.comparator() == null));

        TreeMap<Version, String> reverse =
                new TreeMap<>(Comparator.reverseOrder());
        reverse.putAll(natural);
        System.out.println("reverseKeys=" + reverse.keySet());
        System.out.println("reverseDuplicateCompare="
                + reverse.comparator().compare(first, same));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 TreeMapComparableDemo.java
java TreeMapComparableDemo
```

Stdout:

```text
sameReference=false
sameEquals=true
sameCompare=0
firstBeforeLater=true
oldValue=initial
natural={1.2=updated, 1.10=later, 2.0=major-two}
naturalSize=3
lookup=updated
usesNaturalOrder=true
reverseKeys=[2.0, 1.10, 1.2]
reverseDuplicateCompare=0
```

### 4.1. Khác đối tượng vẫn có thể là cùng khóa

`first` và `same` được tạo bằng hai lời gọi constructor nên `sameReference=false`. Tuy nhiên, chúng cùng biểu diễn 1.2, `equals` trả `true` và `compareTo` trả 0. Lần `put(same, "updated")` cập nhật mapping mà `first` đã tạo, trả về giá trị cũ `initial`.

Map có ba nhóm khóa: 1.2, 1.10 và 2.0. Số lần gọi `put` là bốn nhưng số mapping là ba. `get(new Version(1, 2))` tìm thấy `updated` mà không cần dùng đúng đối tượng đã truyền vào lần chèn đầu.

Đó là hành vi mong muốn khi khóa biểu diễn một giá trị: không cần giữ lại cùng một tham chiếu để có thể tìm dữ liệu.

### 4.2. So sánh từng thành phần, không so chuỗi hiển thị

`compareTo` so `major` trước. Chỉ khi `major` bằng nhau mới so `minor`. Do đó 1.2 đứng trước 1.10 vì 2 nhỏ hơn 10. Chương trình không chuyển khóa thành chuỗi rồi so `"1.2"` với `"1.10"` theo thứ tự ký tự.

Phương thức `toString` chỉ làm dòng in dễ đọc; nó không được `TreeMap` gọi làm quy tắc so sánh khóa. Cài đặt dùng `Integer.compare`, tránh lấy hiệu hai số có thể tràn miền giá trị.

### 4.3. Đảo thứ tự không tách khóa đã tương đương

Map thứ hai nhận `Comparator.reverseOrder()` và duyệt `[2.0, 1.10, 1.2]`. Nó vẫn coi hai phiên bản 1.2 là tương đương, nên `reverseDuplicateCompare=0`.

Đảo chiều thay quan hệ trước/sau; nó không biến các cặp bằng nhau theo so sánh thành khác nhau. Nếu comparator ban đầu làm hai khóa cần giữ riêng bị gộp, thêm `.reversed()` không sửa được lỗi đó.

## 5. Comparator trả 0 nhưng equals trả false

### 5.1. Cần phân biệt hai quan hệ bằng nhau

Với hai khóa hợp lệ a và b, quy tắc thứ tự được gọi là **nhất quán với equals** khi:

```text
compare(a, b) == 0  ⇔  a.equals(b)
```

Dấu hai chiều rất quan trọng. Không chỉ cần `equals=true` thì so sánh bằng 0; cũng cần so sánh bằng 0 thì `equals=true`. Nếu chỉ thỏa một chiều, khái niệm cùng khóa theo map có thể khác với khái niệm cùng đối tượng giá trị ở những API khác.

Tài liệu [TreeMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html) giải thích rằng map dùng so sánh cho mọi khóa. Một thứ tự không nhất quán với `equals` vẫn có thể cho hành vi tìm/cập nhật theo comparator được xác định, nhưng map không còn tuân thủ đầy đủ hợp đồng chung của `Map` dựa trên `equals`.

Không nên hiểu điều này thành “TreeMap luôn kiểm tra equals sau khi comparator trả 0” hoặc “TreeMap sẽ tự ném ngoại lệ khi hai quan hệ khác nhau”. Nó tiếp tục làm việc theo so sánh của mình.

### 5.2. Ví dụ không phân biệt hoa thường

`String.CASE_INSENSITIVE_ORDER` xem `"Java"`, `"JAVA"`, `"java"` là tương đương về thứ tự, trong khi `String.equals` phân biệt nội dung chữ hoa/chữ thường. Đây là ví dụ dễ quan sát việc comparator quyết định khóa trùng.

Lưu chương trình đầy đủ vào `TreeMapCaseInsensitiveDemo.java`:

```java
import java.util.Comparator;
import java.util.HashMap;
import java.util.Map;
import java.util.TreeMap;

public class TreeMapCaseInsensitiveDemo {
    public static void main(String[] args) {
        String first = new String("Java");
        String second = new String("JAVA");
        Comparator<String> order = String.CASE_INSENSITIVE_ORDER;
        System.out.println("stringEquals=" + first.equals(second));
        System.out.println("comparison=" + order.compare(first, second));

        TreeMap<String, String> map = new TreeMap<>(order);
        map.put(first, "initial");
        System.out.println("oldValue=" + map.put(second, "updated"));
        System.out.println("size=" + map.size());
        System.out.println("storedKeys=" + map.keySet());
        System.out.println("getLowercase=" + map.get("java"));
        System.out.println("containsMixedCase=" + map.containsKey("jAvA"));
        System.out.println("removed=" + map.remove("jAvA"));
        System.out.println("sizeAfterRemove=" + map.size());

        Map<String, Integer> tree = new TreeMap<>(order);
        Map<String, Integer> hash = new HashMap<>();
        tree.put("Java", 1);
        hash.put("JAVA", 1);
        System.out.println("treeEqualsHash=" + tree.equals(hash));
        System.out.println("hashEqualsTree=" + hash.equals(tree));

        TreeMap<String, String> nullFriendly =
                new TreeMap<>(Comparator.nullsFirst(order));
        nullFriendly.put(null, "null-key");
        nullFriendly.put("A", null);
        System.out.println("nullFriendlyKeys=" + nullFriendly.keySet());
        System.out.println("nullKeyValue=" + nullFriendly.get(null));
        System.out.println("getLowercaseNullValue=" + nullFriendly.get("a"));
        System.out.println("containsLowercaseA=" + nullFriendly.containsKey("a"));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 TreeMapCaseInsensitiveDemo.java
java TreeMapCaseInsensitiveDemo
```

Stdout:

```text
stringEquals=false
comparison=0
oldValue=initial
size=1
storedKeys=[Java]
getLowercase=updated
containsMixedCase=true
removed=updated
sizeAfterRemove=0
treeEqualsHash=false
hashEqualsTree=true
nullFriendlyKeys=[null, A]
nullKeyValue=null-key
getLowercaseNullValue=null
containsLowercaseA=true
```

### 5.3. Thay giá trị, tìm và xóa bằng một biến thể khác

`stringEquals=false` nhưng `comparison=0`. Sau hai lần `put`, `size=1`; giá trị cũ `initial` được trả ra và mapping nhận giá trị mới `updated`.

Trong lần chạy này, `storedKeys=[Java]` cho thấy dạng khóa được giữ để duyệt vẫn là `Java`, dù giá trị đã được cập nhật bằng lời gọi dùng `JAVA`. Không nên dùng việc cập nhật một khóa tương đương làm cơ chế chuẩn hóa cách viết khóa đang hiển thị, hay dựa vào danh tính đối tượng khóa để quyết định logic nghiệp vụ. Nếu cần một dạng khóa chuẩn, hãy tạo và dùng dạng đó rõ ràng trước khi lưu.

`get("java")`, `containsKey("jAvA")` và `remove("jAvA")` đều nhận diện cùng mapping. Sau remove, map rỗng. Phạm vi của quan hệ tương đương không chỉ nằm ở lệnh chèn thứ hai; nó đi theo các thao tác tra và loại khóa.

### 5.4. Hệ quả khi so sánh với map khác

Phần `treeEqualsHash=false` nhưng `hashEqualsTree=true` cho thấy một biểu hiện cụ thể của việc vi phạm hợp đồng chung. Hai map giữ các khóa `Java` và `JAVA`; khi các hướng so sánh tra cứu theo các quy tắc khóa khác nhau, kết quả phép bằng nhau có thể mất tính đối xứng.

Ở chiều `tree.equals(hash)`, khóa Java của tree được tra trong hash và không trùng JAVA theo `String.equals`. Ở chiều `hash.equals(tree)`, khóa JAVA lại được tra trong tree và khớp Java theo comparator. Đây không phải một bảo đảm nên khai thác trong chương trình. Ví dụ cố ý cho thấy vì sao lời cảnh báo về tính nhất quán với `equals` có ảnh hưởng thực tế, thay vì chỉ là một yêu cầu hình thức. Với map dùng chung qua các API tổng quát, nên thiết kế kiểu khóa và quy tắc so sánh đồng thuận về thế nào là cùng khóa.

Nếu nghiệp vụ thật sự coi mọi biến thể hoa thường là cùng mã, một lựa chọn là xác định dạng chuẩn ở ranh giới nhập dữ liệu hoặc tạo một kiểu khóa có `equals`, `hashCode`, thứ tự cùng dựa trên dạng chuẩn đó. Quy tắc chuẩn hóa phải được chọn theo miền dữ liệu; comparator không tự sửa `String.equals` và cũng không thay thế một chính sách chuẩn hóa được mô tả rõ.

### 5.5. null của khóa và null của giá trị là hai điều khác nhau

Cuối chương trình, `Comparator.nullsFirst(order)` bổ sung quy tắc cho khóa `null`: `null` đứng trước khóa khác `null`, còn hai khóa khác `null` được so bằng comparator đã chọn. Nhờ vậy map có thể giữ khóa `null` trong ví dụ này.

`new TreeMap<>()` dùng thứ tự tự nhiên không cho phép khóa `null`. Một comparator khác không xử lý `null` cũng có thể từ chối nó. Vì vậy không có quy tắc chung rằng mọi `TreeMap` đều nhận hoặc mọi `TreeMap` đều từ chối khóa `null`; điều đó phụ thuộc quy tắc thứ tự.

Giá trị `null` không tham gia so thứ tự khóa. Mapping `A → null` vẫn tồn tại; `get("a")` trả `null` và `containsKey("a")` là `true` theo comparator không phân biệt hoa thường. Kết quả `get == null` không tự chứng minh rằng khóa không có.

## 6. Chương trình 3: tiêu chí phụ quyết định có giữ riêng hai khóa không

### 6.1. Chỉ so độ ưu tiên sẽ gộp các mã cùng mức

Giả sử khóa `Ticket` có hai thành phần: `priority` là độ ưu tiên và `code` là mã. Nếu comparator chỉ nhìn `priority`, hai ticket 1:A và 1:B sẽ được xem là cùng khóa dù record `equals` thấy chúng khác nhau.

Đây không phải lỗi của `Comparator.comparingInt`. Nó đã thực hiện đúng tiêu chí được yêu cầu. Vấn đề là tiêu chí đó chưa thể hiện đủ quan hệ phân biệt khóa mà ứng dụng mong muốn.

Khi muốn thứ tự ưu tiên trước, mã sau, có thể nối tiêu chí bằng `thenComparing`. Tiêu chí sau chỉ được dùng khi tiêu chí trước trả 0; nó không thay đổi kết quả trước/sau đã phân biệt được ở tiêu chí trước.

Lưu chương trình đầy đủ vào `TreeMapComparatorChainDemo.java`:

```java
import java.util.Comparator;
import java.util.Objects;
import java.util.TreeMap;

public class TreeMapComparatorChainDemo {
    record Ticket(int priority, String code) {
        Ticket {
            Objects.requireNonNull(code, "code");
        }

        @Override
        public String toString() {
            return priority + ":" + code;
        }
    }

    public static void main(String[] args) {
        Ticket a = new Ticket(1, "A");
        Ticket b = new Ticket(1, "B");
        Comparator<Ticket> byPriority =
                Comparator.comparingInt(Ticket::priority);

        System.out.println("aEqualsB=" + a.equals(b));
        System.out.println("priorityCompare=" + byPriority.compare(a, b));
        TreeMap<Ticket, String> collapsed = new TreeMap<>(byPriority);
        collapsed.put(a, "alpha");
        System.out.println("collapsedOld=" + collapsed.put(b, "beta"));
        System.out.println("collapsed=" + collapsed);
        System.out.println("collapsedSize=" + collapsed.size());
        System.out.println("lookupA=" + collapsed.get(a));
        System.out.println("reverseStillEqual="
                + (byPriority.reversed().compare(a, b) == 0));

        Comparator<Ticket> fullOrder =
                byPriority.thenComparing(Ticket::code);
        TreeMap<Ticket, String> complete = new TreeMap<>(fullOrder);
        complete.put(new Ticket(2, "C"), "gamma");
        complete.put(b, "beta");
        complete.put(a, "alpha");
        System.out.println("complete=" + complete);
        System.out.println("completeSize=" + complete.size());
        System.out.println("lookupB=" + complete.get(new Ticket(1, "B")));
        System.out.println("sameKeyOld="
                + complete.put(new Ticket(1, "B"), "beta-2"));
        System.out.println("sizeAfterSameKey=" + complete.size());
        System.out.println("completeAfterUpdate=" + complete);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 TreeMapComparatorChainDemo.java
java TreeMapComparatorChainDemo
```

Stdout:

```text
aEqualsB=false
priorityCompare=0
collapsedOld=alpha
collapsed={1:A=beta}
collapsedSize=1
lookupA=beta
reverseStillEqual=true
complete={1:A=alpha, 1:B=beta, 2:C=gamma}
completeSize=3
lookupB=beta
sameKeyOld=beta
sizeAfterSameKey=3
completeAfterUpdate={1:A=alpha, 1:B=beta-2, 2:C=gamma}
```

### 6.2. Đọc kết quả của map chỉ có một tiêu chí

`aEqualsB=false` nhưng `priorityCompare=0`. Lần thêm b trả giá trị cũ `alpha`, map chỉ có một mapping và `lookupA=beta`. Nghĩa là ứng dụng không còn hai chỗ độc lập để lưu dữ liệu alpha và beta theo hai mã.

Dòng `collapsed={1:A=beta}` là kết quả đã quan sát: entry được hiển thị bằng khóa 1:A nhưng giá trị đã được cập nhật bởi lần put dùng 1:B. Nếu chỉ nhìn cột khóa để suy ra giá trị luôn được tạo từ đúng đối tượng khóa ban đầu, có thể hiểu sai dữ liệu.

`reverseStillEqual=true` tiếp tục cho thấy đổi chiều không làm hai khóa ưu tiên bằng nhau trở thành khác nhau.

### 6.3. thenComparing làm rõ điều kiện trả 0

Comparator đầy đủ có logic:

```text
So priority
    ├─ khác nhau → dùng kết quả đó
    └─ bằng nhau → so code
                     ├─ khác nhau → phân biệt hai khóa
                     └─ bằng nhau → trả 0
```

Với record trong bài, `equals` xét đúng hai thành phần `priority` và `code`; `code` được kiểm tra khác `null` khi tạo. Comparator cũng chỉ trả 0 khi cả hai thành phần bằng nhau. Vì vậy thứ tự này nhất quán với `equals` trên miền khóa đó.

Map giữ đủ ba mapping `{1:A=alpha, 1:B=beta, 2:C=gamma}`. Thêm một đối tượng mới cũng biểu diễn 1:B vẫn cập nhật mapping 1:B, trả `beta`, giữ kích thước ba và không đụng đến 1:A.

### 6.4. Chọn tiêu chí phụ theo danh tính khóa, không theo nhu cầu làm khác bất kỳ

Không phải cứ thêm một tiêu chí bất kỳ là tốt. Nếu nối `System.identityHashCode` hoặc một số ngẫu nhiên chỉ để tránh 0, hai đối tượng biểu diễn cùng một khóa nghiệp vụ có thể bị tách ra. Khi đó tạo lại đối tượng khóa để tra cứu có thể không còn tìm đúng nhóm tương đương mong muốn.

Mã định danh cần ổn định và phù hợp với khái niệm cùng khóa. Trong ví dụ này, cặp `priority, code` là toàn bộ giá trị của khóa. Nếu trong mô hình khác chỉ `code` mới là danh tính, còn priority thay đổi độc lập, có thể cần dùng code làm khóa tra cứu và lưu priority ở phần dữ liệu, hoặc thiết kế một chỉ mục thứ tự riêng.

Điều cần quyết định là **những khác biệt nào phải làm hai khóa được lưu riêng**. Không nên lấy một thuộc tính chỉ phục vụ hiển thị rồi mặc định nó đủ làm danh tính cho `TreeMap`.

### 6.5. thenComparing không phải cách gom nhóm nhiều giá trị

Nếu yêu cầu thật sự là một độ ưu tiên chứa nhiều ticket, kiểu dữ liệu có thể cần là `TreeMap<Integer, List<Ticket>>`, với danh sách các ticket nằm ở giá trị. Khi đó hai ticket cùng mức không bị đặt trực tiếp làm hai khóa cạnh tranh.

Cách đó có ý nghĩa khác với `TreeMap<Ticket, Value>` có comparator đầy đủ. Map theo mức ưu tiên trả một nhóm; map theo khóa ghép trả một mapping riêng cho từng cặp thành phần. Chọn theo thao tác ứng dụng cần, thay vì cố sửa comparator để một cấu trúc đồng thời mang hai nghĩa.

## 7. Chương trình 4: BigDecimal và sự khác nhau giữa giá trị số với biểu diễn

### 7.1. Một ví dụ từ thư viện chuẩn

`BigDecimal` là trường hợp quan trọng vì không cần tự viết comparator sai vẫn có thể gặp so sánh bằng 0 nhưng `equals=false`. Với `new BigDecimal("2.0")` và `new BigDecimal("2.00")`: giá trị số bằng nhau, nhưng scale khác nhau.

`compareTo` so theo giá trị số, còn `equals` xét cả giá trị và scale. Chi tiết này được nêu tại [BigDecimal — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html). Không nên diễn giải nó là lỗi làm tròn trong ví dụ: hai chuỗi được tạo trực tiếp thành số thập phân, không đi qua `double`.

Lưu chương trình đầy đủ vào `TreeMapBigDecimalKeyDemo.java`:

```java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.TreeMap;

public class TreeMapBigDecimalKeyDemo {
    public static void main(String[] args) {
        BigDecimal first = new BigDecimal("2.0");
        BigDecimal second = new BigDecimal("2.00");
        System.out.println("equals=" + first.equals(second));
        System.out.println("compareTo=" + first.compareTo(second));
        System.out.println("scales=" + first.scale() + "," + second.scale());

        TreeMap<BigDecimal, String> numeric = new TreeMap<>();
        numeric.put(first, "first");
        System.out.println("numericOld=" + numeric.put(second, "second"));
        System.out.println("numeric=" + numeric);
        System.out.println("numericSize=" + numeric.size());
        System.out.println("numericLookup="
                + numeric.get(new BigDecimal("2.000")));

        Comparator<BigDecimal> numericThenScale =
                Comparator.<BigDecimal>naturalOrder()
                        .thenComparingInt(BigDecimal::scale);
        TreeMap<BigDecimal, String> representation =
                new TreeMap<>(numericThenScale);
        representation.put(first, "first");
        representation.put(second, "second");
        System.out.println("representation=" + representation);
        System.out.println("representationSize=" + representation.size());
        System.out.println("representationLookup="
                + representation.get(new BigDecimal("2.000")));
        System.out.println("normalizedEquals="
                + first.stripTrailingZeros().equals(second.stripTrailingZeros()));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 TreeMapBigDecimalKeyDemo.java
java TreeMapBigDecimalKeyDemo
```

Stdout:

```text
equals=false
compareTo=0
scales=1,2
numericOld=first
numeric={2.0=second}
numericSize=1
numericLookup=second
representation={2.0=first, 2.00=second}
representationSize=2
representationLookup=null
normalizedEquals=true
```

### 7.2. Map theo thứ tự tự nhiên gộp cùng giá trị số

Map `numeric` không nhận comparator riêng nên dùng `BigDecimal.compareTo`. `compareTo=0` làm hai khóa rơi vào cùng một nhóm tương đương. Lần put thứ hai trả `first`, map còn một mapping với giá trị `second`.

`numericLookup=second` cho thấy một khóa thứ ba `2.000` cũng tìm cùng mapping. Khóa dùng lúc tra không cần có cùng scale nếu quy tắc thứ tự chỉ xét giá trị số.

Đây có thể phù hợp với một phần yêu cầu “các cách viết cùng giá trị số là cùng nhóm”, nhưng thứ tự tự nhiên của `BigDecimal` không nhất quán với `BigDecimal.equals`. Khi dùng như một `Map` tổng quát hoặc phối hợp với các cấu trúc dựa trên `equals`, phải nhận thức rõ sự khác nhau đó.

### 7.3. Map xét thêm scale giữ riêng các biểu diễn

Comparator `numericThenScale` so giá trị số trước, rồi so scale khi giá trị số bằng nhau. Vì thế 2.0 và 2.00 được giữ riêng, map có hai mapping. 2.000 mang scale thứ ba nên `representationLookup=null`, vì chưa có khóa đó.

Với `BigDecimal`, bằng nhau về giá trị số và cùng scale cũng tương ứng với điều kiện `equals`; comparator này tạo ra quan hệ 0 phù hợp với `equals`. Nhưng nó cũng **đổi ý nghĩa tra cứu**: truy vấn một giá trị số với scale khác không còn mặc nhiên trúng entry đang có.

Không nên thêm scale chỉ để thấy `size=2` rồi coi đó là lựa chọn luôn đúng. Nếu scale là một phần dữ liệu cần giữ riêng, cách này có lý do. Nếu ứng dụng coi mọi biểu diễn cùng số là một khóa, cần mô hình hóa quan hệ đó nhất quán.

### 7.4. Chuẩn hóa là một lựa chọn về miền dữ liệu

`stripTrailingZeros()` trong ví dụ cho hai giá trị có dạng chuẩn bằng nhau nên `normalizedEquals=true`. Nếu chọn chuẩn hóa làm chính sách khóa, phải áp dụng cùng quy tắc ở lúc thêm, tra và xóa; chỉ chuẩn hóa lúc put mà tra bằng kiểu khóa chưa chuẩn sẽ tạo một hợp đồng khó hiểu.

Không tự đồng nhất chuẩn hóa khóa với định dạng hiển thị hoặc quy tắc làm tròn tiền tệ. `stripTrailingZeros` có thể làm scale âm với một số giá trị; nó không có nghĩa mọi kết quả luôn có scale 0 hoặc luôn được in theo cùng một dạng thập phân. Chọn biểu diễn chuẩn theo yêu cầu dữ liệu và kiểm tra các trường hợp biên của nó.

Điều quan trọng của ví dụ là nhận ra **compareTo và equals có thể chủ ý khác nhau trong một kiểu chuẩn**. Việc các khóa thuộc một lớp thư viện không miễn cho người dùng `TreeMap` kiểm tra quan hệ trùng khóa.

## 8. Comparator phải là một quan hệ thứ tự hợp lệ

### 8.1. Ba ràng buộc cần hiểu

Có thể ký hiệu `c(a, b)` là kết quả so hai khóa a và b. Bên cạnh việc so sánh được mọi khóa trong miền cho phép, comparator cần các quan hệ nhất quán:

1. **Đảo dấu khi đổi chỗ:** dấu của `c(a,b)` phải đối nghịch dấu của `c(b,a)`. Nếu a đứng trước b, b phải đứng sau a. Với hai khóa tương đương, hai chiều cùng bằng 0.
2. **Bắc cầu:** nếu a đứng trước b và b đứng trước c, a cũng phải đứng trước c. Tương tự cho chiều đứng sau.
3. **Nhất quán khi bằng 0:** nếu a và b được xem là tương đương, khi so cả hai với một khóa z, chúng phải cho cùng dấu tương quan với z.

Quy tắc thứ ba giúp “cùng nhóm khóa” có ý nghĩa trong cả cây, chứ không chỉ đúng ở một cặp. Không thể cho a bằng b nhưng a đứng trước z còn b đứng sau z và vẫn mong cấu trúc tìm kiếm có một thứ tự hợp lệ.

Đối với các khóa được chấp nhận, `c(a,a)` phải bằng 0. Comparator không được trả 1 chỉ vì hai tham chiếu khác nhau hoặc vì muốn ép một khóa mới luôn được thêm. Những cách né kết quả 0 như vậy phá vỡ thứ tự thay vì tạo ra một map nhiều giá trị hợp lệ.

Ràng buộc thứ tự và tính nhất quán với `equals` là hai lớp khác nhau. Comparator chỉ theo độ dài chuỗi có thể là một quan hệ thứ tự hợp lệ trên các nhóm độ dài, nhưng không nhất quán với `String.equals`. Comparator dùng phép trừ bị tràn có thể hỏng ngay cả các ràng buộc thứ tự cơ bản.

### 8.2. Vì sao phép trừ số nguyên nguy hiểm?

Đoạn `(a, b) -> a - b` có vẻ ngắn gọn để so số tăng dần. Tuy nhiên, phép trừ `int` có thể tràn miền giá trị, làm dấu của kết quả không còn phản ánh quan hệ giữa hai toán hạng.

Điều này không chỉ làm một lần in bị sai. `TreeMap` dựa vào dấu để chọn đường tìm kiếm. Nếu dấu không nhất quán, cấu trúc không có quan hệ hợp lệ để duy trì và tra cứu. Không nên thử chèn một vài số nhỏ rồi kết luận comparator đã đúng cho toàn miền `int`.

Chương trình tiếp theo kiểm tra trực tiếp các tính chất của phép so sánh. Nó cố ý không đưa comparator sai vào map để tránh biến một hành vi của cấu trúc với thứ tự hỏng thành kết quả mà người học dựa vào.

### 8.3. Chương trình 5: quan sát lỗi tràn số ở comparator

Lưu vào `ComparatorContractDemo.java`:

```java
import java.util.Comparator;

public class ComparatorContractDemo {
    public static void main(String[] args) {
        Comparator<Integer> bad = (left, right) -> left - right;
        Comparator<Integer> good = Integer::compare;
        int minimum = Integer.MIN_VALUE;
        int maximum = Integer.MAX_VALUE;

        System.out.println("badMinVsZero=" + bad.compare(minimum, 0));
        System.out.println("badZeroVsMin=" + bad.compare(0, minimum));
        System.out.println("badOppositeSigns="
                + (Integer.signum(bad.compare(minimum, 0))
                == -Integer.signum(bad.compare(0, minimum))));
        System.out.println("goodOppositeSigns="
                + (Integer.signum(good.compare(minimum, 0))
                == -Integer.signum(good.compare(0, minimum))));

        boolean badPremise = bad.compare(minimum, 0) < 0
                && bad.compare(0, maximum) < 0;
        boolean badConclusion = bad.compare(minimum, maximum) < 0;
        boolean goodPremise = good.compare(minimum, 0) < 0
                && good.compare(0, maximum) < 0;
        boolean goodConclusion = good.compare(minimum, maximum) < 0;
        System.out.println("badTransitivityPremise=" + badPremise);
        System.out.println("badTransitivityConclusion=" + badConclusion);
        System.out.println("goodTransitivityPremise=" + goodPremise);
        System.out.println("goodTransitivityConclusion=" + goodConclusion);
        System.out.println("negatingMinStillNegative=" + (-minimum < 0));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 ComparatorContractDemo.java
java ComparatorContractDemo
```

Stdout:

```text
badMinVsZero=-2147483648
badZeroVsMin=-2147483648
badOppositeSigns=false
goodOppositeSigns=true
badTransitivityPremise=true
badTransitivityConclusion=false
goodTransitivityPremise=true
goodTransitivityConclusion=true
negatingMinStillNegative=true
```

### 8.4. Đọc lỗi qua dấu và tính bắc cầu

`minimum - 0` và `0 - minimum` đều cho `-2147483648` sau phép tính `int`. Cả hai đều âm, nên comparator sai đang nói đồng thời minimum đứng trước 0 và 0 đứng trước minimum. `badOppositeSigns=false` chỉ ra lỗi đó.

Comparator sai còn cho minimum đứng trước 0 và 0 đứng trước maximum, nhưng lại không cho minimum đứng trước maximum. Vì vậy `badTransitivityPremise=true` trong khi `badTransitivityConclusion=false`.

`Integer.compare` xử lý so sánh mà không lấy hiệu dễ tràn nên cả hai kiểm tra tương ứng đúng. Với trường `long`, dùng `Long.compare` hoặc `Comparator.comparingLong`; không lấy hiệu `long` rồi ép về `int`.

`negatingMinStillNegative=true` cho thấy tự đổi dấu một kết quả so sánh bất kỳ cũng có bẫy tại `Integer.MIN_VALUE`. Để đảo một comparator đúng, dùng `reversed()`; để đảo thứ tự tự nhiên, dùng `Comparator.reverseOrder()`. Đừng sửa một comparator vốn sai bằng cách chỉ đổi dấu kết quả.

Các ví dụ số biên cung cấp phản ví dụ đủ để bác bỏ comparator sai. Ngược lại, một số mẫu kiểm tra hữu hạn chạy qua không chứng minh một comparator bất kỳ đúng cho mọi dữ liệu; cài đặt vẫn cần được xây từ các phép so sánh có hợp đồng phù hợp.

## 9. Giữ quy tắc so sánh ổn định trong suốt thời gian lưu khóa

### 9.1. Không sửa trường tham gia so sánh khi khóa đang nằm trong cây

Giả sử một đối tượng khóa đang được đặt trong cây dựa trên điểm ưu tiên bằng 1. Nếu sửa điểm đó thành 100 qua một tham chiếu khác, `TreeMap` không tự biết để tháo khóa ra và chèn lại theo vị trí mới. Cấu trúc hiện tại đã được tổ chức theo các kết quả so sánh trước đó.

Hệ quả có thể là thứ tự duyệt không còn phù hợp với dữ liệu đang thấy hoặc việc tra bằng một khóa tương đương không đi đến vị trí mong đợi. Không dựa vào một kết quả lỗi cụ thể vì nó còn phụ thuộc cấu trúc và chuỗi thao tác; vấn đề gốc là đã làm mất tính ổn định của khóa so sánh.

Cách thiết kế đơn giản là dùng khóa bất biến, chẳng hạn record chỉ gồm các thành phần bất biến như `int` và `String` trong ví dụ. Nếu thật sự cần thay thông tin dùng làm khóa, hãy loại mapping bằng khóa còn nguyên trạng, rồi thêm lại bằng khóa mới theo một quy trình đã xác định. Sửa khóa trước rồi mới cố dùng khóa đó để remove không bảo đảm còn tìm được mapping cũ.

Record không tự làm mọi đối tượng bên trong bất biến sâu. Một record chứa danh sách có thể thay đổi vẫn có thể gặp vấn đề nếu comparator đọc nội dung danh sách đó. Cần kiểm tra dữ liệu mà phép so sánh thực sự phụ thuộc.

### 9.2. Comparator cũng không được đổi ý giữa chừng

Comparator có thể hỏng tính ổn định ngay cả khi bản thân khóa không đổi. Ví dụ, nó đọc một cờ bên ngoài để lúc thì tăng dần, lúc thì giảm dần; hoặc nó phụ thuộc số ngẫu nhiên, thời gian hiện tại, hay một bảng giá trị có thể thay đổi.

Khi các kết quả so sánh thay đổi sau khi cây đã được xây, map không tự sắp lại tất cả entry. Muốn một chính sách thứ tự mới, hãy xây một cấu trúc mới với quy tắc ổn định đã chọn và chuyển dữ liệu một cách có chủ đích; không chỉ thay một biến được comparator cũ đọc.

Đặc biệt, sắp khóa theo giá trị lấy từ một map khác bằng một comparator phụ thuộc trạng thái thay đổi sẽ trộn tra cứu với thứ tự không ổn định. Nếu yêu cầu là xem kết quả theo giá trị tại một thời điểm, thường nên tạo dữ liệu hoặc chỉ mục riêng cho mục đích đó thay vì âm thầm làm danh tính khóa của `TreeMap` phụ thuộc giá trị đang cập nhật.

### 9.3. Giá trị V không phải khóa so sánh

Với `TreeMap<K,V>` bình thường, cập nhật giá trị của một khóa không làm map chuyển sang sắp theo giá trị mới. Comparator nhận các khóa kiểu K, không nhận hai entry để tùy ý xét V.

Một giá trị có thể trùng với giá trị của entry khác mà cả hai mapping vẫn tồn tại, miễn các khóa không tương đương theo comparator. Ngược lại, dùng hai giá trị rất khác nhau không làm một cặp khóa so sánh bằng 0 trở thành hai chỗ lưu.

## 10. Miền khóa hợp lệ, null và lỗi kiểu

### 10.1. Mọi khóa phải so sánh được với nhau

Trong map dùng thứ tự tự nhiên, việc hai lớp đều triển khai `Comparable` chưa đủ để bảo đảm các đối tượng của hai lớp đó so được với nhau. Ví dụ, `Integer` và `Long` không tự có một thứ tự tự nhiên chung chỉ vì cả hai là số.

Không nên bỏ generics hoặc khai báo một kiểu rất rộng rồi đưa vào nhiều loại khóa mà không có quy tắc so sánh chung. Map có thể ném `ClassCastException` khi cần so các khóa không tương thích. Lệnh `get` hoặc `containsKey` có tham số kiểu `Object` cũng không có nghĩa mọi đối tượng truyền vào đều có thể được so với khóa đang có.

Nếu dùng comparator ngoài, nó phải xử lý hợp lệ mọi cặp khóa thuộc miền mà API cho phép. Không có yêu cầu bắt buộc mọi khóa phải cùng một lớp cụ thể nếu comparator thật sự xây được một thứ tự chung, nhưng việc đó cần được thiết kế rõ ràng; ép kiểu tùy tiện không tạo ra thứ tự hợp lệ.

### 10.2. Hai chỗ có thể xuất hiện null trong cấu hình có ý nghĩa khác nhau

`new TreeMap<>(comparator)` với đối tượng comparator bằng `null` nghĩa là dùng thứ tự tự nhiên. Nhưng `Comparator.nullsFirst(null)` có ý nghĩa khác: nó coi mọi khóa khác `null` là bằng nhau, còn `null` đứng trước chúng.

Vì vậy, truyền `null` vào `nullsFirst` không phải cách yêu cầu tự động dùng `compareTo` cho các khóa còn lại. Nếu muốn chuỗi dùng thứ tự tự nhiên và nhận khóa `null`, cấu hình minh họa bên trong một phương thức là:

```java
Comparator<String> order = Comparator.nullsFirst(Comparator.naturalOrder());
TreeMap<String, Integer> map = new TreeMap<>(order);
```

Điểm này quan trọng trực tiếp với khóa trùng: một comparator xem mọi khóa khác `null` là tương đương sẽ chỉ có một nhóm khóa khác `null` để lưu mapping, dù người dùng đưa vào nhiều chuỗi khác nhau.

### 10.3. Nói rõ chính sách thay vì dựa vào ngoại lệ ngẫu nhiên

Nếu API không chấp nhận khóa `null`, hãy mô tả và kiểm tra quy tắc đó ở ranh giới thích hợp. Nếu nhận, chọn comparator có cách xử lý rõ ràng cho `null` và cho các khóa khác `null`. Không tạo comparator chỉ xử lý được một vài cặp rồi mong map tự bổ sung phần còn lại.

Khi `map.comparator()` khác `null`, comparator đó vẫn có thể chỉ ủy quyền cho thứ tự tự nhiên, chẳng hạn một map được tạo bằng `Comparator.naturalOrder()`. Vì thế getter cho biết cách cấu hình được giữ, không phải một phép suy luận rằng thứ tự tự nhiên và comparator ngoài luôn mô tả hai thứ tự khác nhau về kết quả.

## 11. Kiểm tra comparator và hành vi khóa trùng

### 11.1. Kiểm tra quan hệ, không chỉ một danh sách đã sắp

Một lần duyệt vài khóa có vẻ đúng thứ tự chưa chứng minh comparator tốt. Nên kiểm tra những nhóm dữ liệu làm lộ chính sách:

- Hai đối tượng khác tham chiếu nhưng cùng giá trị khóa: phải được nhận diện theo ý định nghiệp vụ.
- Hai khóa giống tiêu chí chính nhưng khác tiêu chí phụ: phải giữ riêng nếu đó là yêu cầu.
- Hai khóa khác nhau theo `equals` nhưng comparator đang trả 0: cần xác nhận đây có phải điều chủ ý, và hiểu giới hạn hợp đồng `Map` nếu giữ thiết kế đó.
- Số biên như `Integer.MIN_VALUE`, 0, `Integer.MAX_VALUE` để phát hiện lỗi dấu và tràn số.
- Các biến thể biểu diễn như `BigDecimal` khác scale hoặc chuỗi khác hoa thường nếu miền dữ liệu cho phép.
- Khóa `null` nếu API hỗ trợ, cùng trường hợp giá trị `null` để không nhầm kết quả get.

Ở mức hợp đồng, có thể kiểm tra các cặp và bộ ba mẫu: đổi chỗ phải đảo dấu; hai quan hệ trước liên tiếp phải kéo theo quan hệ trước bắc cầu; khóa có kết quả 0 phải có cùng dấu tương quan với các khóa thứ ba. Sau đó kiểm tra thêm sự tương ứng với `equals` nếu map cần tuân thủ hợp đồng `Map` tổng quát.

Tài liệu [Comparator — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html) và [Comparable — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html) là nguồn đối chiếu các điều kiện này. Không thay việc hiểu hợp đồng bằng cách quan sát riêng một chuỗi sắp xếp chạy không lỗi.

### 11.2. Kiểm tra thao tác map từ cùng một cặp khóa

Với cặp a, b cần được xem là trùng, hãy xác nhận:

1. Thêm a rồi thêm b không tăng số mapping ở lần sau.
2. Lần put b trả giá trị cũ và giá trị mới được tra thấy bằng cả hai khóa.
3. `containsKey` với một đối tượng mới thuộc cùng nhóm tương đương nhận ra mapping.
4. Remove bằng một khóa tương đương loại đúng mapping đó.

Với cặp cần giữ riêng, kiểm tra chiều ngược: cả hai mapping cùng tồn tại, tra từng khóa trả đúng giá trị riêng, remove một khóa không loại khóa còn lại. Chỉ kiểm tra `size()` chưa đủ nếu comparator hoặc logic tra cứu vẫn không đúng như mong muốn.

`put` trả `null` có thể là thêm mới hoặc thay giá trị cũ vốn đã `null`. Nếu phép kiểm tra cần phân biệt, hãy quan sát sự tồn tại hoặc kích thước trong ngữ cảnh đã được xác định, thay vì coi kết quả `null` là bằng chứng duy nhất.

### 11.3. Chi phí so sánh cũng là một phần chi phí tra cứu

`TreeMap` có chi phí logarit theo số mapping cho các thao tác cơ bản như `get`, `put`, `containsKey`, `remove`. Tuy nhiên, mỗi bước còn phải chạy phép so sánh. Comparator xử lý chuỗi dài, tính toán nặng hoặc tải dữ liệu từ bên ngoài sẽ làm chi phí thực tế tăng.

Giữ comparator ngắn, ổn định và không có tác dụng phụ giúp cả tính đúng lẫn khả năng dự đoán chi phí. Không làm thay đổi chính map trong lúc comparator đang được gọi để tìm vị trí; phép so sánh nên trả lời quan hệ giữa hai khóa thay vì thực hiện công việc cập nhật khác.

## 12. Lỗi thường gặp

| Nhầm lẫn | Hậu quả | Hướng xử lý |
|---|---|---|
| Comparator chỉ dùng để trình bày thứ tự | Không dự đoán được mapping bị cập nhật | Xét cả ý nghĩa `compare == 0` |
| `equals=false` thì TreeMap luôn giữ hai entry | Sai khi so sánh bằng 0 | Kiểm tra quy tắc đang có hiệu lực |
| Có comparator ngoài thì map vẫn gọi equals để phân biệt thêm | Hai khóa vẫn bị gộp ngoài ý muốn | Đưa tiêu chí phân biệt vào comparator hoặc đổi mô hình khóa |
| Chỉ so điểm/độ dài/độ ưu tiên | Các đối tượng khác cùng tiêu chí bị gộp | Bổ sung tiêu chí nhận diện cần thiết |
| Thêm số ngẫu nhiên để tránh trả 0 | Thứ tự không ổn định, không tra lại được như mong muốn | Dùng thành phần khóa ổn định |
| So số bằng phép trừ | Có thể đảo dấu, mất bắc cầu khi tràn số | Dùng hàm compare hoặc comparing theo kiểu số |
| Kiểm tra kết quả đúng bằng -1 hoặc 1 | Sai với comparator trả độ lớn khác | Kiểm tra `< 0`, `== 0`, `> 0` |
| Đảo comparator sẽ tách khóa đang trùng | Kết quả 0 vẫn là 0 | Sửa tiêu chí thay vì chỉ đổi chiều |
| BigDecimal cùng giá trị số luôn equals | Bỏ sót scale | Chọn rõ khóa theo số hay theo biểu diễn |
| Sửa trường khóa trong khi đang lưu | Vị trí cây và dữ liệu khóa không còn tương ứng | Dùng khóa ổn định, thay khóa theo quy trình có chủ đích |
| Cờ bên ngoài đổi thì TreeMap tự sắp lại | Comparator đổi nhưng cây không được xây lại | Dùng quy tắc ổn định cho mỗi cấu trúc |
| `comparator()==null` nghĩa là không có thứ tự | Hiểu sai thứ tự tự nhiên | Đọc đúng ý nghĩa getter |

## 13. Tự kiểm tra

### Câu hỏi

1. Hai khóa khác tham chiếu có bắt buộc tạo hai mapping trong `TreeMap` không?
2. Với comparator chỉ theo độ dài, thêm `cat → 1` rồi `dog → 2` tạo mấy mapping?
3. `TreeMap` có tự gọi `equals` để tách cat và dog sau khi comparator trả 0 không?
4. Vì sao `compare(a,b) == 1` không phải cách kiểm tra chung cho mọi comparator?
5. Comparator được truyền vào có bắt buộc gọi thêm `compareTo` khi trả 0 không?
6. `thenComparing` dùng tiêu chí sau khi nào?
7. `reversed()` có thay đổi nhóm khóa đang so sánh bằng 0 không?
8. `new BigDecimal("2.0")` và `new BigDecimal("2.00")` có đồng thời bằng nhau theo equals và compareTo không?
9. Một comparator đúng về tính bắc cầu đã chắc chắn nhất quán với equals chưa?
10. Vì sao sửa `hashCode` không giải quyết việc `TreeMap` đang gộp hai khóa?

### Đáp án

1. Không. Quan hệ tương đương theo thứ tự mới quyết định; hai đối tượng mới biểu diễn cùng khóa vẫn có thể cập nhật cùng mapping.
2. Một mapping có giá trị mới 2 vì hai độ dài đều ba.
3. Không. Muốn giữ riêng theo nội dung phải bổ sung tiêu chí hoặc chọn mô hình phù hợp.
4. API chỉ quy định số dương, không bắt buộc đúng 1. Dùng `> 0`.
5. Không. Quy tắc comparator là quy tắc có hiệu lực; tiêu chí bổ sung phải được thể hiện rõ.
6. Khi các tiêu chí trước coi hai khóa tương đương, tức cho kết quả 0.
7. Không; đảo thứ tự chỉ đổi quan hệ trước/sau, không tách nhóm tương đương.
8. compareTo trả 0 nhưng equals trả false vì scale khác.
9. Chưa. Comparator theo độ dài có thể là thứ tự hợp lệ nhưng gộp các chuỗi không equals.
10. TreeMap không dùng mã băm để nhận diện khóa trùng; cần xem phép so sánh và kết quả 0.

## 14. Thực hành với kết quả đối chiếu

### Bài 1: từ một tiêu chí sang hai tiêu chí

Tạo `TreeMap<String, Integer>` dùng `Comparator.comparingInt(String::length)`. Chèn `cat → 1`, `dog → 2`, `ox → 3`. Dự đoán số mapping, giá trị tra bằng `pig` và thứ tự các nhóm độ dài trước khi chạy.

Kết quả đối chiếu: có hai mapping, tương ứng độ dài hai và ba. `get("pig")` tìm nhóm độ dài ba và trả 2 dù chuỗi pig chưa từng được chèn. Đây là hệ quả trực tiếp của khóa tương đương theo độ dài.

Làm lại từ map rỗng với comparator độ dài nối thêm thứ tự tự nhiên của chuỗi. Khi đó cat và dog được giữ riêng, kích thước là ba, thứ tự khóa là `[ox, cat, dog]`, còn `get("pig")` trả `null` vì không có khóa pig. Hai lần thử phải dùng hai map mới để cùng có điểm xuất phát rõ ràng.

### Bài 2: kiểm tra một khóa ghép

Dùng record Ticket của chương trình 3. Thêm lần lượt 1:A, 1:B, rồi một đối tượng mới cũng là 1:A, với ba giá trị khác nhau. Với comparator đầy đủ, dự đoán kích thước cuối và mapping nào bị cập nhật.

Kết quả đối chiếu: có hai mapping; lần cuối chỉ cập nhật 1:A. Nếu map còn một mapping, comparator đang bỏ qua code. Nếu có ba mapping, quan hệ khóa không còn đúng với cặp thành phần đang biểu diễn.

### Bài 3: chọn rõ chính sách BigDecimal

Dùng hai map trong chương trình 4 rồi tra bằng 2.000. Giải thích vì sao map thứ nhất trả giá trị đã có, còn map thứ hai trả `null`. Sau đó tự quyết định liệu miền dữ liệu của một ví dụ ứng dụng cần phân biệt scale hay không.

Tiêu chí hoàn thành không phải luôn làm cho cả hai map có cùng `size()`. Cần giải thích được thế nào là cùng khóa, và bảo đảm mọi đường thêm/tra/xóa cùng tuân theo quyết định đó.

### Bài 4: tìm phản ví dụ thay vì chỉ dùng số nhỏ

Với comparator phép trừ, thử các cặp 1 và 2 trước, rồi các giá trị biên ở chương trình 5. Nêu rõ tính chất nào bị vi phạm. Sau đó thay bằng `Integer.compare` và đối chiếu lại các kiểm tra dấu, bắc cầu.

Không cần xây một TreeMap dùng comparator sai để làm bài này. Lỗi đã hiện diện trong quan hệ so sánh; sửa quan hệ đó là điều kiện trước khi dùng nó làm nền tảng cấu trúc tìm kiếm.

## 15. Môi trường chạy và tài liệu

Năm chương trình trong bài độc lập, dùng cú pháp và API tương thích Java 17. Chúng đã được biên dịch bằng `javac --release 17 -encoding UTF-8` và chạy trên JDK 24.0.2; stdout được đối chiếu từ các lần chạy đó. Mỗi lớp `public` được lưu trong tệp trùng tên, không cần thư viện ngoài.

- [TreeMap — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/TreeMap.html): nguồn thứ tự, ý nghĩa khóa so sánh bằng nhau và yêu cầu nhất quán với equals.
- [Comparable — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Comparable.html): thứ tự tự nhiên và hợp đồng của compareTo.
- [Comparator — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): hợp đồng so sánh, nối tiêu chí, đảo chiều và xử lý null.
- [BigDecimal — Java 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): so sánh giá trị số, equals theo giá trị và scale, chuẩn hóa số 0 tận cùng.
