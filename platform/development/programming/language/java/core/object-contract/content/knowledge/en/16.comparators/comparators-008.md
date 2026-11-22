# Phân biệt Comparator dùng cho hiển thị với quan hệ bằng nhau của đối tượng

## Mục tiêu học tập

Trong Java, **thứ tự hiển thị** và **quan hệ bằng nhau của đối tượng** là hai khái niệm độc lập. `Comparator<T>` định nghĩa thứ tự để sắp danh sách: theo tên, điểm số, thời gian, mức độ ưu tiên hoặc giá tiền. Ngược lại, `equals(Object)` xác định hai đối tượng có được xem là bằng nhau theo hợp đồng của lớp hay không. Một comparator dùng để hiển thị có thể coi hai đối tượng là **tương đương theo thứ tự** dù chúng là hai bản ghi nghiệp vụ khác nhau.

Bài này giúp bạn:

- Phân biệt `Comparator.compare(a, b) == 0`, `a.equals(b)`, `a == b` và `a.hashCode()`.
- Giải thích trường hợp hai đối tượng có cùng khóa sắp xếp nhưng không bằng nhau.
- Hiểu vì sao `List.sort` giữ mọi phần tử, còn `TreeSet`/`TreeMap` dùng `compare == 0` để xác định phần tử hoặc khóa tương đương.
- Dùng `thenComparing` để tạo tie-breaker, nhưng không nhầm nó với hợp đồng `equals`.
- Thiết kế đồng thời quy tắc bằng nhau nghiệp vụ và thứ tự hiển thị, đặc biệt với ID, tên trùng nhau, null, chữ hoa/thường và phân trang.

## 1. Các phép kiểm tra có ý nghĩa khác nhau

| Biểu thức | Ý nghĩa |
| --- | --- |
| `a == b` | Hai tham chiếu cùng chỉ tới **một đối tượng** hay không |
| `a.equals(b)` | Hai đối tượng có **bằng nhau theo hợp đồng lớp** hay không |
| `comparator.compare(a, b) == 0` | Hai đối tượng có **cùng vị trí trong thứ tự** mà comparator định nghĩa hay không |
| `a.hashCode() == b.hashCode()` | Hai đối tượng có cùng mã băm hay không; điều này **không chứng minh bằng nhau** |

`compare(a, b)` trả số **âm**, `0` hoặc số **dương** tương ứng `a` đứng trước, tương đương về thứ tự hoặc đứng sau `b`. Không dựa vào trị tuyệt đối cụ thể: chỉ nên xét dấu kết quả.

Một comparator được gọi là **nhất quán với equals** (*consistent with equals*) khi với các phần tử liên quan:

```text
comparator.compare(a, b) == 0  ⇔  a.equals(b)
```

Dấu tương đương hai chiều có nghĩa:

1. Nếu comparator trả `0` thì `equals` trả `true`.
2. Nếu `equals` trả `true` thì comparator trả `0`.

Một comparator dùng **chỉ để sắp xếp giao diện** có thể không nhất quán với `equals` mà vẫn hợp lệ, miễn đáp ứng hợp đồng thứ tự của `Comparator`. Tuy nhiên, khi đưa comparator ấy vào `TreeSet` hoặc `TreeMap`, sự khác biệt này có thể làm mất bản ghi hoặc thay giá trị khóa.

**Không nhầm `Comparator.equals(Object)`:** Đây là phương thức trên **bản thân đối tượng comparator**, không phải cách kiểm tra hai phần tử dữ liệu. `compare(a,b) == 0` mới là cách comparator thể hiện hai phần tử tương đương về thứ tự.

## 2. Một khóa hiển thị có thể đại diện cho nhiều đối tượng

Xét danh sách thành viên:

| ID | Tên | Điểm |
| ---: | --- | ---: |
| 101 | An | 90 |
| 102 | An | 90 |
| 103 | Bình | 80 |

Giao diện xếp hạng theo điểm giảm dần và tên tăng dần. Hai thành viên ID `101` và `102` có cùng khóa hiển thị: điểm `90` và tên `"An"`. Vì thế comparator chỉ so điểm và tên sẽ trả `0`.

Nhưng đó vẫn có thể là hai người khác nhau. Nếu lớp biểu diễn một thành viên bằng record:

