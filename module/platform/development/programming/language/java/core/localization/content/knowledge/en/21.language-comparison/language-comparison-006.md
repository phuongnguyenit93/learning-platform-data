# CollationKey khi cần so sánh lặp lại trong Java

## 1. Bài toán: sắp xếp tên theo ngôn ngữ mà vẫn hiệu quả

Trong ứng dụng đa ngôn ngữ, so sánh và sắp xếp chuỗi **không đơn giản là so sánh mã Unicode**. Thứ tự chữ cái, dấu, phân biệt hoa–thường và những tổ hợp ký tự có thể khác nhau giữa các ngôn ngữ. Vì thế, Java có `java.text.Collator` để so sánh văn bản theo `Locale`.

Giả sử một danh sách tên sản phẩm, tên khách hàng hoặc địa danh có hàng nghìn mục. Khi hiển thị, ứng dụng có thể phải:

1. Sắp xếp danh sách lần đầu.
2. Sắp xếp lại khi dữ liệu được lọc.
3. Tái sắp xếp theo nhóm, phân trang, hoặc hiển thị trong nhiều bảng.
4. So sánh nhiều cặp chuỗi trong các phép tìm kiếm hoặc gom nhóm.

Nếu dùng `collator.compare(a, b)` cho mọi lần so sánh, mỗi lần có thể phải phân tích lại chữ cái, dấu và các quy tắc collation của hai chuỗi. Nếu các **chuỗi giống nhau được so sánh nhiều lần**, Java cung cấp `CollationKey`: tính trước một dạng khóa sắp xếp cho từng chuỗi rồi so sánh các khóa đã chuẩn bị.

Điểm cần hiểu:

- **`Collator.compare`**: áp dụng quy tắc so sánh trực tiếp lên hai chuỗi ở thời điểm so sánh.
- **`Collator.getCollationKey`**: tính trước một biểu diễn so sánh của từng chuỗi dưới **một Collator cụ thể**.
- **`CollationKey.compareTo`**: so sánh hai khóa đã có, thường tiết kiệm công việc khi cùng dữ liệu phải được so sánh lặp đi lặp lại.

**CollationKey không thay đổi quy tắc sắp xếp**, không phải bản dịch, không phải cách chuẩn hóa chuỗi chung cho mọi locale. Nó là phương án **đổi chi phí tạo key một lần lấy chi phí so sánh lặp lại thấp hơn**, kèm chi phí bộ nhớ.

## 2. CollationKey và Collator là gì?

`Collator` là đối tượng có quy tắc so sánh văn bản theo `Locale`, thường bao gồm:

- Thứ tự cơ bản của chữ cái;
- Mức phân biệt dấu/diacritic;
- Mức phân biệt chữ hoa và chữ thường;
- Quy tắc về biến thể ký tự, dấu kết hợp và decomposition;
- Những quy tắc đặc thù ngôn ngữ, như thứ tự chữ cái tiếng Thổ, tiếng Thụy Điển hoặc tiếng Pháp.

`CollationKey` là đối tượng biểu diễn một chuỗi **theo đúng các quy tắc của Collator đã tạo key**.

Ví dụ:

```java
Locale locale = Locale.forLanguageTag("vi-VN");
Collator collator = Collator.getInstance(locale);

CollationKey first = collator.getCollationKey("An");
CollationKey second = collator.getCollationKey("Bình");

int order = first.compareTo(second);
```

Đây là **đoạn minh họa bên trong method** có import `java.text.Collator`, `java.text.CollationKey` và `java.util.Locale`. `order` mang dấu âm, bằng 0 hoặc dấu dương để thể hiện thứ tự dưới quy tắc collation của formatter này; không nên dựa vào độ lớn tuyệt đối của kết quả `compareTo`.

### Bảng API

| API | Đầu vào | Đầu ra / ý nghĩa |
| --- | --- | --- |
| `Collator.getInstance(locale)` | `Locale` | Collator áp dụng các quy tắc của locale |
| `collator.setStrength(level)` | `PRIMARY`, `SECONDARY`, `TERTIARY`, `IDENTICAL` | Mức khác biệt cần xét |
| `collator.setDecomposition(mode)` | Ví dụ `CANONICAL_DECOMPOSITION` | Quy tắc xử lý biểu diễn Unicode tổ hợp |
| `collator.compare(a, b)` | Hai `String` | Giá trị âm/0/dương thể hiện thứ tự |
| `collator.getCollationKey(s)` | Một `String` | `CollationKey` được tạo từ Collator đó |
| `keyA.compareTo(keyB)` | Hai khóa **cùng Collator** | Giá trị âm/0/dương |
| `key.getSourceString()` | Không có tham số | Chuỗi nguồn mà key đại diện |
| `key.toByteArray()` | Không có tham số | Biểu diễn byte của key; không phải chuỗi dùng để dịch |
| `CollationKey.equals/hashCode` | Một key khác / không có tham số | Equality và hash của key theo hợp đồng đối tượng |

`CollationKey` là **abstract class** triển khai `Comparable<CollationKey>`. Ứng dụng không tạo nó bằng `new CollationKey(...)`; hãy gọi `Collator.getCollationKey(String)`.

**Ràng buộc quan trọng nhất theo Java API:** chỉ so sánh hai `CollationKey` được tạo từ **cùng một `Collator`**. Không trộn key từ `Collator.getInstance(Locale.US)` với key từ một Collator cho `vi-VN` hoặc key được tạo sau khi đã đổi cấu hình Collator. Dù hai Collator có vẻ có cùng locale và cùng thuộc tính, tài liệu Java vẫn không hứa rằng mọi key do hai instance khác nhau tạo ra đều có thể so sánh hợp lệ.

## 3. Trực tiếp so sánh với Collator hay tính key trước?