```java
record Member(int id, String name, int score) {}
```

`equals` mặc định của record so **tất cả thành phần**. ID khác nhau làm `equals` trả `false` dù khóa hiển thị trùng nhau.

Sơ đồ:

```text
Thành viên 101 ── điểm 90, tên An ──┐
                                    ├── cùng vị trí theo Comparator
Thành viên 102 ── điểm 90, tên An ──┘

equals của record: khác nhau vì ID khác nhau
```

Đây là tình huống hợp lý trong bảng xếp hạng: **cùng thứ hạng hoặc cùng tiêu chí sắp xếp không đồng nghĩa cùng danh tính**.

## 3. Ví dụ chạy được: List và TreeSet cho kết quả khác nhau

Tạo tệp **`DisplayComparatorDemo.java`** (Java 17+):

```java
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class DisplayComparatorDemo {
    record Member(int id, String name, int score) {}

    public static void main(String[] args) {
        Member an101 = new Member(101, "An", 90);
        Member an102 = new Member(102, "An", 90);
        Member binh103 = new Member(103, "Binh", 80);

        Comparator<Member> forDisplay =
                Comparator.comparingInt(Member::score)
                        .reversed()
                        .thenComparing(Member::name);

        System.out.println("same object: " + (an101 == an102));
        System.out.println("equals: " + an101.equals(an102));
        System.out.println("display compare == 0: "
                + (forDisplay.compare(an101, an102) == 0));

        List<Member> members =
                new ArrayList<>(List.of(an101, an102, binh103));
        members.sort(forDisplay);

        System.out.println("sorted list size: " + members.size());
        System.out.println("sorted IDs: "
                + members.stream().map(Member::id).toList());

        Set<Member> hashSet =
                new HashSet<>(List.of(an101, an102, binh103));

        Set<Member> treeSet = new TreeSet<>(forDisplay);
        treeSet.addAll(List.of(an101, an102, binh103));

        System.out.println("HashSet size: " + hashSet.size());
        System.out.println("TreeSet size: " + treeSet.size());

        Member anotherAn = new Member(999, "An", 90);
        System.out.println("TreeSet contains anotherAn: "
                + treeSet.contains(anotherAn));
        System.out.println("HashSet contains anotherAn: "
                + hashSet.contains(anotherAn));
    }
}
```

Biên dịch và chạy:

```bash
javac DisplayComparatorDemo.java
java DisplayComparatorDemo
```

**Đầu ra chính xác:**

```text
same object: false
equals: false
display compare == 0: true
sorted list size: 3
sorted IDs: [101, 102, 103]
HashSet size: 3
TreeSet size: 2
TreeSet contains anotherAn: true
HashSet contains anotherAn: false
```

**Giải thích:**

- `List.sort(forDisplay)` chỉ thay đổi **thứ tự** phần tử trong danh sách, không loại phần tử có comparator trả `0`. Vì vậy danh sách vẫn có ba thành viên.
- `List.sort` trong Java là sắp xếp **ổn định** (*stable*). Hai phần tử được comparator xem là ngang nhau giữ thứ tự tương đối như trước khi sắp: ở đây `101` trước `102`.
- `HashSet` dùng `equals` và `hashCode` của `Member`. Khác ID nên `an101` và `an102` đều được giữ.
- `TreeSet` được tạo bằng `forDisplay` dùng `compare(a,b) == 0` để xác định phần tử tương đương, vì thế gộp hai thành viên khác ID nhưng cùng tên/điểm.
- `treeSet.contains(new Member(999,"An",90))` trả `true` vì tiêu chí so sánh xem phần tử đó tương đương với một phần tử đã có. `HashSet.contains` trả `false` vì ID khác.

**Điểm rút ra:** Comparator hiển thị phù hợp với việc sắp một `List`; nếu dùng nó để định nghĩa tập hợp có thứ tự, hãy hiểu rõ các phần tử có thể bị coi là trùng.

## 4. Cấu trúc dữ liệu sử dụng quy tắc nào?

| Cấu trúc / thao tác | Quy tắc được dùng | Hệ quả khi `compare == 0` nhưng `equals == false` |
| --- | --- | --- |
| `List.sort(comparator)` | Comparator chỉ quyết định thứ tự | Giữ cả hai phần tử |
| `Collections.sort(list, comparator)` | Comparator chỉ quyết định thứ tự | Giữ cả hai phần tử |
| `stream.sorted(comparator)` | Comparator quyết định thứ tự kết quả | Không tự loại phần tử |
| `HashSet` | `equals` và `hashCode` | Không dùng comparator; hai đối tượng có thể đều tồn tại |
| `HashMap` | `equals` và `hashCode` trên khóa | Không dùng comparator; hai khóa khác nhau theo `equals` có thể cùng tồn tại |
| `TreeSet(comparator)` | `compare == 0` xác định tương đương | Chỉ giữ một đại diện |
| `TreeMap(comparator)` | `compare == 0` xác định khóa tương đương | `put` khóa sau có thể cập nhật giá trị của mục trước |

Một comparator chỉ so một phần của đối tượng rất phổ biến khi dùng cho UI: tên, điểm, giá, thời điểm… Nhưng khi chọn `TreeSet`/`TreeMap`, comparator trở thành một phần của **ngữ nghĩa nhận diện phần tử/khóa** chứ không đơn thuần là công cụ sắp xếp.

Tài liệu Java yêu cầu thứ tự dùng bởi sorted set/map nên **consistent with equals** để các cấu trúc này đáp ứng đúng hợp đồng chung của `Set`/`Map`. Chúng vẫn có hành vi được xác định theo comparator nếu không nhất quán, nhưng dễ gây bất ngờ cho mã khách.

## 5. Ví dụ TreeMap: khóa hiển thị trùng có thể ghi đè giá trị

Giả sử ứng dụng hiển thị nội dung theo tiêu đề không phân biệt chữ hoa/chữ thường. Một comparator phù hợp cho mục tiêu trình bày là:

```java
Comparator<Article> byDisplayTitle =
        Comparator.comparing(
                Article::title,
                String.CASE_INSENSITIVE_ORDER);
```

Đây là đoạn minh họa, giả định kiểu `Article` có accessor `title()`. Comparator coi tiêu đề `"Java"` và `"JAVA"` tương đương, dù hai bài viết có ID khác nhau.

Chạy ví dụ đầy đủ sau.

**Tệp `ComparatorMapDemo.java`:**

```java
import java.util.Comparator;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;

public class ComparatorMapDemo {
    record Article(int id, String title) {}

    public static void main(String[] args) {
        Article a = new Article(1, "Java");
        Article b = new Article(2, "JAVA");
        Article c = new Article(3, "Spring");

        Comparator<Article> displayOrder =
                Comparator.comparing(
                        Article::title,
                        String.CASE_INSENSITIVE_ORDER);

        Comparator<Article> strictOrder =
                displayOrder
                        .thenComparing(Article::title)
                        .thenComparingInt(Article::id);

        System.out.println("a.equals(b): " + a.equals(b));
        System.out.println("display compare zero: "
                + (displayOrder.compare(a, b) == 0));
        System.out.println("strict compare zero: "
                + (strictOrder.compare(a, b) == 0));

        Set<Article> displaySet = new TreeSet<>(displayOrder);
        displaySet.add(a);
        displaySet.add(b);
        displaySet.add(c);

        Set<Article> strictSet = new TreeSet<>(strictOrder);
        strictSet.add(a);
        strictSet.add(b);
        strictSet.add(c);

        System.out.println("display TreeSet size: "
                + displaySet.size());
        System.out.println("strict TreeSet size: "
                + strictSet.size());

        Map<Article, String> displayMap =
                new TreeMap<>(displayOrder);
        displayMap.put(a, "first");
        displayMap.put(b, "second");

        Map<Article, String> hashMap = new HashMap<>();
        hashMap.put(a, "first");
        hashMap.put(b, "second");

        System.out.println("display TreeMap size: "
                + displayMap.size());
        System.out.println("display TreeMap get(a): "
                + displayMap.get(a));
        System.out.println("HashMap size: " + hashMap.size());
    }
}
```

```bash
javac ComparatorMapDemo.java
java ComparatorMapDemo
```

**Đầu ra chính xác:**

```text
a.equals(b): false
display compare zero: true
strict compare zero: false
display TreeSet size: 2
strict TreeSet size: 3
display TreeMap size: 1
display TreeMap get(a): second
HashMap size: 2
```