Giả sử có N tên cần sort. Thuật toán sort thường thực hiện nhiều hơn N phép so sánh (thông thường cỡ N log N với comparison sort). So sánh trực tiếp:

```java
Collator collator = Collator.getInstance(locale);
names.sort(collator::compare);
```

Với mỗi lần comparator được gọi, `collator.compare(a, b)` xử lý các chuỗi liên quan để tìm thứ tự.

Nếu ta tính key trước:

```text
DANH SÁCH TÊN                    CHUẨN BỊ
"An"                           -> keyAn
"Bình"                         -> keyBinh
"Chi"                          -> keyChi

SO SÁNH LẶP LẠI
keyAn.compareTo(keyBinh)
keyAn.compareTo(keyChi)
keyBinh.compareTo(keyChi)
...

Chuỗi chỉ cần được đưa qua getCollationKey một lần
cho mỗi phần tử trong snapshot dữ liệu đó.
```

Chi phí được chia thành:

- **Chuẩn bị:** tạo `CollationKey` cho mỗi chuỗi, phải phân tích toàn bộ chuỗi.
- **So sánh:** `compareTo` trên key thường có lợi khi thực hiện nhiều phép so sánh.
- **Bộ nhớ:** key có kích thước riêng, không miễn phí.
- **Bảo trì:** khi chuỗi, locale hoặc quy tắc Collator thay đổi, key cần được tạo lại.

### Khi nào thực sự lợi?

| Tình huống | Cách tiếp cận thường hợp lý |
| --- | --- |
| So sánh hai chuỗi đúng một lần | `collator.compare(a, b)` thường đơn giản và nhanh hơn |
| Sort một danh sách lớn | Thử tạo keys trước; có thể tiết kiệm thời gian so sánh |
| Sort lại cùng tập chuỗi nhiều lần | Tái sử dụng keys phù hợp nếu config không đổi |
| Dữ liệu thay đổi liên tục, mỗi chuỗi ít được so sánh | Chi phí tạo/cập nhật key có thể không đáng |
| Có nhiều locale cho cùng dữ liệu | Mỗi locale cần **bộ keys riêng**, không dùng key locale này cho locale khác |
| Dữ liệu lớn nhưng có sẵn thứ tự/sort index từ DB | Xem xét database collation/index thay vì tính toàn bộ keys trên JVM |
| Chỉ cần so sánh byte protocol hoặc ID kỹ thuật | Không dùng collation ngôn ngữ nếu không có nhu cầu |

**Không có ngưỡng “từ 100 chuỗi trở lên là nên dùng key” đúng với mọi hệ thống.** Hiệu quả phụ thuộc độ dài tên, bảng chữ, tỷ lệ dấu, thời gian sống của cache, tần suất sort, bộ nhớ và cấu hình JDK/locale provider. Hãy benchmark bằng workload thực tế.

## 4. Ví dụ Java 17: sắp xếp bằng CollationKey

Tạo tệp `CollationKeySortDemo.java`:

```java
import java.text.CollationKey;
import java.text.Collator;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

public class CollationKeySortDemo {
    record Entry(String text, CollationKey key) {}

    public static void main(String[] args) {
        Locale locale = Locale.US;
        Collator collator = Collator.getInstance(locale);
        collator.setStrength(Collator.TERTIARY);

        List<String> names = List.of(
                "Zulu", "Alpha", "Bravo", "Charlie");

        List<Entry> entries = new ArrayList<>();
        for (String name : names) {
            entries.add(new Entry(
                    name, collator.getCollationKey(name)));
        }

        entries.sort(Comparator.comparing(Entry::key));

        for (Entry entry : entries) {
            System.out.println(entry.text());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CollationKeySortDemo.java
java CollationKeySortDemo
```

Stdout với quy tắc `Locale.US` thông dụng:

```text
Alpha
Bravo
Charlie
Zulu
```

Điều quan trọng hơn bảng chữ ví dụ là **thiết kế**:

1. Tạo **một** `Collator`, cấu hình `strength` **trước** khi tạo key.
2. Mỗi `Entry` giữ cả chuỗi gốc và `CollationKey` tương ứng.
3. Comparator dùng `Entry::key`; `CollationKey` tự triển khai `Comparable` nên có thể dùng `Comparator.comparing(...)`.
4. Mỗi lần sort gọi so sánh **key**, không bắt buộc sinh lại key trong comparator.
5. Người dùng vẫn thấy `entry.text()`, **không phải các byte của key**.

Cách này đặc biệt phù hợp khi cùng tập `Entry` được sắp xếp nhiều lần, hoặc cần so sánh từng tên trong nhiều thao tác.

**Cần phân biệt:** ví dụ sort này dùng những từ ASCII đơn giản để giải thích, không chứng minh thứ tự cho mọi bảng chữ. Với tiếng Việt, tiếng Thổ, tiếng Thụy Điển hoặc nhiều dấu/ligature, kết quả phụ thuộc locale và provider. Không hard-code thứ tự các tên nhiều dấu theo suy luận bảng mã.

## 5. Chương trình kiểm tra tính nhất quán với Collator.compare

Theo API Java, hai khóa được tạo bởi một `Collator` có cùng quy tắc phải cho quan hệ thứ tự như khi `Collator.compare` trực tiếp các chuỗi.

Tệp `KeyVsCompareDemo.java`:

```java
import java.text.CollationKey;
import java.text.Collator;
import java.util.Locale;

public class KeyVsCompareDemo {

    private static int sign(int value) {
        return Integer.compare(value, 0);
    }

    public static void main(String[] args) {
        Collator collator = Collator.getInstance(Locale.US);
        collator.setStrength(Collator.PRIMARY);

        String[] values = {
                "Alpha", "alpha", "Bravo", "bravo"
        };

        CollationKey[] keys = new CollationKey[values.length];
        for (int i = 0; i < values.length; i++) {
            keys[i] = collator.getCollationKey(values[i]);
        }

        boolean sameOrder = true;
        for (int i = 0; i < values.length; i++) {
            for (int j = 0; j < values.length; j++) {
                int direct = collator.compare(values[i], values[j]);
                int byKey = keys[i].compareTo(keys[j]);

                if (sign(direct) != sign(byKey)) {
                    sameOrder = false;
                }
            }
        }

        System.out.println("sameOrder=" + sameOrder);
        System.out.println("sameSource=" +
                keys[0].getSourceString().equals(values[0]));
        System.out.println("selfCompare=" +
                keys[0].compareTo(keys[0]));
    }
}
```

```bash
javac -encoding UTF-8 KeyVsCompareDemo.java
java KeyVsCompareDemo
```

Stdout:

```text
sameOrder=true
sameSource=true
selfCompare=0
```

**Vì sao `sign` quan trọng?** Hợp đồng compare chỉ cam kết kết quả **âm / 0 / dương**, không cam kết trị tuyệt đối như `-1` hoặc `+1`. So sánh `Integer.compare(x, 0)` sẽ kiểm tra đúng tính tương đương về thứ tự.

Vòng lặp trên là một **test nhỏ để đối chiếu hành vi**, không phải benchmark hiệu năng. Nó còn cho thấy `getSourceString()` giữ nguyên chuỗi nguồn để ứng dụng có thể lấy lại nội dung hiển thị. Với một `Collator` chuẩn được giữ nguyên cấu hình, `Collator.compare` và `CollationKey.compareTo` phải nhất quán về thứ tự.

## 6. Strength quyết định thế nào là “khác nhau”

`Collator` cho phép chọn độ nhạy so sánh bằng `setStrength`:

| Strength | Ý nghĩa tổng quát | Ghi chú |
| --- | --- | --- |
| `PRIMARY` | Chỉ khác biệt chính thường mang tính chữ cơ sở được xét | Một số dấu/case có thể bị bỏ qua |
| `SECONDARY` | Thêm khác biệt cấp hai | Thường xét thêm một số dấu |
| `TERTIARY` | Thêm khác biệt cấp ba | Thường phân biệt case/biến thể |
| `IDENTICAL` | Xét cả khác biệt tinh hơn | Tùy decomposition và Unicode data |

Cách gán độ quan trọng cho chữ cái, dấu và case **phụ thuộc locale**. Ví dụ trong một ngôn ngữ, một ký tự có dấu được xem là biến thể secondary; ở ngôn ngữ khác, nó là chữ cái riêng thuộc primary. Vì vậy đừng khẳng định cứ `PRIMARY` là “bỏ mọi dấu trong tất cả ngôn ngữ”.

Ví dụ:

```java
Collator collator = Collator.getInstance(
        Locale.forLanguageTag("fr-FR"));

collator.setStrength(Collator.PRIMARY);
CollationKey keyA = collator.getCollationKey("cafe");
CollationKey keyB = collator.getCollationKey("café");
```

Đây là **đoạn minh họa trong method**. Với nhiều provider tiếng Pháp, hai chuỗi có thể được xem là tương đương ở cấp PRIMARY; nhưng không dùng ví dụ đó để suy mọi chữ có dấu của mọi ngôn ngữ đều được gom chung.

### Quy tắc khi cache key theo strength

**Sai:**

```java
Collator collator = Collator.getInstance(locale);
collator.setStrength(Collator.PRIMARY);

CollationKey first = collator.getCollationKey("A");

collator.setStrength(Collator.TERTIARY);
CollationKey second = collator.getCollationKey("a");

// KHÔNG so sánh first với second rồi tin là cùng chính sách.
```

Khi đổi strength sau khi đã tạo key, hai khóa được tạo từ **hai trạng thái quy tắc khác nhau**. Dù về mặt đối tượng vẫn dùng cùng Collator instance, không có cơ sở nghiệp vụ để so sánh chúng như một tập thống nhất. Hãy thiết lập cấu hình hoàn chỉnh **trước** khi tạo keys, giữ bất biến trong vòng đời bộ key và **tạo lại toàn bộ** nếu đổi strength.

**Decomposition cũng vậy:** nếu đổi `setDecomposition(...)`, phải invalidate keys cũ và sinh lại theo thiết lập mới.

## 7. Unicode decomposition và dạng dựng sẵn/tổ hợp

Unicode cho phép một số chữ có nhiều cách biểu diễn:

```text
"é"      U+00E9              (precomposed)
"é"      U+0065 U+0301       (e + combining accent)
```

Hai chuỗi có thể hiển thị giống nhau nhưng `String.equals` trả `false`. `Collator` có lựa chọn decomposition:

- `Collator.NO_DECOMPOSITION`: không thực hiện decomposition khi so sánh.
- `Collator.CANONICAL_DECOMPOSITION`: xử lý canonical decomposition khi cần, hỗ trợ so sánh các dạng Unicode canonically equivalent.
- `Collator.FULL_DECOMPOSITION`: xét thêm compatibility decomposition; có thể khiến một số ký tự tương thích được đối xử gần nhau hơn.

Cần chọn decomposition theo mục tiêu ngôn ngữ và dữ liệu. Nó ảnh hưởng **cả `compare` lẫn key đã tạo**. `java.text.Normalizer` là công cụ riêng để chuẩn hóa văn bản; không đồng nhất normalization của dữ liệu gốc với tùy chọn decomposition của Collator.

Ví dụ:

```java
Collator collator = Collator.getInstance(Locale.FRANCE);
collator.setStrength(Collator.TERTIARY);
collator.setDecomposition(
        Collator.CANONICAL_DECOMPOSITION);

CollationKey composed =
        collator.getCollationKey("\u00E9");
CollationKey decomposed =
        collator.getCollationKey("e\u0301");
```

Đây là code minh họa trong method. Trong so sánh canonical, các biểu diễn tương đương nên có quan hệ bằng nhau theo collation rules được áp dụng. Khi đổi decomposition, không tiếp tục dùng key từ cấu hình cũ trong cùng index/cache.

**Đừng dùng byte representation của key làm dạng normalization.** CollationKey là một khóa so sánh gắn với Collator, không phải văn bản canonical sẽ được tìm kiếm/hiển thị hay lưu như nguồn dữ liệu chính.

## 8. Không được trộn CollationKey từ nhiều Collator

Đây là ràng buộc kỹ thuật quan trọng nhất của loại key này.

Giả sử:

```java
Collator vi = Collator.getInstance(
        Locale.forLanguageTag("vi-VN"));
Collator en = Collator.getInstance(Locale.US);

CollationKey viKey = vi.getCollationKey("Đà Nẵng");
CollationKey enKey = en.getCollationKey("Đà Nẵng");
```

**Không được** dùng `viKey.compareTo(enKey)` để suy ra thứ tự: API ghi rõ CollationKeys không so sánh hợp lệ nếu đến từ Collators khác nhau. Tương tự, không gộp keys từ một Collator PRIMARY vào keys tạo theo TERTIARY.

### Vì sao ràng buộc ấy tồn tại?

Thứ tự ngôn ngữ giống “thước đo có quy tắc”. Nếu mỗi key được tạo bằng một thước đo khác nhau, phép so sánh byte không còn biểu diễn một quan hệ thứ tự thống nhất. Có locale coi chữ có dấu là biến thể của chữ cơ sở; locale khác có thể xếp nó như chữ độc lập. Strength/decomposition còn làm những khác biệt được xét hoặc bị bỏ qua.

### Thiết kế phù hợp

- Một danh sách sort theo **vi-VN/TERTIARY/CANONICAL_DECOMPOSITION** → sinh bộ key bằng một Collator cấu hình tương ứng.
- Chuyển giao diện sang **en-US** → **không** dùng lại bộ key tiếng Việt; tạo Collator/bộ key mới.
- Đổi bộ lọc so sánh không phân biệt dấu/case bằng `PRIMARY` → tạo bộ key riêng, không dùng key `TERTIARY`.
- Nếu cache theo profile, mỗi entry phải có thông tin **locale, strength, decomposition, provider/version nếu cần**, và một chính sách thống nhất về nguồn keys.

Tài liệu Java nói **“cùng một Collator”**, nên thực hành đơn giản nhất là quản lý **một Collator cố định cho một đợt tạo keys** và không trộn key giữa các lần build khác cấu hình. Khi muốn dùng cache qua nhiều phiên của JVM, cần hiểu thêm khả năng thay đổi dữ liệu collation sau nâng cấp.

## 9. Phương án “decorate–sort–undecorate”

Thay vì viết comparator luôn gọi `collator.getCollationKey(...)`, ta chuẩn bị khóa một lần cho mỗi bản ghi rồi sort. Đây là một dạng *decorate–sort–undecorate*.

**Không nên tạo key bên trong comparator như sau:**

```java
names.sort((a, b) -> {
    CollationKey ka = collator.getCollationKey(a);
    CollationKey kb = collator.getCollationKey(b);
    return ka.compareTo(kb);
});
```

Đây là đoạn minh họa trong method. Nó vẫn phải tạo **hai khóa mỗi lần comparator được gọi**, làm mất lợi ích của việc chuẩn bị trước; số lần tạo có thể rất lớn.

**Nên:**

```text
raw records
    |
    v
records + CollationKey (mỗi record một lần)
    |
    v
sort bằng CollationKey.compareTo
    |
    v
xuất records/text gốc theo thứ tự
```

Dưới đây là ví dụ đầy đủ, giữ cả ID và text để không làm mất dữ liệu gốc.

### Java 17 runnable: sort bản ghi và dùng lại keys

Tệp `CachedNameSortDemo.java`:

```java
import java.text.CollationKey;
import java.text.Collator;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;

public class CachedNameSortDemo {
    record Item(int id, String displayName) {}
    record IndexedItem(Item item, CollationKey key) {}

    public static void main(String[] args) {
        Collator collator = Collator.getInstance(Locale.US);
        collator.setStrength(Collator.TERTIARY);

        List<Item> items = List.of(
                new Item(3, "Charlie"),
                new Item(1, "Alpha"),
                new Item(2, "Bravo"));

        List<IndexedItem> indexed = new ArrayList<>();
        for (Item item : items) {
            indexed.add(new IndexedItem(
                    item,
                    collator.getCollationKey(item.displayName())));
        }

        // Một lần sort, không tạo key trong comparator:
        Comparator<IndexedItem> byKey =
                Comparator.comparing(IndexedItem::key);

        indexed.sort(byKey);
        System.out.println("firstSort:");
        for (IndexedItem value : indexed) {
            System.out.println(value.item().id() + "="
                    + value.item().displayName());
        }

        // Sort lại theo cùng quy tắc, tái sử dụng keys:
        indexed.sort(byKey.reversed());
        System.out.println("reverseSort:");
        for (IndexedItem value : indexed) {
            System.out.println(value.item().id() + "="
                    + value.item().displayName());
        }
    }
}
```

```bash
javac -encoding UTF-8 CachedNameSortDemo.java
java CachedNameSortDemo
```

Stdout trên bộ quy tắc thông dụng của `Locale.US`:

```text
firstSort:
1=Alpha
2=Bravo
3=Charlie
reverseSort:
3=Charlie
2=Bravo
1=Alpha
```

Bài học chính không phải sort đảo chiều mà là **cùng ba keys được dùng lại**. Đợt sort thứ hai không cần phân tích lại các chuỗi nguồn thành collation keys.

Nếu danh sách thay đổi tên hiển thị, `IndexedItem` của bản ghi đó phải được thay bằng key mới theo cùng cấu hình. `CollationKey` không tự quan sát hoặc cập nhật khi field `displayName` của object khác thay đổi.

## 10. So sánh lặp lại và cache: không tự động lợi nếu dữ liệu biến động

Ví dụ một UI thường xuyên sort tên khách hàng theo locale hiện tại. Ta có thể cache bộ key theo snapshot dữ liệu; mỗi lần sort/filter dùng lại key.

Tuy nhiên, key cache cần chính sách:

### 10.1. Khi nào invalidation?

| Sự kiện | Có cần tạo lại key không? | Vì sao |
| --- | --- | --- |
| Chuỗi nguồn đổi | **Có** | Key đại diện cho chuỗi cũ |
| Locale đổi | **Có** | Quy tắc thứ tự thay đổi |
| Strength đổi | **Có** | Mức khác biệt đáng kể thay đổi |
| Decomposition đổi | **Có** | Cách xử lý Unicode thay đổi |
| Collation provider/rules đổi | **Có** | Key byte/order có thể khác |
| Chỉ thay thứ tự sort ASC/DESC | Không, nếu cùng tập keys và config | Đảo comparator hoặc kết quả |
| Đổi màu hoặc kích thước chữ UI | Không | Không thay dữ liệu so sánh |
| Chỉ thay giá trị field khác không tham gia sort | Không | Khóa so sánh vẫn từ chuỗi cũ |
| Thêm record mới | Tạo key cho record mới | Đưa vào cùng tập cấu hình |

### 10.2. Định danh cache

Một cache đơn giản có thể gắn với **một sort context**:

```text
SortContext:
  locale: vi-VN
  strength: TERTIARY
  decomposition: CANONICAL_DECOMPOSITION
  ruleVersion: runtime-defined
  datasetRevision: 42
```

Đây là ví dụ **metadata thiết kế**, không phải class của Java API. Trong một lần sort, giữ `Collator` cố định, tạo toàn bộ keys rồi không thay cấu hình. Nếu build lại sort context thì regenerate cả bộ keys; không trộn byte/key cũ với mới.

### 10.3. Cache vô hạn là một lỗi khác

Mỗi `CollationKey` chứa dữ liệu so sánh đã tính và thông tin liên quan đến chuỗi nguồn. Với hàng triệu bản ghi hoặc hàng chục locale, số lượng key và chi phí heap/GC có thể lớn. Một “cache toàn cục mọi chuỗi của mọi ngôn ngữ” có thể chậm hơn so với tạo keys theo snapshot rồi giải phóng.

Thiết kế theo vòng đời rõ ràng: cache per request, per screen, per dataset revision, hoặc LRU có giới hạn; đo heap, tốc độ làm mới và hit rate. Nếu hệ thống đã dùng collation index của database, cân nhắc so sánh/sort ngay tại nơi dữ liệu được lưu.

## 11. Equality, hash và khóa cho Set/Map: không nhầm với chuỗi gốc

Có nhiều khái niệm “bằng nhau”:

1. `String.equals`: cùng chuỗi UTF-16 code units.
2. `Collator.compare(a, b) == 0`: tương đương theo **quy tắc collation hiện tại**, phụ thuộc locale/strength.
3. `CollationKey.compareTo(other) == 0`: hai key cùng Collator tương đương về sort.
4. `String.equalsIgnoreCase`: so sánh không phân biệt case theo quy tắc riêng của Java, **không nhận locale**.

Nếu cấu hình strength = `PRIMARY`, hai chuỗi khác code units có thể được xem bằng nhau theo collation. Khi đưa `CollationKey` vào `TreeMap` hoặc `TreeSet`, comparator/ordering bằng 0 có thể khiến hai chuỗi được coi là **cùng một key sắp xếp**. Điều đó có thể mong muốn khi gom nhóm nhưng **không** tự phù hợp cho dữ liệu định danh duy nhất.

Đừng dùng collation PRIMARY để xác thực password, chữ ký, token hoặc các định danh đòi hỏi equality byte/code-point chính xác. Một kết quả `compareTo == 0` không có nghĩa hai giá trị nguồn giống nhau hoặc có thể hoán đổi về nghiệp vụ.

### 11.1. Vấn đề tie: hai tên có cùng collation weight

Giả sử hai chuỗi được coi bằng nhau ở PRIMARY (ví dụ khác hoa/thường theo locale). Comparator chỉ dùng key sẽ trả 0. Một sort stable có thể giữ thứ tự đầu vào cho hai phần tử này; nhưng nếu đầu vào đến từ query không có thứ tự ổn định, UI có thể thay đổi vị trí giữa các lần load.

Khi muốn thứ tự đầu ra **xác định tuyệt đối**, có thể thêm tie-breaker:

```java
Comparator<IndexedItem> deterministic =
        (a, b) -> {
            int primary = a.key().compareTo(b.key());
            if (primary != 0) {
                return primary;
            }
            return Integer.compare(
                    a.item().id(), b.item().id());
        };
```

Đây là đoạn minh họa trong lớp có record `IndexedItem`/`Item` từ ví dụ trên. Dùng ID làm tie-breaker giúp các bản ghi cùng collation weight được xếp theo ID.