Vì `displayOrder` chỉ so tiêu đề không phân biệt hoa/thường, `a` và `b` được `TreeSet` coi là tương đương; `TreeMap.put(b,"second")` tìm thấy khóa tương đương và thay giá trị `"first"` bằng `"second"`. `HashMap` vẫn giữ hai khóa vì record có ID và title khác nhau theo `equals`.

`strictOrder` có ba cấp:

1. Tiêu đề không phân biệt hoa/thường.
2. Tiêu đề phân biệt hoa/thường.
3. ID.

Với record `Article(int id, String title)` trong ví dụ và tiêu đề không `null`, `strictOrder.compare(a,b) == 0` chỉ khi **cả hai thành phần ID và title giống nhau**. Điều này nhất quán với `equals` mặc định của record, nên `strictSet` giữ cả ba bài.

**Cảnh báo quan trọng:** Thêm ID ở cuối comparator không tự động bảo đảm nhất quán với `equals` cho mọi lớp. Cần kiểm tra chính xác trường nào quyết định bằng nhau của lớp đó.

## 6. Chiều ngược lại: equals true nhưng Comparator khác 0

Không nhất quán có thể xuất hiện theo **hai hướng**:

- `compare(a,b) == 0` nhưng `a.equals(b) == false`: sorted set/map có thể coi hai bản ghi khác nhau là một khóa.
- `a.equals(b) == true` nhưng `compare(a,b) != 0`: sorted set/map có thể giữ hai đại diện mà `equals` coi là bằng nhau.

Ví dụ: một entity `Product` định nghĩa bằng nhau **chỉ bằng ID**, còn tên là thuộc tính hiển thị. Hai phiên bản của cùng ID có tên khác nhau vẫn bằng nhau theo `equals` nhưng khác nhau khi comparator chỉ so tên.

**Tệp `IdEqualityComparatorDemo.java`:**

```java
import java.util.Comparator;
import java.util.HashSet;
import java.util.Set;
import java.util.TreeSet;

public class IdEqualityComparatorDemo {
    static final class Product {
        private final long id;
        private final String label;

        Product(long id, String label) {
            this.id = id;
            this.label = label;
        }

        long id() {
            return id;
        }

        String label() {
            return label;
        }

        @Override
        public boolean equals(Object obj) {
            return this == obj
                    || (obj instanceof Product other && id == other.id);
        }

        @Override
        public int hashCode() {
            return Long.hashCode(id);
        }
    }

    public static void main(String[] args) {
        Product oldVersion = new Product(5L, "A");
        Product newVersion = new Product(5L, "Z");

        Comparator<Product> forDisplay =
                Comparator.comparing(Product::label);
        Comparator<Product> byIdentity =
                Comparator.comparingLong(Product::id);

        Set<Product> hashSet = new HashSet<>();
        hashSet.add(oldVersion);
        hashSet.add(newVersion);

        Set<Product> displaySet = new TreeSet<>(forDisplay);
        displaySet.add(oldVersion);
        displaySet.add(newVersion);

        Set<Product> identitySet = new TreeSet<>(byIdentity);
        identitySet.add(oldVersion);
        identitySet.add(newVersion);

        System.out.println("equals by id: "
                + oldVersion.equals(newVersion));
        System.out.println("display comparator nonzero: "
                + (forDisplay.compare(oldVersion, newVersion) != 0));
        System.out.println("identity comparator zero: "
                + (byIdentity.compare(oldVersion, newVersion) == 0));
        System.out.println("HashSet size: " + hashSet.size());
        System.out.println("TreeSet by display size: "
                + displaySet.size());
        System.out.println("TreeSet by id size: "
                + identitySet.size());
    }
}
```

```bash
javac IdEqualityComparatorDemo.java
java IdEqualityComparatorDemo
```

**Đầu ra chính xác:**

```text
equals by id: true
display comparator nonzero: true
identity comparator zero: true
HashSet size: 1
TreeSet by display size: 2
TreeSet by id size: 1
```

Ở đây `forDisplay` vẫn có ích để **sắp danh sách theo tên**. Nhưng nếu dùng nó trong `TreeSet`, tập hợp có thể nhận hai đại diện cùng ID. `byIdentity` mới nhất quán với `equals` của lớp `Product` vì cả hai chỉ quan tâm ID.

Muốn vừa **duy nhất theo ID**, vừa **hiển thị theo tên**, có thể giữ bản ghi trong `Map<Long,Product>` (ID là khóa), lấy các giá trị thành một danh sách rồi sắp danh sách theo tên. Hai trách nhiệm được thực hiện tách biệt, dễ kiểm tra hơn.

## 7. Tie-breaker giúp thứ tự xác định nhưng không thay thế equals

`thenComparing`, `thenComparingInt`, `thenComparingLong` dùng để bổ sung thứ tự khi các tiêu chí trước bằng nhau. Ví dụ với `Member`:

```java
Comparator<Member> ranking =
        Comparator.comparingInt(Member::score)
                .reversed()
                .thenComparing(Member::name)
                .thenComparingInt(Member::id);
```

Đoạn này là minh họa khi `Member` đã được khai báo như ở mục 3. Nó sắp theo điểm giảm dần, sau đó tên tăng dần, cuối cùng ID tăng dần.

Nếu kiểu `Member` là record gồm đúng `id`, `name`, `score` và tên không `null`, comparator trên nhất quán với `equals` của record: `compare == 0` khi và chỉ khi cả ba thành phần bằng nhau.

Tuy nhiên, với lớp entity có `equals` **chỉ xét ID**, comparator so tên trước rồi ID **không nhất thiết** nhất quán: hai entity cùng ID nhưng đổi tên vẫn có thể bị so khác nhau. Hãy luôn xét hợp đồng lớp cụ thể, không áp dụng mẹo “thêm ID cuối cùng” cho mọi trường hợp.

**Khi nào không cần tie-breaker?** Khi UI cố ý hiển thị hai người cùng điểm/tên với cùng thứ hạng hoặc chấp nhận thứ tự gốc. Khi đó giữ comparator hiển thị và dùng `List.sort` là hợp lý.

**Khi nào nên có tie-breaker?** Khi muốn thứ tự tái lập giữa nhiều lần tải dữ liệu, xuất báo cáo hoặc phân trang. Một khóa ổn định như ID có thể đảm bảo thứ tự ngay cả khi nhiều phần tử trùng tên và điểm.

### 7.1. Stable sort khác thứ tự xác định toàn cục

`List.sort` giữ thứ tự tương đối của các phần tử có `compare == 0` trong **danh sách nguồn**. Nhưng nếu danh sách đầu vào lấy từ nguồn có thứ tự không đảm bảo (như tập hợp hash), thứ tự các phần tử ngang nhau cũng không nhất thiết ổn định giữa nhiều lần tải dữ liệu.

Nếu cần phân trang nhất quán, bổ sung tiêu chí phụ đủ xác định thứ tự. Đây là vấn đề **thứ tự**, không phải lý do để thay đổi `equals`.

## 8. Comparator không quyết định hashCode

Hợp đồng `hashCode` gắn với `equals`:

```text
a.equals(b) == true
    ⇒ a.hashCode() == b.hashCode()
```

Comparator chỉ dùng để hiển thị không làm thay đổi phương thức `hashCode`. Hai bản ghi trùng khóa sắp xếp có thể có hash khác nhau nếu chúng không bằng nhau theo `equals`. Không có quy tắc bắt buộc `compare(a,b) == 0` phải kéo theo `hashCode` bằng nhau.

`TreeSet` và `TreeMap` cũng **không sử dụng hashCode** khi quyết định phần tử/khóa tương đương; chúng dựa vào `compare == 0`. Vì thế sửa `hashCode` không thể chữa lỗi TreeSet gộp những ID khác nhau do comparator chỉ xem tên.

Phân biệt rõ:

```text
Sắp xếp giao diện        -> Comparator với List.sort / Stream.sorted
Bằng nhau của đối tượng  -> equals
Tập hợp hoặc map băm     -> equals + hashCode
Tập hợp hoặc map có thứ tự -> Comparator / Comparable
```

## 9. Những vấn đề thường gặp với Comparator dùng cho UI

### 9.1. Sắp chuỗi không phân biệt hoa/thường