**Cẩn thận về semantics:** thêm ID tạo một thứ tự tổng quát cho UI, nhưng **thay đổi tiêu chí hai phần tử “bằng nhau” đối với comparator**. Nếu muốn gom nhóm các chuỗi coi tương đương theo locale, đừng dùng comparator có tie-breaker để xác định nhóm; hãy dùng **kết quả key compareTo 0** riêng cho grouping.

### 11.2. Hash code và key

`CollationKey` có `equals`/`hashCode` để hỗ trợ các cấu trúc Java. Tuy nhiên, không trộn key sinh từ các Collator khác nhau rồi mong `HashMap<CollationKey,...>` phản ánh đúng equality ngôn ngữ. Một cơ chế cache/index cần bảo đảm **mọi key được xây dựng trong cùng sort context**. Khi giá trị chuỗi khác nhau nhưng có collation weight bằng nhau, cần quyết định rõ sản phẩm muốn giữ hai bản ghi hay gộp chúng.

## 12. toByteArray: không phải định dạng byte ổn định cho API và database

`CollationKey.toByteArray()` trả một dãy byte biểu diễn key. API cho biết các byte có thể được sử dụng để xác định thứ tự khi **hai CollationKey vốn hợp lệ để so sánh**; byte theo thứ tự từ trọng số đáng kể nhất.

Tuy nhiên:

- Dữ liệu byte là **sort representation**, không phải UTF-8 của `getSourceString()`.
- Đây không phải ID duy nhất của chuỗi.
- Không được lấy bytes từ Collator tiếng Việt rồi so sánh với bytes từ Collator tiếng Anh.
- Không giả định bytes sẽ giữ nguyên sau khi JDK, CLDR, locale provider hoặc rule set được cập nhật.
- Không biến chuỗi byte thành giao thức trao đổi giữa nhiều hệ thống không có version/rules chung.
- Không dùng array `byte[]` để làm key HashMap trực tiếp nếu muốn equality theo nội dung: Java array dùng object identity cho `equals`, trừ khi được bọc bằng kiểu có `Arrays.equals/hashCode`.

Đặc biệt, `toByteArray()` **không** thay thế `String.getBytes(StandardCharsets.UTF_8)`. Hai thao tác phục vụ **hai mục tiêu hoàn toàn khác nhau**: một cho collation, một cho encoding văn bản.

### Vì sao không nên persist collation key dài hạn?

Giả sử xây index sort tại JDK 17 theo một bộ dữ liệu CLDR, sau đó deploy lên runtime mới có quy tắc khác. Byte cũ và byte mới có thể không còn tương thích; trộn chúng có thể tạo thứ tự sai. Với persistence/index lớn, cần **version hóa collation rules**, chiến lược rebuild index và test migration, hoặc dùng tính năng index collation của hệ quản trị dữ liệu với hợp đồng nâng cấp được tài liệu hóa.

**Không cần lưu `CollationKey` như một field canonical** khi có thể tái tạo từ tên gốc, locale và rule set đúng phiên bản.

## 13. Locale và ngữ cảnh nghiệp vụ

Một số ví dụ về sự khác biệt thứ tự ngôn ngữ:

- Tiếng Thổ phân biệt chữ I không chấm với chữ i có chấm; lowercase kiểu `Locale.ROOT` không thay thế trật tự collation tiếng Thổ.
- Một số ngôn ngữ xếp chữ có dấu như biến thể của chữ cơ sở; ngôn ngữ khác xem chúng là chữ cái độc lập.
- Ngôn ngữ có quy tắc ghép nhiều chữ (contraction) hoặc chữ được phân rã thành nhiều trọng số (expansion).
- Tên người và tên sản phẩm có thể trộn Latin, chữ viết khác, số và dấu câu, cần policy phù hợp.

`Collator.getInstance(locale)` lấy bộ quy tắc theo locale mà runtime có thể cung cấp. Không phải mọi locale có bộ quy tắc chuyên biệt hoàn toàn; provider có thể fallback theo dữ liệu hỗ trợ. Hệ thống nên xác định danh sách locale hỗ trợ thực tế và kiểm thử thứ tự với tập dữ liệu bản địa.

### Không dùng một Collator cho mọi locale

`CollationKey` của `vi-VN` được xây dựng để xử lý tiếng Việt theo provider. Nếu chuyển màn hình sang `sv-SE` hoặc `tr-TR`, cần xây key theo ngôn ngữ mới. Ngay cả khi cùng văn bản, ý nghĩa “xếp đúng chữ cái” vẫn phụ thuộc người dùng và loại danh sách.

### Default JVM locale

`Collator.getInstance()` sử dụng default locale của JVM. Nếu backend phục vụ đồng thời nhiều người dùng, không dựa vào nó cho mọi request. Nên dùng:

```java
Collator collator = Collator.getInstance(userLocale);
```

Đây là đoạn minh họa trong method có `userLocale` được xác định. Không gọi `Locale.setDefault(...)` theo từng HTTP request: default locale là trạng thái toàn JVM và có thể gây tác động chéo giữa request.

## 14. Thread safety: tránh chia sẻ Collator mutable sai cách

`Collator` có những phương thức như `setStrength` và `setDecomposition`, tức là **mutable**. Không dùng một instance chung rồi thay cấu hình theo locale/strength cho nhiều request đồng thời.

Ngay cả khi cấu hình không đổi, một số triển khai `RuleBasedCollator` của JDK có thể xảy ra **contention** khi dùng chung giữa nhiều luồng. Tùy provider và workload, nên cân nhắc instance theo luồng/request hoặc cơ chế clone có kiểm soát. Nếu cache các `CollationKey` immutable cho một snapshot, nên tạo chúng từ một cấu hình ổn định trước khi chia sẻ cho các thao tác chỉ đọc.

Ví dụ cấu trúc an toàn về mặt ngữ nghĩa:

```text
Request/sort job:
  1. Lấy locale đã được phép.
  2. Tạo một Collator cho locale ấy.
  3. Set strength/decomposition một lần.
  4. Tạo keys cho toàn bộ dữ liệu.
  5. Không mutate Collator đã dùng cho key.
  6. Sort/compare keys trong cùng batch.
  7. Giải phóng hoặc cache batch với metadata và TTL rõ.
```

Không bắt buộc tạo instance trên mỗi lần comparator chạy; chỉ yêu cầu quản lý vòng đời rõ ràng và cùng quy tắc. Nếu benchmark chỉ đo `compareTo` mà quên chi phí tạo keys/heap/GC, có thể kết luận sai về tổng hiệu năng.

## 15. Chiến lược benchmark đúng

Không nên kết luận “`CollationKey` luôn nhanh hơn” chỉ vì một lần thử sắp xếp.

Cần so sánh ít nhất hai hướng trên **cùng tập dữ liệu**:

**A. Direct comparison**

```java
names.sort(collator::compare);
```

**B. Precomputed key**

```text
Tạo các CollationKey cho N phần tử
→ sort theo key.compareTo
→ trả lại danh sách các bản ghi gốc
```

Các đại lượng cần đo:

| Chỉ số | Vì sao cần |
| --- | --- |
| Thời gian tạo toàn bộ keys | Chi phí ban đầu; có thể lớn |
| Thời gian sort bằng keys | Lợi ích so sánh đã chuẩn bị |
| Tổng thời gian A so với tổng thời gian B | Quyết định cho sort một lần |
| Thời gian sort thứ 2/3/4 | Đo lợi ích khi tái sử dụng |
| Kích thước heap và allocations | Keys chiếm bộ nhớ/GC |
| Tỷ lệ dữ liệu được thay đổi | Ảnh hưởng chi phí regenerate |
| Độ dài và alphabet thực tế | Chuỗi ngắn đơn giản khác chuỗi dài nhiều dấu |
| Số lượng locale | Nhiều context có thể nhân chi phí cache |
| JDK/vendor/provider | Collation algorithm/data có thể khác |

### Lưu ý khi benchmark Java

- JVM có JIT và warm-up; không suy từ một lượt chạy đầu tiên.
- Dữ liệu có sẵn thứ tự, trùng lặp nhiều, hoặc gần ngẫu nhiên có thể thay đổi số phép so sánh.
- Tránh đo cả `System.out.println` trong vùng benchmark.
- Nếu cần benchmark nghiêm túc, dùng **JMH (Java Microbenchmark Harness)** hoặc công cụ đo phù hợp, có warm-up, fork, nhiều vòng và kiểm soát GC.
- Kiểm tra hai phương án trả **thứ tự tương đương theo cùng Collator**, thay vì chỉ đo tốc độ.
- Ghi lại chính sách tie-breaker, vì comparator khác nhau có thể cho thứ tự khi key bằng nhau khác.

**Không có con số tốc độ cố định** như “CollationKey nhanh gấp 10 lần”. Hãy đo với dữ liệu ứng dụng thật; chỉ dùng keys nếu lợi ích lớn hơn chi phí chuẩn bị và quản lý.

## 16. Kiểm thử chức năng trước hiệu năng

Một bộ test tốt nên kiểm tra:

1. **Tính tương đương:** với mọi cặp chuỗi trong tập test, `sign(collator.compare(a,b)) == sign(keyA.compareTo(keyB))`.
2. **Locale:** mỗi locale `vi-VN`, `tr-TR`, `en-US`, `sv-SE` dùng bộ keys riêng; kiểm tra trật tự dự kiến với dữ liệu bản địa.
3. **Strength:** PRIMARY/SECONDARY/TERTIARY/IDENTICAL có thể thay kết quả so sánh các biến thể case/dấu.
4. **Decomposition:** thử composed và decomposed Unicode như `"\u00E9"` và `"e\u0301"`.
5. **Không trộn keys:** bổ sung quy tắc code review hoặc type wrapper để key từ context khác không đi vào cùng batch.
6. **Dữ liệu cập nhật:** sửa displayName phải invalidate key liên quan.
7. **Thứ tự trùng:** hai key tương đương theo collation có cách tie-break hoặc stable sort được định nghĩa.
8. **Null:** có policy riêng cho giá trị thiếu; không giả định mọi API so sánh chấp nhận null như chuỗi bình thường.
9. **Không phụ thuộc default locale:** truyền locale tường minh.
10. **Đồng thời:** không có request làm thay strength/decomposition của Collator khác.
11. **Upgrade:** sau nâng JDK/provider, có test nghiệm thu thứ tự và kế hoạch rebuild keys.
12. **Byte keys:** không sử dụng `toByteArray` như hash text/canonical identifier.

### JUnit 5: ví dụ hướng kiểm thử

Đoạn sau nằm **trong test class** có import JUnit tương ứng, không phải một chương trình `main` độc lập:

```java
Collator c = Collator.getInstance(Locale.US);
c.setStrength(Collator.PRIMARY);

String a = "Alpha";
String b = "alpha";

int direct = Integer.signum(c.compare(a, b));
int precomputed = Integer.signum(
        c.getCollationKey(a).compareTo(
                c.getCollationKey(b)));

org.junit.jupiter.api.Assertions.assertEquals(
        direct, precomputed);
```

Test này kiểm tra đúng hợp đồng sign. Trong ứng dụng có nhiều bản dịch, có thể viết parameterized tests theo locale/strength và danh sách cặp thực tế.

## 17. Bài tập thực hành

### Bài 1 — Khi nào cần keys?

Có hai yêu cầu:

- A: kiểm tra `"An"` đứng trước `"Bình"` một lần.
- B: một danh sách 50.000 tên được sort lại 20 lần trong cùng phiên với locale không đổi.