`String.CASE_INSENSITIVE_ORDER` giúp sắp tên theo thứ tự không phân biệt chữ hoa/thường. Nhưng `"java"` và `"JAVA"` có thể bị coi tương đương trong `TreeSet<String>` nếu dùng comparator ấy, dù `String.equals` của chúng trả `false`.

Nếu UI phải theo quy tắc ngôn ngữ, cân nhắc `java.text.Collator` với `Locale` phù hợp. Một collator cũng có thể coi các chuỗi khác nhau là tương đương ở một mức so sánh nhất định, nên hãy xác định rõ nó chỉ dùng sắp hiển thị hay còn được phép quyết định khóa.

### 9.2. Giá trị null

Khi khóa sắp xếp có thể `null`, nhiều comparator được tạo bằng `Comparator.comparing` cần một bộ so sánh hỗ trợ null. Ví dụ:

```java
Comparator<Article> byTitle =
        Comparator.comparing(
                Article::title,
                Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER));
```

Đây là minh họa dùng record `Article` từ mục 5. Tiêu đề `null` được xếp cuối, nhưng nhiều bản ghi có `null` vẫn có thể cùng khóa sắp xếp. Điều đó không sao khi sắp `List`, nhưng cần thận trọng khi dùng làm comparator cho `TreeSet`.

### 9.3. So sánh số

Tránh viết comparator số nguyên bằng phép trừ:

```java
// Có thể overflow với các giá trị int lớn:
(a, b) -> a - b
```

Dùng `Integer.compare(a,b)` hoặc `Comparator.comparingInt(...)` để giữ đúng thứ tự. Với `double`, dùng `Double.compare` hoặc `comparingDouble` và hiểu quy tắc NaN/signed zero khi cần. Comparator không tự biến phép so sánh số thực thành kiểm tra gần đúng.

### 9.4. Trường mutable

Nếu một đối tượng được thêm vào `TreeSet`/`TreeMap` rồi trường quyết định thứ tự bị thay đổi, cấu trúc cây có thể không còn tra cứu đúng theo vị trí khóa ban đầu. Nên tránh sửa trường tham gia comparator khi khóa đang nằm trong cấu trúc có thứ tự. Với danh sách, có thể cập nhật dữ liệu và sắp lại theo yêu cầu giao diện.

## 10. Quy trình chọn giải pháp

1. **Xác định quan hệ bằng nhau từ nghiệp vụ:** ID duy nhất, toàn bộ record component, mã SKU, tổ hợp trường giá trị hay quy tắc rõ ràng khác.
2. **Xác định khóa hiển thị độc lập:** điểm, tên, ngày, giá tiền, trạng thái… và chiều tăng/giảm.
3. **Chọn collection:** `List` để hiển thị đầy đủ; `HashSet`/`HashMap` nếu muốn duy nhất theo `equals/hashCode`; `TreeSet`/`TreeMap` khi thật sự muốn dùng quan hệ tương đương theo comparator.
4. **Xem xét tie-breaker:** thêm khóa ổn định nếu cần thứ tự xác định, đặc biệt cho phân trang.
5. **Kiểm tra hai chiều nhất quán** nếu dùng sorted set/map: trường hợp `compare == 0` nhưng `equals == false`, và `equals == true` nhưng `compare != 0`.
6. **Kiểm tra dữ liệu biên:** khóa `null`, khác hoa/thường, trùng tên, thay đổi trạng thái hoặc nguồn không có thứ tự ổn định.

| Nhu cầu | Cách triển khai phù hợp |
| --- | --- |
| Xếp danh sách thành viên theo điểm/tên, giữ mọi ID | `List.sort(displayComparator)` |
| Sắp kết quả có thứ tự tái lập | Thêm tie-breaker đủ ổn định |
| Duy nhất sản phẩm theo ID | Dùng ID làm khóa map hoặc định nghĩa `equals/hashCode` theo ID |
| Tập hợp duy nhất theo `equals` | `HashSet` |
| Tập hợp có thứ tự và duy nhất theo cùng `equals` | `TreeSet` với comparator consistent-with-equals |
| Cố ý gộp chuỗi theo so sánh không phân biệt hoa/thường | `TreeSet`/`TreeMap` với comparator ấy khi chính sách gộp được chấp nhận |
| Nhóm đối tượng cùng khóa hiển thị mà không mất bản ghi | `Map<GroupKey, List<Item>>` hoặc thao tác grouping tương đương |

## 11. Các lỗi tư duy dễ gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Comparator trả `0` nghĩa là `equals` trả `true`.” | Chỉ đúng với comparator **consistent with equals**. |
| “Hai phần tử cùng khóa sắp xếp là một đối tượng.” | Chúng có thể là hai ID khác nhau. |
| “`List.sort` loại bản ghi trùng thứ hạng.” | Không, nó chỉ thay đổi thứ tự. |
| “`TreeSet` dùng `equals` để kiểm tra trùng.” | Nó dùng `compare == 0` theo comparator/natural ordering. |
| “Thêm ID ở cuối luôn tạo comparator đúng với equals.” | Còn phụ thuộc trường nào quyết định `equals` của lớp. |
| “Nếu comparator dùng cho hiển thị, TreeMap cũng chỉ sắp thứ tự.” | Với `TreeMap`, comparator còn quyết định khóa tương đương, có thể thay giá trị. |
| “Sửa `hashCode` sẽ sửa lỗi TreeSet gộp nhầm.” | TreeSet không dùng hashCode để xác định phần tử trùng. |
| “Muốn sort theo tên thì phải ghi đè equals theo tên.” | Không, comparator có thể định nghĩa độc lập mà không đổi equality. |

## 12. Tự kiểm tra

**Câu 1.** Hai nhân viên khác ID nhưng cùng điểm và tên. Comparator theo điểm/tên trả `0`. Có được kết luận `equals` bằng `true` không?

**Đáp án:** Không. Comparator chỉ xác nhận cùng khóa thứ tự hiển thị; `equals` tùy hợp đồng lớp.

**Câu 2.** Sắp `List` theo điểm, hai người cùng điểm có bị mất một người không?

**Đáp án:** Không. `List.sort` giữ mọi phần tử, đồng thời stable nên giữ thứ tự tương đối của những phần tử comparator trả `0`.

**Câu 3.** Tại sao `TreeSet` có thể chỉ có một phần tử sau khi thêm hai đối tượng khác nhau theo `equals`?

**Đáp án:** Vì comparator của TreeSet có thể trả `0` cho cả hai, khiến TreeSet coi chúng là một phần tử tương đương.

**Câu 4.** Một `TreeMap` so khóa bài viết theo tiêu đề không phân biệt hoa/thường. Thêm `"Java"` rồi `"JAVA"` sẽ như thế nào?

**Đáp án:** Nếu comparator chỉ so tiêu đề không phân biệt hoa/thường, hai khóa tương đương; `put` thứ hai cập nhật giá trị mục đã có, không tạo mục thứ hai.

**Câu 5.** `Product.equals` chỉ so ID; comparator so tên rồi ID. Nó có nhất quán với equals không?

**Đáp án:** Không nhất thiết. Hai phiên bản có cùng ID nhưng khác tên bằng nhau theo `equals`, trong khi comparator có thể trả khác `0`.

**Câu 6.** Ứng dụng cần duy nhất sản phẩm theo ID và hiển thị theo tên. Nên xử lý ra sao?

**Đáp án:** Quản lý khóa bằng ID trong map hoặc collection phù hợp, rồi tạo danh sách dữ liệu để sắp theo tên. Nếu cần phân trang ổn định, thêm ID vào tiêu chí sắp danh sách.

## Kết luận

**`Comparator` xác định thứ tự, còn `equals` xác định sự bằng nhau của đối tượng.** Comparator dùng để hiển thị có thể trả `0` cho các bản ghi khác nhau theo `equals` mà không gây mất dữ liệu nếu chỉ dùng với `List.sort`. Nhưng `TreeSet`/`TreeMap` lấy `compare == 0` làm quan hệ tương đương của phần tử/khóa, do đó comparator hiển thị có thể làm gộp bản ghi hoặc cập nhật nhầm giá trị. Khi cần một sorted set/map tuân thủ quan hệ bằng nhau của đối tượng, phải kiểm tra cả hai chiều của điều kiện **consistent with equals**. Hãy tách chính sách bình đẳng nghiệp vụ khỏi yêu cầu sắp xếp giao diện.