**Gợi ý/đáp án:** A phù hợp `Collator.compare` vì không cần tạo keys. B là ứng viên tốt cho `CollationKey` vì tạo key một lần, sau đó so sánh lặp; vẫn cần benchmark chi phí heap và cập nhật dữ liệu.

### Bài 2 — Đổi locale

Một màn hình tạo keys bằng `Locale.US`, sau đó chuyển sang `vi-VN`. Có thể dùng key cũ để sort tên tiếng Việt không?

**Đáp án:** Không. Phải chọn Collator theo locale mới rồi tạo lại keys cho toàn bộ batch. Quy tắc so sánh có thể khác; API không cho phép so sánh keys từ Collators khác.

### Bài 3 — Đổi strength

Collator đã sinh keys ở `PRIMARY`, sau đó gọi `setStrength(TERTIARY)`. Có thể trộn keys mới và cũ?

**Đáp án:** Không. Strength là một phần của quy tắc so sánh; hãy tạo toàn bộ keys cùng cấu hình mới.

### Bài 4 — So sánh bằng nhau

Ở một locale và strength đang dùng, hai chuỗi khác nhau có `keyA.compareTo(keyB) == 0`. Có nên kết luận `a.equals(b)` là true?

**Đáp án:** Không. Equality theo collation phụ thuộc locale/strength, còn `String.equals` so sánh chính các UTF-16 code units. Cần định nghĩa rõ dùng equality nào trong nghiệp vụ.

### Bài 5 — Comparator ổn định

Hai khách hàng có tên được coi như nhau ở PRIMARY. Muốn UI luôn có thứ tự ổn định qua mỗi lần tải, làm sao?

**Đáp án:** Thêm tie-breaker bằng một ID cố định (hoặc chiến lược khác). Nếu mục tiêu là grouping theo collation, vẫn dùng kết quả key compareTo 0, không dùng comparator đã thêm ID.

### Bài 6 — Tạo key trong comparator

Vì sao sau đây không khai thác tốt ưu điểm CollationKey?

```java
list.sort((a, b) ->
        collator.getCollationKey(a)
                .compareTo(collator.getCollationKey(b)));
```

**Đáp án:** Mỗi phép so sánh lại tạo keys mới. Cần chuẩn bị mỗi key trước khi sort rồi dùng lại.

### Bài 7 — Persist toByteArray

Có thể dùng `CollationKey.toByteArray()` làm thứ tự cố định dài hạn giữa mọi vendor/JDK không?

**Đáp án:** Không nên. Byte representation phụ thuộc quy tắc và triển khai collation; phải version hóa/rebuild nếu có thay đổi môi trường. Nó cũng không phải UTF-8 hoặc identifier canonical.

### Bài 8 — Tối ưu có đáng không?

Một tập chuỗi nhỏ được so sánh duy nhất một lượt, nhưng mỗi key lại khá dài. Đâu là chi phí bỏ qua trong benchmark chỉ đo `compareTo`?

**Đáp án:** Thời gian tạo keys và bộ nhớ/GC. Phải đo tổng workload, không chỉ một phương thức.

## 18. Checklist khi đưa vào production

- [ ] Chọn locale rõ ràng từ ngữ cảnh người dùng hoặc yêu cầu nghiệp vụ.
- [ ] Chọn strength/decomposition được đặc tả và kiểm thử.
- [ ] Sinh keys từ một Collator đã cấu hình cố định cho một sort batch.
- [ ] Không gọi `getCollationKey` trong comparator cho mỗi lần so sánh.
- [ ] Giữ chuỗi gốc để hiển thị, chỉnh sửa và lưu trữ.
- [ ] Không trộn keys từ các Collator khác nhau hoặc từ cấu hình khác.
- [ ] Khi đổi text, locale, rules hoặc JDK/provider, invalidate/rebuild keys.
- [ ] Tính cả memory/GC và chi phí tạo keys trong benchmark.
- [ ] Có tie-breaker khi cần thứ tự ổn định cho các chuỗi được coi tương đương.
- [ ] Không dùng collation equality thay thế equality bảo mật hoặc ID duy nhất.
- [ ] Không dùng `toByteArray` như một chuẩn serialization vĩnh viễn.
- [ ] Không đổi default JVM locale theo từng request.
- [ ] Có test đặc trưng ngôn ngữ cho các locale sản phẩm thực sự hỗ trợ.

## 19. Tổng kết

**`CollationKey` là tối ưu hóa cho so sánh ngôn ngữ lặp lại.** Nếu chỉ có hai chuỗi cần so sánh một lần, `Collator.compare` là phương án gọn và thường hiệu quả. Khi cùng nhiều chuỗi tham gia nhiều phép so sánh — nhất là sắp xếp hoặc sắp xếp lại — việc tính `CollationKey` trước một lần rồi so sánh các keys thường có lợi.

Nhưng lợi ích chỉ đúng nếu bảo toàn **cùng Collator và cùng quy tắc locale/strength/decomposition**, quản lý vòng đời key, invalidate khi dữ liệu thay đổi, và đo cả chi phí sinh key/bộ nhớ. Kết quả `compareTo == 0` phản ánh **tương đương theo collation**, không nhất thiết là hai chuỗi `String` giống hệt. Hãy lưu text gốc làm nguồn dữ liệu; xem `CollationKey` như **dữ liệu dẫn xuất để sắp xếp**, không phải định danh lâu dài hay bản dịch.

### Tài liệu tham khảo Java 17

- [CollationKey — Oracle Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/CollationKey.html)
- [Collator — Oracle Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Collator.html)
- [RuleBasedCollator — Oracle Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/RuleBasedCollator.html)
- [Normalizer — Oracle Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
